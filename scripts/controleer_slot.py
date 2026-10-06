"""Probeert de forward-test met opzet kapot te maken en controleert dat dat niet lukt.

Dit script valt de eigen database aan met alle middelen die we hebben, de
geheime sleutel inbegrepen. Elke poging hoort te mislukken. Lukt er een wel,
dan is dat een ernstig probleem en moet het meteen opgelost worden.

De vervalste records krijgen met opzet een kloppend controlegetal. Anders
zouden ze allemaal al op de eerste horde stranden en zou je nooit te weten
komen of de beveiligingen daarachter werken.

Draai dit na elke wijziging aan sql/01_schema.sql.

Gebruik:
    python scripts/controleer_slot.py
"""

from __future__ import annotations

import json
import sys
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

uitslagen = []


def koppen(sleutel: str) -> dict:
    return {
        "apikey": sleutel,
        "Authorization": "Bearer " + sleutel,
        "Content-Type": "application/json",
    }


def poging(omschrijving: str, hoort_te: str, functie) -> None:
    try:
        r = functie()
        gelukt = r.status_code in (200, 201, 204)
        code = str(r.status_code)
        melding = ""
        if not gelukt:
            try:
                j = r.json()
                melding = (j.get("message") or j.get("details") or "")[:78]
            except Exception:
                melding = r.text[:78]
    except Exception as ex:
        gelukt = False
        code = type(ex).__name__
        melding = str(ex)[:78]

    goed = (gelukt and hoort_te == "lukken") or (not gelukt and hoort_te == "mislukken")
    uitslagen.append(goed)
    print(f"   {'OK  ' if goed else 'FOUT'}  {omschrijving}")
    print(f"         hoort te {hoort_te}  ->  HTTP {code}  {melding}")


def maak_record(echt: dict, **afwijkingen) -> dict:
    """Bouwt een volledig geldig signaalrecord met kloppend controlegetal.

    Zo komt de aanval voorbij de hashcontrole en wordt de beveiliging
    erachter werkelijk op de proef gesteld.
    """
    payload = {
        "record_type": "signal",
        "schema_version": 1,
        "created_at_utc": "2027-01-04T12:00:00+00:00",
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
        "strategy_version": echt["strategy_version"],
    }
    payload.update({k: v for k, v in afwijkingen.items() if k in payload})

    canoniek = canonical_json(payload)
    entry_hash = sha256_text(canoniek)
    volledig = dict(payload)
    volledig["entry_hash"] = entry_hash

    rij = dict(payload)
    rij["entry_hash"] = entry_hash
    rij["seq"] = afwijkingen.get("seq", 999)
    rij["canonical_payload"] = canoniek
    rij["ledger_line"] = canonical_json(volledig)

    # afwijkingen die alleen de kolom raken en niet de gehashte inhoud
    for k, v in afwijkingen.items():
        if k.startswith("kolom_"):
            rij[k[len("kolom_"):]] = v
    return rij


r = requests.get(f"{URL}/rest/v1/signals?select=*&order=seq.asc",
                 headers=koppen(GEHEIM), timeout=30)
r.raise_for_status()
signalen = r.json()
if not signalen:
    print("Er staat nog geen signaal in de database. Importeer eerst.")
    sys.exit(1)
doel = signalen[0]
entry_hash = doel["entry_hash"]

print("AANVALSTEST OP DE FORWARD-TEST")
print("=" * 78)
print(f"project : {URL}")
print(f"doelwit : signaal {doel['signal_market_date']} ({entry_hash[:16]}...)")

print("\n1. WIJZIGEN EN WISSEN MET DE GEHEIME SLEUTEL")
print("   (die sleutel omzeilt alle gewone beveiliging van Supabase)")

poging("een score in het signaal wijzigen", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/signals?entry_hash=eq.{entry_hash}",
    headers=koppen(GEHEIM), data=json.dumps({"coverage_pct": 1.0}), timeout=30))

poging("het signaal verwijderen", "mislukken", lambda: requests.delete(
    f"{URL}/rest/v1/signals?entry_hash=eq.{entry_hash}",
    headers=koppen(GEHEIM), timeout=30))

poging("alle signalen in een keer wissen", "mislukken", lambda: requests.delete(
    f"{URL}/rest/v1/signals?seq=gte.0", headers=koppen(GEHEIM), timeout=30))

poging("de strategie herschrijven", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/strategies?strategy_hash=eq.{doel['strategy_hash']}",
    headers=koppen(GEHEIM),
    data=json.dumps({"strategy_version": "stiekem gewijzigd"}), timeout=30))

poging("een symbool uit het universum halen", "mislukken", lambda: requests.delete(
    f"{URL}/rest/v1/signal_universe?entry_hash=eq.{entry_hash}&symbol=eq.MRNA",
    headers=koppen(GEHEIM), timeout=30))

poging("de uitvoering van de portefeuille wijzigen", "mislukken", lambda: requests.patch(
    f"{URL}/rest/v1/executions?entry_hash=eq.{entry_hash}",
    headers=koppen(GEHEIM), data=json.dumps({"fx_rate": 1.0}), timeout=30))

print("\n2. EEN VERVALST RECORD BINNENSMOKKELEN")
print("   (elk met een kloppend controlegetal, zodat de lagen erachter getest worden)")

poging("verkeerd controlegetal", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps({**maak_record(doel), "entry_hash": "0" * 64}), timeout=30))

poging("een tweede keten naast de echte beginnen", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, previous_hash=doel["previous_hash"])), timeout=30))

poging("een tweede signaal op dezelfde dag", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, signal_market_date=doel["signal_market_date"])),
    timeout=30))

poging("het bestaande volgnummer overnemen", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, seq=1)), timeout=30))

poging("een signaal met een onbekende strategie", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, strategy_hash="b" * 64)), timeout=30))

poging("kolom zegt iets anders dan de gehashte inhoud", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, kolom_coverage_pct=42.0)), timeout=30))

poging("gehashte Top-5 vervangen in de kolom", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, kolom_selected=[
        {"rank": 1, "ticker": "WINNAAR", "score": 100.0, "signal_close": 1.0}])), timeout=30))

poging("logboekregel die niet bij de inhoud hoort", "mislukken", lambda: requests.post(
    f"{URL}/rest/v1/signals", headers=koppen(GEHEIM),
    data=json.dumps(maak_record(doel, kolom_ledger_line='{"verzonnen":true}')), timeout=30))

if LEZEN:
    print("\n3. MET DE LEESSLEUTEL (die in de webapp van het dashboard staat)")

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

print("\n4. IS ER ECHT NIETS VERANDERD?")

r = requests.get(f"{URL}/rest/v1/signals?select=*&order=seq.asc",
                 headers=koppen(GEHEIM), timeout=30)
na = r.json()
onveranderd = (len(na) == len(signalen) and na[0] == doel)
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

print("\n" + "=" * 78)
mislukt = uitslagen.count(False)
if mislukt:
    print(f"LET OP: {mislukt} van de {len(uitslagen)} controles ging mis. Niet verdergaan.")
    sys.exit(1)
print(f"ALLE {len(uitslagen)} CONTROLES GOED.")
print("De vastgelegde forward-test kan niet gewijzigd of gewist worden,")
print("ook niet met de geheime sleutel.")
print("=" * 78)
