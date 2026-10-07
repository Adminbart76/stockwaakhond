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

Als de database het weigert
===========================
Er wordt eerst lokaal weggeschreven en dan pas in de database: het lokale
bestand is de bron van waarheid (beslissing 7). Weigert de database daarna, dan
staat de wissel lokaal en niet in de spiegel. Dat is geen ramp en geen verlies,
maar het hoort wel rechtgezet te worden, en zeker niet met de hand.

Daarvoor is --alleen-database: die rekent niets opnieuw uit en haalt alleen de
database bij met wat er lokaal al staat. Zonder die weg zou iemand in de
verleiding komen om het record opnieuw te berekenen, en dan hangt de uitkomst
af van de koersen op dat latere moment.

Dividend en wisselkoers liggen vast
===================================
Sinds 7 oktober 2026 hoeft er bij een wissel niets meer gekozen te worden:

  * dividend is BRUTO, aan beide kanten. Het recht wordt bepaald met het aantal
    aandelen van de ex-datum, het geld gaat mee zodra de betaaldatum voorbij is.
    Zie sw/dividend.py.
  * de wisselkoers is de 1-minuutbalk van de slotbel, met de ECB-referentiekoers
    als controlegetal. Zie sw/fx.py.

Wat er wel nog kan stoppen: een dividend dat Yahoo kent en onze tabel niet. Dan
zou de wissel met te weinig geld vastgelegd worden, en dat ligt daarna voor
altijd vast.

Gebruik:
    python scripts/leg_herbalans_vast.py --toon        (alleen tonen)
    python scripts/leg_herbalans_vast.py              (echt vastleggen)
    python scripts/leg_herbalans_vast.py --alleen-database   (database bijhalen)
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
from sw import dividend as div                          # noqa: E402
from sw import fx as fxr                                # noqa: E402
from sw import herbalans as hb                          # noqa: E402
from sw import ledger as led                            # noqa: E402
from sw import prices as pr                             # noqa: E402
from sw.strategy import canonical_json, sha256_text     # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402

LEDGER = PROJECT / "forward_log" / "ledger.jsonl"
UITVOERINGEN = PROJECT / "forward_log" / "executions.jsonl"

ALLEEN_TONEN = "--toon" in sys.argv
ALLEEN_DATABASE = "--alleen-database" in sys.argv


def stop(bericht: str) -> None:
    print("\n" + "=" * 74)
    print("GESTOPT: " + bericht)
    print("Er is niets vastgelegd.")
    print("=" * 74)
    sys.exit(1)


def stop_maar_lokaal_staat_het(bericht: str) -> None:
    """Hier is wél iets vastgelegd, alleen niet in de database.

    Met opzet een andere melding dan stop(): "er is niets vastgelegd" zou hier
    gewoon niet waar zijn, en dat is precies het soort regel waardoor iemand
    later denkt dat hij opnieuw mag beginnen.
    """
    print("\n" + "=" * 74)
    print("HALF KLAAR: " + bericht)
    print()
    print("De wissel staat wel in forward_log/executions.jsonl, en dat bestand")
    print("is de bron van waarheid. Er is niets verloren en er mag niets")
    print("opnieuw berekend worden: dan zou de uitkomst van de koersen van NU")
    print("afhangen in plaats van van de slotkoers van de uitvoeringsdag.")
    print()
    print("Zodra de oorzaak weg is, haal je de database bij met:")
    print("    python scripts/leg_herbalans_vast.py --alleen-database")
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


# ------------------------------------------- 0. alleen de database bijhalen
if ALLEEN_DATABASE:
    kop("De database bijhalen met wat er lokaal al staat")

    if not UITVOERINGEN.exists():
        stop("er staat lokaal nog geen enkele uitvoering.")
    lokaal = [
        json.loads(l) for l in
        UITVOERINGEN.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    ok, bericht = hb.verify_keten(lokaal)
    if not ok:
        stop("de lokale keten klopt niet: " + bericht)

    db = Supabase.schrijver(lees_instellingen())
    in_db = {u["exec_hash"] for u in db.select("executions", "select=exec_hash")}
    ontbreken = [u for u in hb.sorteer_keten(lokaal) if u["exec_hash"] not in in_db]

    if not ontbreken:
        klaar("de database heeft alles al; er valt niets bij te halen.")

    for u in ontbreken:
        print(f"   {u['execution_date']}  {u['exec_hash'][:24]}...")
        rij = {
            "exec_hash": u["exec_hash"],
            "entry_hash": u["entry_hash"],
            "execution_date": u["execution_date"],
            "fx_pair": u["fx_pair"],
            "fx_rate": u["fx_rate"],
            "fx_source": u["fx_source"],
            "fx_asof": u["fx_asof"],
            "start_capital_eur": u["start_capital_eur"],
            "cost_pct": u["cost_pct"],
            "cost_eur": u["cost_eur"],
            "invested_eur": u["invested_eur"],
            "positions": u["positions"],
            "benchmark": u["benchmark"],
            "canonical_payload": u["canonical_payload"],
        }
        # De velden die alleen een wissel heeft. De eerste instap heeft ze niet.
        for veld in ("record_type", "prev_exec_hash", "turnover", "cost_usd",
                     "invested_usd", "cash_usd", "opening"):
            if veld in u:
                rij[veld] = u[veld]
        try:
            db.insert("executions", [rij])
        except Exception as fout:
            stop(
                "de database weigert het nog steeds:\n" + str(fout) + "\n"
                "Er is dus nog niets bijgehaald. Zoek eerst uit waarom; het\n"
                "lokale bestand blijft ondertussen de bron van waarheid."
            )
        db.insert("audit_log", [{
            "actor": "scripts/leg_herbalans_vast.py --alleen-database",
            "action": "database bijgehaald met een lokaal bestaande uitvoering",
            "detail": {"exec_hash": u["exec_hash"],
                       "execution_date": u["execution_date"]},
        }])

    terug = db.select("executions", "select=*&order=execution_date.asc")
    ok, bericht = hb.verify_keten(terug)
    if not ok:
        stop("de keten in de database klopt na het bijhalen niet: " + bericht)

    print(f"\n   {len(ontbreken)} uitvoering(en) bijgehaald")
    print(f"   keten: {bericht}")
    print("\n" + "=" * 74)
    print("BIJGEHAALD - database en lokaal bestand zijn weer gelijk.")
    print("=" * 74)
    sys.exit(0)


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

# Vanaf de eerste uitvoering van de keten ophalen, niet vanaf het signaal. De
# herbelegging van het SPY-dividend heeft de slotkoersen van vroegere
# betaaldagen nodig; met een reeks die pas bij het laatste signaal begint, zou
# een oudere uitkering er als "nog niet herbelegd" uitzien en voor altijd
# contant blijven staan.
vanaf = min(
    str(hb.sorteer_keten(bestaande)[0]["execution_date"]),
    str(signaal["signal_market_date"]),
)
echt, herrekend = pr.haal_koersen(nodig, start=vanaf)
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

fx_gelezen_op = datetime.now(timezone.utc)
fx_mag, fx_stand, fx_uitleg = bk.leesvenster(uitvoeringsdag, nu=fx_gelezen_op)
vanaf_hier, tot_hier = bk.leesvenster_in_het_hier(uitvoeringsdag)

if not fx_mag:
    if fx_stand == "te_laat":
        stop(
            "het venster om de wisselkoers vast te leggen is gesloten.\n"
            + fx_uitleg + "\n"
            f"Vastleggen kan op de dag zelf tussen {vanaf_hier} en {tot_hier} uur\n"
            "bij ons. Is dat venster voorbij, dan hoort hier een mens naar te\n"
            "kijken: dat is een beheershandeling en geen gewone wissel."
        )
    klaar(
        "de wisselkoers van die dag kan nog niet vastgelegd worden.\n"
        + fx_uitleg + "\n"
        f"Probeer opnieuw tussen {vanaf_hier} en {tot_hier} uur bij ons."
    )

# De regel van 7 oktober 2026: de laatste afgesloten 1-minuutbalk die eindigt op
# of voor de slotbel, plus de ECB-referentiekoers als onafhankelijk controlegetal.
# Wijken die twee meer dan 1 procent af, dan komt er niets uit en kijkt er een
# mens naar.
try:
    fx_bewijs = fxr.wisselkoers_van(uitvoeringsdag, gelezen_op=fx_gelezen_op)
except fxr.GeenWisselkoers as fout:
    stop(
        "de wisselkoers van die dag is niet volgens de regel te bepalen.\n"
        + str(fout) + "\n"
        "Er wordt geen ander getal in de plaats gezet."
    )
except Exception as fout:
    stop(
        "de wisselkoers of het controlegetal kon niet opgehaald worden:\n"
        + str(fout) + "\n"
        "De ECB-referentiekoers is op te zoeken op ecb.europa.eu; zonder\n"
        "controlegetal wordt er niets vastgelegd."
    )

fx = float(fx_bewijs["fx_rate"])
fx_asof = fx_bewijs["fx_asof"]
balk = fx_bewijs["balk"]
ecb = fx_bewijs["ecb"]

print(f"   {fx_uitleg}")
print(f"   slotkoersen van {uitvoeringsdag.date()} (echte koers, niet herrekend):")
for t in nodig:
    print(f"      {t:<6} {koersen[t]:>10.4f} USD")
print(f"   wisselkoers    : 1 euro = {fx:.6f} dollar")
print(f"      uit de balk  : {balk['bar_start'].strftime('%H:%M')}-"
      f"{balk['bar_end'].strftime('%H:%M')} in New York"
      + ("  (de minuut van de slotbel)" if balk["normaal"]
         else f"  (terugval: {balk['seconden_voor_slotbel'] // 60} minuut(en) "
              f"voor de slotbel)"))
print(f"      gelezen om   : {fx_gelezen_op.strftime('%H:%M')} UTC")
print(f"   controlegetal  : ECB {ecb['koers']:.6f} van {ecb['datum']}"
      + ("" if ecb["zelfde_dag"] else "  (laatste beschikbare dag)"))
print(f"      verschil     : {fx_bewijs['fx_control_deviation_pct']:+.3f} %  "
      f"(grens: 1 %)")


# ---------------------------------------------------------- 4. dividend
kop("4. Dividend sinds de vorige uitvoering")

# De conventie ligt vast: bruto, aan beide kanten. Er is niets te kiezen.
# Wat hier wel gebeurt:
#   * het RECHT wordt bepaald met het aantal aandelen van de ex-datum, ook van
#     een aandeel dat inmiddels verkocht is;
#   * het GELD gaat mee zodra de betaaldatum voorbij is - niet eerder;
#   * het dividend van SPY wordt herbelegd in SPY, tegen de eerstvolgende
#     slotkoers op of na de betaaldatum.
cfg = lees_instellingen()
bm_ticker = vorige["benchmark"]["ticker"]

try:
    alle_dividenden = Supabase.lezer(cfg).select(
        "dividends", "select=*&order=ex_date.asc")
except Exception as fout:
    stop("de dividendtabel kon niet gelezen worden: " + str(fout))

try:
    onze_events = div.portefeuille_dividenden(
        bestaande, alle_dividenden, benchmark_ticker=bm_ticker)
    spy_events = div.spy_dividenden(
        bestaande, alle_dividenden, echt[bm_ticker] if bm_ticker in echt.columns else None,
        benchmark_ticker=bm_ticker)
except ValueError as fout:
    stop(
        "de dividendtabel is niet bruikbaar: " + str(fout) + "\n"
        "Vul de ontbrekende gegevens aan met scripts/leg_dividend_vast.py."
    )

# Wat Yahoo kent en onze tabel niet, is het echte gevaar: dan zou deze wissel
# met te weinig geld vastgelegd worden, en dat ligt daarna voor altijd vast.
begin_keten = hb.sorteer_keten(bestaande)[0]["execution_date"]
bekend = {(r["ticker"], str(r["ex_date"])) for r in alle_dividenden}
gemist = []
try:
    van_yahoo = pr.haal_dividenden(
        sorted(set(gehouden) | {bm_ticker}), start=begin_keten)
except Exception as fout:
    stop(
        "er kon niet nagekeken worden of er een dividend gemist is:\n"
        + str(fout) + "\n"
        "Zonder die controle kan deze wissel met te weinig geld vastgelegd\n"
        "worden, en dat is niet meer te herstellen."
    )
for ticker, uitkeringen in van_yahoo.items():
    for ex, bedrag in uitkeringen.items():
        if pd.Timestamp(ex) > pd.Timestamp(uitvoeringsdag):
            continue
        if (ticker, ex) in bekend:
            continue
        # Alleen wat we werkelijk gekregen zouden hebben. Een uitkering van voor
        # de dag dat we dat aandeel kochten, levert ons niets op en hoort de
        # wissel dus niet te blokkeren. Zelfde regel als de berekening gebruikt.
        if div.recht_op(bestaande, ticker, ex, bm_ticker) > 0:
            gemist.append((ticker, ex, bedrag))

if gemist:
    regels = "\n".join(
        f"      {t:<6} ex {e}  bruto {b:.4f} USD" for t, e, b in sorted(gemist))
    stop(
        f"Yahoo kent {len(gemist)} uitkering(en) die niet in onze tabel staan:\n"
        + regels + "\n"
        "Leg die eerst vast met scripts/leg_dividend_vast.py (met de betaaldatum\n"
        "en de bron erbij). Zou deze wissel nu doorgaan, dan werd ze met te\n"
        "weinig geld vastgelegd - en dat ligt daarna voor altijd vast."
    )

mee_van_ons = div.betaald_tussen(
    onze_events, vorige["execution_date"], uitvoeringsdag)
dividend_usd = div.som(mee_van_ons)
dividend_detail = div.detail(mee_van_ons)

# Aan de kant van SPY: alles wat betaald is sinds de vorige uitvoering, en
# daarvan het deel dat inmiddels herbelegd is.
spy_betaald = div.betaald_tussen(spy_events, vorige["execution_date"], uitvoeringsdag)
spy_dividend_usd = div.som(spy_betaald)
spy_detail = div.detail(spy_betaald)

vorige_stand = div.spy_stand_op(
    float(hb.sorteer_keten(bestaande)[0]["benchmark"]["shares"]),
    spy_events, vorige["execution_date"])
nu_stand = div.spy_stand_op(
    float(hb.sorteer_keten(bestaande)[0]["benchmark"]["shares"]),
    spy_events, uitvoeringsdag)
spy_extra_shares = round(nu_stand["aandelen"] - vorige_stand["aandelen"], 10)
spy_herbelegd_usd = round(
    float(vorige_stand["contant_usd"]) + spy_dividend_usd - float(nu_stand["contant_usd"]), 8)

# De stand die we nu uit de uitkeringen berekenen, moet overeenkomen met wat er
# in de vorige uitvoering staat. Lopen die uiteen, dan is er onderweg iets aan de
# dividendtabel veranderd, en dan zou deze wissel een SPY-positie vastleggen die
# niet volgt uit wat er daarvoor stond.
in_record = float(vorige["benchmark"].get("cash_usd") or 0.0)
if abs(in_record - float(vorige_stand["contant_usd"])) > 0.01:
    stop(
        f"het contante SPY-dividend klopt niet: de vorige uitvoering zegt "
        f"{in_record:.2f} USD, uit de dividendtabel volgt "
        f"{vorige_stand['contant_usd']:.2f} USD.\n"
        "Er is sindsdien iets aan de dividendgegevens veranderd. Zoek dat eerst\n"
        "uit; een wissel die hierop rust zou een verkeerde SPY-positie\n"
        "vastleggen."
    )
in_record_aandelen = float(vorige["benchmark"]["shares"])
if abs(in_record_aandelen - float(vorige_stand["aandelen"])) > 1e-6:
    stop(
        f"het aantal SPY-aandelen klopt niet: de vorige uitvoering zegt "
        f"{in_record_aandelen:.6f}, uit de uitkeringen volgt "
        f"{vorige_stand['aandelen']:.6f}.\n"
        "Zoek dat eerst uit."
    )

if not mee_van_ons and not spy_betaald:
    print("   geen dividend beschikbaar gekomen in deze periode")
    print("   (het recht ontstaat op de ex-datum, het geld op de betaaldatum)")
else:
    for e in mee_van_ons + spy_betaald:
        print(f"      {e['ticker']:<6} ex {pd.Timestamp(e['ex_date']).date()}  "
              f"betaald {pd.Timestamp(e['pay_date']).date()}  "
              f"{e['bedrag_usd']:>8.2f} USD")
    print(f"   conventie      : {div.CONVENTIE_TEKST}")
    print(f"   portefeuille   : {dividend_usd:.2f} USD  (gaat mee in deze wissel)")
    print(f"   {bm_ticker:<14} : {spy_dividend_usd:.2f} USD betaald, "
          f"{spy_herbelegd_usd:.2f} USD herbelegd")
    if spy_extra_shares:
        print(f"   {bm_ticker} koopt er {spy_extra_shares:.6f} aandelen bij "
              f"met zijn eigen dividend")

nog_niet_betaald = [
    e for e in onze_events
    if pd.Timestamp(e["pay_date"]) > pd.Timestamp(uitvoeringsdag)
]
if nog_niet_betaald:
    print()
    print("   Nog niet beschikbaar (recht erop, geld komt later):")
    for e in nog_niet_betaald:
        print(f"      {e['ticker']:<6} ex {pd.Timestamp(e['ex_date']).date()}  "
              f"betaald {pd.Timestamp(e['pay_date']).date()}  "
              f"{e['bedrag_usd']:>8.2f} USD")
    print("   Dat geld gaat mee in de wissel NA de betaaldatum, ook als het")
    print("   aandeel dan niet meer in de portefeuille zit.")


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
    fx_source=fxr.BRON,
    fx_asof=fx_asof,
    dividend_cash_usd=dividend_usd,
    spy_dividend_cash_usd=spy_dividend_usd,
    spy_herbelegd_usd=spy_herbelegd_usd,
    spy_extra_shares=spy_extra_shares,
    dividend_detail=dividend_detail,
    spy_dividend_detail=spy_detail,
    dividend_conventie=(
        f"{div.CONVENTIE_TEKST}, uit de tabel dividends"
        if (dividend_usd or spy_dividend_usd or spy_herbelegd_usd) else None
    ),
    fx_bewijs={
        "fx_bar_start": fx_bewijs["fx_bar_start"],
        "fx_bar_end": fx_bewijs["fx_bar_end"],
        "fx_bar_normaal": fx_bewijs["fx_bar_normaal"],
        "fx_control_source": fx_bewijs["fx_control_source"],
        "fx_control_date": fx_bewijs["fx_control_date"],
        "fx_control_rate": fx_bewijs["fx_control_rate"],
        "fx_control_same_day": fx_bewijs["fx_control_same_day"],
        "fx_control_deviation_pct": fx_bewijs["fx_control_deviation_pct"],
    },
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
      f"{'onaangeroerd':>12}   (maatstaf, wisselt niet mee)")
if spy_extra_shares:
    print(f"   {bm['ticker']} heeft er {spy_extra_shares:.6f} aandelen bijgekocht "
          f"met eigen dividend, zonder kost")
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
try:
    db.insert("executions", [rij])
except Exception as fout:
    stop_maar_lokaal_staat_het(
        "de database weigerde de wissel.\nTechnische melding: " + str(fout))
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
    "source": fxr.BRON,
    "bar_start": fx_bewijs["fx_bar_start"],
    "bar_end": fx_bewijs["fx_bar_end"],
    "control_source": fx_bewijs["fx_control_source"],
    "control_date": fx_bewijs["fx_control_date"],
    "control_rate": fx_bewijs["fx_control_rate"],
    "control_deviation_pct": fx_bewijs["fx_control_deviation_pct"],
}], negeer_dubbel=True)
print("   database : fx_snapshots (met de balk en het ECB-controlegetal)")

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
