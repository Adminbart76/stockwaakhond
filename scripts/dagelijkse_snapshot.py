"""Legt na de slotbel de koersen van vandaag vast.

Waarom dit nodig is: Yahoo verlaagt oude koersen zodra er dividend wordt
uitgekeerd. Zonder vastgelegde dagkoersen zou de grafiek van de portefeuille
met terugwerkende kracht blijven schuiven, en zou het rendement van vorige
maand er volgende maand anders uitzien.

Draait elke beursdag na de slotbel. Voegt alleen toe, overschrijft nooit.
Houdt meteen het gratis Supabase-project wakker, dat anders na zeven dagen
zonder activiteit pauzeert.

Een dag is compleet of hij bestaat niet
=======================================
Ontbreekt er een koers van een aandeel dat in de portefeuille zit, of van de
maatstaf SPY, dan wordt er niets vastgelegd en faalt deze taak. Een dag met
vier van de zes koersen is niet te herstellen (toevoegen kan, maar de dag is
dan al als gedaan geboekt) en geeft een gat in de grafiek dat niemand opmerkt.

Hetzelfde geldt voor de wisselkoers: zolang die bij deze handelsdag hoort
(tot middernacht in Londen), hoort hij erbij. Levert Yahoo hem niet, dan is dat
een probleem en geen reden om de dag half weg te schrijven.

Zonder de geheime sleutel
=========================
Dit script schrijft met de leessleutel plus een eigen schrijfteken
(SNAPSHOT_WRITE_TOKEN). Dat teken geeft recht op precies een ding: de koersen
van de afgesloten beursdag van vandaag, van de aandelen die NU in de
portefeuille zitten, allemaal samen. Geen signaal, geen instap, geen oudere
dag, niets wijzigen, niets wissen - dat zit in de database zelf
dichtgespijkerd, niet in dit bestand. Zie sql/03_smalle_deur.sql.

Een oudere dag herstellen kan hiermee dus niet. Daarvoor is er een aparte
beheerdershandeling met de geheime sleutel: scripts/herstel_dagkoers.py.

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
from sw import herbalans as hb                         # noqa: E402
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


kop("1. Welke beursdag is dit, en is hij voorbij?")

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


kop("2. Welke aandelen zitten er NU in de portefeuille?")

# Met opzet niet "alles wat ooit gekozen is": een aandeel dat vorige maand
# verkocht is, hoort geen koersen meer te kunnen laten bijschrijven. De lijst
# komt dus uit de actuele uitvoering, en alleen zolang er nog geen uitvoering
# is uit het laatste signaal.
uitvoeringen = db.select("executions", "select=*&order=execution_date.asc")
tickers = []
if uitvoeringen:
    ok, bericht = hb.verify_keten(uitvoeringen)
    if not ok:
        stop("de keten van uitvoeringen klopt niet: " + bericht)
    tickers = hb.actieve_tickers(uitvoeringen)
    print(f"   uit de actuele uitvoering: {', '.join(tickers)}")
else:
    signalen = db.select("signals", "select=selected&order=seq.desc&limit=1")
    if not signalen:
        klaar("er is nog geen signaal vastgelegd.")
    tickers = sorted({x["ticker"] for x in signalen[0]["selected"]} | {"SPY"})
    print(f"   nog geen uitvoering, dus uit het laatste signaal: {', '.join(tickers)}")

# Wat de database zelf toelaat moet hetzelfde zijn. Verschilt het, dan stoppen
# we en melden we het; zelf bijsturen zou het verschil wegmoffelen.
try:
    deur = db.rpc("mag_dagkoers_vastleggen", {"p_datum": str(vandaag.date())})
except Exception as fout:
    deur = None
    print(f"   (de database kon niet gevraagd worden: {fout})")

if isinstance(deur, dict):
    volgens_db = sorted(deur.get("toegestane_tickers") or [])
    print(f"   de database staat toe    : {', '.join(volgens_db)}")
    print(f"   lijst komt uit           : {deur.get('bron_van_de_lijst')}")
    if volgens_db and volgens_db != sorted(tickers):
        stop(
            "wij volgen andere aandelen dan de database toelaat.\n"
            f"   hier        : {', '.join(sorted(tickers))}\n"
            f"   database    : {', '.join(volgens_db)}\n"
            "Dat verschil hoort niemand stil recht te trekken."
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


kop("4. Is de dag compleet?")


def haal_uit(frames, ticker):
    """De echte en de herrekende slotkoers van die dag, of None."""
    kaal, bijgesteld = frames
    waarde = float(kaal.at[laatste_dag, ticker]) if ticker in kaal.columns else None
    adj = (float(bijgesteld.at[laatste_dag, ticker])
           if ticker in bijgesteld.columns and laatste_dag in bijgesteld.index else None)
    if waarde is None or waarde != waarde or waarde <= 0:
        return None, None
    return waarde, (adj if adj == adj else None)


koersen = []
ontbreekt = []
for t in tickers:
    waarde_echt, waarde_adj = haal_uit((echt, herrekend), t)
    if waarde_echt is None:
        ontbreekt.append(t)
        continue
    koersen.append({
        "ticker": t,
        "close_raw": waarde_echt,
        "close_adjusted": waarde_adj,
        "source": "Yahoo Finance dagslotkoers",
    })
    print(f"      {t:<6} {waarde_echt:>10.4f} USD")

# Yahoo laat geregeld een enkel aandeel weg uit een verzoek om meerdere
# tegelijk. Dat is geen echt ontbrekende koers maar een hik, en hij is op
# 7 oktober 2026 meteen de eerste keer opgetreden (MRNA). Daarom: wie ontbreekt,
# wordt nog een keer apart gevraagd voor de taak faalt.
if ontbreekt:
    print(f"   {', '.join(ontbreekt)} ontbreekt; nog een keer apart proberen")
    nog_steeds = []
    for t in ontbreekt:
        try:
            waarde_echt, waarde_adj = haal_uit(pr.haal_koersen([t], start=vanaf), t)
        except Exception as fout:
            print(f"      {t:<6} niet gelukt: {fout}")
            waarde_echt = None
        if waarde_echt is None:
            nog_steeds.append(t)
            continue
        koersen.append({
            "ticker": t,
            "close_raw": waarde_echt,
            "close_adjusted": waarde_adj,
            "source": "Yahoo Finance dagslotkoers",
        })
        print(f"      {t:<6} {waarde_echt:>10.4f} USD   (tweede poging)")
    ontbreekt = nog_steeds

if ontbreekt:
    stop(
        "deze dag is niet compleet: geen bruikbare slotkoers voor "
        + ", ".join(ontbreekt) + ".\n"
        "Er wordt geen halve dag vastgelegd: dat geeft een gat in de grafiek\n"
        "dat niemand opmerkt. Start de taak opnieuw bij Actions (Run workflow);\n"
        "lukt het die dag niet meer, dan kan de dag later met de hand\n"
        "bijgeschreven worden met scripts/herstel_dagkoers.py."
    )

# De wisselkoers mag alleen vastgelegd worden op de dag zelf, na de slotbel.
# Daarna rapporteert Yahoo voor diezelfde datum een ander getal, en dan zou
# er een koers in de geschiedenis komen die niet bij die dag hoort.
fx_rij = None
fx_gemist = ""
fx_mag, fx_stand, fx_uitleg = pr.wisselkoers_is_definitief(laatste_dag)
print()
print("   wisselkoers: " + fx_uitleg)

if fx_mag:
    bruikbaar = None
    if laatste_dag in fx.index:
        waarde = float(fx.loc[laatste_dag])
        if (waarde == waarde and waarde > 0
                and pd.Timestamp(fx.index[-1]).normalize() == laatste_dag.normalize()):
            bruikbaar = waarde

    if bruikbaar is None:
        stop(
            f"de wisselkoers van {laatste_dag.date()} hoort bij deze dag en is "
            "niet bruikbaar opgehaald.\n"
            "Zonder wisselkoers is er voor die dag geen bedrag in euro, dus\n"
            "wordt er niets vastgelegd. Dit venster loopt tot middernacht in\n"
            "Londen: binnen dat venster opnieuw draaien lost het op."
        )
    fx_rij = {"pair": "EURUSD", "rate": bruikbaar, "source": pr.FX_BRON}
    print(f"      1 euro = {bruikbaar:.6f} dollar")
elif fx_stand == "te_laat":
    # De slotkoersen van die dag staan wél vast en horen gewoon weggeschreven
    # te worden. Alleen de wisselkoers slaan we over, en daarover wordt
    # achteraf alarm geslagen: een ontbrekende dag in de wisselkoersen mag
    # niet stilletjes voorbijgaan.
    fx_gemist = fx_uitleg
    print("   de wisselkoers wordt NIET vastgelegd, de slotkoersen wel")
else:
    klaar("de wisselkoers van vandaag staat nog niet vast. " + fx_uitleg)

# Koersen voor het scherm. Dit is geen bewijsmateriaal; lukt het niet, dan
# is dat geen reden om de hele taak te laten falen.
live = []
try:
    laatste, tijdstip = pr.laatste_koersen(tickers)
    live = [{"ticker": t, "price_usd": k, "as_of": tijdstip,
             "source": "Yahoo Finance, vertraagd"} for t, k in laatste.items()
            if t in tickers]
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

if fx_gemist:
    # Eerst kijken of hij er misschien al staat. Deze taak draait een paar keer
    # per avond; de eerste keer binnen het venster legt de wisselkoers vast, en
    # dan hoeft een latere ronde geen alarm meer te slaan over iets wat gewoon
    # in orde is.
    staat_er_al = False
    try:
        staat_er_al = bool(db.select(
            "fx_snapshots",
            f"select=rate&pair=eq.EURUSD&snapshot_date=eq.{laatste_dag.date()}"))
    except Exception as fout:
        print(f"   (kon niet nakijken of de wisselkoers er al staat: {fout})")

    print()
    print("=" * 70)
    if staat_er_al:
        print(f"De wisselkoers van {laatste_dag.date()} stond er al, dus er is")
        print("niets misgelopen. Deze ronde kwam alleen te laat om hem zelf nog")
        print("vast te leggen.")
        print("=" * 70)
    else:
        print(f"LET OP: de wisselkoers van {laatste_dag.date()} ontbreekt.")
        print(fx_gemist)
        print()
        print("De slotkoersen van die dag staan wel vast. Dit gebeurt als deze taak")
        print("te laat draait: na middernacht in Londen. De taak start meerdere")
        print("keren per avond, dus als dit gebeurt, zijn ze allemaal te laat")
        print("geweest. De koers van die dag moet dan uit een andere bron komen")
        print("en met de hand bijgeschreven worden met scripts/herstel_dagkoers.py.")
        print("=" * 70)
        sys.exit(1)
