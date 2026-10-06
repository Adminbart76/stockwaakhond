"""Probeert de forward-test met opzet kapot te maken en controleert dat dat niet lukt.

Dit script valt de eigen database aan met alle middelen die we hebben, de
geheime sleutel inbegrepen. Elke poging hoort te mislukken. Lukt er een wel,
dan is dat een ernstig probleem en moet het meteen opgelost worden.

De vervalste records krijgen met opzet een kloppend controlegetal. Anders
zouden ze allemaal al op de eerste horde stranden en zou je nooit te weten
komen of de beveiligingen daarachter werken.

Twee dingen die hier bewust ingebouwd zijn
==========================================
1. ELK VERVALST SIGNAAL DRAAGT EEN ONECHTE STRATEGIEVERSIE.
   Dat is het vangnet. De database weigert elk signaal waarvan de versie niet
   bij de strategie hoort, en die controle staat als laatste in de rij. Zo
   krijgt elke aanval eerst de kans om op zijn eigen regel te stranden - en als
   die regel er niet zou staan, blijft het vangnet over. Zonder zo'n vangnet
   zou een aanval die een gat vindt een vals signaal in de keten zetten, en
   dat is niet meer weg te halen.

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
from datetime import date, timedelta
from pathlib import Path

import requests

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw.strategy import canonical_json, sha256_text  # noqa: E402
from sw.supabase_io import lees_instellingen         # noqa: E402

cfg = lees_instellingen()
URL = cfg["SUPABASE_URL"].rstrip("/")
GEHEIM = cfg["SUPABASE_SERVICE_KEY"]
LEZEN = cfg.get("SUPABASE_ANON_KEY")
TEKEN = cfg.get("SNAPSHOT_WRITE_TOKEN")

# Zo'n versie bestaat niet in de tabel strategies. Daarom weigert de database
# elk record dat hem draagt, wat er verder ook in staat.
AANVALSVERSIE = "AANVALSTEST_GEEN_ECHTE_VERSIE"

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
    juiste controlegetal van de voorganger, een datum ruim 28 dagen later. Zo
    komt de aanval voorbij alle lagen en wordt de regel die je wilt testen
    werkelijk op de proef gesteld.

    Behalve de strategieversie: die is onecht, en dat is het vangnet.
    """
    payload = {
        "record_type": "signal",
        "schema_version": 1,
        "created_at_utc": "2027-01-04T21:00:00+00:00",
        "signal_market_date": "2027-01-04",
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
        "strategy_version": AANVALSVERSIE,
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
        print(f"   {'OK  ' if waarde else 'NEE '}  {naam}")
else:
    print(f"   FOUT  hardening_status() bestaat nog niet (HTTP {r.status_code})")

ketenregels = bool(stand.get("keten_moet_kloppen"))
uitvoeringsregels = bool(stand.get("velden_moeten_kloppen"))
schrijfdeur = bool(stand.get("schrijfdeur_bestaat"))
teken_gezet = bool(stand.get("schrijfteken_ingesteld"))
uitslagen.append(ketenregels and uitvoeringsregels and schrijfdeur)

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
    print("\n2. HET VANGNET: EEN ONECHTE STRATEGIEVERSIE")
    print("   (werkt dit niet, dan stopt het script hier)")

    vangnet = poging(
        "een verder volkomen geldig signaal met een onechte strategieversie",
        "mislukken",
        lambda: requests.post(
            f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
            data=json.dumps(maak_record(doel)), timeout=30),
        melding_bevat="strategieversie")

    if not vangnet:
        print()
        print("   " + "!" * 70)
        print("   Het vangnet werkt niet zoals verwacht. Er worden geen verdere")
        print("   pogingen gedaan: die zouden een vals signaal kunnen achterlaten.")
        print("   Zoek eerst uit waarom public.controleer_keten() de onechte")
        print("   strategieversie niet weigert.")
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

    te_snel = str(date.fromisoformat(doel["signal_market_date"]) + timedelta(days=14))
    poging("te snel een nieuw signaal (binnen 28 dagen)", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, signal_market_date=te_snel)), timeout=30),
        melding_bevat="Te vroeg")

    poging("een tweede signaal op dezelfde dag", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, signal_market_date=doel["signal_market_date"])),
        timeout=30), melding_bevat="Te vroeg")

    poging("een signaal met een onbekende strategie", "mislukken", lambda: requests.post(
        f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
        data=json.dumps(maak_record(doel, strategy_hash="b" * 64)), timeout=30),
        melding_bevat="strategie")

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

    if TEKEN and teken_gezet:
        poging("een aandeel dat niet in de portefeuille zit", "mislukken",
               lambda: rpc(sleutel, "leg_dagkoersen_vast", {
                   "p_token": TEKEN, "p_datum": "2026-10-06",
                   "p_koersen": [{"ticker": "VERZONNEN", "close_raw": 1.0}]}),
               melding_bevat="hoort niet bij de portefeuille")

        poging("een koers voor een dag die nog moet komen", "mislukken",
               lambda: rpc(sleutel, "leg_dagkoersen_vast", {
                   "p_token": TEKEN, "p_datum": "2030-01-02",
                   "p_koersen": [{"ticker": "SPY", "close_raw": 1.0}]}),
               melding_bevat="bestaat nog geen slotkoers")

        # Een bestaande slotkoers overschrijven: de aanroep mag slagen, maar
        # er mag niets veranderen.
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
            onveranderd = (
                antwoord.status_code == 200
                and str(na.get("close_raw")) == str(rij.get("close_raw"))
            )
            uitslagen.append(onveranderd)
            print(f"   {'OK  ' if onveranderd else 'FOUT'}  een bestaande slotkoers "
                  f"overschrijven verandert niets")
            print(f"         koers blijft {rij.get('close_raw')} "
                  f"(nu: {na.get('close_raw')})")
    else:
        print("   (het schrijfteken zelf is hier niet bekend; die pogingen zijn")
        print("    overgeslagen. Zet SNAPSHOT_WRITE_TOKEN in SLEUTELS_INVULLEN.txt")
        print("    en voer de regel uit die daar bij punt 6 staat.)")


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


print("\n" + "=" * 78)
mislukt = uitslagen.count(False)
if mislukt:
    print(f"LET OP: {mislukt} van de {len(uitslagen)} controles ging mis. Niet verdergaan.")
    sys.exit(1)
print(f"ALLE {len(uitslagen)} CONTROLES GOED.")
print("De vastgelegde forward-test kan niet gewijzigd of gewist worden,")
print("ook niet met de geheime sleutel. Een vervalst signaal komt er niet in,")
print("en de dagelijkse taak kan met haar schrijfteken alleen koersen toevoegen.")
print("=" * 78)
