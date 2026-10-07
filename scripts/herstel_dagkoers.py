"""Een ontbrekende dag in de koersgeschiedenis herstellen. Met de hand, bewust.

Waarom dit een apart script is
==============================
De dagelijkse taak op GitHub mag sinds ronde 3 alleen nog de afgesloten
beursdag van vandaag wegschrijven, compleet, en niets anders. Geen oudere
datum, geen aandeel dat niet meer in de portefeuille zit. Dat is de hele
bedoeling: wie van buiten in de geschiedenis kan schrijven, kan de geschiedenis
kleuren.

Maar er blijft een echte situatie over: de taak heeft een keer niet gedraaid,
en er mist een dag. Die dag bijschrijven is geen fraude, het is onderhoud. Het
hoort alleen een bewuste handeling van Bart te zijn, met de geheime sleutel die
nergens anders staat dan op zijn eigen computer, en het hoort in het
beheerslogboek te komen.

Wat dit script NIET doet
========================
  * een bestaande koers overschrijven. Dat kan niemand; de database weigert
    het. Dit script voegt alleen toe wat er nog niet staat.
  * een wisselkoers van Yahoo halen voor een dag die voorbij is. Yahoo geeft
    voor zo'n datum een ander getal terug dan de koers die bij de slotkoersen
    van die dag hoorde (gemeten: 0,3 % verschil). Wil je de wisselkoers van een
    oude dag toevoegen, dan moet je die zelf meegeven, met de bron erbij.
  * iets raken in signals of executions. Daar hoort geen onderhoud bij.

Gebruik:
    python scripts/herstel_dagkoers.py --dag=2026-11-12 ^
        --tickers=MRNA,ILMN,MPC,HPE,VLO,SPY ^
        --reden="de taak van 12 november is niet gedraaid"

    met een wisselkoers erbij, uit een eigen bron:
    python scripts/herstel_dagkoers.py --dag=2026-11-12 --tickers=SPY ^
        --reden="..." --wisselkoers=1.1234 ^
        --wisselkoers-bron="ECB referentiekoers van 12 november 2026"

    --toon doet alles behalve wegschrijven.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import prices as pr                             # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402


def stop(bericht: str) -> None:
    print("\n" + "=" * 74)
    print("GESTOPT: " + bericht)
    print("Er is niets vastgelegd.")
    print("=" * 74)
    sys.exit(1)


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


argumenten = {}
for arg in sys.argv[1:]:
    if arg.startswith("--") and "=" in arg:
        naam, waarde = arg[2:].split("=", 1)
        argumenten[naam] = waarde

ALLEEN_TONEN = "--toon" in sys.argv
dag = argumenten.get("dag")
tickers = [t.strip().upper() for t in argumenten.get("tickers", "").split(",") if t.strip()]
reden = argumenten.get("reden", "").strip()
wisselkoers = argumenten.get("wisselkoers")
wisselkoers_bron = argumenten.get("wisselkoers-bron", "").strip()

if not dag or not tickers or not reden:
    stop(
        "geef minstens --dag, --tickers en --reden mee.\n"
        "Voorbeeld:\n"
        '  python scripts/herstel_dagkoers.py --dag=2026-11-12 '
        '--tickers=MRNA,SPY --reden="de taak is niet gedraaid"'
    )

try:
    dag_ts = pd.Timestamp(dag).normalize()
except Exception:
    stop(f"'{dag}' is geen datum.")


kop("1. Mag deze dag?")

dicht, uitleg = pr.beurs_is_gesloten_voor(dag_ts)
print("   " + uitleg)
if not dicht:
    stop("die beursdag is nog niet afgesloten. Er valt dus niets te herstellen.")
if dag_ts.dayofweek > 4:
    stop(f"{dag_ts.date()} is een weekenddag; daar is geen slotkoers van.")
print(f"   dag      : {dag_ts.date()}")
print(f"   aandelen : {', '.join(tickers)}")
print(f"   reden    : {reden}")


kop("2. Wat staat er al?")

cfg = lees_instellingen()
if not cfg.get("SUPABASE_SERVICE_KEY"):
    stop(
        "de geheime sleutel ontbreekt. Dit is een beheerdershandeling en werkt\n"
        "alleen met SUPABASE_SERVICE_KEY uit SLEUTELS_INVULLEN.txt."
    )

db = Supabase.schrijver(cfg)
al_aanwezig = {
    r["ticker"] for r in
    db.select("price_snapshots", f"select=ticker&snapshot_date=eq.{dag_ts.date()}")
}
if al_aanwezig:
    print(f"   staat er al: {', '.join(sorted(al_aanwezig))}")
else:
    print("   er staat nog niets voor die dag")

te_doen = [t for t in tickers if t not in al_aanwezig]
if not te_doen and not wisselkoers:
    print("\nEr is niets te herstellen: alles staat er al.")
    sys.exit(0)


kop("3. Koersen ophalen")

vanaf = str((dag_ts - pd.Timedelta(days=10)).date())
echt, herrekend = pr.haal_koersen(te_doen or tickers, start=vanaf, eind=str(dag_ts.date()))
if dag_ts not in echt.index:
    stop(
        f"Yahoo heeft geen slotkoersen voor {dag_ts.date()}. Was het een "
        "feestdag?\nDan is er niets te herstellen."
    )

rijen = []
for t in te_doen:
    waarde = float(echt.at[dag_ts, t]) if t in echt.columns else None
    adj = float(herrekend.at[dag_ts, t]) if t in herrekend.columns else None
    if waarde is None or waarde != waarde or waarde <= 0:
        stop(f"geen bruikbare slotkoers voor {t} op {dag_ts.date()}.")
    print(f"      {t:<6} {waarde:>10.4f} USD")
    rijen.append({
        "snapshot_date": str(dag_ts.date()),
        "ticker": t,
        "close_raw": waarde,
        "close_adjusted": (adj if adj == adj else None),
        "source": f"Yahoo Finance dagslotkoers, bijgeschreven met de hand ({reden})",
    })

fx_rij = None
if wisselkoers:
    if not wisselkoers_bron:
        stop(
            "geef bij een wisselkoers ook --wisselkoers-bron mee.\n"
            "Een koers zonder bron is een getal zonder bewijs."
        )
    try:
        koers = float(wisselkoers)
    except ValueError:
        stop(f"'{wisselkoers}' is geen koers.")
    if not 0.5 < koers < 2.0:
        stop(f"{koers} dollar voor een euro is geen koers.")
    print(f"   wisselkoers: 1 euro = {koers:.6f} dollar   ({wisselkoers_bron})")
    fx_rij = {
        "snapshot_date": str(dag_ts.date()),
        "pair": "EURUSD",
        "rate": koers,
        "source": wisselkoers_bron + " (met de hand bijgeschreven)",
    }
else:
    print("   geen wisselkoers meegegeven, dus die wordt niet aangevuld")
    print("   (Yahoo geeft voor een dag die voorbij is een ander getal terug)")


kop("4. Vastleggen")

if ALLEEN_TONEN:
    print("   (alleen tonen: er is niets vastgelegd)")
    sys.exit(0)

print("   Dit voegt toe aan de onaantastbare geschiedenis. Overschrijven kan niet,")
print("   terugdraaien ook niet.")
antwoord = input("   Typ JA om door te gaan: ").strip()
if antwoord != "JA":
    stop("afgebroken op jouw vraag.")

if rijen:
    db.insert("price_snapshots", rijen, negeer_dubbel=True)
    print(f"   price_snapshots : {len(rijen)} koersen bijgeschreven")
if fx_rij:
    db.insert("fx_snapshots", [fx_rij], negeer_dubbel=True)
    print("   fx_snapshots    : wisselkoers bijgeschreven")

db.insert("audit_log", [{
    "actor": "scripts/herstel_dagkoers.py",
    "action": "dag met de hand bijgeschreven",
    "detail": {
        "dag": str(dag_ts.date()),
        "tickers": te_doen,
        "wisselkoers": fx_rij["rate"] if fx_rij else None,
        "wisselkoers_bron": wisselkoers_bron or None,
        "reden": reden,
    },
}])

print("\n" + "=" * 74)
print(f"BIJGESCHREVEN - {dag_ts.date()} is aangevuld.")
print("De handeling staat in het beheerslogboek, met de reden erbij.")
print("=" * 74)
