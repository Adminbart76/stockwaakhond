"""Wachters op de doorlopende portefeuille.

Eén keer 1.000 euro, daarna alleen wisselen. Dat is de afspraak, en dit bestand
bewaakt ze op de enige manier die werkt: met getallen.

Het gevaar dat hier bewaakt wordt, is stil. Zou `bereken_herbalans()` ooit weer
met een vers bedrag beginnen, dan ziet de grafiek er netjes uit, klopt elke
afzonderlijke maand, en is alleen de reeks als geheel verzonnen. Daarom wordt
hieronder niet alleen gerekend of de uitkomst klopt, maar ook expliciet dat ze
NIET gelijk is aan een nieuwe start.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sw import herbalans as hb
from sw import portfolio as pf

PROJECT = Path(__file__).resolve().parent.parent

# De werkelijke getallen van de instap van 6 oktober 2026.
INSTAPKOERSEN = {
    "MRNA": 187.46000671, "ILMN": 273.54000854, "MPC": 432.35998535,
    "HPE": 70.48000336, "VLO": 419.22000122,
}
SPY_INSTAP = 779.09002686
FX = 1.1262530088
NIEUWE_TOP5 = ["AAPL", "MSFT", "KO", "XOM", "JNJ"]


@pytest.fixture
def instap():
    return pf.bereken_instap(
        entry_hash="signaal-1",
        execution_date="2026-10-06",
        tickers=list(INSTAPKOERSEN),
        koersen_usd=INSTAPKOERSEN,
        fx_eurusd=FX,
        spy_koers_usd=SPY_INSTAP,
        fx_source="test",
        fx_asof="2026-10-06T20:54:00+00:00",
    )


def koersen_na(factor: float, ook: dict | None = None) -> dict:
    """Alle instapkoersen maal een factor, plus eventueel nieuwe aandelen.

    Een aandeel dat al in de portefeuille zat, houdt zijn eigen koers: anders
    zou een test die vijf aandelen laat staan ze stilletjes allemaal op dezelfde
    prijs zetten, en dan meet hij iets anders dan hij beweert.
    """
    uit = {t: k * factor for t, k in INSTAPKOERSEN.items()}
    uit["SPY"] = SPY_INSTAP * factor
    for ticker, koers in (ook or {}).items():
        uit.setdefault(ticker, koers)
    return uit


def wissel(instap, nieuwe_tickers=None, factor=1.0, **extra):
    nieuwe_tickers = nieuwe_tickers or NIEUWE_TOP5
    koersen = koersen_na(factor, {t: 100.0 for t in nieuwe_tickers})
    return hb.bereken_herbalans(
        entry_hash="signaal-2",
        execution_date="2026-11-04",
        vorige_uitvoering=instap,
        nieuwe_tickers=nieuwe_tickers,
        koersen_usd=koersen,
        fx_eurusd=FX,
        spy_koers_usd=koersen["SPY"],
        fx_source="test",
        fx_asof="2026-11-04T21:00:00+00:00",
        **extra,
    )


# ------------------------------------------------- geen nieuw geld, nooit meer
def test_er_wordt_niet_opnieuw_met_1000_euro_begonnen(instap):
    """De kern van punt 1 van de audit."""
    herb = wissel(instap, factor=1.20)

    assert herb["start_capital_eur"] == 1000.0, (
        "Het startkapitaal is de meetlat van de hele reeks en blijft 1.000 euro."
    )
    assert herb["invested_eur"] > 1100.0, (
        "Na 20 procent winst hoort er meer dan 1.100 euro belegd te worden. "
        "Staat hier ongeveer 998,50, dan begint de code opnieuw met 1.000 euro."
    )
    assert herb["invested_eur"] != pytest.approx(998.50, abs=1.0)


def test_verlies_gaat_net_zo_hard_mee(instap):
    herb = wissel(instap, factor=0.75)
    assert herb["invested_eur"] < 760.0
    assert herb["opening"]["total_usd"] == pytest.approx(
        sum(p["shares"] * INSTAPKOERSEN[p["ticker"]] * 0.75
            for p in instap["positions"]), rel=1e-9)


def test_de_waarde_na_de_wissel_is_de_waarde_ervoor_min_de_kost(instap):
    herb = wissel(instap, factor=1.05)
    assert herb["invested_usd"] == pytest.approx(
        herb["opening"]["total_usd"] - herb["cost_usd"], abs=1e-6)
    opnieuw = sum(p["shares"] * p["buy_price_usd"] for p in herb["positions"])
    assert opnieuw == pytest.approx(herb["invested_usd"], rel=1e-9)


def test_de_inzet_per_aandeel_is_gelijk_verdeeld(instap):
    herb = wissel(instap, factor=1.05)
    bedragen = {p["invested_usd"] for p in herb["positions"]}
    assert len(bedragen) == 1
    assert all(p["target_weight"] == pytest.approx(0.2) for p in herb["positions"])


# --------------------------------------------------------------- de omzetkost
def test_de_eerste_instap_geeft_omzet_een(instap):
    """Zo is 1,50 euro op 1.000 euro ontstaan. Die uitkomst moet blijven."""
    assert hb.bereken_omzet({}, {t: 0.2 for t in NIEUWE_TOP5}, 1.0) == pytest.approx(1.0)
    assert instap["cost_eur"] == pytest.approx(1.50)


def test_een_volledige_wissel_rekent_over_de_hele_portefeuille(instap):
    herb = wissel(instap, factor=1.0)
    assert herb["turnover"] == pytest.approx(1.0, abs=1e-9)
    assert herb["cost_usd"] == pytest.approx(
        herb["opening"]["total_usd"] * 0.0015, abs=1e-7)


def test_wie_dezelfde_vijf_houdt_betaalt_vrijwel_niets(instap):
    herb = wissel(instap, nieuwe_tickers=list(INSTAPKOERSEN), factor=1.0)
    assert herb["turnover"] == pytest.approx(0.0, abs=1e-6)
    assert herb["cost_usd"] == pytest.approx(0.0, abs=1e-6)
    # en dan verandert ook het aantal aandelen niet
    oud = {p["ticker"]: p["shares"] for p in instap["positions"]}
    for p in herb["positions"]:
        assert p["shares"] == pytest.approx(oud[p["ticker"]], rel=1e-8)


def test_wie_er_twee_wisselt_betaalt_over_twee_vijfden(instap):
    """Drie blijven staan, twee gaan eruit. Dus 2 x 20 % omzet."""
    blijft = list(INSTAPKOERSEN)[:3]
    nieuw = blijft + ["AAPL", "MSFT"]
    herb = wissel(instap, nieuwe_tickers=nieuw, factor=1.0)
    assert herb["turnover"] == pytest.approx(0.4, abs=1e-6)
    assert herb["cost_usd"] < wissel(instap, factor=1.0)["cost_usd"]


def test_drift_kost_iets_maar_niet_veel(instap):
    """Alle vijf blijven, maar de koersen zijn uit elkaar gelopen."""
    koersen = dict(INSTAPKOERSEN)
    koersen["MRNA"] = koersen["MRNA"] * 1.5
    koersen["HPE"] = koersen["HPE"] * 0.7
    koersen["SPY"] = SPY_INSTAP
    herb = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-11-04",
        vorige_uitvoering=instap, nieuwe_tickers=list(INSTAPKOERSEN),
        koersen_usd=koersen, fx_eurusd=FX, spy_koers_usd=SPY_INSTAP,
        fx_source="test", fx_asof="2026-11-04T21:00:00+00:00")
    assert 0.0 < herb["turnover"] < 0.2


def test_de_omzetformule_komt_nog_overeen_met_de_bevroren_simulatie():
    """app.py is bevroren. Deze formule hoort er letterlijk uit te komen.

    Loopt een van de twee ooit weg van de andere, dan meet de doorlopende
    portefeuille iets anders dan de bevroren curve, en dan vergelijkt het
    dashboard twee rekenwijzen in plaats van twee beleggingen.
    """
    tekst = (PROJECT / "app.py").read_text(encoding="utf-8")
    assert "turnover = 0.5 * (stock_turnover + cash_turnover)" in tekst
    assert "fee = turnover * (cost_pct / 100.0)" in tekst


def test_de_kostenconventie_blijft_eenzijdig(instap):
    """Het openstaande punt uit CLAUDE.md wordt hier niet beslist."""
    herb = wissel(instap, factor=1.0)
    assert herb["cost_pct"] == pytest.approx(0.15)
    assert "eenzijdig" in herb["turnover_convention"]
    tweezijdig = wissel(instap, factor=1.0, omzet_factor=2.0)
    assert tweezijdig["cost_usd"] == pytest.approx(2 * herb["cost_usd"], abs=1e-7)


# ----------------------------------------------------------------------- SPY
def test_spy_wordt_niet_teruggezet_en_betaalt_niet_mee(instap):
    herb = wissel(instap, factor=1.30)
    oud, nieuw = instap["benchmark"], herb["benchmark"]
    assert nieuw["shares"] == oud["shares"]
    assert nieuw["buy_price_usd"] == oud["buy_price_usd"]
    assert nieuw["invested_eur"] == oud["invested_eur"] == 998.50
    assert nieuw["cash_usd"] == 0.0


def test_spy_groeit_mee_in_de_waardering(instap):
    herb = wissel(instap, factor=1.30)
    koersen = koersen_na(1.30, {t: 100.0 for t in NIEUWE_TOP5})
    w = pf.waardeer(herb, koersen, FX, datum="2026-11-05",
                    spy_koers_usd=koersen["SPY"])
    assert w.inleg_eur == 1000.0
    assert w.spy_resultaat_pct == pytest.approx(
        (998.50 * 1.30 / 1000.0 - 1.0) * 100, abs=0.01)


# ---------------------------------------------------------------- de keten
def test_de_wissel_hangt_aan_de_vorige_uitvoering(instap):
    herb = wissel(instap, factor=1.05)
    assert herb["prev_exec_hash"] == instap["exec_hash"]
    assert herb["exec_hash"] != instap["exec_hash"]
    ok, bericht = hb.verify_keten([instap, herb])
    assert ok, bericht
    assert hb.laatste_uitvoering([instap, herb])["exec_hash"] == herb["exec_hash"]


def test_de_volgorde_komt_uit_de_keten_en_niet_uit_de_lijst(instap):
    herb = wissel(instap, factor=1.05)
    assert hb.sorteer_keten([herb, instap])[0]["exec_hash"] == instap["exec_hash"]


def test_een_gebroken_keten_wordt_gezien(instap):
    herb = wissel(instap, factor=1.05)
    kapot = dict(herb, prev_exec_hash="a" * 64)
    ok, bericht = hb.verify_keten([instap, kapot])
    assert not ok and "voorganger" in bericht


def test_twee_ketens_naast_elkaar_worden_gezien(instap):
    een = wissel(instap, factor=1.05)
    twee = wissel(instap, nieuwe_tickers=["KO", "XOM", "JNJ", "PG", "T"], factor=1.05)
    ok, bericht = hb.verify_keten([instap, een, twee])
    assert not ok and "twee ketens" in bericht.lower()


def test_een_gewijzigde_inhoud_wordt_gezien(instap):
    herb = wissel(instap, factor=1.05)
    gesjoemeld = dict(herb)
    gesjoemeld["canonical_payload"] = herb["canonical_payload"].replace(
        "\"turnover\":1.0", "\"turnover\":0.1")
    ok, bericht = hb.verify_keten([instap, gesjoemeld])
    assert not ok and "controlegetal" in bericht


def test_een_wissel_kan_niet_voor_de_vorige_uitvoering_liggen(instap):
    with pytest.raises(ValueError, match="niet na de vorige"):
        hb.bereken_herbalans(
            entry_hash="signaal-2", execution_date="2026-10-05",
            vorige_uitvoering=instap, nieuwe_tickers=NIEUWE_TOP5,
            koersen_usd=koersen_na(1.0, {t: 100.0 for t in NIEUWE_TOP5}),
            fx_eurusd=FX, spy_koers_usd=SPY_INSTAP, fx_source="test",
            fx_asof="2026-10-05T21:00:00+00:00")


# ------------------------------------------------------ welke aandelen leven
def test_actieve_tickers_zijn_die_van_nu_en_niet_die_van_toen(instap):
    herb = wissel(instap, factor=1.05)
    actief = hb.actieve_tickers([instap, herb])
    assert actief == sorted(NIEUWE_TOP5 + ["SPY"])
    for oud in INSTAPKOERSEN:
        assert oud not in actief, (
            "Een aandeel dat verkocht is, hoort geen koersen meer te kunnen "
            "laten bijschrijven."
        )
    # voor de grafiek heb je het verleden wél nodig
    assert "MRNA" in hb.tickers_in_keten([instap, herb])


def test_zonder_uitvoering_is_er_geen_actieve_lijst():
    assert hb.actieve_tickers([]) == []


# -------------------------------------------------------------------- koersen
def test_zonder_koers_geen_wissel(instap):
    koersen = koersen_na(1.0, {t: 100.0 for t in NIEUWE_TOP5})
    del koersen["MPC"]
    with pytest.raises(pf.KoersOntbreekt) as fout:
        hb.bereken_herbalans(
            entry_hash="signaal-2", execution_date="2026-11-04",
            vorige_uitvoering=instap, nieuwe_tickers=NIEUWE_TOP5,
            koersen_usd=koersen, fx_eurusd=FX, spy_koers_usd=SPY_INSTAP,
            fx_source="test", fx_asof="2026-11-04T21:00:00+00:00")
    assert "MPC" in fout.value.ontbreekt


def test_ook_een_nieuw_aandeel_zonder_koers_blokkeert(instap):
    koersen = koersen_na(1.0, {t: 100.0 for t in NIEUWE_TOP5})
    koersen["AAPL"] = 0.0
    with pytest.raises(pf.KoersOntbreekt):
        hb.bereken_herbalans(
            entry_hash="signaal-2", execution_date="2026-11-04",
            vorige_uitvoering=instap, nieuwe_tickers=NIEUWE_TOP5,
            koersen_usd=koersen, fx_eurusd=FX, spy_koers_usd=SPY_INSTAP,
            fx_source="test", fx_asof="2026-11-04T21:00:00+00:00")


# ------------------------------------------------------------------- dividend
def test_dividendgeld_gaat_mee_naar_de_volgende_periode(instap):
    zonder = wissel(instap, factor=1.0)
    met = wissel(instap, factor=1.0, dividend_cash_usd=40.0,
                 dividend_conventie="bruto, test")
    assert met["opening"]["cash_usd"] == pytest.approx(40.0)
    assert met["opening"]["total_usd"] == pytest.approx(
        zonder["opening"]["total_usd"] + 40.0, abs=1e-6)
    assert met["invested_usd"] > zonder["invested_usd"]
    assert met["cash_usd"] == 0.0, "Na de wissel staat het geld in aandelen."


def test_dividend_zonder_conventie_wordt_geweigerd(instap):
    with pytest.raises(ValueError, match="conventie"):
        wissel(instap, factor=1.0, dividend_cash_usd=40.0)


def test_dividend_kan_niet_negatief_zijn(instap):
    with pytest.raises(ValueError, match="negatief"):
        wissel(instap, factor=1.0, dividend_cash_usd=-1.0,
               dividend_conventie="bruto, test")


def test_het_dividend_van_spy_blijft_bij_spy(instap):
    herb = wissel(instap, factor=1.0, spy_dividend_cash_usd=12.0,
                  dividend_conventie="bruto, test")
    assert herb["benchmark"]["cash_usd"] == pytest.approx(12.0)
    assert herb["benchmark"]["shares"] == instap["benchmark"]["shares"], (
        "SPY koopt niets bij: het dividend blijft contant staan."
    )
    assert herb["opening"]["cash_usd"] == 0.0, (
        "Het dividend van SPY hoort niet in de portefeuille van StockWaakhond."
    )


# -------------------------------------------------------------------- verloop
def test_het_verloop_wisselt_van_mandje_op_de_wisseldag(instap):
    herb = wissel(instap, factor=1.10)

    dagen = pd.date_range("2026-10-06", "2026-11-06", freq="B")
    kolommen = sorted(set(INSTAPKOERSEN) | set(NIEUWE_TOP5) | {"SPY"})
    koersen = pd.DataFrame(index=dagen, columns=kolommen, dtype=float)
    for dag in dagen:
        factor = 1.0 if dag < pd.Timestamp("2026-10-21") else 1.10
        for t in INSTAPKOERSEN:
            koersen.at[dag, t] = INSTAPKOERSEN[t] * factor
        for t in NIEUWE_TOP5:
            koersen.at[dag, t] = 100.0
        koersen.at[dag, "SPY"] = SPY_INSTAP * factor
    fx = pd.Series(FX, index=dagen)

    verloop = hb.bouw_verloop_keten([instap, herb], koersen, fx)

    assert verloop.loc["2026-10-06", "portefeuille_eur"] == pytest.approx(998.50, abs=0.01)
    assert verloop.loc["2026-11-04", "wissel"]
    assert bool(verloop.loc["2026-11-03", "wissel"]) is False

    # Op de wisseldag is de waarde die van vlak ervoor, min de kost. Geen sprong.
    ervoor = verloop.loc["2026-11-03", "portefeuille_eur"]
    erna = verloop.loc["2026-11-04", "portefeuille_eur"]
    assert erna == pytest.approx(ervoor - herb["cost_usd"] / FX, abs=0.02)

    # De dag na de wissel beweegt het nieuwe mandje, niet het oude.
    assert verloop.loc["2026-11-05", "portefeuille_eur"] == pytest.approx(erna, abs=0.01)

    # SPY loopt door op zijn eigen koers en is nergens teruggezet.
    assert verloop.loc["2026-11-04", "spy_eur"] == pytest.approx(
        998.50 * 1.10, abs=0.02)


def test_het_verloop_meet_tegen_de_oorspronkelijke_duizend_euro(instap):
    herb = wissel(instap, factor=1.10)
    dagen = pd.date_range("2026-10-06", "2026-11-06", freq="B")
    kolommen = sorted(set(INSTAPKOERSEN) | set(NIEUWE_TOP5) | {"SPY"})
    koersen = pd.DataFrame(1.0, index=dagen, columns=kolommen, dtype=float)
    for dag in dagen:
        factor = 1.0 if dag < pd.Timestamp("2026-10-21") else 1.10
        for t in INSTAPKOERSEN:
            koersen.at[dag, t] = INSTAPKOERSEN[t] * factor
        for t in NIEUWE_TOP5:
            koersen.at[dag, t] = 100.0
        koersen.at[dag, "SPY"] = SPY_INSTAP * factor
    verloop = hb.bouw_verloop_keten(
        [instap, herb], koersen, pd.Series(FX, index=dagen))

    laatste = verloop.iloc[-1]
    assert laatste["resultaat_pct"] == pytest.approx(
        (laatste["portefeuille_eur"] / 1000.0 - 1.0) * 100, abs=1e-9)


# --------------------------------------------- de echte, vastgelegde instap
def test_de_vastgelegde_instap_van_6_oktober_blijft_de_eerste_schakel():
    """Geen enkele nieuwe functie mag aan dat record raken."""
    regels = [
        json.loads(r) for r in
        (PROJECT / "forward_log" / "executions.jsonl")
        .read_text(encoding="utf-8").splitlines() if r.strip()
    ]
    echt = regels[0]
    voor = json.dumps(echt, sort_keys=True)

    herb = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-11-04",
        vorige_uitvoering=echt, nieuwe_tickers=NIEUWE_TOP5,
        koersen_usd={t: 100.0 for t in NIEUWE_TOP5}
        | {p["ticker"]: p["buy_price_usd"] for p in echt["positions"]},
        fx_eurusd=FX, spy_koers_usd=SPY_INSTAP, fx_source="test",
        fx_asof="2026-11-04T21:00:00+00:00")

    assert herb["prev_exec_hash"] == echt["exec_hash"]
    assert json.dumps(echt, sort_keys=True) == voor, (
        "De vastgelegde uitvoering is onderweg gewijzigd."
    )
    assert herb["start_capital_eur"] == 1000.0
    ok, bericht = hb.verify_keten([echt, herb])
    assert ok, bericht
