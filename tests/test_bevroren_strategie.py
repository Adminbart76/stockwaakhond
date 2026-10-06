"""Wachters op de bevroren strategie.

Deze tests bestaan om een heel specifiek soort fout te vangen: iemand (ook ik,
ook later, ook met de beste bedoelingen) die de scoreformule bijstelt nadat de
forward-test al loopt. Dat is precies wat een forward-test waardeloos maakt.

Faalt hier iets, dan is dat geen testprobleem maar een inhoudelijk alarm.
Niet de test aanpassen. De wijziging terugdraaien.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from sw import strategy

PROJECT = Path(__file__).resolve().parent.parent
ORIGINEEL = PROJECT / "bewijs" / "app.py.bevroren-2026-10-06"
LEDGER = PROJECT / "forward_log" / "ledger.jsonl"

# De waarden zoals ze in het allereerste vastgelegde signaal staan.
# Deze getallen horen handmatig overgetypt te zijn, niet uit de code gehaald:
# anders zou een wijziging in de code de test stilletjes meeveranderen.
VERWACHTE_STRATEGIEHASH = "a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18"
VERWACHTE_VERSIE = "SW_SCORE_V3_FROZEN_2026-10-06"
VERWACHTE_GEWICHTEN = {
    "return_12m_percentile": 25,
    "return_6m_percentile": 20,
    "return_3m_percentile": 15,
    "relative_strength_6m_percentile": 15,
    "close_above_ma200": 10,
    "ma50_above_ma200": 5,
    "low_volatility_3m_percentile": 5,
    "low_drawdown_3m_percentile": 5,
}


def test_strategiehash_is_onveranderd():
    """Het hart van alles: wijzigt de formule, dan wijzigt deze hash."""
    assert strategy.STRATEGY_HASH == VERWACHTE_STRATEGIEHASH, (
        "De scoreformule is gewijzigd. Dat mag niet zolang deze forward-test "
        "loopt. Draai de wijziging terug, of begin een nieuwe strategieversie "
        "met een eigen logboek."
    )


def test_strategieversie_is_onveranderd():
    assert strategy.STRATEGY_VERSION == VERWACHTE_VERSIE


def test_de_acht_gewichten_kloppen_stuk_voor_stuk():
    gewichten = strategy.STRATEGY_SPEC["weights"]
    assert gewichten == VERWACHTE_GEWICHTEN
    assert sum(gewichten.values()) == 100, "De gewichten moeten samen 100 zijn."


def test_top_vijf_en_kosten_staan_vast():
    assert strategy.STRATEGY_SPEC["top_n_default"] == 5
    assert strategy.STRATEGY_SPEC["cost_pct_default"] == 0.15
    assert strategy.STRATEGY_SPEC["benchmark"] == "SPY"
    assert strategy.STRATEGY_SPEC["minimum_candidate_coverage_pct"] == 98.0


def test_terugkijkperiodes_staan_vast():
    assert strategy.STRATEGY_SPEC["lookbacks_trading_days"] == {
        "3m": 63, "6m": 126, "12m": 252, "ma50": 50, "ma200": 200,
    }


def test_hash_blijft_hetzelfde_bij_andere_sleutelvolgorde():
    """De hash mag niet afhangen van de volgorde waarin velden toevallig staan."""
    omgekeerd = dict(reversed(list(strategy.STRATEGY_SPEC.items())))
    assert strategy.spec_hash(omgekeerd) == strategy.STRATEGY_HASH


def _spec_uit_originele_app() -> dict:
    """Haalt STRATEGY_SPEC uit de bevroren kopie van de oorspronkelijke app.py.

    Die kopie is nooit aangeraakt. Door de twee te vergelijken bewijzen we dat
    bij het opsplitsen van de code geen enkel cijfer is verschoven.
    """
    bron = ORIGINEEL.read_text(encoding="utf-8")
    boom = ast.parse(bron)

    namen = {}
    for knoop in boom.body:
        if not isinstance(knoop, ast.Assign):
            continue
        doel = knoop.targets[0]
        if not isinstance(doel, ast.Name):
            continue
        if doel.id == "STRATEGY_VERSION":
            namen["STRATEGY_VERSION"] = ast.literal_eval(knoop.value)
        elif doel.id == "STRATEGY_SPEC":
            # Vervang de verwijzing naar STRATEGY_VERSION door de waarde zelf,
            # zodat de rest een zuivere letterlijke waarde is.
            vervangen = ast.parse(
                ast.unparse(knoop.value).replace(
                    "STRATEGY_VERSION", repr(namen["STRATEGY_VERSION"])
                ),
                mode="eval",
            )
            return ast.literal_eval(vervangen)
    raise AssertionError("STRATEGY_SPEC niet gevonden in de bevroren app.py")


def test_spec_is_identiek_aan_de_oorspronkelijke_app():
    """Bij het opsplitsen van app.py mag er niets veranderd zijn."""
    assert ORIGINEEL.exists(), "De bevroren kopie van app.py ontbreekt in bewijs/."
    origineel = _spec_uit_originele_app()
    assert origineel == strategy.STRATEGY_SPEC, (
        "De formule in sw/strategy.py wijkt af van de oorspronkelijke app.py."
    )


def test_hash_van_originele_app_komt_overeen():
    origineel = _spec_uit_originele_app()
    tekst = json.dumps(origineel, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(tekst.encode("utf-8")).hexdigest() == VERWACHTE_STRATEGIEHASH


@pytest.mark.skipif(not LEDGER.exists(), reason="nog geen logboek")
def test_elk_vastgelegd_signaal_draagt_dezelfde_strategie():
    """De formule in de code hoort nog bij wat er in het logboek staat."""
    regels = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    for i, regel in enumerate(regels, 1):
        assert regel["strategy_hash"] == VERWACHTE_STRATEGIEHASH, (
            f"Regel {i} hoort bij een andere strategie dan de bevroren formule."
        )
        assert strategy.spec_hash(regel["formula_spec"]) == regel["strategy_hash"], (
            f"Regel {i}: de opgeslagen formule past niet bij de opgeslagen hash."
        )
