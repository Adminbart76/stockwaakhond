"""Wachters op het forward-logboek zelf.

Controleert dat de hash-keten klopt, dat het bestaande signaal onveranderd is,
en - net zo belangrijk - dat er nergens code bijkomt waarmee een oud signaal
gewijzigd of verwijderd kan worden.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sw import ledger, strategy

PROJECT = Path(__file__).resolve().parent.parent
LEDGER = PROJECT / "forward_log" / "ledger.jsonl"
BEWIJS = PROJECT / "bewijs" / "ledger.jsonl"

EERSTE_ENTRY_HASH = "0426e47ccd6e0b4f7fcecd772ce21dc5778db862e359f5eb4d239f5ce8bd5d15"
EERSTE_UNIVERSE_HASH = "3114cc28ea6cb1aa0b1025f7ee01fffa9c697244cf64ca20cf013a1c8f9e813b"
EERSTE_TOP5 = ["MRNA", "ILMN", "MPC", "HPE", "VLO"]


@pytest.fixture
def regels():
    assert LEDGER.exists(), "Het forward-logboek ontbreekt."
    return ledger.read_ledger(LEDGER)


def test_de_keten_is_intact(regels):
    ok, bericht = ledger.verify_ledger(regels)
    assert ok, bericht


def test_eerste_regel_begint_bij_genesis(regels):
    assert regels[0]["previous_hash"] == "GENESIS"


def test_het_eerste_signaal_is_onveranderd(regels):
    eerste = regels[0]
    assert eerste["entry_hash"] == EERSTE_ENTRY_HASH
    assert eerste["signal_market_date"] == "2026-10-05"
    assert eerste["universe_hash"] == EERSTE_UNIVERSE_HASH
    assert [s["ticker"] for s in eerste["selected"]] == EERSTE_TOP5


def test_signalen_staan_op_datum_en_zijn_uniek(regels):
    signalen = [e for e in regels if e.get("record_type") == "signal"]
    datums = [e["signal_market_date"] for e in signalen]
    assert datums == sorted(datums), "Signalen staan niet op volgorde van datum."
    assert len(datums) == len(set(datums)), "Twee signalen op dezelfde datum."


def test_elk_signaal_houdt_zich_aan_de_eigen_regels(regels):
    for i, e in enumerate([x for x in regels if x.get("record_type") == "signal"], 1):
        gekozen = e["selected"]
        assert len(gekozen) == e["formula_spec"]["top_n_default"], f"Regel {i}: geen Top-5."
        assert [s["rank"] for s in gekozen] == list(range(1, len(gekozen) + 1))
        assert len({s["ticker"] for s in gekozen}) == len(gekozen), f"Regel {i}: dubbel aandeel."

        scores = [s["score"] for s in gekozen]
        assert scores == sorted(scores, reverse=True), f"Regel {i}: scores niet aflopend."

        # Bij een gelijke stand hoort alfabetisch gekozen te zijn, nooit willekeurig.
        for a, b in zip(gekozen, gekozen[1:]):
            if a["score"] == b["score"]:
                assert a["ticker"] < b["ticker"], (
                    f"Regel {i}: gelijke score maar niet alfabetisch ({a['ticker']}, {b['ticker']})."
                )

        assert e["coverage_pct"] >= e["formula_spec"]["minimum_candidate_coverage_pct"]
        assert all(s["signal_close"] > 0 for s in gekozen)
        assert e["spy_signal_close"] > 0


def test_dekking_klopt_met_de_aantallen(regels):
    for e in regels:
        verwacht = round(100.0 * e["eligible_count"] / e["universe_count"], 6)
        assert abs(verwacht - e["coverage_pct"]) < 1e-6


def test_de_kopie_in_bewijs_is_identiek_aan_het_origineel():
    assert BEWIJS.exists(), "De veiligheidskopie in bewijs/ ontbreekt."
    assert BEWIJS.read_bytes() == LEDGER.read_bytes(), (
        "De kopie in bewijs/ wijkt af van het werkende logboek. Uitzoeken welke "
        "van de twee gewijzigd is voor je verdergaat."
    )


def test_een_gewijzigd_record_wordt_opgemerkt(regels):
    """Omgekeerde proef: de controle moet ook echt iets vangen."""
    geknoeid = json.loads(json.dumps(regels[0]))
    geknoeid["selected"][0]["score"] = 99.9
    ok, bericht = ledger.verify_ledger([geknoeid])
    assert not ok and "gewijzigd" in bericht


def test_een_losgekoppelde_keten_wordt_opgemerkt(regels):
    geknoeid = json.loads(json.dumps(regels[0]))
    geknoeid["previous_hash"] = "iets anders"
    ok, _ = ledger.verify_ledger([geknoeid])
    assert not ok


def test_een_vervalste_formule_wordt_opgemerkt(regels):
    """Formule stiekem aanpassen en de hash meeveranderen mag niet lukken."""
    geknoeid = json.loads(json.dumps(regels[0]))
    geknoeid["formula_spec"]["weights"]["return_12m_percentile"] = 30
    payload = {k: v for k, v in geknoeid.items() if k != "entry_hash"}
    geknoeid["entry_hash"] = strategy.sha256_text(strategy.canonical_json(payload))
    ok, bericht = ledger.verify_ledger([geknoeid])
    assert not ok, "Een aangepaste formule met kloppende entry_hash glipt er doorheen."
    assert "formule" in bericht


def test_er_bestaat_geen_manier_om_iets_te_wissen():
    """Niemand mag ooit een functie toevoegen die een signaal verwijdert of wijzigt."""
    bron = (PROJECT / "sw" / "ledger.py").read_text(encoding="utf-8")
    verboden = [
        "def delete", "def remove", "def update_entry", "def edit",
        "def rewrite", "def overwrite", "def recalculate_entry", "def wijzig",
        "def verwijder",
    ]
    gevonden = [v for v in verboden if v in bron]
    assert not gevonden, f"Verboden bewerking gevonden in sw/ledger.py: {gevonden}"

    # Het logboek mag alleen bijschrijvend geopend worden, nooit overschrijvend.
    assert 'open("w"' not in bron and "'w'" not in bron.replace("newline", ""), (
        "sw/ledger.py opent het logboek ergens overschrijvend in plaats van bijschrijvend."
    )
