"""Wachter op de signaaldatum: een lopende beursdag mag nooit meetellen.

Het gevaar in een getal
=======================
Yahoo levert tijdens de handelsdag al een rij voor vandaag. Die koers verandert
die dag nog. Zou een signaal daarop berekend worden, dan staat er in het
logboek een keuze die gemaakt is op cijfers die een paar uur later anders waren
- en dan bewijst het logboek niets meer.

Deze tests bouwen zelf een koersreeks op, zonder internet, en geven het moment
mee waarop er gescoord wordt. De scoreformule zelf blijft onaangeroerd: dat
wordt elders bewaakt door tests/test_bevroren_strategie.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from sw import strategy


def utc(tekst: str) -> datetime:
    return datetime.fromisoformat(tekst).astimezone(timezone.utc)


TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
UNIVERSUM = TICKERS


@pytest.fixture
def koersen() -> pd.DataFrame:
    """Driehonderd beursdagen die eindigen op dinsdag 6 oktober 2026.

    Vaste getallen, geen toeval: dezelfde invoer moet altijd dezelfde Top-5
    geven, anders bewijst een test niets.
    """
    dagen = pd.bdate_range(end="2026-10-06", periods=300)
    kolommen = {}
    for i, t in enumerate(TICKERS + ["SPY"]):
        groei = 1.0 + (i + 1) / 4000.0
        golf = np.sin(np.arange(len(dagen)) / 9.0) * (i + 1) / 100.0
        kolommen[t] = 100.0 * (groei ** np.arange(len(dagen))) * (1.0 + golf)
    return pd.DataFrame(kolommen, index=dagen)


def test_tijdens_de_handelsdag_wordt_gisteren_de_signaaldag(koersen):
    _, signaaldatum, _ = strategy.build_score_table(
        koersen, UNIVERSUM, nu=utc("2026-10-06T18:00:00+00:00"))
    assert signaaldatum == pd.Timestamp("2026-10-05")


def test_na_de_slotbel_wordt_vandaag_de_signaaldag(koersen):
    _, signaaldatum, _ = strategy.build_score_table(
        koersen, UNIVERSUM, nu=utc("2026-10-06T20:30:00+00:00"))
    assert signaaldatum == pd.Timestamp("2026-10-06")


def test_een_voorlopige_dagkoers_kan_de_top_vijf_niet_veranderen(koersen):
    """De proef op de som, met een dagrij die de uitslag zou omgooien.

    AAA krijgt op de lopende dag een sprong van vijftig procent. Zou die rij
    meegeteld worden, dan stond AAA bovenaan. Dat mag niet gebeuren zolang de
    beurs van die dag niet gesloten is.
    """
    zonder_vandaag = koersen.iloc[:-1]
    met_voorlopige_dag = koersen.copy()
    met_voorlopige_dag.loc[met_voorlopige_dag.index[-1], "AAA"] *= 1.5

    tabel_a, datum_a, dekking_a = strategy.build_score_table(
        zonder_vandaag, UNIVERSUM, nu=utc("2026-10-06T18:00:00+00:00"))
    tabel_b, datum_b, dekking_b = strategy.build_score_table(
        met_voorlopige_dag, UNIVERSUM, nu=utc("2026-10-06T18:00:00+00:00"))

    assert datum_a == datum_b == pd.Timestamp("2026-10-05")
    assert list(tabel_a["Ticker"]) == list(tabel_b["Ticker"])
    assert dekking_a == dekking_b
    assert tabel_a["Score"].tolist() == tabel_b["Score"].tolist()


def test_na_de_slotbel_telt_diezelfde_dagkoers_wel_mee(koersen):
    """Omgekeerde proef: de wachter houdt niets tegen wat wel mag meetellen."""
    met_sprong = koersen.copy()
    met_sprong.loc[met_sprong.index[-1], "AAA"] *= 1.5

    tabel, datum, _ = strategy.build_score_table(
        met_sprong, UNIVERSUM, nu=utc("2026-10-06T20:30:00+00:00"))

    assert datum == pd.Timestamp("2026-10-06")
    assert tabel["Ticker"].iloc[0] == "AAA"


def test_zonder_een_enkele_voltooide_dag_wordt_er_niet_gescoord(koersen):
    """Alle dagen liggen in de toekomst: dan hoort er geen signaal te komen."""
    with pytest.raises(ValueError, match="voltooide beursdag"):
        strategy.build_score_table(
            koersen, UNIVERSUM, nu=utc("2024-01-02T20:30:00+00:00"))


def test_de_wachter_raakt_de_formule_niet(koersen):
    """De gewichten en de strategiehash blijven exact wat ze waren."""
    assert strategy.STRATEGY_HASH == strategy.GENESIS_STRATEGY_HASH
    tabel, _, _ = strategy.build_score_table(
        koersen, UNIVERSUM, nu=utc("2026-10-06T20:30:00+00:00"))
    assert tabel["Score"].max() <= 100.0
    assert tabel["Score"].min() >= 0.0
