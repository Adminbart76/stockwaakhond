"""Legt de wissel van de virtuele portefeuille vast: de tweede en volgende keer.

Het verschil met scripts/leg_instap_vast.py
===========================================
De instap begint met 1.000 euro. Een wissel begint met wat er IS. Er komt geen
geld bij: de waarde van de portefeuille op de slotkoers van die dag wordt
herverdeeld over de nieuwe Top-5, en de kost wordt gerekend over wat er
werkelijk van hand verwisselt.

Daarom kan dit script niet dezelfde berekening gebruiken. Zie sw/herbalans.py
voor de regels en audit/ONTWERP_doorlopende_portefeuille_2026-10-07.md voor het
waarom.

Dit gebeurt lokaal, bij Bart, en nooit vanuit GitHub: het schrijft in
`executions`, en dat is bewijsmateriaal.

Volgorde:
  1. het logboek en de keten van uitvoeringen nakijken
  2. de uitvoeringsdag bepalen en controleren dat de beurs dicht is
  3. koersen en wisselkoers ophalen
  4. dividend sinds de vorige uitvoering opzoeken
  5. de wissel berekenen en tonen
  6. vastleggen: eerst lokaal, dan in de database
  7. terugcontroleren

Afloop:
    exitcode 0 - vastgelegd, of niets te doen (al gebeurd, beurs nog open,
                 nog geen beursdag na het signaal)
    exitcode 1 - er is iets mis en iemand moet ernaar kijken

Gebruik:
    python scripts/leg_herbalans_vast.py --toon        (alleen tonen)
    python scripts/leg_herbalans_vast.py              (echt vastleggen)
    python scripts/leg_herbalans_vast.py --dividend=netto
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import beurskalender as bk                      # noqa: E402
from sw import herbalans as hb                          # noqa: E402
from sw import ledger as led                            # noqa: E402
from sw import prices as pr                             # noqa: E402
from sw.strategy import canonical_json, sha256_text     # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402

LEDGER = PROJECT / "forward_log" / "ledger.jsonl"
UITVOERINGEN = PROJECT / "forward_log" / "executions.jsonl"

ALLEEN_TONEN = "--toon" in sys.argv
DIVIDEND_CONVENTIE = None
for arg in sys.argv[1:]:
    if arg.startswith("--dividend="):
        DIVIDEND_CONVENTIE = arg.split("=", 1)[1].strip().lower()


def stop(bericht: str) -> None:
    print("\n" + "=" * 74)
    print("GESTOPT: " + bericht)
    print("Er is niets vastgelegd.")
    print("=" * 74)
    sys.exit(1)


def klaar(bericht: str) -> None:
    """Niets te doen. Dat is een normale uitkomst, geen fout."""
    print("\n" + "=" * 74)
    print("NIETS TE DOEN: " + bericht)
    print("=" * 74)
    sys.exit(0)


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


# ------------------------------------------------------- 1. logboek en keten
kop("1. Het signaal en de bestaande portefeuille")

regels = led.read_ledger(LEDGER)
ok, bericht = led.verify_ledger(regels)
if not ok:
    stop("het logboek klopt niet: " + bericht)

signalen = [e for e in regels if e.get("record_type") == "signal"]
if not signalen:
    stop("er is nog geen signaal vastgelegd.")

signaal = signalen[-1]
nieuwe_tickers = [s["ticker"] for s in signaal["selected"]]
print(f"   signaaldatum   : {signaal['signal_market_date']}")
print(f"   nieuwe Top-5   : {', '.join(nieuwe_tickers)}")

bestaande = []
if UITVOERINGEN.exists():
    bestaande = [
        json.loads(l) for l in
        UITVOERINGEN.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
if not bestaande:
    stop(
        "er staat nog geen instap. De eerste keer gebruik je\n"
        "scripts/leg_instap_vast.py; dit script is voor elke keer daarna."
    )

ok, bericht = hb.verify_keten(bestaande)
if not ok:
    stop("de keten van uitvoeringen klopt niet: " + bericht)

vorige = hb.laatste_uitvoering(bestaande)
gehouden = [p["ticker"] for p in vorige["positions"]]
print(f"   vorige wissel  : {vorige['execution_date']}")
print(f"   nu in bezit    : {', '.join(gehouden)}")
print(f"   {bericht}")

if any(u["entry_hash"] == signaal["entry_hash"] for u in bestaande):
    klaar(
        "voor dit signaal is de wissel al vastgelegd, en dat gebeurt maar een keer.\n"
        "De koersen van die dag staan dus al vast en veranderen niet meer."
    )


# ------------------------------------------------------- 2. uitvoeringsdag
kop("2. De uitvoeringsdag bepalen")

nodig = sorted(set(nieuwe_tickers) | set(gehouden) | {vorige["benchmark"]["ticker"]})
echt, herrekend = pr.haal_koersen(nodig, start=signaal["signal_market_date"])
uitvoeringsdag = pr.eerste_handelsdag_na(echt.index, signaal["signal_market_date"])

if uitvoeringsdag is None:
    klaar(
        "er is nog geen beursdag geweest na de signaaldatum.\n"
        "De portefeuille wisselt tegen de slotkoers van de eerste beursdag na\n"
        "het signaal. Probeer opnieuw na de volgende slotbel."
    )

print(f"   eerste beursdag na het signaal: {uitvoeringsdag.date()}")

dicht, uitleg = pr.beurs_is_gesloten_voor(uitvoeringsdag)
print(f"   {uitleg}")
if not dicht:
    klaar(
        "de slotkoers van die dag staat nog niet vast.\n"
        "Zolang er gehandeld wordt geeft Yahoo een voorlopige koers die later\n"
        "nog verandert. Een wisselkoers die voor altijd vastligt, mag geen\n"
        "voorlopige koers zijn."
    )


# ----------------------------------------------------------- 3. koersen
kop("3. Koersen en wisselkoers ophalen")

koersen = pr.koersen_op(echt, uitvoeringsdag)
ontbreekt = [t for t in nodig if t not in koersen]
if ontbreekt:
    stop(
        "geen slotkoers gevonden voor: " + ", ".join(ontbreekt) + ".\n"
        "Zonder de koers van elk aandeel dat je HEBT en elk aandeel dat je\n"
        "KRIJGT, is er geen waarde en dus geen wissel. Er wordt niets geschat."
    )

fx_reeks = pr.haal_wisselkoers(start=signaal["signal_market_date"])
fx_gelezen_op = datetime.now(timezone.utc)
if uitvoeringsdag not in fx_reeks.index:
    stop(f"geen wisselkoers gevonden voor {uitvoeringsdag.date()}.")

fx_mag, fx_stand, fx_uitleg = pr.wisselkoers_is_definitief(
    uitvoeringsdag, nu=fx_gelezen_op)
vanaf_hier, tot_hier = bk.venster_in_het_hier(uitvoeringsdag)
if not fx_mag:
    if fx_stand == "te_laat":
        stop(
            "de wisselkoers van die dag is niet meer betrouwbaar op te halen.\n"
            + fx_uitleg + "\n"
            f"Vastleggen kan op de dag zelf tussen {vanaf_hier} en {tot_hier} uur\n"
            "bij ons. Is dat venster voorbij, dan hoort hier een mens naar te\n"
            "kijken: de koers van die dag moet dan uit een andere bron komen\n"
            "en met de hand bevestigd worden."
        )
    klaar(
        "de wisselkoers van die dag staat nog niet vast.\n" + fx_uitleg + "\n"
        f"Probeer opnieuw tussen {vanaf_hier} en {tot_hier} uur bij ons."
    )

if pd.Timestamp(fx_reeks.index[-1]).normalize() != uitvoeringsdag.normalize():
    stop(
        f"de wisselkoersreeks loopt tot {pd.Timestamp(fx_reeks.index[-1]).date()} "
        f"en niet tot {uitvoeringsdag.date()}.\n"
        "De dagwaarde van die dag is dan niet meer de koers die bij de\n"
        "slotkoersen van die dag hoort."
    )

fx = float(fx_reeks.loc[uitvoeringsdag])
fx_asof = fx_gelezen_op.isoformat()

print(f"   {fx_uitleg}")
print(f"   slotkoersen van {uitvoeringsdag.date()} (echte koers, niet herrekend):")
for t in nodig:
    print(f"      {t:<6} {koersen[t]:>10.4f} USD")
print(f"   wisselkoers    : 1 euro = {fx:.6f} dollar   ({pr.FX_BRON})")


# ---------------------------------------------------------- 4. dividend
kop("4. Dividend sinds de vorige uitvoering")

cfg = lees_instellingen()
dividend_usd, spy_dividend_usd = 0.0, 0.0
try:
    rijen = Supabase.lezer(cfg).select(
        "dividends",
        f"select=*&ex_date=gt.{vorige['execution_date']}"
        f"&ex_date=lte.{uitvoeringsdag.date()}",
    )
except Exception as fout:
    stop("de dividendtabel kon niet gelezen worden: " + str(fout))

bm_ticker = vorige["benchmark"]["ticker"]
van_belang = [r for r in rijen if r["ticker"] in set(gehouden) | {bm_ticker}]

if not van_belang:
    print("   geen dividend uitgekeerd in deze periode")
elif DIVIDEND_CONVENTIE not in ("bruto", "netto"):
    stop(
        f"er is in deze periode dividend uitgekeerd ({len(van_belang)} keer), "
        "maar de conventie ligt niet vast.\n"
        "Welk deel een Belgische belegger overhoudt, is een beslissing en geen\n"
        "aanname. Kies die eerst, en draai dan opnieuw met --dividend=bruto of\n"
        "--dividend=netto. Stil nul euro meerekenen zou een wissel met een\n"
        "verkeerd bedrag vastleggen, en die ligt daarna voor altijd vast."
    )
else:
    veld = "gross_per_share_usd" if DIVIDEND_CONVENTIE == "bruto" else "net_per_share_usd"
    aantallen = {p["ticker"]: float(p["shares"]) for p in vorige["positions"]}
    aantallen[bm_ticker] = float(vorige["benchmark"]["shares"])
    for r in van_belang:
        per_aandeel = r.get(veld)
        if per_aandeel is None:
            stop(
                f"voor {r['ticker']} op {r['ex_date']} staat er geen "
                f"{DIVIDEND_CONVENTIE}bedrag in de dividendtabel.\n"
                "Vul dat eerst in; er wordt geen percentage verzonnen."
            )
        bedrag = float(per_aandeel) * aantallen[r["ticker"]]
        if r["ticker"] == bm_ticker:
            spy_dividend_usd += bedrag
        else:
            dividend_usd += bedrag
        print(f"      {r['ticker']:<6} {r['ex_date']}  {bedrag:>8.2f} USD")
    print(f"   conventie      : {DIVIDEND_CONVENTIE}")
    print(f"   portefeuille   : {dividend_usd:.2f} USD")
    print(f"   {bm_ticker:<14} : {spy_dividend_usd:.2f} USD")


# ----------------------------------------------------------- 5. de wissel
kop("5. De wissel berekenen")

wissel = hb.bereken_herbalans(
    entry_hash=signaal["entry_hash"],
    execution_date=str(uitvoeringsdag.date()),
    vorige_uitvoering=vorige,
    nieuwe_tickers=nieuwe_tickers,
    koersen_usd=koersen,
    fx_eurusd=fx,
    spy_koers_usd=koersen[bm_ticker],
    fx_source=pr.FX_BRON,
    fx_asof=fx_asof,
    dividend_cash_usd=dividend_usd,
    spy_dividend_cash_usd=spy_dividend_usd,
    dividend_conventie=(
        f"{DIVIDEND_CONVENTIE}, uit de tabel dividends"
        if (dividend_usd or spy_dividend_usd) else None
    ),
)

opening = wissel["opening"]
print(f"   waarde voor de wissel    USD {opening['total_usd']:>12.2f}")
print(f"      waarvan aandelen      USD {opening['positions_usd']:>12.2f}")
print(f"      waarvan contant       USD {opening['cash_usd']:>12.2f}")
print(f"   omzet                        {wissel['turnover'] * 100:>11.2f} %")
print(f"   kost ({wissel['cost_pct']} %)             USD {wissel['cost_usd']:>12.2f}")
print(f"   opnieuw belegd           USD {wissel['invested_usd']:>12.2f}"
      f"   (EUR {wissel['invested_eur']:.2f})")
print()
print(f"   {'aandeel':<8}{'koers USD':>12}{'aantal':>14}{'inzet USD':>12}")
for p in wissel["positions"]:
    print(f"   {p['ticker']:<8}{p['buy_price_usd']:>12.4f}{p['shares']:>14.6f}"
          f"{p['invested_usd']:>12.2f}")
bm = wissel["benchmark"]
print(f"   {bm['ticker']:<8}{bm['buy_price_usd']:>12.4f}{bm['shares']:>14.6f}"
      f"{'onaangeroerd':>12}   (maatstaf, koopt niets bij)")
print()
print(f"   verwijst naar vorige     : {wissel['prev_exec_hash'][:32]}...")
print(f"   controlegetal wissel     : {wissel['exec_hash'][:32]}...")

# narekenen
if abs(opening["total_usd"] - wissel["cost_usd"] - wissel["invested_usd"]) > 0.01:
    stop("de waarde voor de wissel min de kost is niet het belegde bedrag.")
hersom = sum(p["shares"] * p["buy_price_usd"] for p in wissel["positions"])
if abs(hersom - wissel["invested_usd"]) > 0.01:
    stop("de aantallen maal de koersen kloppen niet met het belegde bedrag.")
if wissel["start_capital_eur"] != vorige["start_capital_eur"]:
    stop("het startkapitaal is veranderd. Er mag geen nieuw geld bijkomen.")
print("   nagerekend               : er is geen geld bijgekomen of verdwenen")

if ALLEEN_TONEN:
    print("\n(alleen tonen: er is niets vastgelegd)")
    sys.exit(0)


# ---------------------------------------------------------- 6. vastleggen
kop("6. Vastleggen")

with UITVOERINGEN.open("a", encoding="utf-8", newline="\n") as f:
    f.write(canonical_json(wissel) + "\n")
print(f"   lokaal   : {UITVOERINGEN.name}")

db = Supabase.schrijver(cfg)

rij = {
    "exec_hash": wissel["exec_hash"],
    "entry_hash": wissel["entry_hash"],
    "record_type": wissel["record_type"],
    "prev_exec_hash": wissel["prev_exec_hash"],
    "execution_date": wissel["execution_date"],
    "fx_pair": wissel["fx_pair"],
    "fx_rate": wissel["fx_rate"],
    "fx_source": wissel["fx_source"],
    "fx_asof": wissel["fx_asof"],
    "start_capital_eur": wissel["start_capital_eur"],
    "cost_pct": wissel["cost_pct"],
    "cost_eur": wissel["cost_eur"],
    "cost_usd": wissel["cost_usd"],
    "invested_eur": wissel["invested_eur"],
    "invested_usd": wissel["invested_usd"],
    "turnover": wissel["turnover"],
    "cash_usd": wissel["cash_usd"],
    "opening": wissel["opening"],
    "positions": wissel["positions"],
    "benchmark": wissel["benchmark"],
    "canonical_payload": wissel["canonical_payload"],
}
db.insert("executions", [rij])
print("   database : executions")

snapshots = []
for t in nodig:
    snapshots.append({
        "snapshot_date": str(uitvoeringsdag.date()),
        "ticker": t,
        "close_raw": float(echt.at[uitvoeringsdag, t]) if t in echt.columns else None,
        "close_adjusted": (float(herrekend.at[uitvoeringsdag, t])
                           if t in herrekend.columns else None),
        "source": "Yahoo Finance dagslotkoers",
    })
db.insert("price_snapshots", snapshots, negeer_dubbel=True)
print(f"   database : price_snapshots ({len(snapshots)} koersen)")

db.insert("fx_snapshots", [{
    "snapshot_date": str(uitvoeringsdag.date()),
    "pair": "EURUSD",
    "rate": fx,
    "source": pr.FX_BRON,
}], negeer_dubbel=True)
print("   database : fx_snapshots")

db.insert("audit_log", [{
    "actor": "scripts/leg_herbalans_vast.py",
    "action": "wissel vastgelegd",
    "detail": {
        "entry_hash": wissel["entry_hash"],
        "exec_hash": wissel["exec_hash"],
        "prev_exec_hash": wissel["prev_exec_hash"],
        "execution_date": wissel["execution_date"],
        "turnover": wissel["turnover"],
    },
}])


# ----------------------------------------------------- 7. terugcontroleren
kop("7. Terugcontroleren")

terug = db.select("executions", f"select=*&exec_hash=eq.{wissel['exec_hash']}")
if len(terug) != 1:
    stop("de wissel staat niet terug te vinden in de database.")

uit_db = terug[0]
if sha256_text(uit_db["canonical_payload"]) != uit_db["exec_hash"]:
    stop("het controlegetal in de database klopt niet met de inhoud.")
if uit_db["canonical_payload"] != wissel["canonical_payload"]:
    stop("de inhoud in de database wijkt af van wat lokaal is weggeschreven.")

alles = db.select("executions", "select=*&order=execution_date.asc")
ok, bericht = hb.verify_keten(alles)
if not ok:
    stop("de keten in de database klopt niet: " + bericht)

print("   controlegetal        : klopt")
print("   inhoud lokaal vs db  : identiek")
print(f"   keten                : {bericht}")

print("\n" + "=" * 74)
print("VASTGELEGD")
print(f"De portefeuille is op {wissel['execution_date']} gewisseld naar")
print(f"{', '.join(nieuwe_tickers)}, met {wissel['invested_eur']:.2f} euro")
print("uit de portefeuille zelf. Er is geen euro bijgekomen.")
print("=" * 74)
