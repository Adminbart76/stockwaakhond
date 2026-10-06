"""Legt na de slotbel de koersen van vandaag vast.

Waarom dit nodig is: Yahoo verlaagt oude koersen zodra er dividend wordt
uitgekeerd. Zonder vastgelegde dagkoersen zou de grafiek van de portefeuille
met terugwerkende kracht blijven schuiven, en zou het rendement van vorige
maand er volgende maand anders uitzien.

Draait elke beursdag na de slotbel. Voegt alleen toe, overschrijft nooit.
Houdt meteen het gratis Supabase-project wakker, dat anders na zeven dagen
zonder activiteit pauzeert.

Zonder de geheime sleutel
=========================
Dit script schrijft met de leessleutel plus een eigen schrijfteken
(SNAPSHOT_WRITE_TOKEN). Dat teken geeft recht op precies een ding: een
dagkoers toevoegen van een aandeel dat in de portefeuille zit. Geen signaal,
geen instap, niets wijzigen, niets wissen - dat zit in de database zelf
dichtgespijkerd, niet in dit bestand. Zie sql/02_hardening.sql.

Daardoor hoeft de geheime schrijfsleutel niet meer in GitHub te staan.

Afloop:
    exitcode 0 - klaar, of niets te doen (weekend, feestdag, beurs nog open)
    exitcode 1 - er is iets mis en iemand moet ernaar kijken

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

from sw import beurskalender as bk                     # noqa: E402
from sw import prices as pr                            # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


def klaar(bericht: str) -> None:
    """Niets te doen. Dat is een normale uitkomst, geen fout."""
    print("\n" + "=" * 70)
    print("NIETS TE DOEN: " + bericht)
    print("=" * 70)
    sys.exit(0)


def stop(bericht: str) -> None:
    """Hier moet iemand naar kijken. De taak hoort dus te falen."""
    print("\n" + "=" * 70)
    print("GESTOPT: " + bericht)
    print("Er is niets vastgelegd.")
    print("=" * 70)
    sys.exit(1)


cfg = lees_instellingen()
if not cfg.get("SUPABASE_URL") or not cfg.get("SUPABASE_ANON_KEY"):
    stop("SUPABASE_URL of SUPABASE_ANON_KEY ontbreekt.")

token = cfg.get("SNAPSHOT_WRITE_TOKEN")
if not token:
    stop(
        "SNAPSHOT_WRITE_TOKEN ontbreekt.\n"
        "Zonder dat schrijfteken kan er niets vastgelegd worden. Het staat in\n"
        "SLEUTELS_INVULLEN.txt en hoort als GitHub-secret ingesteld te zijn."
    )

db = Supabase.lezer(cfg)


kop("1. Welke aandelen volgen we?")

signalen = db.select("signals", "select=selected,entry_hash&order=seq.asc")
if not signalen:
    klaar("er is nog geen signaal vastgelegd.")

tickers = {"SPY"}
for s in signalen:
    tickers.update(x["ticker"] for x in s["selected"])
tickers = sorted(tickers)
print(f"   {len(tickers)} stuks: {', '.join(tickers)}")


kop("2. Is de beurs gesloten?")

# De beursdag zoals New York hem telt, niet onze eigen kalenderdag. Om half
# een 's nachts bij ons is het daar nog de vorige dag, en dat is de dag
# waarvan de slotkoers net definitief geworden is.
vandaag = bk.handelsdag_nu()
print(f"   het is nu {vandaag.date()} in New York")
dicht, uitleg = pr.beurs_is_gesloten_voor(vandaag)
print("   " + uitleg)
if not dicht:
    klaar(
        "de beurs is nog niet definitief gesloten. Een voorlopige koers hoort "
        "niet in de geschiedenis."
    )


kop("3. Koersen ophalen")

vanaf = str((vandaag - pd.Timedelta(days=12)).date())
try:
    echt, herrekend = pr.haal_koersen(tickers, start=vanaf)
    fx = pr.haal_wisselkoers(start=vanaf)
except Exception as fout:
    stop("de koersen konden niet opgehaald worden: " + str(fout))

if len(echt) == 0:
    stop("geen koersdata ontvangen.")

laatste_dag = echt.index[-1]
print(f"   laatste beursdag in de gegevens: {laatste_dag.date()}")

if laatste_dag.normalize() != vandaag:
    klaar(
        f"de laatste beursdag in de gegevens is {laatste_dag.date()} en niet "
        "vandaag. Waarschijnlijk een feestdag of weekend."
    )


kop("4. Klaarzetten wat vastgelegd wordt")

koersen = []
for t in tickers:
    waarde_echt = float(echt.at[laatste_dag, t]) if t in echt.columns else None
    waarde_adj = float(herrekend.at[laatste_dag, t]) if t in herrekend.columns else None
    if waarde_echt is None or waarde_echt != waarde_echt or waarde_echt <= 0:
        print(f"   {t}: geen koers, overgeslagen")
        continue
    koersen.append({
        "ticker": t,
        "close_raw": waarde_echt,
        "close_adjusted": (waarde_adj if waarde_adj == waarde_adj else None),
        "source": "Yahoo Finance dagslotkoers",
    })
    print(f"      {t:<6} {waarde_echt:>10.4f} USD")

if not koersen:
    stop("geen enkele bruikbare slotkoers gevonden.")

# De wisselkoers mag alleen vastgelegd worden op de dag zelf, na de slotbel.
# Daarna rapporteert Yahoo voor diezelfde datum een ander getal, en dan zou
# er een koers in de geschiedenis komen die niet bij die dag hoort.
fx_rij = None
fx_mag, fx_stand, fx_uitleg = pr.wisselkoers_is_definitief(laatste_dag)
print()
print("   wisselkoers: " + fx_uitleg)

if fx_mag:
    if laatste_dag not in fx.index:
        print("   geen wisselkoers voor vandaag ontvangen, overgeslagen")
    elif pd.Timestamp(fx.index[-1]).normalize() != laatste_dag.normalize():
        print(
            f"   de laatste wisselkoers in de gegevens is van "
            f"{pd.Timestamp(fx.index[-1]).date()} en niet van vandaag, overgeslagen"
        )
    else:
        koers = float(fx.loc[laatste_dag])
        fx_rij = {"pair": "EURUSD", "rate": koers, "source": pr.FX_BRON}
        print(f"      1 euro = {koers:.6f} dollar")
elif fx_stand == "te_laat":
    stop(
        "de wisselkoers van vandaag is niet meer betrouwbaar op te halen.\n" + fx_uitleg
    )

# Koersen voor het scherm. Dit is geen bewijsmateriaal; lukt het niet, dan
# is dat geen reden om de hele taak te laten falen.
live = []
try:
    laatste, tijdstip = pr.laatste_koersen(tickers)
    live = [{"ticker": t, "price_usd": k, "as_of": tijdstip,
             "source": "Yahoo Finance, vertraagd"} for t, k in laatste.items()]
except Exception as fout:
    print(f"   (koersen voor het scherm niet gelukt, niet erg: {fout})")


kop("5. Vastleggen via het schrijfteken")

try:
    uitslag = db.rpc("leg_dagkoersen_vast", {
        "p_token": token,
        "p_datum": str(laatste_dag.date()),
        "p_koersen": koersen,
        "p_fx": fx_rij,
        "p_live": live,
    })
except Exception as fout:
    stop("vastleggen mislukte: " + str(fout))

if isinstance(uitslag, dict):
    print(f"   slotkoersen nieuw        : {uitslag.get('koersen_nieuw')}")
    print(f"   stonden er al            : {uitslag.get('koersen_stonden_er_al')}")
    print(f"   wisselkoers nieuw        : {uitslag.get('wisselkoers_nieuw')}")
    print(f"   schermkoersen bijgewerkt : {uitslag.get('schermkoersen_bijgewerkt')}")
else:
    print(f"   antwoord van de database : {uitslag}")


print("\n" + "=" * 70)
print(f"KLAAR - {laatste_dag.date()} staat vast en verandert niet meer.")
print("Uitgevoerd om " + datetime.now(timezone.utc).isoformat())
print("=" * 70)
