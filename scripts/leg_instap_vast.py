"""Legt de instap van de virtuele portefeuille van 1.000 euro vast.

Dit mag maar een keer per signaal. Daarna staat de instapkoers voor altijd
vast en wordt hij nooit meer herberekend.

Het script weigert te werken zolang de Amerikaanse beurs niet definitief
gesloten is. Zolang er gehandeld wordt geeft Yahoo een voorlopige koers die
later die dag nog verandert, en een instapkoers die we voor altijd vastleggen
mag geen voorlopige koers zijn.

Volgorde:
  1. het signaal ophalen en de uitvoeringsdag bepalen
  2. controleren dat de beurs dicht is
  3. echte slotkoersen en de wisselkoers ophalen
  4. de instap berekenen
  5. tonen wat er vastgelegd gaat worden
  6. vastleggen: eerst lokaal, dan in de database
  7. terugcontroleren

Gebruik:
    python scripts/leg_instap_vast.py --toon     (alleen tonen, niets vastleggen)
    python scripts/leg_instap_vast.py            (echt vastleggen)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import ledger as led                      # noqa: E402
from sw import portfolio as pf                    # noqa: E402
from sw import prices as pr                       # noqa: E402
from sw.strategy import canonical_json, sha256_text  # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402

LEDGER = PROJECT / "forward_log" / "ledger.jsonl"
UITVOERINGEN = PROJECT / "forward_log" / "executions.jsonl"

ALLEEN_TONEN = "--toon" in sys.argv


def stop(bericht: str) -> None:
    print("\n" + "=" * 74)
    print("GESTOPT: " + bericht)
    print("Er is niets vastgelegd.")
    print("=" * 74)
    sys.exit(1)


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


# -------------------------------------------------------------- 1. signaal
kop("1. Het signaal opzoeken")

regels = led.read_ledger(LEDGER)
ok, bericht = led.verify_ledger(regels)
if not ok:
    stop("het logboek klopt niet: " + bericht)

signalen = [e for e in regels if e.get("record_type") == "signal"]
if not signalen:
    stop("er is nog geen signaal vastgelegd.")

signaal = signalen[-1]
tickers = [s["ticker"] for s in signaal["selected"]]
print(f"   signaaldatum   : {signaal['signal_market_date']}")
print(f"   Top-5          : {', '.join(tickers)}")
print(f"   entry_hash     : {signaal['entry_hash'][:24]}...")

# al vastgelegd?
bestaande = []
if UITVOERINGEN.exists():
    bestaande = [json.loads(l) for l in UITVOERINGEN.read_text(encoding="utf-8").splitlines() if l.strip()]
if any(u["entry_hash"] == signaal["entry_hash"] for u in bestaande):
    stop("voor dit signaal is de instap al vastgelegd. Dat gebeurt maar een keer.")


# ------------------------------------------------------- 2. uitvoeringsdag
kop("2. De uitvoeringsdag bepalen")

echt, herrekend = pr.haal_koersen(tickers + ["SPY"], start=signaal["signal_market_date"])
uitvoeringsdag = pr.eerste_handelsdag_na(echt.index, signaal["signal_market_date"])

if uitvoeringsdag is None:
    stop(
        "er is nog geen beursdag geweest na de signaaldatum.\n"
        "De portefeuille stapt in tegen de slotkoers van de eerste beursdag na\n"
        "het signaal. Probeer opnieuw na de volgende slotbel."
    )

print(f"   eerste beursdag na het signaal: {uitvoeringsdag.date()}")

dicht, uitleg = pr.beurs_is_gesloten_voor(uitvoeringsdag)
print(f"   {uitleg}")
if not dicht:
    stop(
        "de slotkoers van die dag staat nog niet vast.\n"
        "Zolang er gehandeld wordt geeft Yahoo een voorlopige koers die later\n"
        "nog verandert. Een instapkoers die voor altijd vastligt, mag geen\n"
        "voorlopige koers zijn."
    )


# ------------------------------------------------------------- 3. koersen
kop("3. Koersen en wisselkoers ophalen")

koersen = pr.koersen_op(echt, uitvoeringsdag)
ontbreekt = [t for t in tickers + ["SPY"] if t not in koersen]
if ontbreekt:
    stop("geen slotkoers gevonden voor: " + ", ".join(ontbreekt))

fx_reeks = pr.haal_wisselkoers(start=signaal["signal_market_date"])
if uitvoeringsdag not in fx_reeks.index:
    stop(f"geen wisselkoers gevonden voor {uitvoeringsdag.date()}.")
fx = float(fx_reeks.loc[uitvoeringsdag])

print(f"   slotkoersen van {uitvoeringsdag.date()} (echte koers, niet herrekend):")
for t in tickers:
    print(f"      {t:<6} {koersen[t]:>10.4f} USD")
print(f"      {'SPY':<6} {koersen['SPY']:>10.4f} USD   (vergelijkingsmaatstaf)")
print(f"   wisselkoers    : 1 euro = {fx:.6f} dollar   ({pr.FX_BRON})")


# -------------------------------------------------------------- 4. instap
kop("4. De instap berekenen")

instap = pf.bereken_instap(
    entry_hash=signaal["entry_hash"],
    execution_date=str(uitvoeringsdag.date()),
    tickers=tickers,
    koersen_usd=koersen,
    fx_eurusd=fx,
    spy_koers_usd=koersen["SPY"],
    fx_source=pr.FX_BRON,
    fx_asof=datetime.now(timezone.utc).isoformat(),
)

print(f"   startkapitaal        EUR {instap['start_capital_eur']:>10.2f}")
print(f"   transactiekost 0,15% EUR {instap['cost_eur']:>10.2f}")
print(f"   werkelijk belegd     EUR {instap['invested_eur']:>10.2f}")
print()
print(f"   {'aandeel':<8}{'koers USD':>12}{'aantal':>14}{'inzet EUR':>12}")
for p in instap["positions"]:
    print(f"   {p['ticker']:<8}{p['buy_price_usd']:>12.4f}{p['shares']:>14.6f}"
          f"{p['invested_eur']:>12.2f}")
bm = instap["benchmark"]
print(f"   {'SPY':<8}{bm['buy_price_usd']:>12.4f}{bm['shares']:>14.6f}"
      f"{bm['invested_eur']:>12.2f}   (benchmark, dezelfde inleg)")
print()
print(f"   controlegetal instap : {instap['exec_hash'][:32]}...")

# narekenen
totaal = sum(p["invested_eur"] for p in instap["positions"])
if abs(totaal - instap["invested_eur"]) > 0.01:
    stop(f"de inzetten tellen op tot {totaal:.2f} en niet tot {instap['invested_eur']:.2f}.")
for p in instap["positions"]:
    if abs(p["shares"] * p["buy_price_usd"] - p["invested_usd"]) > 0.01:
        stop(f"het aantal aandelen van {p['ticker']} klopt niet met het ingelegde bedrag.")
print("   nagerekend           : inzetten en aantallen kloppen")

if ALLEEN_TONEN:
    print("\n(alleen tonen: er is niets vastgelegd)")
    sys.exit(0)


# ----------------------------------------------------------- 5. vastleggen
kop("5. Vastleggen")

# -- lokaal eerst: dat blijft de bron van waarheid
UITVOERINGEN.parent.mkdir(parents=True, exist_ok=True)
with UITVOERINGEN.open("a", encoding="utf-8", newline="\n") as f:
    f.write(canonical_json(instap) + "\n")
print(f"   lokaal   : {UITVOERINGEN.name}")

cfg = lees_instellingen()
db = Supabase.schrijver(cfg)

rij = {
    "exec_hash": instap["exec_hash"],
    "entry_hash": instap["entry_hash"],
    "execution_date": instap["execution_date"],
    "fx_pair": instap["fx_pair"],
    "fx_rate": instap["fx_rate"],
    "fx_source": instap["fx_source"],
    "fx_asof": instap["fx_asof"],
    "start_capital_eur": instap["start_capital_eur"],
    "cost_pct": instap["cost_pct"],
    "cost_eur": instap["cost_eur"],
    "invested_eur": instap["invested_eur"],
    "positions": instap["positions"],
    "benchmark": instap["benchmark"],
    "canonical_payload": instap["canonical_payload"],
}
db.insert("executions", [rij])
print("   database : executions")

# -- de slotkoersen van die dag ook vastleggen, zodat de grafiek niet schuift
snapshots = []
for t in sorted(set(tickers + ["SPY"])):
    rij_echt = float(echt.at[uitvoeringsdag, t]) if t in echt.columns else None
    rij_adj = float(herrekend.at[uitvoeringsdag, t]) if t in herrekend.columns else None
    snapshots.append({
        "snapshot_date": str(uitvoeringsdag.date()),
        "ticker": t,
        "close_raw": rij_echt,
        "close_adjusted": rij_adj,
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
    "actor": "scripts/leg_instap_vast.py",
    "action": "instap vastgelegd",
    "detail": {
        "entry_hash": instap["entry_hash"],
        "exec_hash": instap["exec_hash"],
        "execution_date": instap["execution_date"],
    },
}])


# ------------------------------------------------------- 6. terugcontroleren
kop("6. Terugcontroleren")

terug = db.select("executions", f"select=*&exec_hash=eq.{instap['exec_hash']}")
if len(terug) != 1:
    stop("de instap staat niet terug te vinden in de database.")

uit_db = terug[0]
if sha256_text(uit_db["canonical_payload"]) != uit_db["exec_hash"]:
    stop("het controlegetal in de database klopt niet met de inhoud.")
if uit_db["canonical_payload"] != instap["canonical_payload"]:
    stop("de inhoud in de database wijkt af van wat lokaal is weggeschreven.")

opnieuw = json.loads(uit_db["canonical_payload"])
if opnieuw["positions"] != instap["positions"]:
    stop("de posities in de database wijken af.")

print("   controlegetal        : klopt")
print("   inhoud lokaal vs db  : identiek")
print(f"   posities             : {len(opnieuw['positions'])} stuks, ongewijzigd")

print("\n" + "=" * 74)
print("VASTGELEGD")
print(f"De virtuele portefeuille is op {instap['execution_date']} ingestapt")
print(f"met {instap['invested_eur']:.2f} euro, verdeeld over {len(tickers)} aandelen.")
print("Deze instapkoersen veranderen nooit meer.")
print("=" * 74)
