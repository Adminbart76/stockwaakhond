"""Wachters op de tweede curve: kosten over wat er werkelijk verhandeld is.

De officiële curve rekent de eenzijdige omzet van de bevroren simulatie. Deze
curve rekent de som van de absolute dollarbedragen van alle echte orders. Het
verschil is geen factor twee:

  volledige wissel         ongeveer 200 % verhandeld  ->  ongeveer 0,30 %
  dezelfde vijf, wat drift een paar procent verhandeld
  alleen contant beleggen  precies dat contante geld, en niet het dubbele

Die laatste is de reden dat hier geen `omzet_factor=2` staat. Twee keer de
eenzijdige omzet klopt bij een volledige wissel en is fout bij alle andere.

En het belangrijkste: de officiële curve mag hier nooit door vervangen worden.
Dat wordt hieronder letterlijk nagerekend op de instap van 6 oktober 2026.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sw import herbalans as hb
from sw import portfolio as pf
from sw import realistisch as re
from tests.hulp_fx import bewijs_voor

VIJF = ["A", "B", "C", "D", "E"]
ANDERE_VIJF = ["V", "W", "X", "Y", "Z"]
KOERS = {t: 100.0 for t in VIJF + ANDERE_VIJF}
KOERS["SPY"] = 500.0
FX = 1.10


@pytest.fixture
def instap():
    return pf.bereken_instap(
        entry_hash="signaal-1",
        execution_date="2026-10-06",
        tickers=VIJF,
        koersen_usd=KOERS,
        fx_eurusd=FX,
        spy_koers_usd=KOERS["SPY"],
        fx_source="test",
        fx_asof="2026-10-06T20:54:00+00:00",
    )


# -------------------------------------------------------- de rekenregel zelf
def test_een_volledige_wissel_verhandelt_twee_keer_de_portefeuille():
    huidig = {t: 200.0 for t in VIJF}           # 1.000 dollar in vijf aandelen
    doel = {t: 200.0 for t in ANDERE_VIJF}      # alles naar vijf andere

    assert re.verhandeld_usd(huidig, doel) == pytest.approx(2000.0), (
        "Alles verkopen en alles kopen is twee keer de portefeuille."
    )
    assert re.kost_usd(huidig, doel, 0.15) == pytest.approx(3.00)
    assert re.kost_usd(huidig, doel, 0.15) / 1000.0 * 100 == pytest.approx(0.30), (
        "Bij een volledige wissel kost het ongeveer 0,30 procent in plaats van 0,15."
    )


def test_dezelfde_vijf_zonder_drift_verhandelt_niets():
    huidig = {t: 200.0 for t in VIJF}
    assert re.verhandeld_usd(huidig, dict(huidig)) == pytest.approx(0.0), (
        "Niets te doen is niets te betalen."
    )


def test_dezelfde_vijf_met_drift_verhandelt_alleen_het_verschil():
    """De koersen zijn uit elkaar gelopen; er wordt alleen bijgesteld."""
    huidig = {"A": 260.0, "B": 220.0, "C": 200.0, "D": 180.0, "E": 140.0}
    doel = {t: 200.0 for t in VIJF}

    # verkopen: 60 + 20 = 80, kopen: 20 + 60 = 80
    assert re.verhandeld_usd(huidig, doel) == pytest.approx(160.0)
    assert re.verhandeld_usd(huidig, doel) < 2 * 1000.0 * 0.5, (
        "Een beetje drift is geen volledige wissel."
    )


def test_alleen_contant_geld_beleggen_wordt_niet_kunstmatig_verdubbeld():
    """5 procent contant dat alleen bestaande posities bijkoopt, is 5 procent.

    Dit is de kern van de beslissing: NIET simpelweg twee keer de eenzijdige
    omzet. Er wordt niets verkocht, dus er is ook niets dubbel te rekenen.
    """
    totaal = 1000.0
    huidig = {t: 190.0 for t in VIJF}           # 950 dollar in aandelen
    contant = 50.0
    doel = {t: totaal / 5 for t in VIJF}        # 200 per stuk

    verhandeld = re.verhandeld_usd(huidig, doel)
    assert verhandeld == pytest.approx(50.0), (
        "Alleen het contante geld gaat over de toonbank."
    )
    assert verhandeld / totaal == pytest.approx(0.05)
    assert verhandeld != pytest.approx(100.0), "Niet verdubbelen."
    assert contant == pytest.approx(50.0)


def test_verkopen_plus_contant_plus_bijkopen_bij_elkaar():
    """Twee aandelen eruit, drie blijven, en er staat ook contant geld."""
    huidig = {"A": 300.0, "B": 250.0, "C": 200.0, "D": 150.0, "E": 50.0}
    contant = 50.0                                    # totaal 1.000
    doel = {"A": 250.0, "B": 250.0, "C": 250.0, "V": 250.0}

    # A: -50, B: 0, C: +50, D: -150, E: -50, V: +250  ->  som = 550
    assert re.verhandeld_usd(huidig, doel) == pytest.approx(550.0)
    assert contant == pytest.approx(50.0)
    assert re.verhandeld_usd(huidig, doel) < 2000.0, (
        "Wat blijft staan, wordt niet verhandeld."
    )


# ------------------------------------------------------------------ één stap
def test_een_stap_belegt_wat_er_na_de_kosten_overblijft():
    posities = {t: 2.0 for t in VIJF}              # 5 x 2 x 100 = 1.000
    uit = re.stap(posities, KOERS, ANDERE_VIJF, contant_usd=0.0, cost_pct=0.15)

    assert uit["waarde_voor_usd"] == pytest.approx(1000.0)
    assert uit["verhandeld_usd"] == pytest.approx(2000.0)
    assert uit["verhandeld_deel"] == pytest.approx(2.0)
    assert uit["kost_usd"] == pytest.approx(3.0)
    assert uit["belegd_usd"] == pytest.approx(997.0)
    assert sum(n * 100.0 for n in uit["posities"].values()) == pytest.approx(997.0)


def test_de_realistische_kost_is_hoger_dan_de_bevroren_kost_bij_een_wissel():
    posities = {t: 2.0 for t in VIJF}
    papier = re.stap(posities, KOERS, ANDERE_VIJF, contant_usd=0.0, cost_pct=0.15)

    bevroren_omzet = hb.bereken_omzet(
        {t: 0.2 for t in VIJF}, {t: 0.2 for t in ANDERE_VIJF}, 0.0)
    bevroren_kost = 1000.0 * bevroren_omzet * 0.15 / 100.0

    assert papier["kost_usd"] == pytest.approx(2 * bevroren_kost), (
        "Bij een volledige wissel is dit wel precies het dubbele."
    )
    assert papier["kost_usd"] > bevroren_kost


def test_bij_alleen_contant_beleggen_zijn_de_twee_formules_gelijk():
    """Hier mag de realistische curve niet duurder zijn dan de officiële.

    De bevroren formule rekent 0,5 x (gewichtsverschillen + contant). Wordt er
    alleen contant geld belegd, dan is dat precies het contante geld - net als
    de werkelijk verhandelde notional. Twee keer de omzet nemen zou hier wel
    verdubbelen, en dat zou fout zijn.
    """
    huidig_waarden = {t: 190.0 for t in VIJF}
    doel_waarden = {t: 200.0 for t in VIJF}
    werkelijk = re.verhandeld_usd(huidig_waarden, doel_waarden) / 1000.0

    bevroren = hb.bereken_omzet(
        {t: 0.19 for t in VIJF}, {t: 0.20 for t in VIJF}, 0.05)

    assert werkelijk == pytest.approx(bevroren, abs=1e-12)
    assert hb.bereken_omzet(
        {t: 0.19 for t in VIJF}, {t: 0.20 for t in VIJF}, 0.05,
        omzet_factor=2.0) == pytest.approx(0.10), (
        "omzet_factor=2 zou hier het dubbele rekenen van wat er verhandeld is."
    )


# ------------------------------------------------------------- de hele keten
def test_de_instap_is_in_beide_curves_identiek(instap):
    """Alles stond contant en er werd alleen gekocht: dan zijn ze gelijk.

    Daarom raakt deze beslissing de bestaande uitvoering van 6 oktober 2026
    niet, en lopen de curves pas uit elkaar bij de eerste echte wissel.
    """
    papier = re.papieren_keten([instap])
    assert len(papier) == 1

    assert papier[0]["cost_eur"] == pytest.approx(float(instap["cost_eur"]), abs=1e-6)
    assert papier[0]["invested_eur"] == pytest.approx(
        float(instap["invested_eur"]), abs=1e-6)
    for p, q in zip(papier[0]["positions"],
                    sorted(instap["positions"], key=lambda x: x["ticker"])):
        assert p["ticker"] == q["ticker"]
        assert p["shares"] == pytest.approx(q["shares"], rel=1e-9)


def test_de_papieren_keten_houdt_minder_over_na_een_wissel(instap):
    koersen = dict(KOERS)
    wissel = hb.bereken_herbalans(
        entry_hash="signaal-2",
        execution_date="2026-11-04",
        vorige_uitvoering=instap,
        nieuwe_tickers=ANDERE_VIJF,
        koersen_usd=koersen,
        fx_eurusd=FX,
        spy_koers_usd=KOERS["SPY"],
        fx_source="test",
        fx_asof="2026-11-04T21:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-11-04", FX),
    )

    papier = re.papieren_keten([instap, wissel])
    assert len(papier) == 2
    assert papier[1]["verhandeld_deel"] == pytest.approx(2.0, abs=1e-6)
    assert papier[1]["cost_usd"] > float(wissel["cost_usd"]), (
        "Een volledige wissel kost in de realistische curve het dubbele."
    )
    assert papier[1]["invested_usd"] < float(wissel["invested_usd"])

    papier_aandelen = {p["ticker"]: p["shares"] for p in papier[1]["positions"]}
    for p in wissel["positions"]:
        assert papier_aandelen[p["ticker"]] < p["shares"], (
            "Minder geld na de kosten is minder aandelen."
        )


def test_de_papieren_keten_verandert_de_officiele_records_niet(instap):
    wissel = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-11-04",
        vorige_uitvoering=instap, nieuwe_tickers=ANDERE_VIJF,
        koersen_usd=dict(KOERS), fx_eurusd=FX, spy_koers_usd=KOERS["SPY"],
        fx_source="test", fx_asof="2026-11-04T21:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-11-04", FX))

    voor = (instap["exec_hash"], wissel["exec_hash"],
            instap["canonical_payload"], wissel["canonical_payload"])
    re.papieren_keten([instap, wissel])
    na = (instap["exec_hash"], wissel["exec_hash"],
          instap["canonical_payload"], wissel["canonical_payload"])

    assert voor == na, (
        "De realistische curve wordt elke keer opnieuw gerekend en raakt het "
        "bewijsmateriaal niet aan."
    )


def test_de_papieren_curve_heeft_geen_controlegetal(instap):
    papier = re.papieren_keten([instap])
    assert papier[0]["exec_hash"] == "papier-1", (
        "Een leesbare naam en geen hash: dit is geen bewijsmateriaal en het "
        "hoort er ook niet op te lijken."
    )
    assert "canonical_payload" not in papier[0]


def test_dividendgeld_wordt_in_de_papieren_curve_met_eigen_aantallen_gerekend(instap):
    """De papieren portefeuille heeft na een wissel minder aandelen.

    Dus ook minder dividend. Het bedrag uit het officiële record overnemen zou de
    papieren curve geld geven dat ze niet verdient - en dan meet de tweede curve
    niet meer wat ze belooft.
    """
    eerste = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-10-20",
        vorige_uitvoering=instap, nieuwe_tickers=ANDERE_VIJF,
        koersen_usd=dict(KOERS), fx_eurusd=FX, spy_koers_usd=KOERS["SPY"],
        fx_source="test", fx_asof="2026-10-20T20:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-10-20", FX))

    # De ex-datum ligt NA die wissel, dus na het punt waarop de twee curves uit
    # elkaar gaan lopen.
    per_aandeel = 1.0
    aandelen_officieel = {p["ticker"]: p["shares"] for p in eerste["positions"]}
    detail = [{
        "ticker": "V", "ex_date": "2026-11-02", "pay_date": "2026-11-10",
        "per_share_usd": per_aandeel,
        "shares": aandelen_officieel["V"],
        "bedrag_usd": round(aandelen_officieel["V"] * per_aandeel, 8),
        "conventie": "bruto",
    }]
    tweede = hb.bereken_herbalans(
        entry_hash="signaal-3", execution_date="2026-11-20",
        vorige_uitvoering=eerste, nieuwe_tickers=VIJF,
        koersen_usd=dict(KOERS), fx_eurusd=FX, spy_koers_usd=KOERS["SPY"],
        fx_source="test", fx_asof="2026-11-20T21:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-11-20", FX),
        dividend_cash_usd=detail[0]["bedrag_usd"],
        dividend_conventie="bruto, test",
        dividend_detail=detail)

    papier = re.papieren_keten([instap, eerste, tweede])
    papier_aandelen = {p["ticker"]: p["shares"] for p in papier[1]["positions"]}
    gerekend = papier[2]["dividend_cash_usd"]

    assert gerekend == pytest.approx(papier_aandelen["V"] * per_aandeel), (
        "Het bedrag per aandeel is hetzelfde; het aantal aandelen is dat van de "
        "papieren portefeuille."
    )
    assert gerekend < detail[0]["bedrag_usd"], (
        "Minder aandelen is minder dividend."
    )


def test_dividend_zonder_uitsplitsing_stopt_de_papieren_curve(instap):
    """Zonder bedrag per aandeel is er niets na te rekenen, dus wordt er niets geschat."""
    wissel = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-11-04",
        vorige_uitvoering=instap, nieuwe_tickers=ANDERE_VIJF,
        koersen_usd=dict(KOERS), fx_eurusd=FX, spy_koers_usd=KOERS["SPY"],
        fx_source="test", fx_asof="2026-11-04T21:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-11-04", FX),
        dividend_cash_usd=40.0, dividend_conventie="bruto, test")

    with pytest.raises(ValueError, match="uitsplitsing"):
        re.papieren_keten([instap, wissel])


def test_het_verloop_van_de_papieren_curve_blijft_onder_de_officiele(instap):
    wissel = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-10-20",
        vorige_uitvoering=instap, nieuwe_tickers=ANDERE_VIJF,
        koersen_usd=dict(KOERS), fx_eurusd=FX, spy_koers_usd=KOERS["SPY"],
        fx_source="test", fx_asof="2026-10-20T20:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-10-20", FX))

    dagen = pd.date_range("2026-10-06", "2026-10-30", freq="B")
    kolommen = sorted(set(VIJF) | set(ANDERE_VIJF) | {"SPY"})
    koersen = pd.DataFrame(
        [[KOERS[t] for t in kolommen] for _ in dagen], index=dagen, columns=kolommen)
    fx = pd.Series([FX] * len(dagen), index=dagen)

    officieel = hb.bouw_verloop_keten([instap, wissel], koersen, fx)
    papier = re.bouw_verloop_papier([instap, wissel], koersen, fx)

    assert len(papier) == len(officieel)
    laatste_dag = officieel.index[-1]
    assert papier.loc[laatste_dag, "portefeuille_eur"] < \
        officieel.loc[laatste_dag, "portefeuille_eur"]
    assert papier.loc[laatste_dag, "spy_eur"] == pytest.approx(
        officieel.loc[laatste_dag, "spy_eur"]), (
        "SPY wisselt niet en is in beide curves hetzelfde fonds."
    )
