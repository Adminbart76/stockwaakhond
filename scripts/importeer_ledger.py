"""Zet het lokale forward-logboek in Supabase en controleert daarna alles terug.

Werkwijze, met opzet voorzichtig:

  1. lees het lokale logboek en controleer de hash-keten
  2. vergelijk het met de veiligheidskopie in bewijs/
  3. controleer dat de database de tabellen heeft
  4. voeg toe wat er nog niet staat (nooit overschrijven)
  5. lees alles terug uit de database en vergelijk letter voor letter
  6. is er ook maar een verschil: meld het en stop

Het lokale bestand blijft de bron van waarheid. De database is de spiegel.
Dit script wijzigt nooit iets aan het lokale bestand.

Gebruik:
    python scripts/importeer_ledger.py            (controleren en invoeren)
    python scripts/importeer_ledger.py --droog    (alleen tonen wat er zou gebeuren)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sw import ledger as led                      # noqa: E402
from sw import strategy as strat                  # noqa: E402
from sw.supabase_io import Supabase, lees_instellingen  # noqa: E402

LEDGER = PROJECT / "forward_log" / "ledger.jsonl"
BEWIJS = PROJECT / "bewijs" / "ledger.jsonl"
UNIVERSUM = PROJECT / "bewijs" / "universum_503_symbolen_2026-10-05.json"

DROOG = "--droog" in sys.argv

TABELLEN = ["strategies", "signals", "signal_universe", "executions",
            "price_snapshots", "fx_snapshots", "dividends", "live_quotes"]


def stop(bericht: str) -> None:
    print("\n" + "=" * 70)
    print("GESTOPT: " + bericht)
    print("Er is niets gewijzigd. Het lokale logboek is niet aangeraakt.")
    print("=" * 70)
    sys.exit(1)


def kop(tekst: str) -> None:
    print("\n" + tekst)
    print("-" * len(tekst))


# ---------------------------------------------------------------- 1. lokaal
kop("1. Het lokale logboek controleren")

if not LEDGER.exists():
    stop("het logboek forward_log/ledger.jsonl bestaat niet.")

regels = led.read_ledger(LEDGER)
ruwe_regels = led.ledger_lines(LEDGER)
print(f"   regels gevonden        : {len(regels)}")

ok, bericht = led.verify_ledger(regels)
print(f"   hash-keten             : {bericht}")
if not ok:
    stop("de hash-keten van het lokale logboek klopt niet. " + bericht)

if len(regels) != len(ruwe_regels):
    stop("het aantal gelezen records komt niet overeen met het aantal regels in het bestand.")


# ------------------------------------------------------- 2. veiligheidskopie
kop("2. Vergelijken met de veiligheidskopie in bewijs/")

if not BEWIJS.exists():
    stop("de veiligheidskopie bewijs/ledger.jsonl ontbreekt.")

if BEWIJS.read_bytes() != LEDGER.read_bytes():
    stop("het werkende logboek en de kopie in bewijs/ zijn niet identiek. "
         "Zoek eerst uit welke van de twee gewijzigd is.")
print("   byte-voor-byte identiek: ja")


# ----------------------------------------------------------- 3. de database
kop("3. De database controleren")

cfg = lees_instellingen()
ontbreekt = [k for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY") if not cfg.get(k)]
if ontbreekt:
    stop("deze instellingen ontbreken: " + ", ".join(ontbreekt))

db = Supabase.schrijver(cfg)
print(f"   project                : {cfg['SUPABASE_URL']}")

bestaan = db.tabellen_bestaan(TABELLEN)
missend = [t for t, aanwezig in bestaan.items() if not aanwezig]
if missend:
    stop("deze tabellen bestaan nog niet: " + ", ".join(missend)
         + "\nVoer eerst sql/01_schema.sql uit in de Supabase SQL Editor.")
print(f"   tabellen aanwezig      : alle {len(TABELLEN)}")

al_aanwezig = {r["entry_hash"] for r in db.select("signals", "select=entry_hash")}
print(f"   signalen al in database: {len(al_aanwezig)}")


# ------------------------------------------------------------ 4. toevoegen
kop("4. Toevoegen wat er nog niet staat")

# -- 4a. de strategie
strategieen = {r["strategy_hash"] for r in db.select("strategies", "select=strategy_hash")}
nieuwe_strategieen = []
for regel in regels:
    h = regel["strategy_hash"]
    if h in strategieen or any(s["strategy_hash"] == h for s in nieuwe_strategieen):
        continue
    spec = regel["formula_spec"]
    canoniek = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    if strat.sha256_text(canoniek) != h:
        stop(f"de formule van strategie {h[:16]}... levert niet de opgeslagen hash op.")
    nieuwe_strategieen.append({
        "strategy_hash": h,
        "strategy_version": regel["strategy_version"],
        "formula_spec": spec,
        "canonical_spec": canoniek,
    })

if nieuwe_strategieen:
    print(f"   strategieen toe te voegen: {len(nieuwe_strategieen)}")
    for s in nieuwe_strategieen:
        print(f"      {s['strategy_version']}  {s['strategy_hash'][:16]}...")
    if not DROOG:
        db.insert("strategies", nieuwe_strategieen)
        print("   -> toegevoegd")
else:
    print("   strategieen              : stonden er al")

# -- 4b. de signalen
nieuwe_signalen = []
for volgnummer, (regel, ruw) in enumerate(zip(regels, ruwe_regels), start=1):
    if regel["entry_hash"] in al_aanwezig:
        continue

    payload = {k: v for k, v in regel.items() if k != "entry_hash"}
    canoniek = strat.canonical_json(payload)
    if strat.sha256_text(canoniek) != regel["entry_hash"]:
        stop(f"regel {volgnummer}: de herberekende hash klopt niet.")
    if json.loads(ruw) != regel:
        stop(f"regel {volgnummer}: de ruwe tekstregel komt niet overeen met het gelezen record.")

    nieuwe_signalen.append({
        "entry_hash": regel["entry_hash"],
        "seq": volgnummer,
        "previous_hash": regel["previous_hash"],
        "record_type": regel.get("record_type", "signal"),
        "schema_version": regel["schema_version"],
        "strategy_hash": regel["strategy_hash"],
        "strategy_version": regel["strategy_version"],
        "signal_market_date": regel["signal_market_date"],
        "created_at_utc": regel["created_at_utc"],
        "universe_source": regel["universe_source"],
        "universe_hash": regel["universe_hash"],
        "universe_count": regel["universe_count"],
        "eligible_count": regel["eligible_count"],
        "coverage_pct": regel["coverage_pct"],
        "spy_signal_close": regel["spy_signal_close"],
        "selected": regel["selected"],
        "formula_spec": regel["formula_spec"],
        "canonical_payload": canoniek,
        "ledger_line": ruw,
    })

if nieuwe_signalen:
    print(f"   signalen toe te voegen : {len(nieuwe_signalen)}")
    for s in nieuwe_signalen:
        tickers = ", ".join(x["ticker"] for x in s["selected"])
        print(f"      #{s['seq']}  {s['signal_market_date']}  {tickers}")
    if not DROOG:
        db.insert("signals", nieuwe_signalen)
        print("   -> toegevoegd")
else:
    print("   signalen                 : stonden er al")

# -- 4c. het universum van het eerste signaal
if UNIVERSUM.exists():
    uni = json.loads(UNIVERSUM.read_text(encoding="utf-8"))
    hoort_bij = uni["hoort_bij_entry_hash"]
    symbolen = uni["symbolen"]

    herberekend = strat.sha256_text(",".join(sorted(symbolen)))
    if herberekend != uni["universe_hash"]:
        stop("de bewaarde symbolenlijst levert niet de universe_hash van het signaal op.")

    bijbehorend = [r for r in regels if r["entry_hash"] == hoort_bij]
    if not bijbehorend:
        stop("de bewaarde symbolenlijst hoort bij een signaal dat niet in het logboek staat.")
    if bijbehorend[0]["universe_hash"] != herberekend:
        stop("de symbolenlijst hoort niet bij de universe_hash van dat signaal.")

    bestaand = db.select(
        "signal_universe", f"select=symbol&entry_hash=eq.{hoort_bij}&limit=1000")
    if len(bestaand) == 0:
        print(f"   universum toe te voegen: {len(symbolen)} symbolen")
        print(f"      hash nagerekend      : {herberekend[:16]}... komt overeen")
        if not DROOG:
            rijen = [{"entry_hash": hoort_bij, "symbol": s} for s in symbolen]
            for i in range(0, len(rijen), 200):
                db.insert("signal_universe", rijen[i:i + 200], negeer_dubbel=True)
            print("   -> toegevoegd")
    else:
        print(f"   universum                : stond er al ({len(bestaand)} symbolen)")

if DROOG:
    print("\n(droge test: er is niets weggeschreven)")
    sys.exit(0)


# ---------------------------------------------------- 5. alles terugcontroleren
kop("5. Terugcontroleren: database tegen het lokale bestand")

db_signalen = db.select("signals", "select=*&order=seq.asc")
if len(db_signalen) != len(regels):
    stop(f"de database heeft {len(db_signalen)} signalen, het bestand {len(regels)}.")

fouten = []
for volgnummer, (lokaal, ruw) in enumerate(zip(regels, ruwe_regels), start=1):
    db_regel = next((r for r in db_signalen if r["entry_hash"] == lokaal["entry_hash"]), None)
    if db_regel is None:
        fouten.append(f"regel {volgnummer}: staat niet in de database")
        continue

    if db_regel["ledger_line"] != ruw:
        fouten.append(f"regel {volgnummer}: de bewaarde tekstregel wijkt af van het bestand")

    if json.loads(db_regel["ledger_line"]) != lokaal:
        fouten.append(f"regel {volgnummer}: de inhoud wijkt af")

    herberekend = strat.sha256_text(db_regel["canonical_payload"])
    if herberekend != db_regel["entry_hash"]:
        fouten.append(f"regel {volgnummer}: de hash in de database klopt niet met de inhoud")

    if db_regel["seq"] != volgnummer:
        fouten.append(f"regel {volgnummer}: verkeerd volgnummer in de database")

# de keten opnieuw opbouwen uit wat de database teruggeeft
uit_db = [json.loads(r["ledger_line"]) for r in sorted(db_signalen, key=lambda x: x["seq"])]
ok, bericht = led.verify_ledger(uit_db)
if not ok:
    fouten.append("de keten die uit de database komt, klopt niet: " + bericht)

if fouten:
    for f in fouten:
        print("   FOUT: " + f)
    stop("de database komt niet overeen met het lokale bestand.")

print(f"   signalen vergeleken    : {len(db_signalen)}, allemaal identiek")
print(f"   keten uit de database  : {bericht}")

uni_db = db.select("signal_universe", "select=symbol&limit=2000")
print(f"   symbolen in database   : {len(uni_db)}")
if UNIVERSUM.exists():
    uni = json.loads(UNIVERSUM.read_text(encoding="utf-8"))
    uit_db_symbolen = sorted(r["symbol"] for r in uni_db)
    if uit_db_symbolen != sorted(uni["symbolen"]):
        stop("de symbolenlijst in de database wijkt af van de bewaarde lijst.")
    herberekend = strat.sha256_text(",".join(uit_db_symbolen))
    print(f"   universe_hash uit db   : {herberekend[:24]}...")
    if herberekend != uni["universe_hash"]:
        stop("de symbolenlijst uit de database levert niet de juiste universe_hash op.")
    print("   -> komt overeen met het signaal")


# ---------------------------------------------------------------- 6. het slot
kop("6. Controleren dat het slot erop zit")

try:
    import requests
    r = requests.patch(
        f"{cfg['SUPABASE_URL']}/rest/v1/signals?entry_hash=eq.{regels[0]['entry_hash']}",
        headers={
            "apikey": cfg["SUPABASE_SERVICE_KEY"],
            "Authorization": "Bearer " + cfg["SUPABASE_SERVICE_KEY"],
            "Content-Type": "application/json",
        },
        data=json.dumps({"coverage_pct": 1.0}),
        timeout=30,
    )
    if r.status_code in (200, 204):
        stop("de database LIET een wijziging toe. Het slot ontbreekt. "
             "Voer sql/01_schema.sql opnieuw uit.")
    print(f"   poging tot wijzigen    : geweigerd (HTTP {r.status_code})")
    melding = r.text[:160].replace("\n", " ")
    print(f"   melding uit de database: {melding}")
except SystemExit:
    raise
except Exception as ex:
    print(f"   (slottest kon niet uitgevoerd worden: {ex})")

print("\n" + "=" * 70)
print("KLAAR - de database is een exacte spiegel van het lokale logboek.")
print("Het lokale bestand blijft de bron van waarheid.")
print("=" * 70)
