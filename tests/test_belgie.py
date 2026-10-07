"""Wachters op de Belgische laag.

Deze laag is een AFGELEIDE simulatie: dezelfde trades als Strategie A, met de
Belgische beurstaks, de brokerkosten, de wisselkosten en de Belgische belasting
op dividend en op gerealiseerde winst erbij. Ze mag de officiele curve nooit
veranderen, en dat wordt hieronder letterlijk nagerekend.

Twee dingen worden met opzet op twee niveaus getest:

  * de fiscale rekenregels los, met bedragen die groot genoeg zijn om de
    vrijstellingen te raken. Met 1.000 euro kom je nooit aan een meerwaarde van
    10.000 euro, dus zou dat deel van de wet anders nooit getest worden;
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

REGELS = be.BE_TAX_RULES_2026_V2


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
    assert REGELS.naam == "BE_TAX_RULES_2026_V2"
    assert be.REGELS_NU is REGELS


def test_de_vorige_regelversie_blijft_bestaan_als_spoor():
    """V1 is het historische spoor en wordt niet achteraf bijgewerkt.

    Zo blijft narekenbaar met welk bedrag er vóór 8 oktober 2026 gerekend werd.
    """
    assert be.BE_TAX_RULES_2026_V1.naam == "BE_TAX_RULES_2026_V1"
    assert be.BE_TAX_RULES_2026_V1.meerwaarde_vrijstelling_eur == pytest.approx(
        4855.0), "V1 houdt het wettelijke basisbedrag."
    assert be.REGELS_NU is not be.BE_TAX_RULES_2026_V1


def test_de_vrijstelling_op_meerwaarde_is_het_effectieve_bedrag_van_2026():
    """Het basisbedrag van de wettekst is niet wat er vrijgesteld wordt.

    De parlementaire stukken bij de aangenomen wet bepalen dat de vrijstelling
    voor inkomstenjaar 2026 effectief 10.000 euro bedraagt. Dat is het bedrag
    waarmee gerekend hoort te worden.
    """
    assert be.MEERWAARDE_VRIJSTELLING_BASISBEDRAG_EUR == pytest.approx(4855.0)
    assert be.MEERWAARDE_VRIJSTELLING_EFFECTIEF_2026_EUR == pytest.approx(10_000.0)
    assert REGELS.meerwaarde_vrijstelling_eur == pytest.approx(10_000.0)

    herkomst = be.HERKOMST["meerwaarde_vrijstelling_eur"]
    assert herkomst["status"] == be.STATUS_EXACT
    assert "10.000" in herkomst["waarde"]
    assert "56K1244" in herkomst["bron"]


def test_de_dividendvrijstelling_van_833_euro_is_bevestigd():
    assert REGELS.dividend_vrijstelling_eur == pytest.approx(833.0)

    herkomst = be.HERKOMST["dividend_vrijstelling_eur"]
    assert herkomst["status"] == be.STATUS_EXACT
    assert "859" not in str(herkomst), (
        "Het alternatieve bedrag van 859 euro is nagekeken en niet van "
        "toepassing; het hoort niet meer in de herkomst te staan."
    )


def test_de_kosten_blijven_buiten_de_meerwaardebasis_en_dat_staat_vast():
    """Geen aanname meer: de parlementaire toelichting zegt het uitdrukkelijk."""
    assert REGELS.kosten_in_meerwaardebasis is False
    herkomst = be.HERKOMST["kosten_in_meerwaardebasis"]
    assert herkomst["status"] == be.STATUS_EXACT
    assert "56K1244" in herkomst["bron"]


def test_geen_enkele_regel_staat_nog_te_bevestigen():
    """Wat er op het scherm komt, is nagekeken of eerlijk als aanname gemeld."""
    open_punten = [sleutel for sleutel, blok in be.HERKOMST.items()
                   if blok["status"] == be.STATUS_TE_BEVESTIGEN]
    assert open_punten == [], (
        "Deze regels staan nog als 'te bevestigen': " + ", ".join(open_punten)
    )


def test_de_regels_dragen_hun_eigen_inkomstenjaar():
    """De bedragen worden geïndexeerd, dus ze horen bij één jaar.

    Een raming over een ander jaar wordt wel gerekend, maar nooit stil: het
    jaarblok zegt zelf dat de regels er niet bij horen.
    """
    assert REGELS.geldig_voor_inkomstenjaar == 2026

    jaren = be.meerwaardejaren([
        {"verkoop_datum": "2026-11-04", "resultaat_eur": 12_000.0},
        {"verkoop_datum": "2027-03-02", "resultaat_eur": 12_000.0},
    ], REGELS)

    assert jaren[2026]["regels_gelden_voor_dit_jaar"] is True
    assert jaren[2027]["regels_gelden_voor_dit_jaar"] is False, (
        "2027 heeft een eigen, geïndexeerd bedrag en dus een eigen regelversie "
        "nodig. Zolang die er niet is, moet dat zichtbaar zijn."
    )
    assert jaren[2027]["regelversie"] == "BE_TAX_RULES_2026_V2"
    assert jaren[2027]["regels_voor_inkomstenjaar"] == 2026


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
        naam="BE_TAX_RULES_2026_V2+broker-test",
        broker_fixed_fee_per_order_eur=2.0,
        broker_variable_fee_pct=0.05,
        broker_minimum_fee_eur=3.0,
        fx_conversion_fee_pct=0.25,
        # Verplicht zodra er een broker staat: anders betaalt elk order twee
        # keer. Zie de test hieronder.
        basiskost_pct=0.0,
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


def test_een_broker_naast_de_basiskost_kan_niet_ingesteld_worden():
    """Fail-closed: dezelfde kost twee keer rekenen is geen instelling.

    `basiskost_pct` staat op de PLAATS van de brokerkosten zolang er geen broker
    is. Blijft hij staan terwijl er een broker bijkomt, dan betaalt elk order
    twee keer, en dat is aan de cijfers niet te zien. Een waarschuwing in de
    documentatie is niet genoeg; zo'n configuratie bestaat hier niet.
    """
    for wijziging in (
        {"broker_fixed_fee_per_order_eur": 2.0},
        {"broker_variable_fee_pct": 0.25},
        {"broker_minimum_fee_eur": 5.0},
    ):
        with pytest.raises(ValueError, match="twee keer gerekend"):
            be.met(REGELS, naam="broker-zonder-nul", **wijziging)

        # Met de basiskost expliciet op nul kan het wel.
        goed = be.met(REGELS, naam="broker-met-nul", basiskost_pct=0.0, **wijziging)
        assert goed.broker_ingesteld is True
        assert goed.basiskost_pct == 0.0

    # Een niet-nul basiskost naast een broker kan evenmin.
    with pytest.raises(ValueError, match="twee keer gerekend"):
        be.met(REGELS, naam="broker-met-0.15", basiskost_pct=0.15,
               broker_fixed_fee_per_order_eur=2.0)

    # Wisselkosten zijn geen brokerkost per order en mogen dus wel naast de
    # basiskost staan: ze dubbelen niets.
    assert be.met(REGELS, naam="alleen-wissel",
                  fx_conversion_fee_pct=0.25).fx_kosten_ingesteld is True


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


# ================================================= de lijst orders en de kosten
# De kosten hangen van de orders af en de orders van de kosten. Welke aandelen
# een order KRIJGEN hangt er ook van af. De oplossing moet op beide punten bij
# zichzelf passen: de orders in de lijst zijn precies de orders die er zijn.
MIN_ORDER_USD = be.MINIMUM_ORDER_EUR * FX


def _zelfconsistent(uit: dict) -> bool:
    """Levert de uitkomst precies de lijst orders op waarmee ze gerekend is?"""
    return be._orders_boven_de_drempel(uit["orders"], FX) == uit["actief"]


def test_een_order_dat_door_de_kosten_boven_de_cent_komt_telt_mee():
    """A staat precies op zijn doel VOOR de kosten, dus niet erna.

    Zonder kosten zou A's doel 1.000 / 5 = 200 dollar zijn - precies wat hij al
    waard is, dus geen order. De kosten verlagen dat doel, en dan moet er wel
    iets van A verkocht worden. Die kost hoort dus meegerekend te worden.
    """
    huidig = {"A": 200.0, "B": 300.0, "C": 300.0, "D": 100.0, "E": 100.0}
    uit = be._los_kosten_op(REGELS, huidig, list("ABCDE"), 1000.0, FX, 0.15)

    assert uit["actief"] == list("ABCDE")
    assert abs(uit["orders"]["A"]) > MIN_ORDER_USD
    assert [o["ticker"] for o in uit["orderlog"]] == list("ABCDE")
    assert [o for o in uit["orderlog"] if o["ticker"] == "A"][0]["kant"] == "verkoop"
    assert _zelfconsistent(uit)


def test_een_order_dat_door_de_kosten_onder_de_cent_zakt_verdwijnt():
    """De omgekeerde richting: A staat precies op zijn doel NA de kosten.

    Narekenbaar: bij een doelbedrag van 199,50 dollar zijn de vier andere orders
    100,50 + 100,50 + 99,50 + 99,50 dollar. Daar is samen 2 dollar kosten op
    (0,35 % beurstaks plus 0,15 % transactiekost), en (800 - 2) / 4 is weer
    precies 199,50. A staat daar al, dus A krijgt geen order - ook al zou hij er
    zonder kosten een van 40 cent krijgen.
    """
    huidig = {"A": 199.50, "B": 300.0, "C": 300.0, "D": 100.0, "E": 100.0}
    totaal = 999.50

    zonder_kosten = totaal / 5 - 199.50
    assert zonder_kosten > MIN_ORDER_USD, (
        "Zonder kosten zou hier wel een order staan; anders test dit niets."
    )

    uit = be._los_kosten_op(REGELS, huidig, list("ABCDE"), totaal, FX, 0.15)

    assert uit["actief"] == list("BCDE"), "A hoort er niet in te staan."
    assert [o["ticker"] for o in uit["orderlog"]] == list("BCDE")
    assert abs(uit["orders"]["A"]) < MIN_ORDER_USD
    assert _zelfconsistent(uit)


def test_een_minimumkost_per_order_blijft_zelfconsistent():
    """Een minimumkost springt met een sprongetje; de lijst moet blijven kloppen.

    Dit is de configuratie waarin het vroeger mis kon gaan: de lijst werd één
    keer vooraf bepaald en daarna vastgehouden, zodat er een minimumkost van
    vijf euro gerekend kon worden over een order dat er niet was.
    """
    regels = be.met(REGELS, naam="min-5-euro", basiskost_pct=0.0,
                    broker_minimum_fee_eur=5.0)
    huidig = {"A": 194.0, "B": 201.5, "C": 201.5, "D": 201.5, "E": 201.5}
    uit = be._los_kosten_op(regels, huidig, list("ABCDE"), 1000.0, FX, 0.0)

    assert _zelfconsistent(uit)
    assert uit["actief"] == list("ABCDE")
    assert uit["kosten"]["broker_eur"] == pytest.approx(25.0), (
        "Vijf orders, elk het minimum van vijf euro."
    )
    for regel in uit["orderlog"]:
        assert regel["broker_eur"] == pytest.approx(5.0)


def test_een_vaste_kost_per_order_blijft_zelfconsistent():
    regels = be.met(REGELS, naam="vast-2-euro", basiskost_pct=0.0,
                    broker_fixed_fee_per_order_eur=2.0)
    uit = be._los_kosten_op(regels, {}, list("ABCDE"), 1000.0, FX, 0.0)

    assert _zelfconsistent(uit)
    assert uit["kosten"]["broker_eur"] == pytest.approx(10.0), "Vijf keer 2 euro."


def test_het_plafond_op_de_beurstaks_breekt_de_berekening_niet():
    """Boven 457.143 euro per order staat de taks stil op 1.600 euro.

    Een vlak stuk in de kostenfunctie mag de berekening niet laten dwalen.
    """
    uit = be._los_kosten_op(REGELS, {}, list("ABCDE"), 5_000_000_000.0, FX, 0.15)

    assert _zelfconsistent(uit)
    assert uit["kosten"]["tob_eur"] == pytest.approx(5 * 1600.0)
    for regel in uit["orderlog"]:
        assert regel["tob_eur"] == pytest.approx(1600.0)


def test_een_orderlijst_die_blijft_wisselen_geeft_een_harde_fout():
    """Is er geen zelfconsistente oplossing, dan komt er geen cijfer.

    Bij een minimumkost van vijf euro bestaat er een stand waarin het ene
    antwoord het andere uitsluit: zet je A in de lijst, dan duwen de vijf euro
    kosten zijn order onder de eurocent; laat je hem eruit, dan heeft hij een
    order van ongeveer een euro. Beide antwoorden spreken zichzelf tegen.

    Vroeger kwam daar stil een getal uit - vijf euro kosten over een order van
    nul dollar. Nu stopt het, want welk van de twee je kiest hangt af van de
    rekenrichting en dat is niet narekenbaar.
    """
    regels = be.met(REGELS, naam="min-5-euro", basiskost_pct=0.0,
                    broker_minimum_fee_eur=5.0)
    huidig = {"A": 194.48, "B": 201.38, "C": 201.38, "D": 201.38, "E": 201.38}

    with pytest.raises(ValueError, match="komt niet tot rust"):
        be._los_kosten_op(regels, huidig, list("ABCDE"), 1000.0, FX, 0.0)


@pytest.mark.parametrize("naam_regels,wijziging", [
    ("zonder brokerkosten", {}),
    ("vaste kost per order", {"basiskost_pct": 0.0,
                              "broker_fixed_fee_per_order_eur": 2.0}),
    ("kost in procent", {"basiskost_pct": 0.0, "broker_variable_fee_pct": 0.5}),
    ("minimumkost per order", {"basiskost_pct": 0.0,
                               "broker_minimum_fee_eur": 5.0}),
    ("alles samen", {"basiskost_pct": 0.0,
                     "broker_fixed_fee_per_order_eur": 1.0,
                     "broker_variable_fee_pct": 0.25,
                     "broker_minimum_fee_eur": 3.0,
                     "fx_conversie_bij_elke_order": True,
                     "fx_conversion_fee_pct": 0.5}),
])
def test_de_uitkomst_past_altijd_bij_haar_eigen_orderlijst(naam_regels, wijziging):
    """De wachter op de hele zoektocht, over scherpe en stompe standen.

    Voor elke stand geldt: of er komt een uitkomst waarin de lijst orders
    precies de orders zijn die er zijn, of er komt een foutmelding. Nooit een
    uitkomst waarin de twee uiteenlopen - dan zou er een kost op een order staan
    dat niet bestaat, of een order zonder kost.
    """
    regels = be.met(REGELS, naam=f"test-{naam_regels}", **wijziging)
    tickers = list("ABCDE")

    standen = {
        "volledige rotatie": {"V": 200.0, "W": 200.0, "X": 200.0,
                              "Y": 200.0, "Z": 200.0},
        "gedeeltelijke rotatie": {"A": 300.0, "B": 300.0, "C": 200.0,
                                  "Y": 100.0, "Z": 100.0},
        "alles al op gewicht": {t: 200.0 for t in tickers},
        "instap uit contant geld": {},
        "een aandeel net naast zijn doel": {
            "A": 199.99, "B": 200.0, "C": 200.0, "D": 200.0, "E": 200.01},
        "een aandeel precies op zijn doel": {
            "A": 200.0, "B": 300.0, "C": 300.0, "D": 100.0, "E": 100.0},
        "een aandeel op zijn doel na de kosten": {
            "A": 199.50, "B": 300.0, "C": 300.0, "D": 100.0, "E": 100.0},
        "een cent naast de drempel": {
            "A": 1000.0 - 0.01105, "B": 0.0, "C": 0.0, "D": 0.0, "E": 0.0},
    }

    for naam, huidig in standen.items():
        totaal = round(sum(huidig.values()) or 1000.0, 8)
        try:
            uit = be._los_kosten_op(regels, huidig, tickers, totaal, FX, 0.15)
        except ValueError as fout:
            assert ("niet tot rust" in str(fout)
                    or "niets over om te beleggen" in str(fout)), (
                f"{naam}: onverwachte foutmelding - {fout}"
            )
            continue

        assert _zelfconsistent(uit), (
            f"{naam}: de lijst {uit['actief']} past niet bij de orders "
            f"{be._orders_boven_de_drempel(uit['orders'], FX)}."
        )
        gerekend = sorted(o["ticker"] for o in uit["orderlog"])
        assert gerekend == uit["actief"], (
            f"{naam}: er is kost gerekend voor {gerekend} en niet voor "
            f"{uit['actief']}."
        )


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
def test_de_vrijstelling_van_10000_euro_wordt_eerst_opgebruikt():
    verkopen = [{"verkoop_datum": "2026-11-04", "resultaat_eur": 4000.0}]
    jaar = be.meerwaardejaren(verkopen, REGELS)[2026]

    assert jaar["vrijstelling_beschikbaar_eur"] == pytest.approx(10_000.0)
    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(4000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(0.0)
    assert jaar["belasting_eur"] == pytest.approx(0.0)


def test_net_onder_de_vrijstelling_is_er_geen_belasting():
    """9.999 euro winst: de hele schijf is nog niet op."""
    jaar = be.meerwaardejaren(
        [{"verkoop_datum": "2026-11-04", "resultaat_eur": 9_999.0}], REGELS)[2026]

    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(9_999.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(0.0)
    assert jaar["belasting_eur"] == pytest.approx(0.0)


def test_precies_op_de_vrijstelling_is_er_geen_belasting():
    """Exact 10.000 euro winst: de grens zelf is nog vrijgesteld."""
    jaar = be.meerwaardejaren(
        [{"verkoop_datum": "2026-11-04", "resultaat_eur": 10_000.0}], REGELS)[2026]

    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(10_000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(0.0)
    assert jaar["belasting_eur"] == pytest.approx(0.0)


def test_een_euro_boven_de_vrijstelling_kost_tien_cent():
    """10.001 euro winst: alleen die ene euro is belastbaar."""
    jaar = be.meerwaardejaren(
        [{"verkoop_datum": "2026-11-04", "resultaat_eur": 10_001.0}], REGELS)[2026]

    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(10_000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(1.0)
    assert jaar["belasting_eur"] == pytest.approx(0.10)


def test_boven_de_vrijstelling_geldt_tien_procent():
    verkopen = [{"verkoop_datum": "2026-11-04", "resultaat_eur": 15_000.0}]
    jaar = be.meerwaardejaren(verkopen, REGELS)[2026]

    assert jaar["gebruikte_vrijstelling_eur"] == pytest.approx(10_000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(5_000.0)
    assert jaar["tarief_pct"] == 10.0
    assert jaar["belasting_eur"] == pytest.approx(500.0)


def test_minderwaarden_van_hetzelfde_jaar_gaan_eerst_van_de_meerwaarden_af():
    verkopen = [
        {"verkoop_datum": "2026-05-04", "resultaat_eur": 20_000.0},
        {"verkoop_datum": "2026-11-04", "resultaat_eur": -3_000.0},
    ]
    jaar = be.meerwaardejaren(verkopen, REGELS)[2026]

    assert jaar["meerwaarden_eur"] == pytest.approx(20_000.0)
    assert jaar["minderwaarden_eur"] == pytest.approx(3_000.0)
    assert jaar["netto_gerealiseerd_eur"] == pytest.approx(17_000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(7_000.0)
    assert jaar["belasting_eur"] == pytest.approx(700.0)


def test_een_verlies_gaat_niet_over_naar_het_volgende_jaar():
    verkopen = [
        {"verkoop_datum": "2026-11-04", "resultaat_eur": -8_000.0},
        {"verkoop_datum": "2027-03-02", "resultaat_eur": 25_000.0},
    ]
    jaren = be.meerwaardejaren(verkopen, REGELS)

    assert jaren[2026]["belasting_eur"] == pytest.approx(0.0)
    assert jaren[2027]["belastbare_basis_eur"] == pytest.approx(15_000.0), (
        "Het verlies van 2026 verlaagt de basis van 2027 niet."
    )


def test_een_elders_gebruikte_meerwaardevrijstelling_vermindert_de_onze():
    """De vrijstelling is persoonlijk: wat elders op is, is hier op."""
    regels = be.met(
        REGELS,
        naam="BE_TAX_RULES_2026_V2+extern",
        external_capital_gain_exemption_used_eur=4_000.0,
    )
    verkopen = [{"verkoop_datum": "2026-11-04", "resultaat_eur": 15_000.0}]
    jaar = be.meerwaardejaren(verkopen, regels)[2026]

    assert jaar["vrijstelling_totaal_eur"] == pytest.approx(10_000.0)
    assert jaar["vrijstelling_beschikbaar_eur"] == pytest.approx(6_000.0)
    assert jaar["belastbare_basis_eur"] == pytest.approx(9_000.0)
    assert jaar["belasting_eur"] == pytest.approx(900.0)


def test_een_volledig_elders_gebruikte_vrijstelling_laat_niets_over():
    regels = be.met(
        REGELS, naam="test", external_capital_gain_exemption_used_eur=12_000.0)
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
