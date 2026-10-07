"""Wachters op de Belgische laag.

Deze laag is een AFGELEIDE simulatie: dezelfde trades als Strategie A, met de
Belgische beurstaks, de brokerkosten, de wisselkosten en de Belgische belasting
op dividend en op gerealiseerde winst erbij. Ze mag de officiele curve nooit
veranderen, en dat wordt hieronder letterlijk nagerekend.

Twee dingen worden met opzet op twee niveaus getest:

  * de fiscale rekenregels los, met bedragen die groot genoeg zijn om de
    vrijstellingen te raken. Met 1.000 euro kom je nooit aan een meerwaarde van
    4.855 euro, dus zou dat deel van de wet anders nooit getest worden;
  * de hele keten, met de bedragen die er werkelijk zijn.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sw import belgie as be
from sw import herbalans as hb
from sw import portfolio as pf
from sw import realistisch as rl
from tests.hulp_fx import bewijs_voor

VIJF = ["A", "B", "C", "D", "E"]
ANDERE_VIJF = ["V", "W", "X", "Y", "Z"]
KOERS = {t: 100.0 for t in VIJF + ANDERE_VIJF}
KOERS["SPY"] = 500.0
FX = 1.10

REGELS = be.BE_TAX_RULES_2026_V1


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


def wissel_na(vorige, datum, nieuwe_tickers, koersen, nummer=2, **extra):
    return hb.bereken_herbalans(
        entry_hash=f"signaal-{nummer}",
        execution_date=datum,
        vorige_uitvoering=vorige,
        nieuwe_tickers=nieuwe_tickers,
        koersen_usd=dict(koersen),
        fx_eurusd=FX,
        spy_koers_usd=koersen["SPY"],
        fx_source="test",
        fx_asof=f"{datum}T21:00:00+00:00",
        fx_bewijs=bewijs_voor(datum, FX),
        **extra,
    )


# ===================================================== de regels zelf
def test_de_regelversie_heeft_een_naam():
    """Een wetswijziging in 2027 mag 2026 niet stil veranderen."""
    assert REGELS.naam == "BE_TAX_RULES_2026_V1"
    assert be.REGELS_NU is REGELS


def test_brokerkosten_staan_standaard_op_nul_en_dat_is_zichtbaar():
    """Geen verzonnen brokerkosten, en geen stilte over het feit dat er geen zijn."""
    assert REGELS.broker_fixed_fee_per_order_eur == 0.0
    assert REGELS.broker_variable_fee_pct == 0.0
    assert REGELS.broker_minimum_fee_eur == 0.0
    assert REGELS.broker_ingesteld is False
    assert be.brokerkost_eur(REGELS, 200.0) == 0.0
    assert be.HERKOMST["broker_fixed_fee_per_order_eur"]["status"] == \
        be.STATUS_NIET_INGESTELD


def test_fx_kosten_staan_standaard_op_nul_en_dat_is_zichtbaar():
    assert REGELS.fx_conversion_fee_pct == 0.0
    assert REGELS.fx_kosten_ingesteld is False
    assert be.fx_kost_eur(REGELS, 1000.0) == 0.0
    assert be.HERKOMST["fx_conversion_fee_pct"]["status"] == be.STATUS_NIET_INGESTELD


def test_een_brokerconfiguratie_kan_er_zonder_bouwwerk_in(instap):
    """De laag moet later aan een echte broker gekoppeld kunnen worden."""
    met_broker = be.met(
        REGELS,
        naam="BE_TAX_RULES_2026_V1+broker-test",
        broker_fixed_fee_per_order_eur=2.0,
        broker_variable_fee_pct=0.05,
        broker_minimum_fee_eur=3.0,
        fx_conversion_fee_pct=0.25,
    )
    assert met_broker.broker_ingesteld is True
    assert be.brokerkost_eur(met_broker, 200.0) == pytest.approx(3.0), (
        "2 + 0,05 % van 200 = 2,10, dus het minimum van 3 euro geldt."
    )
    assert be.brokerkost_eur(met_broker, 10000.0) == pytest.approx(7.0)

    zonder = be.belgische_keten([instap], regels=REGELS)
    met = be.belgische_keten([instap], regels=met_broker)
    assert met["kosten_totaal"]["broker_eur"] > 0
    assert met["kosten_totaal"]["fx_eur"] > 0
    assert met["kosten_totaal"]["totaal_eur"] > zonder["kosten_totaal"]["totaal_eur"]
    assert REGELS.broker_ingesteld is False, "De standaardregels blijven ongemoeid."


# ============================================================== de beurstaks
def test_de_beurstaks_is_0_35_procent_per_order():
    assert be.tob_eur(REGELS, "A", 200.0) == pytest.approx(0.70)
    assert be.tob_tarief(REGELS, "A").pct == 0.35


def test_de_beurstaks_wordt_per_order_geheven_en_niet_op_het_totaal():
    """200 euro verkopen en 200 euro kopen is twee keer de taks op 200 euro."""
    verkoop = be.tob_eur(REGELS, "A", 200.0)
    aankoop = be.tob_eur(REGELS, "V", 200.0)
    assert verkoop + aankoop == pytest.approx(1.40)
    assert verkoop + aankoop == pytest.approx(be.tob_eur(REGELS, "A", 400.0)), (
        "Twee orders van 200 kosten evenveel taks als een order van 400 - maar "
        "het hoort wel per order gerekend te worden, want pas dan werkt het "
        "maximum per verrichting."
    )


def test_het_wettelijke_maximum_per_verrichting_geldt():
    assert be.tob_eur(REGELS, "A", 1_000_000.0) == pytest.approx(1600.0)


def test_het_tarief_is_per_instrumenttype_instelbaar():
    regels = be.met(
        REGELS,
        naam="test-fonds",
        instrumenttype_per_ticker={"IWDA": "fonds_kapitalisatie_be"},
    )
    assert be.tob_eur(regels, "IWDA", 200.0) == pytest.approx(2.64)
    assert be.tob_eur(regels, "A", 200.0) == pytest.approx(0.70)


def test_een_onbekend_instrumenttype_wordt_niet_geraden():
    regels = be.met(REGELS, naam="test", instrumenttype_per_ticker={"X": "warrant"})
    with pytest.raises(ValueError, match="beurstakstarief"):
        be.tob_eur(regels, "X", 100.0)


# =================================================== orders in de hele keten
def test_bij_de_instap_wordt_er_alleen_gekocht_dus_alleen_koop_taks(instap):
    uit = be.belgische_keten([instap])
    assert [o["kant"] for o in uit["orders"]] == ["koop"] * 5
    assert uit["verkopen"] == [], "Er is niets verkocht, dus niets gerealiseerd."

    # 0,35 % + 0,15 % over het belegde bedrag, en de kosten komen van dat bedrag
    # af: 1.000 / 1,005 = 995,02 belegd.
    assert uit["kosten_totaal"]["tob_eur"] == pytest.approx(3.4826, abs=1e-4)
    assert uit["kosten_totaal"]["basis_eur"] == pytest.approx(1.4925, abs=1e-4)
    assert uit["kosten_totaal"]["totaal_eur"] == pytest.approx(4.9751, abs=1e-4)


def test_een_volledige_rotatie_betaalt_taks_aan_beide_kanten(instap):
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)
    uit = be.belgische_keten([instap, wissel])

    van_de_wissel = [o for o in uit["orders"] if o["datum"] == "2026-11-04"]
    assert sorted(o["kant"] for o in van_de_wissel) == ["koop"] * 5 + ["verkoop"] * 5

    verkocht = sum(o["bedrag_eur"] for o in van_de_wissel if o["kant"] == "verkoop")
    gekocht = sum(o["bedrag_eur"] for o in van_de_wissel if o["kant"] == "koop")
    taks = sum(o["tob_eur"] for o in van_de_wissel)

    assert verkocht == pytest.approx(995.02, abs=0.05)
    assert taks == pytest.approx((verkocht + gekocht) * 0.0035, abs=1e-6), (
        "De taks staat op de som van alle orderbedragen, elk apart gerekend."
    )
    assert taks == pytest.approx(6.93, abs=0.02), (
        "Een volledige wissel kost ongeveer 0,70 % beurstaks: 0,35 % verkopen "
        "plus 0,35 % kopen."
    )


def test_een_gedeeltelijke_rotatie_belast_alleen_wat_er_beweegt(instap):
    """Drie aandelen blijven staan; alleen het verschil wordt verhandeld."""
    koersen = dict(KOERS)
    koersen["A"] = 150.0        # 50 % erbij
    koersen["B"] = 50.0         # 50 % eraf
    wissel = wissel_na(instap, "2026-11-04", ["A", "B", "C", "V", "W"], koersen)

    uit = be.belgische_keten([instap, wissel])
    van_de_wissel = [o for o in uit["orders"] if o["datum"] == "2026-11-04"]
    per_ticker = {o["ticker"]: o for o in van_de_wissel}

    assert per_ticker["A"]["kant"] == "verkoop", "A is te zwaar geworden."
    assert per_ticker["B"]["kant"] == "koop", "B is te licht geworden."
    assert per_ticker["D"]["kant"] == "verkoop"
    assert per_ticker["V"]["kant"] == "koop"

    volledig = be.belgische_keten(
        [instap, wissel_na(instap, "2026-11-04", ANDERE_VIJF, koersen)])
    assert uit["kosten_totaal"]["tob_eur"] < volledig["kosten_totaal"]["tob_eur"], (
        "Wat blijft staan, wordt niet verhandeld en betaalt dus geen taks."
    )


def test_een_aandeel_dat_precies_op_gewicht_blijft_geeft_geen_order(instap):
    """Vijf gelijke koersen en dezelfde vijf aandelen: er beweegt niets."""
    wissel = wissel_na(instap, "2026-11-04", VIJF, KOERS)
    uit = be.belgische_keten([instap, wissel])

    van_de_wissel = [o for o in uit["orders"] if o["datum"] == "2026-11-04"]
    assert van_de_wissel == [], (
        "Geen order is geen beurstaks en geen brokerkost."
    )
    assert uit["verkopen"] == []


# ======================================================== FIFO en meerwaarde
def test_fifo_verkoopt_het_oudste_pakketje_eerst():
    posities = be.Posities()
    posities.koop("A", "2026-10-06", shares=10.0, kost_eur=100.0)   # 10 euro per stuk
    posities.koop("A", "2026-11-04", shares=10.0, kost_eur=200.0)   # 20 euro per stuk

    gerealiseerd = posities.verkoop("A", "2026-12-02", shares=10.0, opbrengst_eur=250.0)

    assert len(gerealiseerd) == 1
    assert gerealiseerd[0]["koop_datum"] == "2026-10-06", "Het oudste pakketje eerst."
    assert gerealiseerd[0]["kostprijs_eur"] == pytest.approx(100.0)
    assert gerealiseerd[0]["resultaat_eur"] == pytest.approx(150.0)
    assert posities.aantal("A") == pytest.approx(10.0)
    assert posities.kostprijs_eur("A") == pytest.approx(200.0)


def test_fifo_over_twee_pakketjes_tegelijk():
    posities = be.Posities()
    posities.koop("A", "2026-10-06", shares=10.0, kost_eur=100.0)
    posities.koop("A", "2026-11-04", shares=10.0, kost_eur=200.0)

    gerealiseerd = posities.verkoop("A", "2026-12-02", shares=15.0, opbrengst_eur=300.0)

    assert [g["koop_datum"] for g in gerealiseerd] == ["2026-10-06", "2026-11-04"]
    assert sum(g["shares"] for g in gerealiseerd) == pytest.approx(15.0)
    assert sum(g["kostprijs_eur"] for g in gerealiseerd) == pytest.approx(200.0)
    assert sum(g["opbrengst_eur"] for g in gerealiseerd) == pytest.approx(300.0)
    assert posities.aantal("A") == pytest.approx(5.0)


def test_er_kan_niet_meer_verkocht_worden_dan_er_is():
    posities = be.Posities()
    posities.koop("A", "2026-10-06", shares=1.0, kost_eur=100.0)
    with pytest.raises(ValueError, match="shorten"):
        posities.verkoop("A", "2026-11-04", shares=2.0, opbrengst_eur=200.0)


def test_een_gerealiseerde_winst_komt_in_het_jaar_van_de_verkoop(instap):
    koersen = {t: 120.0 for t in VIJF}       # 20 procent erbij
    koersen.update({t: 100.0 for t in ANDERE_VIJF})
    koersen["SPY"] = 500.0
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, koersen)

    uit = be.belgische_keten([instap, wissel])
    jaar = uit["meerwaarde_per_jaar"][2026]

    assert jaar["meerwaarden_eur"] == pytest.approx(0.20 * 995.02, abs=0.5)
    assert jaar["minderwaarden_eur"] == pytest.approx(0.0)
    assert jaar["netto_gerealiseerd_eur"] > 0
    assert jaar["belasting_eur"] == pytest.approx(0.0), (
        "Onder de vrijstelling van 4.855 euro is er geen belasting."
    )


def test_een_gerealiseerd_verlies_komt_als_minderwaarde(instap):
    koersen = {t: 80.0 for t in VIJF}        # 20 procent eraf
    koersen.update({t: 100.0 for t in ANDERE_VIJF})
    koersen["SPY"] = 500.0
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, koersen)

    jaar = be.belgische_keten([instap, wissel])["meerwaarde_per_jaar"][2026]

    assert jaar["minderwaarden_eur"] == pytest.approx(0.20 * 995.02, abs=0.5)
    assert jaar["meerwaarden_eur"] == pytest.approx(0.0)
    assert jaar["netto_gerealiseerd_eur"] < 0
    assert jaar["belasting_eur"] == pytest.approx(0.0), (
        "Een verlies geeft geen belasting - en ook geen teruggave."
    )


def test_winst_en_verlies_in_hetzelfde_jaar_gaan_tegen_elkaar_af(instap):
    """Twee aandelen flink omhoog, twee flink omlaag, in hetzelfde jaar."""
    koersen = dict(KOERS)
    koersen.update({"A": 150.0, "B": 150.0, "C": 50.0, "D": 50.0, "E": 100.0})
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, koersen)

    jaar = be.belgische_keten([instap, wissel])["meerwaarde_per_jaar"][2026]

    assert jaar["meerwaarden_eur"] > 0
    assert jaar["minderwaarden_eur"] > 0
    assert jaar["netto_gerealiseerd_eur"] == pytest.approx(
        jaar["meerwaarden_eur"] - jaar["minderwaarden_eur"], abs=1e-6)
    assert jaar["netto_gerealiseerd_eur"] == pytest.approx(0.0, abs=1.0), (
        "Twee keer plus 50 % en twee keer min 50 % heffen elkaar op."
    )


def test_fifo_over_twee_pakketjes_binnen_de_keten(instap):
    """Een aandeel blijft staan, wordt bijgekocht, en gaat er later uit.

    Dan liggen er twee pakketjes met een verschillende prijs, en moet de
    verkoop ze allebei raken - het oudste eerst. Dat is het geval waarin FIFO
    pas echt iets doet.
    """
    goedkoper = dict(KOERS)
    goedkoper["A"] = 50.0                       # A halveert, dus wordt bijgekocht
    eerste = wissel_na(instap, "2026-11-04", ["A", "V", "W", "X", "Y"], goedkoper)

    duurder = dict(KOERS)
    duurder["A"] = 150.0                        # en gaat er daarna uit, hoger
    tweede = wissel_na(eerste, "2026-12-02", ANDERE_VIJF, duurder, nummer=3)

    uit = be.belgische_keten([instap, eerste, tweede])
    verkopen_a = [v for v in uit["verkopen"]
                  if v["ticker"] == "A" and v["verkoop_datum"] == "2026-12-02"]

    assert len(verkopen_a) == 2, "De verkoop raakt allebei de pakketjes."
    assert [v["koop_datum"] for v in verkopen_a] == ["2026-10-06", "2026-11-04"], (
        "Het oudste pakketje gaat eerst."
    )
    assert verkopen_a[0]["kostprijs_eur"] > verkopen_a[1]["kostprijs_eur"], (
        "Het eerste pakketje is tegen 100 dollar gekocht, het tweede tegen 50."
    )
    assert all(v["resultaat_eur"] > 0 for v in verkopen_a)
    assert verkopen_a[1]["resultaat_eur"] > verkopen_a[0]["resultaat_eur"], (
        "Het goedkoop gekochte pakketje levert de grootste winst op."
    )


def test_een_verlies_van_het_ene_jaar_verrekent_niet_met_winst_van_het_andere(instap):
    """Een wissel in december en een in januari, met winst en verlies."""
    hoger = {t: 130.0 for t in VIJF}
    hoger.update({t: 100.0 for t in ANDERE_VIJF})
    hoger["SPY"] = 500.0
    december = wissel_na(instap, "2026-12-02", ANDERE_VIJF, hoger)

    lager = dict(KOERS)
    lager.update({t: 70.0 for t in ANDERE_VIJF})
    januari = wissel_na(december, "2027-01-05", VIJF, lager, nummer=3)

    jaren = be.belgische_keten([instap, december, januari])["meerwaarde_per_jaar"]

    assert sorted(jaren) == [2026, 2027]
    assert jaren[2026]["meerwaarden_eur"] > 0
    assert jaren[2026]["minderwaarden_eur"] == pytest.approx(0.0)
    assert jaren[2027]["minderwaarden_eur"] > 0
    assert jaren[2027]["meerwaarden_eur"] == pytest.approx(0.0)
    assert jaren[2026]["netto_gerealiseerd_eur"] > 0, (
        "Het verlies van 2027 mag de winst van 2026 niet verlagen."
    )
    assert jaren[2027]["belasting_eur"] == pytest.approx(0.0)
    assert jaren[2027]["gebruikte_vrijstelling_eur"] == pytest.approx(0.0), (
        "Een verliesjaar gebruikt geen vrijstelling."
    )


def test_dividendgeld_dat_meebelegd_wordt_betaalt_maar_een_keer_beurstaks(instap):
    """Contant dividend gaat in de koopkant van de wissel, en nergens anders.

    Zou het ook aan de verkoopkant meegerekend worden, dan betaalt hetzelfde
    geld twee keer beurstaks.
    """
    dividenden = [{
        "ticker": "A", "ex_date": "2026-10-20", "pay_date": "2026-10-30",
        "gross_per_share_usd": 4.0, "source": "test",
    }]
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)
    uit = be.belgische_keten([instap, wissel], dividenden=dividenden)

    contant_usd = float(uit["dividenden"][0]["netto_usd"])
    assert contant_usd > 0

    van_de_wissel = [o for o in uit["orders"] if o["datum"] == "2026-11-04"]
    verkocht = sum(o["bedrag_usd"] for o in van_de_wissel if o["kant"] == "verkoop")
    gekocht = sum(o["bedrag_usd"] for o in van_de_wissel if o["kant"] == "koop")
    kosten_usd = sum(o["totaal_eur"] for o in van_de_wissel) * FX

    assert gekocht == pytest.approx(verkocht + contant_usd - kosten_usd, abs=1e-4), (
        "Het dividendgeld zit alleen in de koopkant."
    )
    taks = sum(o["tob_eur"] for o in van_de_wissel)
    assert taks == pytest.approx((verkocht + gekocht) / FX * 0.0035, abs=1e-6)


# ============================= de meerwaardebelasting los, met echte bedragen
def test_de_vrijstelling_van_4855_euro_wordt_eerst_opgebruikt():
    verkopen = [{"verkoop_datum": "2026-11-04", "resultaat_eur": 4000.0}]
    jaar = be.meerwaardejaren(verkopen, REGELS)[2026]

    assert jaar["vrijstelling_beschikbaar_eur"] == pytest.approx(4855.0)
    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(4000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(0.0)
    assert jaar["belasting_eur"] == pytest.approx(0.0)


def test_boven_de_vrijstelling_geldt_tien_procent():
    verkopen = [{"verkoop_datum": "2026-11-04", "resultaat_eur": 10_000.0}]
    jaar = be.meerwaardejaren(verkopen, REGELS)[2026]

    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(4855.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(5145.0)
    assert jaar["tarief_pct"] == 10.0
    assert jaar["belasting_eur"] == pytest.approx(514.50)


def test_minderwaarden_van_hetzelfde_jaar_gaan_eerst_van_de_meerwaarden_af():
    verkopen = [
        {"verkoop_datum": "2026-05-04", "resultaat_eur": 10_000.0},
        {"verkoop_datum": "2026-11-04", "resultaat_eur": -3_000.0},
    ]
    jaar = be.meerwaardejaren(verkopen, REGELS)[2026]

    assert jaar["meerwaarden_eur"] == pytest.approx(10_000.0)
    assert jaar["minderwaarden_eur"] == pytest.approx(3_000.0)
    assert jaar["netto_gerealiseerd_eur"] == pytest.approx(7_000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(2_145.0)
    assert jaar["belasting_eur"] == pytest.approx(214.50)


def test_een_verlies_gaat_niet_over_naar_het_volgende_jaar():
    verkopen = [
        {"verkoop_datum": "2026-11-04", "resultaat_eur": -8_000.0},
        {"verkoop_datum": "2027-03-02", "resultaat_eur": 10_000.0},
    ]
    jaren = be.meerwaardejaren(verkopen, REGELS)

    assert jaren[2026]["belasting_eur"] == pytest.approx(0.0)
    assert jaren[2027]["belastbare_basis_eur"] == pytest.approx(5_145.0), (
        "Het verlies van 2026 verlaagt de basis van 2027 niet."
    )


def test_een_elders_gebruikte_meerwaardevrijstelling_vermindert_de_onze():
    regels = be.met(
        REGELS,
        naam="BE_TAX_RULES_2026_V1+extern",
        external_capital_gain_exemption_used_eur=4_000.0,
    )
    verkopen = [{"verkoop_datum": "2026-11-04", "resultaat_eur": 5_000.0}]
    jaar = be.meerwaardejaren(verkopen, regels)[2026]

    assert jaar["vrijstelling_beschikbaar_eur"] == pytest.approx(855.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(4_145.0)
    assert jaar["belasting_eur"] == pytest.approx(414.50)


def test_een_volledig_elders_gebruikte_vrijstelling_laat_niets_over():
    regels = be.met(
        REGELS, naam="test", external_capital_gain_exemption_used_eur=9_000.0)
    jaar = be.meerwaardejaren(
        [{"verkoop_datum": "2026-11-04", "resultaat_eur": 1_000.0}], regels)[2026]

    assert jaar["vrijstelling_beschikbaar_eur"] == pytest.approx(0.0)
    assert jaar["belasting_eur"] == pytest.approx(100.0)


# ================================================================== dividend
def test_de_buitenlandse_bronheffing_wordt_niet_twee_keer_belast():
    """Belgie heft 30 procent op wat er na de Amerikaanse heffing overblijft."""
    uit = be.belast_dividend(REGELS, "A", 100.0)

    assert uit["bronheffing_pct"] == 15.0
    assert uit["bronheffing"] == pytest.approx(15.0)
    assert uit["belgische_basis"] == pytest.approx(85.0)
    assert uit["rv"] == pytest.approx(25.50), (
        "30 % van 85, niet van 100. Anders wordt de Amerikaanse heffing een "
        "tweede keer belast."
    )
    assert uit["netto"] == pytest.approx(59.50)


def test_de_bronheffing_is_per_land_instelbaar():
    regels = be.met(
        REGELS,
        naam="test-landen",
        foreign_withholding_pct={"US": 15.0, "BE": 0.0},
        land_per_ticker={"PROX": "BE"},
    )
    assert be.belast_dividend(regels, "PROX", 100.0)["netto"] == pytest.approx(70.0)
    assert be.belast_dividend(regels, "A", 100.0)["netto"] == pytest.approx(59.50)


def test_een_onbekend_land_wordt_niet_geraden():
    regels = be.met(REGELS, naam="test", land_per_ticker={"ASML": "NL"})
    with pytest.raises(ValueError, match="bronheffing"):
        be.belast_dividend(regels, "ASML", 100.0)


def test_dividend_onder_de_vrijstelling_wordt_volledig_terugvorderbaar():
    uitkeringen = [{
        "pay_date": "2026-11-10", "bruto_eur": 100.0, "bronheffing_eur": 15.0,
        "belgische_basis_eur": 85.0, "rv_eur": 25.50, "netto_eur": 59.50,
    }]
    jaar = be.dividendjaren(uitkeringen, REGELS)[2026]

    assert jaar["vrijgesteld_deel_eur"] == pytest.approx(100.0)
    assert jaar["terug_te_vorderen_eur"] == pytest.approx(25.50), (
        "De hele Belgische voorheffing komt terug, en niet 30 % van bruto - er "
        "is maar 25,50 ingehouden."
    )
    assert jaar["netto_na_terugvordering_eur"] == pytest.approx(85.0)


def test_dividend_boven_de_vrijstelling_komt_maar_gedeeltelijk_terug():
    """1.000 euro bruto, waarvan 833 euro vrijgesteld."""
    uitkeringen = [{
        "pay_date": "2026-11-10", "bruto_eur": 1000.0, "bronheffing_eur": 150.0,
        "belgische_basis_eur": 850.0, "rv_eur": 255.0, "netto_eur": 595.0,
    }]
    jaar = be.dividendjaren(uitkeringen, REGELS)[2026]

    assert jaar["vrijgesteld_deel_eur"] == pytest.approx(833.0)
    assert jaar["terug_te_vorderen_eur"] == pytest.approx(255.0 * 0.833)
    assert jaar["terug_te_vorderen_eur"] < 255.0


def test_een_elders_gebruikte_dividendvrijstelling_vermindert_de_onze():
    regels = be.met(
        REGELS,
        naam="BE_TAX_RULES_2026_V1+extern",
        external_dividend_exemption_used_eur=600.0,
    )
    uitkeringen = [{
        "pay_date": "2026-11-10", "bruto_eur": 500.0, "bronheffing_eur": 75.0,
        "belgische_basis_eur": 425.0, "rv_eur": 127.50, "netto_eur": 297.50,
    }]
    jaar = be.dividendjaren(uitkeringen, regels)[2026]

    assert jaar["vrijstelling_beschikbaar_eur"] == pytest.approx(233.0)
    assert jaar["vrijgesteld_deel_eur"] == pytest.approx(233.0)
    assert jaar["terug_te_vorderen_eur"] == pytest.approx(127.50 * 233.0 / 500.0)


def test_meerdere_uitkeringen_in_hetzelfde_jaar_tellen_samen_voor_de_vrijstelling():
    uitkeringen = [
        {"pay_date": "2026-03-10", "bruto_eur": 500.0, "bronheffing_eur": 75.0,
         "belgische_basis_eur": 425.0, "rv_eur": 127.50, "netto_eur": 297.50},
        {"pay_date": "2026-06-10", "bruto_eur": 500.0, "bronheffing_eur": 75.0,
         "belgische_basis_eur": 425.0, "rv_eur": 127.50, "netto_eur": 297.50},
        {"pay_date": "2027-03-10", "bruto_eur": 500.0, "bronheffing_eur": 75.0,
         "belgische_basis_eur": 425.0, "rv_eur": 127.50, "netto_eur": 297.50},
    ]
    jaren = be.dividendjaren(uitkeringen, REGELS)

    assert jaren[2026]["aantal_uitkeringen"] == 2
    assert jaren[2026]["bruto_eur"] == pytest.approx(1000.0)
    assert jaren[2026]["vrijgesteld_deel_eur"] == pytest.approx(833.0), (
        "De vrijstelling geldt per jaar, niet per uitkering."
    )
    assert jaren[2027]["vrijgesteld_deel_eur"] == pytest.approx(500.0), (
        "Het volgende jaar begint met een volle vrijstelling."
    )


def test_dividend_in_de_keten_komt_netto_in_de_portefeuille(instap):
    """Het ingehouden deel komt nooit op de rekening, dus ook niet in de curve."""
    dividenden = [{
        "ticker": "A", "ex_date": "2026-10-20", "pay_date": "2026-10-30",
        "gross_per_share_usd": 1.0, "source": "test",
    }]
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)

    uit = be.belgische_keten([instap, wissel], dividenden=dividenden)
    assert len(uit["dividenden"]) == 1
    uitkering = uit["dividenden"][0]

    aandelen_a = next(
        p["shares"] for p in uit["stappen"][0]["positions"] if p["ticker"] == "A")
    assert uitkering["shares"] == pytest.approx(aandelen_a), (
        "Het recht wordt met de EIGEN aantallen van deze laag gerekend."
    )
    assert uitkering["bruto_usd"] == pytest.approx(aandelen_a)
    assert uitkering["netto_usd"] == pytest.approx(aandelen_a * 0.595)

    officieel = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date="2026-11-04",
        vorige_uitvoering=instap, nieuwe_tickers=ANDERE_VIJF,
        koersen_usd=dict(KOERS), fx_eurusd=FX, spy_koers_usd=KOERS["SPY"],
        fx_source="test", fx_asof="2026-11-04T21:00:00+00:00",
        fx_bewijs=bewijs_voor("2026-11-04", FX),
        dividend_cash_usd=10.0, dividend_conventie="bruto, test")
    assert float(officieel["opening"]["dividend_cash_usd"]) == pytest.approx(10.0), (
        "De officiele curve blijft bruto rekenen."
    )


def test_dividend_van_een_verkocht_aandeel_komt_toch_binnen(instap):
    """Ex-datum voor de wissel, betaaldatum erna: het geld komt alsnog."""
    dividenden = [{
        "ticker": "A", "ex_date": "2026-10-20", "pay_date": "2026-11-20",
        "gross_per_share_usd": 1.0, "source": "test",
    }]
    eerste = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)
    tweede = wissel_na(eerste, "2026-12-02", VIJF, KOERS, nummer=3)

    uit = be.belgische_keten([instap, eerste, tweede], dividenden=dividenden)
    assert len(uit["dividenden"]) == 1
    assert uit["dividenden"][0]["pay_date"] == "2026-11-20"
    assert uit["dividenden"][0]["netto_usd"] > 0, (
        "A was op de ex-dag in bezit; dat het later verkocht is, verandert het "
        "recht niet."
    )


# ============================================ niets per trade uit de portefeuille
def test_de_meerwaardebelasting_gaat_niet_per_trade_van_de_portefeuille_af(instap):
    """De broker houdt die belasting niet in; ze is een aparte raming."""
    koersen = {t: 500.0 for t in VIJF}       # vijf keer over de kop
    koersen.update({t: 100.0 for t in ANDERE_VIJF})
    koersen["SPY"] = 500.0

    regels = be.met(
        REGELS, naam="test-zonder-vrijstelling", meerwaarde_vrijstelling_eur=0.0)
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, koersen)
    uit = be.belgische_keten([instap, wissel], regels=regels)

    belasting = uit["meerwaarde_per_jaar"][2026]["belasting_eur"]
    assert belasting > 0, "Zonder vrijstelling is er wel belasting."

    waardering = be.waardeer_belgisch(uit, koersen, FX)
    belegd = sum(
        p["shares"] * koersen[p["ticker"]] for p in uit["stappen"][-1]["positions"])

    assert waardering["portefeuille_eur"] == pytest.approx(
        (belegd + uit["contant_usd"]) / FX, abs=1e-6), (
        "In de portefeuillewaarde zit geen meerwaardebelasting."
    )
    assert waardering["netto_eur"] == pytest.approx(
        waardering["portefeuille_eur"] - belasting, abs=1e-6), (
        "De belasting staat apart, als fiscale reserve."
    )
    assert waardering["netto_eur"] < waardering["portefeuille_eur"]


def test_de_waardering_noemt_de_winst_die_nog_niet_verkocht_is(instap):
    """Op winst die nog in de portefeuille zit, staat nog geen belasting."""
    uit = be.belgische_keten([instap])
    hoger = {t: 150.0 for t in VIJF}
    hoger["SPY"] = 500.0

    waardering = be.waardeer_belgisch(uit, hoger, FX)
    assert waardering["latente_meerwaarde_eur"] == pytest.approx(
        0.50 * 995.02, abs=0.5)
    assert waardering["meerwaardebelasting_eur"] == pytest.approx(0.0)
    assert waardering["netto_eur"] == pytest.approx(waardering["portefeuille_eur"])


# ============================================== de officiele curve blijft heel
def test_de_belgische_laag_verandert_de_officiele_records_niet(instap):
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)
    voor = (instap["exec_hash"], wissel["exec_hash"],
            instap["canonical_payload"], wissel["canonical_payload"])

    be.belgische_keten([instap, wissel], dividenden=[{
        "ticker": "A", "ex_date": "2026-10-20", "pay_date": "2026-10-30",
        "gross_per_share_usd": 1.0, "source": "test"}])

    na = (instap["exec_hash"], wissel["exec_hash"],
          instap["canonical_payload"], wissel["canonical_payload"])
    assert voor == na, (
        "De Belgische laag wordt elke keer opnieuw gerekend en raakt het "
        "bewijsmateriaal niet aan."
    )


def test_de_belgische_laag_verandert_de_officiele_curve_niet(instap):
    wissel = wissel_na(instap, "2026-10-20", ANDERE_VIJF, KOERS)
    dagen = pd.date_range("2026-10-06", "2026-10-30", freq="B")
    kolommen = sorted(set(VIJF) | set(ANDERE_VIJF) | {"SPY"})
    koersen = pd.DataFrame(
        [[KOERS[t] for t in kolommen] for _ in dagen], index=dagen, columns=kolommen)
    fx = pd.Series([FX] * len(dagen), index=dagen)

    voor = hb.bouw_verloop_keten([instap, wissel], koersen, fx)
    be.bouw_verloop_belgie([instap, wissel], koersen, fx)
    na = hb.bouw_verloop_keten([instap, wissel], koersen, fx)

    pd.testing.assert_frame_equal(voor, na)


def test_de_belgische_curve_blijft_onder_de_officiele_en_de_realistische(instap):
    wissel = wissel_na(instap, "2026-10-20", ANDERE_VIJF, KOERS)
    dagen = pd.date_range("2026-10-06", "2026-10-30", freq="B")
    kolommen = sorted(set(VIJF) | set(ANDERE_VIJF) | {"SPY"})
    koersen = pd.DataFrame(
        [[KOERS[t] for t in kolommen] for _ in dagen], index=dagen, columns=kolommen)
    fx = pd.Series([FX] * len(dagen), index=dagen)

    officieel = hb.bouw_verloop_keten([instap, wissel], koersen, fx)
    papier = rl.bouw_verloop_papier([instap, wissel], koersen, fx)
    belgisch = be.bouw_verloop_belgie([instap, wissel], koersen, fx)

    dag = officieel.index[-1]
    assert belgisch.loc[dag, "portefeuille_eur"] < papier.loc[dag, "portefeuille_eur"]
    assert papier.loc[dag, "portefeuille_eur"] < \
        officieel.loc[dag, "portefeuille_eur"]


def test_de_belgische_curve_toont_geen_maatstaf(instap):
    """SPY is hier geen Belgische praktijkbenchmark, dus er staat geen kolom."""
    dagen = pd.date_range("2026-10-06", "2026-10-16", freq="B")
    kolommen = sorted(set(VIJF) | {"SPY"})
    koersen = pd.DataFrame(
        [[KOERS[t] for t in kolommen] for _ in dagen], index=dagen, columns=kolommen)
    fx = pd.Series([FX] * len(dagen), index=dagen)

    belgisch = be.bouw_verloop_belgie([instap], koersen, fx)
    assert "portefeuille_eur" in belgisch.columns
    for kolom in ("spy_eur", "spy_resultaat_pct", "voorsprong_pct"):
        assert kolom not in belgisch.columns
    assert be.BELGISCHE_PRAKTIJKBENCHMARK is None, (
        "Er is nog geen UCITS-instrument gekozen."
    )


def test_de_belgische_keten_is_elke_keer_hetzelfde(instap):
    """Zelfde records in, zelfde getallen uit: niets hangt van het moment af."""
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)
    een = be.belgische_keten([instap, wissel])
    twee = be.belgische_keten([instap, wissel])

    assert een["kosten_totaal"] == twee["kosten_totaal"]
    assert een["orders"] == twee["orders"]
    assert een["verkopen"] == twee["verkopen"]
    assert een["stappen"] == twee["stappen"]


def test_de_marge_op_het_geld_is_zo_strak_als_ze_kan_zijn(instap):
    """Bij een volledige wissel krijgt elk aandeel een order.

    Dan is er niets overgeslagen, en hoort de marge op het geld niet meer te
    zijn dan een cent voor het afronden. Een ruimere marge zou een echte
    rekenfout van tien cent kunnen verbergen.
    """
    wissel = wissel_na(instap, "2026-11-04", ANDERE_VIJF, KOERS)
    uit = be.belgische_keten([instap, wissel])

    stap = uit["stappen"][-1]
    waarde_usd = sum(p["shares"] * KOERS[p["ticker"]] for p in stap["positions"])
    kosten_usd = uit["kosten_totaal"]["totaal_eur"] * FX

    assert float(stap["cash_usd"]) == pytest.approx(0.0, abs=1e-6), (
        "Alles wat niet naar de kosten gaat, zit in de aandelen."
    )
    assert waarde_usd + kosten_usd == pytest.approx(1000.0 * FX, abs=1e-4)


def test_de_belgische_stappen_dragen_geen_controlegetal(instap):
    uit = be.belgische_keten([instap])
    assert uit["stappen"][0]["exec_hash"] == "belgie-1", (
        "Een leesbare naam en geen hash: dit is geen bewijsmateriaal."
    )
    assert "canonical_payload" not in uit["stappen"][0]
    assert uit["stappen"][0]["officieel_exec_hash"] == instap["exec_hash"]


def test_er_verdwijnt_of_ontstaat_geen_geld(instap):
    """Wat erin gaat, komt er als aandelen, kosten of contant geld weer uit."""
    koersen = dict(KOERS)
    koersen.update({"A": 150.0, "B": 50.0})
    wissel = wissel_na(instap, "2026-11-04", ["A", "B", "C", "V", "W"], koersen)
    uit = be.belgische_keten([instap, wissel])

    stap = uit["stappen"][-1]
    waarde_usd = sum(
        p["shares"] * koersen[p["ticker"]] for p in stap["positions"])
    kosten_usd = uit["kosten_totaal"]["totaal_eur"] * FX
    beginwaarde_usd = 1000.0 * FX

    assert waarde_usd + float(stap["cash_usd"]) + kosten_usd == pytest.approx(
        beginwaarde_usd, abs=1e-4), (
        "De koersen van A en B heffen elkaar op, dus blijft alleen de kost over."
    )
