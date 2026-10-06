"""Legt na de slotbel de koersen van vandaag vast.

Waarom dit nodig is: Yahoo verlaagt oude koersen zodra er dividend wordt
uitgekeerd. Zonder vastgelegde dagkoersen zou de grafiek van de portefeuille
met terugwerkende kracht blijven schuiven, en zou het rendement van vorige
maand er volgende maand anders uitzien.

Draait elke beursdag na de slotbel. Voegt alleen toe, overschrijft nooit.
Houdt meteen het gratis Supabase-project wakker, dat anders na zeven dagen
zonder activiteit pauzeert.

Gebruik:
    python scripts/dagelijkse_snapshot.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import prices as pr                            # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


cfg = lees_instellingen()
db = Supabase.schrijver(cfg)

kop("1. Welke aandelen volgen we?")

signalen = db.select("signals", "select=selected,entry_hash&order=seq.asc")
if not signalen:
    print("   Nog geen signaal vastgelegd. Niets te doen.")
    sys.exit(0)

tickers = {"SPY"}
for s in signalen:
    tickers.update(x["ticker"] for x in s["selected"])
tickers = sorted(tickers)
print(f"   {len(tickers)} stuks: {', '.join(tickers)}")


kop("2. Is de beurs gesloten?")

vandaag = pd.Timestamp.today().normalize()
dicht, uitleg = pr.beurs_is_gesloten_voor(vandaag)
print("   " + uitleg)
if not dicht:
    print("\n   De beurs is nog niet definitief gesloten. Er wordt niets")
    print("   vastgelegd: een voorlopige koers hoort niet in de geschiedenis.")
    sys.exit(0)


kop("3. Koersen ophalen")

vanaf = str((vandaag - pd.Timedelta(days=12)).date())
echt, herrekend = pr.haal_koersen(tickers, start=vanaf)
fx = pr.haal_wisselkoers(start=vanaf)

if len(echt) == 0:
    print("   Geen koersdata ontvangen.")
    sys.exit(1)

laatste_dag = echt.index[-1]
print(f"   laatste beursdag in de gegevens: {laatste_dag.date()}")

if laatste_dag.normalize() != vandaag:
    print("   Dat is niet vandaag. Waarschijnlijk een feestdag of weekend.")
    print("   Er wordt niets vastgelegd.")
    sys.exit(0)


kop("4. Vastleggen wat er nog niet staat")

bestaand = db.select(
    "price_snapshots", f"select=ticker&snapshot_date=eq.{laatste_dag.date()}")
al_er = {r["ticker"] for r in bestaand}

rijen = []
for t in tickers:
    if t in al_er:
        continue
    waarde_echt = float(echt.at[laatste_dag, t]) if t in echt.columns else None
    waarde_adj = float(herrekend.at[laatste_dag, t]) if t in herrekend.columns else None
    if waarde_echt is None or waarde_echt != waarde_echt:
        print(f"   {t}: geen koers, overgeslagen")
        continue
    rijen.append({
        "snapshot_date": str(laatste_dag.date()),
        "ticker": t,
        "close_raw": waarde_echt,
        "close_adjusted": waarde_adj,
        "source": "Yahoo Finance dagslotkoers",
    })

if rijen:
    db.insert("price_snapshots", rijen, negeer_dubbel=True)
    print(f"   {len(rijen)} koersen vastgelegd")
    for r in rijen:
        print(f"      {r['ticker']:<6} {r['close_raw']:>10.4f} USD")
else:
    print(f"   stonden er al ({len(al_er)} koersen voor {laatste_dag.date()})")

# wisselkoers
if laatste_dag in fx.index:
    bestaand_fx = db.select(
        "fx_snapshots", f"select=pair&snapshot_date=eq.{laatste_dag.date()}")
    if not bestaand_fx:
        koers = float(fx.loc[laatste_dag])
        db.insert("fx_snapshots", [{
            "snapshot_date": str(laatste_dag.date()),
            "pair": "EURUSD",
            "rate": koers,
            "source": pr.FX_BRON,
        }], negeer_dubbel=True)
        print(f"   wisselkoers vastgelegd: 1 euro = {koers:.6f} dollar")
    else:
        print("   wisselkoers stond er al")
else:
    print("   geen wisselkoers voor vandaag gevonden")


kop("5. Actuele koersen bijwerken voor het scherm")

try:
    laatste, tijdstip = pr.laatste_koersen(tickers)
    db.upsert("live_quotes", [{
        "ticker": t,
        "price_usd": k,
        "as_of": tijdstip,
        "source": "Yahoo Finance, vertraagd",
    } for t, k in laatste.items()])
    print(f"   {len(laatste)} koersen bijgewerkt")
except Exception as fout:
    print(f"   (niet gelukt, niet erg: {fout})")

db.insert("audit_log", [{
    "actor": "scripts/dagelijkse_snapshot.py",
    "action": "dagsnapshot",
    "detail": {"datum": str(laatste_dag.date()), "nieuw": len(rijen)},
}])

print("\n" + "=" * 70)
print(f"KLAAR - {laatste_dag.date()} staat vast en verandert niet meer.")
print("Uitgevoerd om " + datetime.now(timezone.utc).isoformat())
print("=" * 70)
