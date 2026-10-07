"""Probeert de forward-test met opzet kapot te maken en controleert dat dat niet lukt.

Dit script valt de eigen database aan met alle middelen die we hebben, de
geheime sleutel inbegrepen. Elke poging hoort te mislukken. Lukt er een wel,
dan is dat een ernstig probleem en moet het meteen opgelost worden.

De vervalste records krijgen met opzet een kloppend controlegetal. Anders
zouden ze allemaal al op de eerste horde stranden en zou je nooit te weten
komen of de beveiligingen daarachter werken.

Twee dingen die hier bewust ingebouwd zijn
==========================================
1. ELK VERVALST SIGNAAL DRAAGT EEN DATUM IN DE TOEKOMST.
   Dat is het vangnet. Een keuze kan niet gemaakt zijn op een beursdag die nog
   moet komen, dus de database weigert zo'n record altijd - en die controle
   staat als laatste in de rij. Zo krijgt elke aanval eerst de kans om op zijn
   eigen regel te stranden, en wat er door een ontbrekende regel heen zou
   glippen, strandt alsnog. Zonder zo'n vangnet zou een aanval die een gat
   vindt een vals signaal in de keten zetten, en dat is niet meer weg te halen.

2. HET VANGNET WORDT ALS EERSTE GETEST.
   Werkt dat niet zoals verwacht, dan stopt dit script onmiddellijk en wordt
   er geen enkele andere poging gedaan.

Draai dit na elke wijziging aan sql/01_schema.sql of sql/02_hardening.sql.

Gebruik:
    python scripts/controleer_slot.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import herbalans as hb                       # noqa: E402
from sw.strategy import canonical_json, sha256_text  # noqa: E402
from sw.supabase_io import lees_instellingen         # noqa: E402

cfg = lees_instellingen()
URL = cfg["SUPABASE_URL"].rstrip("/")
GEHEIM = cfg["SUPABASE_SERVICE_KEY"]
LEZEN = cfg.get("SUPABASE_ANON_KEY")
TEKEN = cfg.get("SNAPSHOT_WRITE_TOKEN")

# Een beursdag die nog moet komen. Daarom weigert de database elk record dat
# deze datum draagt, wat er verder ook in staat.
AANVALSDATUM = "2027-01-04"

# De klok van de beurs. Een deel van de regels hieronder gaat over tijd, en dan
# doet het ertoe of het in New York nu voor of na de slotbel is.
BEURS = ZoneInfo("America/New_York")
NU_NY = datetime.now(BEURS)
VANDAAG_NY = NU_NY.date()
NA_DE_SLOTBEL = (NU_NY.hour, NU_NY.minute) >= (16, 20)

uitslagen = []


def koppen(sleutel: str) -> dict:
    return {
        "apikey": sleutel,
        "Authorization": "Bearer " + sleutel,
        "Content-Type": "application/json",
    }


def poging(omschrijving: str, hoort_te: str, functie, melding_bevat: str = "") -> bool:
    """Doet een poging en vertelt of de uitkomst is wat we wilden.

    melding_bevat: welk stukje tekst er in de weigering hoort te staan. Zonder
    dat zou een poging ook kunnen stranden op een heel andere regel, en dan
    weet je nog niet of de regel die je wilde testen er wel staat.
    """
    try:
        r = functie()
        gelukt = r.status_code in (200, 201, 204)
        code = str(r.status_code)
        melding = ""
        if not gelukt:
            try:
                j = r.json()
                melding = (j.get("message") or j.get("details") or "")[:200]
            except Exception:
                melding = r.text[:200]
    except Exception as ex:
        gelukt = False
        code = type(ex).__name__
        melding = str(ex)[:200]

    goed = (gelukt and hoort_te == "lukken") or (not gelukt and hoort_te == "mislukken")
    if goed and melding_bevat and melding_bevat.lower() not in melding.lower():
        goed = False
        melding = f"[verwachte reden niet gevonden: '{melding_bevat}'] " + melding

    uitslagen.append(goed)
    print(f"   {'OK  ' if goed else 'FOUT'}  {omschrijving}")
    print(f"         hoort te {hoort_te}  ->  HTTP {code}  {melding[:78]}")
    return goed


def maak_record(echt: dict, **afwijkingen) -> dict:
    """Bouwt een signaalrecord met kloppend controlegetal en kloppende keten.

    Alles sluit aan bij het echte laatste signaal: het volgnummer erna, het
    juiste controlegetal van de voorganger, de juiste formule en versie. Zo
    komt de aanval voorbij alle lagen en wordt de regel die je wilt testen
    werkelijk op de proef gesteld.

    Behalve de signaaldatum: die ligt in de toekomst, en dat is het vangnet.
    """
    payload = {
        "record_type": "signal",
        "schema_version": 1,
        "created_at_utc": AANVALSDATUM + "T21:00:00+00:00",
        "signal_market_date": AANVALSDATUM,
        "universe_source": echt["universe_source"],
        "universe_hash": "f" * 64,
        "universe_count": 500,
        "eligible_count": 500,
        "coverage_pct": 100.0,
        "selected": [{"rank": 1, "ticker": "FAKE", "score": 100.0, "signal_close": 1.0}],
        "spy_signal_close": 800.0,
        "formula_spec": echt["formula_spec"],
        "previous_hash": echt["entry_hash"],
        "strategy_hash": echt["strategy_hash"],
        "strategy_version": echt["strategy_version"],
    }
    payload.update({k: v for k, v in afwijkingen.items() if k in payload})

    canoniek = canonical_json(payload)
    entry_hash = sha256_text(canoniek)
    volledig = dict(payload)
    volledig["entry_hash"] = entry_hash

    rij = dict(payload)
    rij["entry_hash"] = entry_hash
    rij["seq"] = afwijkingen.get("seq", int(echt["seq"]) + 1)
    rij["canonical_payload"] = canoniek
    rij["ledger_line"] = canonical_json(volledig)

    # afwijkingen die alleen de kolom raken en niet de gehashte inhoud
    for k, v in afwijkingen.items():
        if k.startswith("kolom_"):
            rij[k[len("kolom_"):]] = v
    return rij


def maak_uitvoering(echt: dict, **afwijkingen) -> dict:
    """Bouwt een uitvoeringsrecord met kloppend controlegetal.

    Vertrekt van de echte uitvoering, zodat de vorm exact klopt. Elke aanval
    hieronder mikt op dezelfde entry_hash als die echte uitvoering, en die is
    uniek: zou de regel die we testen ontbreken, dan weigert de database het
    record nog altijd. Deze pogingen kunnen dus niets kapotmaken.
    """
    payload = json.loads(echt["canonical_payload"])
    for k, v in afwijkingen.items():
        if not k.startswith("kolom_"):
            payload[k] = v

    canoniek = canonical_json(payload)
    rij = {
        "exec_hash": sha256_text(canoniek),
        "entry_hash": payload["entry_hash"],
        "execution_date": payload["execution_date"],
        "fx_pair": payload["fx_pair"],
        "fx_rate": payload["fx_rate"],
        "fx_source": payload["fx_source"],
        "fx_asof": payload["fx_asof"],
        "start_capital_eur": payload["start_capital_eur"],
        "cost_pct": payload["cost_pct"],
        "cost_eur": payload["cost_eur"],
        "invested_eur": payload["invested_eur"],
        "positions": payload["positions"],
        "benchmark": payload["benchmark"],
        "canonical_payload": canoniek,
    }
    for k, v in afwijkingen.items():
        if k.startswith("kolom_"):
            rij[k[len("kolom_"):]] = v
    return rij


def rpc(sleutel: str, functie: str, argumenten: dict):
    return requests.post(
        f"{URL}/rest/v1/rpc/{functie}",
        headers=koppen(sleutel),
        data=json.dumps(argumenten),
        timeout=30,
    )


# --------------------------------------------------------------- het doelwit
r = requests.get(f"{URL}/rest/v1/signals?select=*&order=seq.asc",
                 headers=koppen(GEHEIM), timeout=30)
r.raise_for_status()
signalen = r.json()
if not signalen:
    print("Er staat nog geen signaal in de database. Importeer eerst.")
    sys.exit(1)
doel = signalen[-1]        # de punt van de keten
eerste = signalen[0]
entry_hash = eerste["entry_hash"]

r = requests.get(f"{URL}/rest/v1/executions?select=*", headers=koppen(GEHEIM), timeout=30)
uitvoeringen = r.json() if r.status_code == 200 else []

print("AANVALSTEST OP DE FORWARD-TEST")
print("=" * 78)
print(f"project : {URL}")
print(f"doelwit : signaal {eerste['signal_market_date']} ({entry_hash[:16]}...)")
print(f"keten   : {len(signalen)} signaal/signalen, punt is seq {doel['seq']}")


# ===========================================================================
print("\n0. STAAT DE VERSTEVIGING UIT sql/02_hardening.sql ERIN?")

stand = {}
r = rpc(LEZEN or GEHEIM, "hardening_status", {})
if r.status_code == 200:
    stand = r.json() or {}
    for naam, waarde in sorted(stand.items()):
        if isinstance(waarde, bool):
            print(f"   {'OK  ' if waarde else 'NEE '}  {naam}")
        else:
            print(f"         {naam}: {waarde}")
else:
    print(f"   FOUT  hardening_status() bestaat nog niet (HTTP {r.status_code})")

ketenregels = bool(stand.get("keten_moet_kloppen"))
uitvoeringsregels = bool(stand.get("velden_moeten_kloppen"))
schrijfdeur = bool(stand.get("schrijfdeur_bestaat"))
teken_gezet = bool(stand.get("schrijfteken_ingesteld"))
uitslagen.append(ketenregels and uitvoeringsregels and schrijfdeur)

# Bestaan is niet genoeg: een trigger kan uitgezet zijn en blijft dan gewoon in
# de lijst staan terwijl hij niets meer doet.
AANSTAAN = [
    "keten_moet_kloppen_staat_aan",
    "velden_moeten_kloppen_staat_aan",
    "wisselkoersbewijs_staat_aan",
    "hash_moet_kloppen_staat_aan",
    "sloten_staan_aan",
]
uit = [naam for naam in AANSTAAN if not stand.get(naam)]
uitslagen.append(not uit)
print(f"   {'OK  ' if not uit else 'FOUT'}  alle wachters staan ook werkelijk aan"
      + (f" (uit of onbekend: {', '.join(uit)})" if uit else ""))

deur_versie = int(stand.get("deur_versie") or 0)
uitslagen.append(deur_versie >= 4)
print(f"   {'OK  ' if deur_versie >= 4 else 'FOUT'}  de schrijfdeur is versie "
      f"{deur_versie} (verwacht: 4 of hoger)")
if deur_versie < 4:
    print()
    print("   " + "!" * 70)
    if deur_versie < 3:
        print("   sql/03_smalle_deur.sql is niet uitgevoerd, of 02_hardening.sql is")
        print("   er daarna nog eens over gegaan. Voer 03 opnieuw uit in de SQL")
        print("   Editor van Supabase; zolang dat niet gebeurd is, staat de deur voor")
        print("   de dagelijkse taak wijder open dan bedoeld.")
    else:
        print("   sql/04_dividend_en_fx.sql is niet uitgevoerd, of 03 is er daarna")
        print("   nog eens over gegaan. Zonder 04 is de betaaldatum van een dividend")
        print("   niet verplicht en wordt de minuutbalk van de wisselkoers niet")
        print("   nagerekend. Voer 04 uit in de SQL Editor van Supabase.")
    print("   " + "!" * 70)

# De betaaldatum van een dividend en het spoor van de wisselkoers (sql/04).
# Wat hier nagekeken wordt, is de werkelijke toestand van de database
# (pg_attribute, pg_constraint, pg_trigger) en niet een bewering van een
# functie. Het GEDRAG van wisselkoersbewijs_moet_kloppen wordt met opzet niet
# met een poging getest: een uitvoering die alleen op die wachter stuit, zou bij
# een ontbrekende wachter in de echte keten belanden, en weghalen kan niet meer.
# Dat gedrag staat in tests/test_fx_regel.py en in de tekst van sql/04.
VIER = [
    ("dividend_betaaldatum_verplicht",
     "een dividend kan niet zonder betaaldatum worden vastgelegd"),
    ("dividend_betaaldag_na_exdag",
     "een betaaldag voor de ex-dag wordt geweigerd"),
    ("fx_spoor_kolommen",
     "de minuutbalk en het ECB-controlegetal kunnen bewaard worden"),
    ("wisselkoersbewijs_moet_kloppen",
     "de minuutbalk van een uitvoering wordt nagerekend"),
]
for naam, uitleg in VIER:
    goed = bool(stand.get(naam))
    uitslagen.append(goed)
    print(f"   {'OK  ' if goed else 'FOUT'}  {uitleg}")

if not ketenregels:
    print()
    print("   " + "!" * 70)
    print("   De ketenregels staan nog niet in de database. Voer eerst")
    print("   sql/02_hardening.sql uit in de SQL Editor van Supabase.")
    print("   Zolang dat niet gebeurd is, worden de pogingen hieronder NIET")
    print("   gedaan: een vervalst signaal zou er dan werkelijk in komen, en")
    print("   weghalen kan niet meer.")
    print("   " + "!" * 70)


# ===========================================================================
print("\n1. WIJZIGEN EN WISSEN MET DE GEHEIME SLEUTEL")
print("   (die sleutel omzeilt alle gewone beveiliging van Supabase)")

poging("een score in het signaal wijzigen", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/signals?entry_hash=eq.{entry_hash}",
    headers=koppen(GEHEIM), data=json.dumps({"coverage_pct": 1.0}), timeout=30),
    melding_bevat="append-only")

poging("het signaal verwijderen", "mislukken", lambda: requests.delete(
    f"{URL}/rest/v1/signals?entry_hash=eq.{entry_hash}",
    headers=koppen(GEHEIM), timeout=30), melding_bevat="append-only")

poging("alle signalen in een keer wissen", "mislukken", lambda: requests.delete(
    f"{URL}/rest/v1/signals?seq=gte.0", headers=koppen(GEHEIM), timeout=30),
    melding_bevat="append-only")

poging("de strategie herschrijven", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/strategies?strategy_hash=eq.{doel['strategy_hash']}",
    headers=koppen(GEHEIM),
    data=json.dumps({"strategy_version": "stiekem gewijzigd"}), timeout=30),
    melding_bevat="append-only")

poging("een symbool uit het universum halen", "mislukken", lambda: requests.delete(
    f"{URL}/rest/v1/signal_universe?entry_hash=eq.{entry_hash}&symbol=eq.MRNA",
    headers=koppen(GEHEIM), timeout=30), melding_bevat="append-only")

poging("de uitvoering van de portefeuille wijzigen", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/executions?entry_hash=eq.{entry_hash}",
    headers=koppen(GEHEIM), data=json.dumps({"fx_rate": 1.0}), timeout=30),
    melding_bevat="append-only")

poging("een vastgelegde slotkoers wijzigen", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/price_snapshots?ticker=eq.SPY",
    headers=koppen(GEHEIM), data=json.dumps({"close_raw": 1.0}), timeout=30),
    melding_bevat="append-only")


# ===========================================================================
if ketenregels:
    print("\n2. HET VANGNET: EEN SIGNAALDATUM DIE NOG MOET KOMEN")
    print("   (werkt dit niet, dan stopt het script hier)")

    vangnet = poging(
        "een verder volkomen geldig signaal, gedateerd in de toekomst",
        "mislukken",
        lambda: requests.post(
            f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
            data=json.dumps(maak_record(doel)), timeout=30),
        melding_bevat="toekomst")

    if not vangnet:
        print()
        print("   " + "!" * 70)
        print("   Het vangnet werkt niet zoals verwacht. Er worden geen verdere")
        print("   pogingen gedaan: die zouden een vals signaal kunnen achterlaten.")
        print("   Zoek eerst uit waarom public.controleer_keten() een signaaldatum")
        print("   in de toekomst niet weigert.")
        print("   " + "!" * 70)
        print(f"\nLET OP: {uitslagen.count(False)} van de {len(uitslagen)} controles ging mis.")
        sys.exit(1)


# ===========================================================================
if ketenregels:
    print("\n3. EEN VERVALST SIGNAAL BINNENSMOKKELEN")
    print("   (elk met een kloppend controlegetal en een kloppende keten,")
    print("    zodat precies een regel op de proef gesteld wordt)")

    poging("verkeerd controlegetal", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps({**maak_record(doel), "entry_hash": "0" * 64}), timeout=30),
        melding_bevat="controlegetal")

    poging("volgnummer sluit niet aan", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, seq=99)), timeout=30),
        melding_bevat="volgnummer")

    poging("verwijst niet naar het laatste signaal", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, previous_hash="a" * 64)), timeout=30),
        melding_bevat="laatste signaal")

    poging("een tweede keten naast de echte beginnen", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, previous_hash="GENESIS")), timeout=30),
        melding_bevat="laatste signaal")

    # Deze draagt de datum van het vorige signaal. Dat is twee keer fout - te
    # vroeg, en die datum is al gebruikt - en dus ook zonder de 28-dagenregel
    # onmogelijk. Een datum die alleen maar te vroeg is, zou hier niet veilig
    # te proberen zijn.
    poging("te snel een nieuw signaal (binnen 28 dagen)", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, signal_market_date=doel["signal_market_date"])),
        timeout=30), melding_bevat="Te vroeg")

    poging("een signaal met een onbekende strategie", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, strategy_hash="b" * 64)), timeout=30),
        melding_bevat="strategie")

    poging("een verzonnen strategieversie bij een echte strategie", "mislukken",
        lambda: requests.post(
            f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
            data=json.dumps(maak_record(doel, strategy_version="SW_SCORE_V4_VERZONNEN")),
            timeout=30),
        melding_bevat="strategieversie")

    gewijzigde_formule = json.loads(json.dumps(doel["formula_spec"]))
    gewijzigde_formule["weights"]["return_12m_percentile"] = 30
    poging("een formule die niet bij de strategie hoort", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, formula_spec=gewijzigde_formule)), timeout=30),
        melding_bevat="formule")

    poging("moment van vastleggen anders in de kolom", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(
            doel, kolom_created_at_utc="2026-01-01T00:00:00+00:00")), timeout=30),
        melding_bevat="created_at_utc")

    poging("kolom zegt iets anders dan de gehashte inhoud", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, kolom_coverage_pct=42.0)), timeout=30),
        melding_bevat="kolommen")

    poging("gehashte Top-5 vervangen in de kolom", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, kolom_selected=[
            {"rank": 1, "ticker": "WINNAAR", "score": 100.0, "signal_close": 1.0}])),
        timeout=30), melding_bevat="kolommen")

    poging("logboekregel die niet bij de inhoud hoort", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, kolom_ledger_line='{"verzonnen":true}')),
        timeout=30), melding_bevat="logboekregel")


# ===========================================================================
if uitvoeringen and uitvoeringsregels:
    print("\n4. DE UITVOERING VAN DE PORTEFEUILLE")
    print("   (deze pogingen mikken op een bestaande, unieke uitvoering en")
    print("    kunnen dus niets achterlaten)")

    echte_uitvoering = uitvoeringen[0]

    poging("bron van de wisselkoers anders in de kolom", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/executions", headers=koppen(GEHEIM),
        data=json.dumps(maak_uitvoering(
            echte_uitvoering, kolom_fx_source="Verzonnen bron")), timeout=30),
        melding_bevat="fx_source")

    poging("moment van de wisselkoers anders in de kolom", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/executions", headers=koppen(GEHEIM),
        data=json.dumps(maak_uitvoering(
            echte_uitvoering, kolom_fx_asof="2027-01-01T00:00:00+00:00")), timeout=30),
        melding_bevat="fx_asof")

    poging("wisselkoers van een heel ander moment", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/executions", headers=koppen(GEHEIM),
        data=json.dumps(maak_uitvoering(
            echte_uitvoering, fx_asof="2026-10-13T20:00:00+00:00")), timeout=30),
        melding_bevat="slotbel")

    poging("instappen op de signaaldag zelf", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/executions", headers=koppen(GEHEIM),
        data=json.dumps(maak_uitvoering(
            echte_uitvoering, execution_date=eerste["signal_market_date"])), timeout=30),
        melding_bevat="na de signaaldag")

elif not uitvoeringen:
    print("\n4. DE UITVOERING VAN DE PORTEFEUILLE")
    print("   (overgeslagen: er staat nog geen uitvoering in de database)")


# ===========================================================================
if schrijfdeur:
    print("\n5. DE SMALLE SCHRIJFDEUR VOOR DE DAGELIJKSE TAAK")
    print("   (die werkt met de leessleutel plus een eigen schrijfteken)")

    sleutel = LEZEN or GEHEIM

    poging("dagkoersen wegschrijven zonder schrijfteken", "mislukken",
           lambda: rpc(sleutel, "leg_dagkoersen_vast", {
               "p_token": None, "p_datum": "2026-10-06",
               "p_koersen": [{"ticker": "SPY", "close_raw": 1.0}]}),
           melding_bevat="schrijfteken")

    poging("dagkoersen wegschrijven met een verzonnen schrijfteken", "mislukken",
           lambda: rpc(sleutel, "leg_dagkoersen_vast", {
               "p_token": "x" * 40, "p_datum": "2026-10-06",
               "p_koersen": [{"ticker": "SPY", "close_raw": 1.0}]}),
           melding_bevat="klopt niet")

    if TEKEN and teken_gezet and deur_versie < 3:
        print()
        print("   " + "!" * 70)
        print("   De smallere deur uit sql/03_smalle_deur.sql staat nog niet in de")
        print("   database. De pogingen hieronder worden NIET gedaan: zonder die")
        print("   regels zou een van hen werkelijk een verzonnen wisselkoers op een")
        print("   oude dag kunnen achterlaten, en weghalen kan niet meer.")
        print("   Voer eerst 03 uit in de SQL Editor van Supabase.")
        print("   " + "!" * 70)

    if TEKEN and teken_gezet and deur_versie >= 3:
        # Een dag die al voorbij is. De bestaande slotkoers van SPY staat er al,
        # dus zelfs als elke regel zou ontbreken, kan deze poging niets
        # veranderen: bestaande koersen worden nooit overschreven.
        poging("een koers bijschrijven op een willekeurige oude dag", "mislukken",
               lambda: rpc(sleutel, "leg_dagkoersen_vast", {
                   "p_token": TEKEN, "p_datum": "2026-10-06",
                   "p_koersen": [{"ticker": "SPY", "close_raw": 1.0}]}),
               melding_bevat="beursdag van nu")

        poging("een koers voor een dag die nog moet komen", "mislukken",
               lambda: rpc(sleutel, "leg_dagkoersen_vast", {
                   "p_token": TEKEN, "p_datum": "2030-01-02",
                   "p_koersen": [{"ticker": "SPY", "close_raw": 1.0}]}),
               melding_bevat="beursdag van nu")

        poging("een willekeurige wisselkoers op een verkeerde dag", "mislukken",
               lambda: rpc(sleutel, "leg_dagkoersen_vast", {
                   "p_token": TEKEN, "p_datum": "2026-10-05",
                   "p_koersen": [{"ticker": "SPY", "close_raw": 1.0}],
                   "p_fx": {"pair": "EURUSD", "rate": 1.5}}),
               melding_bevat="beursdag van nu")

        # Deze poging kan alleen slagen op een weekdag na de slotbel; daarvoor
        # strandt ze op de tijdregel en zegt ze dus niets over de tickerregel.
        if NA_DE_SLOTBEL and VANDAAG_NY.weekday() < 5:
            poging("een aandeel dat niet in de huidige portefeuille zit", "mislukken",
                   lambda: rpc(sleutel, "leg_dagkoersen_vast", {
                       "p_token": TEKEN, "p_datum": str(VANDAAG_NY),
                       "p_koersen": [{"ticker": "AAPL", "close_raw": 1.0}]}),
                   melding_bevat="huidige portefeuille")
        else:
            print("   (de poging met een vreemd aandeel is overgeslagen: in New York")
            print("    is de beurs nu niet gesloten, dus die strandt op de tijdregel.")
            print("    Hieronder wordt dezelfde regel bevraagd zonder te schrijven.)")

        # Een bestaande slotkoers overschrijven. Sinds de smallere deur wordt
        # zo'n aanroep al op de datum geweigerd; of hij nu strandt of niet, de
        # koers die er staat moet dezelfde blijven.
        r = requests.get(
            f"{URL}/rest/v1/price_snapshots?select=*&order=snapshot_date.desc&limit=1",
            headers=koppen(GEHEIM), timeout=30)
        bestaand = r.json() if r.status_code == 200 else []
        if bestaand:
            rij = bestaand[0]
            antwoord = rpc(sleutel, "leg_dagkoersen_vast", {
                "p_token": TEKEN,
                "p_datum": rij["snapshot_date"],
                "p_koersen": [{"ticker": rij["ticker"], "close_raw": 1.0}],
            })
            r2 = requests.get(
                f"{URL}/rest/v1/price_snapshots?select=*"
                f"&snapshot_date=eq.{rij['snapshot_date']}&ticker=eq.{rij['ticker']}",
                headers=koppen(GEHEIM), timeout=30)
            na = (r2.json() or [{}])[0]
            onveranderd = str(na.get("close_raw")) == str(rij.get("close_raw"))
            uitslagen.append(onveranderd)
            print(f"   {'OK  ' if onveranderd else 'FOUT'}  een bestaande slotkoers "
                  f"overschrijven verandert niets")
            print(f"         koers blijft {rij.get('close_raw')} "
                  f"(nu: {na.get('close_raw')}, antwoord: HTTP "
                  f"{antwoord.status_code})")

    if not (TEKEN and teken_gezet):
        print("   (het schrijfteken zelf is hier niet bekend; die pogingen zijn")
        print("    overgeslagen. Zet SNAPSHOT_WRITE_TOKEN in SLEUTELS_INVULLEN.txt")
        print("    en voer de regel uit die daar bij punt 6 staat.)")


# ===========================================================================
if schrijfdeur and deur_versie >= 3:
    print("\n5b. DE DEUR BEVRAGEN ZONDER TE SCHRIJVEN")
    print("   (twee regels worden pas bereikt als al het andere klopt: 'de dag")
    print("    moet compleet zijn' en 'dit is geen koers'. Die echt proberen zou")
    print("    bij een gat in de beveiliging een dag met verzonnen cijfers")
    print("    achterlaten, en dat is niet meer weg te halen. Daarom wordt")
    print("    dezelfde vraag gesteld aan een functie die niets wegschrijft.)")

    def vraag(**argumenten):
        r = rpc(LEZEN or GEHEIM, "mag_dagkoers_vastleggen", argumenten)
        if r.status_code != 200:
            print(f"   FOUT  mag_dagkoers_vastleggen() antwoordde HTTP {r.status_code}")
            uitslagen.append(False)
            return None
        return r.json()

    def controle(omschrijving: str, antwoord, veld: str, verwacht) -> None:
        gevonden = antwoord.get(veld) if isinstance(antwoord, dict) else None
        goed = gevonden == verwacht
        uitslagen.append(goed)
        print(f"   {'OK  ' if goed else 'FOUT'}  {omschrijving}")
        print(f"         {veld} = {gevonden}   (verwacht: {verwacht})")

    een_minuut_voor_de_bel = datetime.combine(
        VANDAAG_NY, time(15, 59), BEURS).astimezone(timezone.utc).isoformat()
    antwoord = vraag(p_datum=str(VANDAAG_NY), p_nu=een_minuut_voor_de_bel)
    controle("vandaag, een minuut voor de slotbel: mag niet", antwoord, "mag", False)
    controle("   en de reden is de slotbel", antwoord,
             "na_de_slotbel_plus_marge", False)

    zaterdag = VANDAAG_NY - timedelta(days=(VANDAAG_NY.weekday() - 5) % 7)
    antwoord = vraag(p_datum=str(zaterdag))
    controle(f"een zaterdag ({zaterdag}): mag niet", antwoord, "mag", False)
    controle("   en de reden is dat het geen beursdag is", antwoord,
             "is_een_weekdag", False)

    antwoord = vraag(p_datum=str(VANDAAG_NY))
    actief = (antwoord or {}).get("toegestane_tickers") or []
    bron = (antwoord or {}).get("bron_van_de_lijst")
    goed = bron == "de actuele uitvoering"
    uitslagen.append(goed)
    print(f"   {'OK  ' if goed else 'FOUT'}  de lijst komt uit de huidige "
          f"portefeuille en niet uit alle oude signalen")
    print(f"         {len(actief)} aandelen: {', '.join(actief)}")
    print(f"         bron: {bron}")

    if len(actief) >= 2:
        antwoord = vraag(p_datum=str(VANDAAG_NY), p_tickers=actief[:-1])
        controle(f"een dag zonder {actief[-1]}: niet compleet",
                 antwoord, "lijst_is_compleet", False)
        antwoord = vraag(p_datum=str(VANDAAG_NY), p_tickers=actief)
        controle("de volledige lijst: compleet", antwoord,
                 "lijst_is_compleet", True)

    antwoord = vraag(p_datum=str(VANDAAG_NY), p_fx=99.0)
    controle("een wisselkoers van 99 dollar voor een euro: geen koers",
             antwoord, "wisselkoers_bruikbaar", False)
    antwoord = vraag(p_datum=str(VANDAAG_NY), p_fx=1.13)
    controle("een wisselkoers van 1,13: wel een koers",
             antwoord, "wisselkoers_bruikbaar", True)


# ===========================================================================
if LEZEN:
    print("\n6. MET DE LEESSLEUTEL (die in de webapp van het dashboard staat)")

    poging("het signaal lezen", "lukken", lambda: requests.get(
        f"{URL}/rest/v1/signals?select=entry_hash", headers=koppen(LEZEN), timeout=30))

    poging("het universum lezen", "lukken", lambda: requests.get(
        f"{URL}/rest/v1/signal_universe?select=symbol&limit=5",
        headers=koppen(LEZEN), timeout=30))

    poging("een signaal toevoegen", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(LEZEN),
        data=json.dumps(maak_record(doel)), timeout=30))

    poging("een signaal wijzigen", "mislukken", lambda: requests.patch(
        f"{URL}/rest/v1/signals?entry_hash=eq.{entry_hash}",
        headers=koppen(LEZEN), data=json.dumps({"coverage_pct": 1.0}), timeout=30))

    poging("een signaal verwijderen", "mislukken", lambda: requests.delete(
        f"{URL}/rest/v1/signals?entry_hash=eq.{entry_hash}",
        headers=koppen(LEZEN), timeout=30))

    poging("in het beheerslogboek kijken", "mislukken", lambda: requests.get(
        f"{URL}/rest/v1/audit_log?select=*", headers=koppen(LEZEN), timeout=30))

    poging("rechtstreeks een slotkoers toevoegen", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/price_snapshots", headers=koppen(LEZEN),
        data=json.dumps([{"snapshot_date": "2026-10-06", "ticker": "SPY",
                          "close_raw": 1.0, "source": "aanvalstest"}]), timeout=30))

    poging("in de geheimen van de database kijken", "mislukken", lambda: requests.get(
        f"{URL}/rest/v1/snapshot_sleutels?select=*", headers=koppen(LEZEN), timeout=30))


# ===========================================================================
print("\n7. IS ER ECHT NIETS VERANDERD?")

r = requests.get(f"{URL}/rest/v1/signals?select=*&order=seq.asc",
                 headers=koppen(GEHEIM), timeout=30)
na = r.json()
onveranderd = (len(na) == len(signalen) and na[0] == eerste)
uitslagen.append(onveranderd)
print(f"   {'OK  ' if onveranderd else 'FOUT'}  het signaal is na alle pogingen nog exact hetzelfde")
print(f"         aantal signalen: {len(signalen)} voor, {len(na)} na")

r = requests.get(f"{URL}/rest/v1/signal_universe?select=symbol&limit=2000",
                 headers=koppen(GEHEIM), timeout=30)
aantal = len(r.json())
goed = aantal == 503
uitslagen.append(goed)
print(f"   {'OK  ' if goed else 'FOUT'}  het universum telt nog 503 symbolen (gevonden: {aantal})")

herberekend = sha256_text(na[0]["canonical_payload"])
goed = herberekend == entry_hash
uitslagen.append(goed)
print(f"   {'OK  ' if goed else 'FOUT'}  het controlegetal klopt nog met de inhoud")

if uitvoeringen:
    r = requests.get(f"{URL}/rest/v1/executions?select=*", headers=koppen(GEHEIM), timeout=30)
    na_uit = r.json()
    goed = (len(na_uit) == len(uitvoeringen) and na_uit[0] == uitvoeringen[0])
    uitslagen.append(goed)
    print(f"   {'OK  ' if goed else 'FOUT'}  de uitvoering van de portefeuille is onveranderd")

    # De keten van uitvoeringen: een doorlopende portefeuille van 1.000 euro
    # staat of valt ermee dat elke wissel aan de vorige hangt en er maar een
    # aan kan hangen.
    ok, bericht = hb.verify_keten(na_uit)
    uitslagen.append(ok)
    print(f"   {'OK  ' if ok else 'FOUT'}  de keten van uitvoeringen klopt")
    print(f"         {bericht}")


print("\n" + "=" * 78)
mislukt = uitslagen.count(False)
if mislukt:
    print(f"LET OP: {mislukt} van de {len(uitslagen)} controles ging mis. Niet verdergaan.")
    sys.exit(1)
print(f"ALLE {len(uitslagen)} CONTROLES GOED.")
print("De vastgelegde forward-test kan niet gewijzigd of gewist worden,")
print("ook niet met de geheime sleutel. Een vervalst signaal komt er niet in,")
print("en de dagelijkse taak kan met haar schrijfteken alleen de koersen van")
print("vandaag toevoegen, van de aandelen die nu in de portefeuille zitten.")
print()
print("Wat deze test NIET kan uitsluiten, en wat je dus elders moet nakijken:")
print("wie eigenaar is van de database kan triggers en functies wijzigen of")
print("uitzetten - ook de functie die hierboven vertelt dat ze aanstaan. Het")
print("controlespoor buiten de database blijft daarom nodig: de openbare")
print("Git-geschiedenis, de hash-keten in forward_log/ en de bestanden in")
print("bewijs/. Wijkt de database daarvan af, dan is de database fout.")
print("=" * 78)
