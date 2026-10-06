"""Wachters op de rekenkunde van de virtuele portefeuille.

Hier gaat het om geld, wisselkoersen en percentages. Dat is precies het soort
rekenwerk waar stille fouten in sluipen die pas maanden later opvallen. Deze
tests controleren de randgevallen die er echt toe doen, met de getallen van het
eerste signaal.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sw import portfolio as pf

KOERSEN = {"MRNA": 203.21, "ILMN": 293.69, "MPC": 433.47, "HPE": 68.36, "VLO": 419.33}
TICKERS = list(KOERSEN)
SPY = 774.83
FX = 1.1266


@pytest.fixture
def instap():
    return pf.bereken_instap(
        entry_hash="test",
        execution_date="2026-10-06",
        tickers=TICKERS,
        koersen_usd=KOERSEN,
        fx_eurusd=FX,
        spy_koers_usd=SPY,
        fx_source="test",
        fx_asof="2026-10-06T20:00:00+00:00",
    )


def test_kosten_worden_vooraf_afgetrokken(instap):
    assert instap["start_capital_eur"] == 1000.0
    assert instap["cost_eur"] == pytest.approx(1.50, abs=1e-6)
    assert instap["invested_eur"] == pytest.approx(998.50, abs=1e-6)


def test_de_vijf_posities_zijn_gelijk_verdeeld(instap):
    posities = instap["positions"]
    assert len(posities) == 5
    for p in posities:
        assert p["invested_eur"] == pytest.approx(998.50 / 5, abs=1e-6)
        assert p["target_weight"] == pytest.approx(0.2, abs=1e-9)


def test_de_inzetten_tellen_op_tot_het_belegde_bedrag(instap):
    totaal = sum(p["invested_eur"] for p in instap["positions"])
    assert totaal == pytest.approx(instap["invested_eur"], abs=1e-6)


def test_aandelen_maal_aankoopkoers_geeft_het_ingelegde_bedrag(instap):
    for p in instap["positions"]:
        assert p["shares"] * p["buy_price_usd"] == pytest.approx(p["invested_usd"], rel=1e-9)


def test_fracties_zijn_echt_nodig(instap):
    """Zonder fracties kan 1.000 euro niet gelijk over deze vijf verdeeld worden."""
    kleiner_dan_een = [p["ticker"] for p in instap["positions"] if p["shares"] < 1]
    assert set(kleiner_dan_een) == {"ILMN", "MPC", "VLO"}


def test_de_benchmark_krijgt_dezelfde_behandeling(instap):
    bm = instap["benchmark"]
    assert bm["invested_eur"] == pytest.approx(instap["invested_eur"], abs=1e-6)
    assert bm["shares"] * bm["buy_price_usd"] == pytest.approx(bm["invested_usd"], rel=1e-9)


def test_zonder_koersbeweging_is_het_resultaat_alleen_de_kosten(instap):
    """Niets beweegt: dan sta je precies de transactiekost in het rood."""
    w = pf.waardeer(instap, KOERSEN, FX, "2026-10-06", spy_koers_usd=SPY)
    assert w.totaal_eur == pytest.approx(998.50, abs=0.01)
    assert w.resultaat_eur == pytest.approx(-1.50, abs=0.01)
    assert w.spy_waarde_eur == pytest.approx(998.50, abs=0.01)
    assert w.voorsprong_pct == pytest.approx(0.0, abs=1e-6)


def test_tien_procent_koersstijging_komt_volledig_door(instap):
    hoger = {t: k * 1.10 for t, k in KOERSEN.items()}
    w = pf.waardeer(instap, hoger, FX, "2026-11-06", spy_koers_usd=SPY)
    assert w.totaal_eur == pytest.approx(998.50 * 1.10, abs=0.01)
    for p in w.posities:
        assert p["koersrendement_pct"] == pytest.approx(10.0, abs=1e-6)


def test_een_sterkere_dollar_verhoogt_de_waarde_in_euro(instap):
    """Koersen onveranderd, dollar sterker: dan wordt de portefeuille meer waard."""
    w = pf.waardeer(instap, KOERSEN, 1.05, "2026-11-06", spy_koers_usd=SPY)
    verwacht = 998.50 * (FX / 1.05)
    assert w.totaal_eur == pytest.approx(verwacht, abs=0.01)
    assert w.resultaat_eur > 0


def test_een_zwakkere_dollar_verlaagt_de_waarde_in_euro(instap):
    w = pf.waardeer(instap, KOERSEN, 1.25, "2026-11-06", spy_koers_usd=SPY)
    assert w.totaal_eur == pytest.approx(998.50 * (FX / 1.25), abs=0.01)
    assert w.resultaat_eur < 0


def test_valuta_telt_precies_een_keer_mee(instap):
    """Koers en wisselkoers bewegen allebei: het effect mag niet dubbel tellen."""
    hoger = {t: k * 1.20 for t, k in KOERSEN.items()}
    nieuwe_fx = 1.05
    w = pf.waardeer(instap, hoger, nieuwe_fx, "2026-11-06", spy_koers_usd=SPY * 1.20)
    verwacht = 998.50 * 1.20 * (FX / nieuwe_fx)
    assert w.totaal_eur == pytest.approx(verwacht, abs=0.01)


def test_de_uitsplitsing_telt_exact_op_tot_het_totaal():
    """De twee delen samen moeten precies het totaal geven, anders telt iets dubbel."""
    for rendement in (-0.30, -0.05, 0.0, 0.07, 0.25):
        for fx_nu in (0.95, 1.05, 1.1266, 1.30):
            s = pf.splits_resultaat(rendement, FX, fx_nu)
            assert s["koersdeel_pct"] + s["valutadeel_pct"] == pytest.approx(
                s["totaal_pct"], abs=1e-6)


def test_de_uitsplitsing_klopt_met_de_echte_waardering(instap):
    hoger = {t: k * 1.15 for t, k in KOERSEN.items()}
    nieuwe_fx = 1.08
    w = pf.waardeer(instap, hoger, nieuwe_fx, "2026-11-06", spy_koers_usd=SPY)
    s = pf.splits_resultaat(0.15, FX, nieuwe_fx)
    # Het rendement op het belegde bedrag, dus zonder de instapkost.
    rendement_op_belegd = (w.totaal_eur / instap["invested_eur"] - 1.0) * 100
    assert rendement_op_belegd == pytest.approx(s["totaal_pct"], abs=1e-3)


def test_de_aandelen_in_de_portefeuille_tellen_op_tot_honderd(instap):
    gemengd = {"MRNA": 250.0, "ILMN": 280.0, "MPC": 450.0, "HPE": 60.0, "VLO": 400.0}
    w = pf.waardeer(instap, gemengd, FX, "2026-11-06", spy_koers_usd=SPY)
    assert sum(p["aandeel_pct"] for p in w.posities) == pytest.approx(100.0, abs=0.05)


def test_dividend_komt_er_bovenop(instap):
    zonder = pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=SPY)
    met = pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=SPY, dividend_eur=5.0)
    assert met.totaal_eur == pytest.approx(zonder.totaal_eur + 5.0, abs=0.01)


# ----------------------------------------------- dividend aan beide kanten
def test_dividend_telt_ook_bij_de_benchmark_mee(instap):
    """SPY keert zelf dividend uit. Dat hoort net zo mee te tellen."""
    w = pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=SPY,
                    spy_dividend_eur=4.0)
    assert w.spy_waarde_eur == pytest.approx(998.50 + 4.0, abs=0.01)
    assert w.spy_dividend_eur == pytest.approx(4.0, abs=1e-9)


def test_gelijk_dividend_aan_beide_kanten_verandert_de_voorsprong_niet(instap):
    zonder = pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=SPY)
    met = pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=SPY,
                      dividend_eur=6.0, spy_dividend_eur=6.0)
    assert met.totaal_eur == pytest.approx(zonder.totaal_eur + 6.0, abs=0.01)
    assert met.spy_waarde_eur == pytest.approx(zonder.spy_waarde_eur + 6.0, abs=0.01)
    assert met.voorsprong_pct == pytest.approx(zonder.voorsprong_pct, abs=1e-6)


def test_dividend_bij_een_kant_alleen_geeft_een_onverdiende_voorsprong(instap):
    """Dit is precies de fout die we niet willen maken, hier vastgelegd."""
    eenzijdig = pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=SPY,
                            dividend_eur=10.0)
    assert eenzijdig.voorsprong_pct == pytest.approx(1.0, abs=0.01)


DIVIDENDEN = [
    {"ticker": "MPC", "ex_date": "2026-11-16",
     "gross_per_share_usd": 1.0, "net_per_share_usd": 0.70},
    {"ticker": "SPY", "ex_date": "2026-12-18",
     "gross_per_share_usd": 2.0, "net_per_share_usd": 1.40},
    {"ticker": "KOMT_NIET_VOOR", "ex_date": "2026-11-16",
     "gross_per_share_usd": 9.0, "net_per_share_usd": 9.0},
]


def test_dividend_wordt_voor_beide_kanten_op_dezelfde_manier_gerekend(instap):
    fx = pd.Series([FX] * 10, index=pd.date_range("2026-11-10", periods=10, freq="D"))
    fx = pd.concat([fx, pd.Series([FX] * 40,
                                  index=pd.date_range("2026-11-20", periods=40, freq="D"))])

    aandelen_sw = {p["ticker"]: p["shares"] for p in instap["positions"]}
    aandelen_bm = {instap["benchmark"]["ticker"]: instap["benchmark"]["shares"]}

    sw = pf.dividend_reeks(DIVIDENDEN, aandelen_sw, fx)
    bm = pf.dividend_reeks(DIVIDENDEN, aandelen_bm, fx)

    mpc = next(p for p in instap["positions"] if p["ticker"] == "MPC")
    assert sw.loc[pd.Timestamp("2026-11-16")] == pytest.approx(
        mpc["shares"] * 0.70 / FX, rel=1e-9)
    assert bm.loc[pd.Timestamp("2026-12-18")] == pytest.approx(
        instap["benchmark"]["shares"] * 1.40 / FX, rel=1e-9)

    # Een aandeel dat je niet hebt, levert niets op.
    assert len(sw) == 1 and len(bm) == 1


def test_bruto_in_plaats_van_netto_is_een_keuze_die_voor_beide_geldt(instap):
    fx = pd.Series([FX] * 60, index=pd.date_range("2026-11-10", periods=60, freq="D"))
    aandelen = {"MPC": 1.0}
    netto = pf.dividend_reeks(DIVIDENDEN, aandelen, fx, netto=True)
    bruto = pf.dividend_reeks(DIVIDENDEN, aandelen, fx, netto=False)
    assert bruto.iloc[0] == pytest.approx(netto.iloc[0] / 0.70, rel=1e-9)


def test_een_ontbrekend_nettobedrag_wordt_niet_zelf_verzonnen():
    fx = pd.Series([FX] * 60, index=pd.date_range("2026-11-10", periods=60, freq="D"))
    zonder_netto = [{"ticker": "MPC", "ex_date": "2026-11-16",
                     "gross_per_share_usd": 1.0, "net_per_share_usd": None}]
    with pytest.raises(ValueError, match="nettobedrag"):
        pf.dividend_reeks(zonder_netto, {"MPC": 1.0}, fx)


def test_zonder_wisselkoers_wordt_dividend_niet_omgerekend():
    leeg = pd.Series(dtype=float)
    with pytest.raises(ValueError, match="wisselkoers"):
        pf.dividend_reeks(DIVIDENDEN, {"MPC": 1.0}, leeg)


# --------------------------------------------- geen koers, dan geen bedrag
def test_een_ontbrekende_koers_verzint_niets(instap):
    """Valt een koers weg, dan komt er geen bedrag. Ook niet de aankoopkoers.

    Vroeger werd stil de aankoopkoers aangehouden. Het scherm toonde dan een
    bedrag dat eruitzag als "nu waard" terwijl het dat niet was.
    """
    deels = {t: k for t, k in KOERSEN.items() if t != "MPC"}
    with pytest.raises(pf.KoersOntbreekt) as fout:
        pf.waardeer(instap, deels, FX, "2026-11-06", spy_koers_usd=SPY)
    assert fout.value.ontbreekt == ["MPC"]


def test_een_ontbrekende_benchmarkkoers_verzint_ook_niets(instap):
    with pytest.raises(pf.KoersOntbreekt) as fout:
        pf.waardeer(instap, KOERSEN, FX, "2026-11-06", spy_koers_usd=None)
    assert fout.value.ontbreekt == ["SPY"]


def test_een_koers_van_nul_is_geen_koers(instap):
    kapot = dict(KOERSEN, HPE=0.0)
    with pytest.raises(pf.KoersOntbreekt):
        pf.waardeer(instap, kapot, FX, "2026-11-06", spy_koers_usd=SPY)


def test_onmogelijke_invoer_wordt_geweigerd():
    with pytest.raises(ValueError):
        pf.bereken_instap("x", "2026-10-06", TICKERS, KOERSEN, 0.0, SPY, "t", "t")
    with pytest.raises(ValueError):
        pf.bereken_instap("x", "2026-10-06", TICKERS, {"MRNA": 0.0}, FX, SPY, "t", "t")
    with pytest.raises(ValueError):
        pf.bereken_instap("x", "2026-10-06", [], {}, FX, SPY, "t", "t")


def test_de_instap_heeft_een_controlegetal(instap):
    from sw.strategy import sha256_text
    assert instap["exec_hash"] == sha256_text(instap["canonical_payload"])
    assert len(instap["exec_hash"]) == 64


def test_hetzelfde_rekenwerk_geeft_hetzelfde_controlegetal(instap):
    opnieuw = pf.bereken_instap(
        entry_hash="test", execution_date="2026-10-06", tickers=TICKERS,
        koersen_usd=KOERSEN, fx_eurusd=FX, spy_koers_usd=SPY,
        fx_source="test", fx_asof="2026-10-06T20:00:00+00:00",
    )
    assert opnieuw["exec_hash"] == instap["exec_hash"]


def test_het_verloop_begint_op_de_instapdag(instap):
    datums = pd.date_range("2026-10-06", periods=5, freq="B")
    koersen = pd.DataFrame(
        {t: [KOERSEN[t]] * 5 for t in TICKERS} | {"SPY": [SPY] * 5}, index=datums)
    fx = pd.Series([FX] * 5, index=datums)
    verloop = pf.bouw_verloop(instap, koersen, fx)
    assert len(verloop) == 5
    assert verloop.index[0] == pd.Timestamp("2026-10-06")
    assert verloop["portefeuille_eur"].iloc[0] == pytest.approx(998.50, abs=0.01)


def test_het_verloop_telt_dividend_bij_beide_kanten(instap):
    """Allebei dividend op dezelfde dag: dan blijft het verschil gelijk."""
    datums = pd.date_range("2026-10-06", periods=5, freq="B")
    koersen = pd.DataFrame(
        {t: [KOERSEN[t]] * 5 for t in TICKERS} | {"SPY": [SPY] * 5}, index=datums)
    fx = pd.Series([FX] * 5, index=datums)

    exdag = datums[2]
    verloop = pf.bouw_verloop(
        instap, koersen, fx,
        dividend_per_dag=pd.Series([3.0], index=[exdag]),
        spy_dividend_per_dag=pd.Series([3.0], index=[exdag]),
    )

    assert verloop["portefeuille_eur"].iloc[1] == pytest.approx(998.50, abs=0.01)
    assert verloop["portefeuille_eur"].iloc[2] == pytest.approx(998.50 + 3.0, abs=0.01)
    assert verloop["spy_eur"].iloc[2] == pytest.approx(998.50 + 3.0, abs=0.01)
    assert verloop["voorsprong_pct"].iloc[2] == pytest.approx(0.0, abs=1e-6)
    assert verloop["dividend_eur"].iloc[4] == pytest.approx(3.0, abs=1e-9)
    assert verloop["spy_dividend_eur"].iloc[4] == pytest.approx(3.0, abs=1e-9)


def test_grootste_terugval_wordt_goed_gemeten():
    reeks = pd.Series([100.0, 110.0, 99.0, 105.0])
    assert pf.max_daling(reeks) == pytest.approx(-10.0, abs=1e-6)
