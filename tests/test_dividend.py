"""Wachters op het dividend: wie er recht op heeft, en wanneer het geld er is.

De fouten die hier bewaakt worden, zijn allemaal stil. Ze geven een nette curve
met een verkeerd getal erin:

  1. dividend op de ex-datum als contant geld meebeleggen - dan belegt de
     portefeuille geld dat er nog niet is;
  2. het dividend van een aandeel vergeten dat tussen ex-datum en betaaldag
     verkocht is - dan bestelen we de strategie;
  3. dividend toekennen voor een aandeel dat we op de ex-datum niet hadden -
     dan rekent de strategie zich rijk;
  4. het dividend van SPY contant laten staan terwijl het van ons herbelegd
     wordt - dan krijgt StockWaakhond elk jaar een voorsprong die ze niet
     verdiend heeft;
  5. hetzelfde dividend twee keer meetellen, een keer contant en een keer in
     aandelen.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sw import dividend as div
from sw import herbalans as hb
from sw import portfolio as pf

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


@pytest.fixture
def wissel(instap):
    """Een wissel op 4 november 2026 naar vijf andere aandelen."""
    koersen = {t: k for t, k in INSTAPKOERSEN.items()}
    koersen.update({t: 100.0 for t in NIEUWE_TOP5})
    koersen["SPY"] = SPY_INSTAP
    return hb.bereken_herbalans(
        entry_hash="signaal-2",
        execution_date="2026-11-04",
        vorige_uitvoering=instap,
        nieuwe_tickers=NIEUWE_TOP5,
        koersen_usd=koersen,
        fx_eurusd=FX,
        spy_koers_usd=SPY_INSTAP,
        fx_source="test",
        fx_asof="2026-11-04T21:00:00+00:00",
    )


def rij(ticker, ex, pay, bedrag, netto=None):
    return {
        "ticker": ticker, "ex_date": ex, "pay_date": pay,
        "gross_per_share_usd": bedrag, "net_per_share_usd": netto,
        "source": "test",
    }


# ------------------------------------------------------------ de twee datums
def test_een_dividend_zonder_betaaldatum_wordt_geweigerd():
    zonder = {"ticker": "MPC", "ex_date": "2026-10-20",
              "gross_per_share_usd": 0.91, "source": "test"}
    with pytest.raises(ValueError, match="betaaldatum"):
        div.lees_rij(zonder)


def test_een_dividend_zonder_brutobedrag_wordt_geweigerd():
    zonder = {"ticker": "MPC", "ex_date": "2026-10-20",
              "pay_date": "2026-11-18", "source": "test"}
    with pytest.raises(ValueError, match="bruto"):
        div.lees_rij(zonder)


def test_betalen_voor_de_exdatum_kan_niet():
    with pytest.raises(ValueError, match="verkeerd"):
        div.lees_rij(rij("MPC", "2026-10-20", "2026-10-01", 0.91))


def test_de_conventie_is_bruto_en_niet_te_kiezen():
    gelezen = div.lees_rij(rij("MPC", "2026-10-20", "2026-11-18", 0.91, netto=0.60))
    assert gelezen["per_share_usd"] == pytest.approx(0.91), (
        "De officiele curve rekent bruto. Het nettobedrag staat in de tabel als "
        "informatie, niet als rekenbasis."
    )
    assert div.CONVENTIE == "bruto"


# --------------------------------------------- recht op de ex-datum, geld later
def test_exdatum_voor_de_wissel_en_betaaldag_erna(instap, wissel):
    """Het klassieke geval: recht op MPC, geld pas na de wissel."""
    keten = [instap, wissel]
    dividenden = [rij("MPC", "2026-10-20", "2026-11-18", 1.00)]

    events = div.portefeuille_dividenden(keten, dividenden)
    assert len(events) == 1
    e = events[0]

    mpc = next(p for p in instap["positions"] if p["ticker"] == "MPC")
    assert e["shares"] == pytest.approx(mpc["shares"]), (
        "Het recht hoort bij het aantal aandelen van de ex-datum."
    )
    assert e["bedrag_usd"] == pytest.approx(mpc["shares"] * 1.00)
    assert pd.Timestamp(e["pay_date"]) == pd.Timestamp("2026-11-18")


def test_verkocht_tussen_exdatum_en_betaaldag_levert_toch_dividend_op(instap, wissel):
    """MPC is op 4 november verkocht; het dividend komt op 18 november binnen."""
    keten = [instap, wissel]
    events = div.portefeuille_dividenden(
        keten, [rij("MPC", "2026-10-20", "2026-11-18", 1.00)])

    assert len(events) == 1, (
        "Een dividend waar we recht op hadden, komt binnen ook als het aandeel "
        "inmiddels verkocht is. Het weglaten zou de strategie bestelen."
    )
    assert "MPC" not in [p["ticker"] for p in wissel["positions"]]

    # En het geld komt NA de wissel binnen, dus het gaat niet mee in die wissel.
    assert div.betaald_tussen(events, instap["execution_date"],
                              wissel["execution_date"]) == []


def test_geen_dividend_als_we_het_aandeel_op_de_exdatum_niet_hadden(instap, wissel):
    keten = [instap, wissel]
    # AAPL komt pas op 4 november in de portefeuille; de ex-datum is eerder.
    events = div.portefeuille_dividenden(
        keten, [rij("AAPL", "2026-10-20", "2026-11-18", 1.00)])
    assert events == [], "Geen bezit op de ex-datum is geen dividend."


def test_kopen_op_de_exdatum_geeft_geen_recht(instap, wissel):
    """Wie op de ex-dag koopt, krijgt dat dividend niet.

    De wissel gebeurt tegen de slotkoers van 4 november. Valt de ex-datum op
    diezelfde 4 november, dan was het OUDE mandje die dag in bezit.
    """
    keten = [instap, wissel]

    nieuw = div.portefeuille_dividenden(
        keten, [rij("AAPL", "2026-11-04", "2026-11-25", 1.00)])
    assert nieuw == [], "AAPL is op de ex-dag zelf gekocht: geen recht."

    oud = div.portefeuille_dividenden(
        keten, [rij("MPC", "2026-11-04", "2026-11-25", 1.00)])
    assert len(oud) == 1, "MPC was die dag nog in bezit: wel recht."


def test_het_geld_komt_op_de_betaaldag_in_de_reeks(instap, wissel):
    events = div.portefeuille_dividenden(
        [instap, wissel], [rij("MPC", "2026-10-20", "2026-11-18", 1.00)])
    reeks = div.contant_per_betaaldag(events)

    assert list(reeks.index) == [pd.Timestamp("2026-11-18")], (
        "Op de ex-datum is het geld er nog niet. Zou het daar staan, dan belegt "
        "de portefeuille bij een wissel geld dat ze nog niet heeft."
    )


def test_een_betaaldag_op_de_wisseldag_gaat_mee_in_die_wissel(instap, wissel):
    events = div.portefeuille_dividenden(
        [instap, wissel], [rij("MPC", "2026-10-20", "2026-11-04", 1.00)])
    mee = div.betaald_tussen(events, instap["execution_date"], wissel["execution_date"])
    assert len(mee) == 1, (
        "Geld dat op de uitvoeringsdag beschikbaar is, staat die avond in de kas."
    )


def test_een_betaaldag_op_de_vorige_wisseldag_telt_niet_opnieuw(instap, wissel):
    events = div.portefeuille_dividenden(
        [instap, wissel], [rij("MPC", "2026-10-06", "2026-10-06", 1.00)])
    # Bezit op de ex-datum 6 oktober: toen was er nog niets (we kochten die dag).
    assert events == []

    verzonnen = [{
        "ticker": "MPC", "ex_date": pd.Timestamp("2026-10-20"),
        "pay_date": pd.Timestamp("2026-10-06"), "per_share_usd": 1.0,
        "shares": 1.0, "bedrag_usd": 1.0,
    }]
    assert div.betaald_tussen(verzonnen, "2026-10-06", "2026-11-04") == [], (
        "Een betaaldag die gelijk is aan de vorige uitvoeringsdag is toen al "
        "meegegaan en mag niet nog eens meetellen."
    )


# ----------------------------------------------------------- SPY herbelegt
def spy_koersen(waarde: float = 800.0) -> pd.Series:
    dagen = pd.date_range("2026-10-06", "2026-12-31", freq="B")
    return pd.Series([waarde] * len(dagen), index=dagen)


def test_het_aantal_spy_aandelen_stijgt_na_herbelegging(instap):
    events = div.spy_dividenden(
        [instap], [rij("SPY", "2026-10-20", "2026-11-18", 2.00)], spy_koersen(800.0))

    assert len(events) == 1
    e = events[0]
    begin = float(instap["benchmark"]["shares"])
    assert e["shares"] == pytest.approx(begin)
    assert e["bedrag_usd"] == pytest.approx(begin * 2.00)
    assert pd.Timestamp(e["herbeleg_datum"]) == pd.Timestamp("2026-11-18")
    assert e["aandelen_bij"] == pytest.approx(begin * 2.00 / 800.0)

    na = div.spy_stand_op(begin, events, "2026-11-18")
    assert na["aandelen"] > begin, "SPY koopt bij met zijn eigen dividend."
    assert na["contant_usd"] == 0.0


def test_spy_herbelegt_op_de_eerste_koers_op_of_na_de_betaaldag(instap):
    """De betaaldag valt op een zaterdag: dan is het de maandag erna."""
    events = div.spy_dividenden(
        [instap], [rij("SPY", "2026-10-20", "2026-11-21", 2.00)], spy_koersen())
    assert pd.Timestamp(events[0]["herbeleg_datum"]) == pd.Timestamp("2026-11-23")


def test_spy_dividend_telt_nooit_dubbel(instap):
    """Tussen betaaldag en herbelegdag is het contant, daarna zit het in aandelen."""
    dagen = pd.date_range("2026-11-20", "2026-12-31", freq="B")
    laat = pd.Series([800.0] * len(dagen), index=dagen)

    events = div.spy_dividenden(
        [instap], [rij("SPY", "2026-10-20", "2026-11-18", 2.00)], laat)
    begin = float(instap["benchmark"]["shares"])
    bedrag = events[0]["bedrag_usd"]

    voor = div.spy_stand_op(begin, events, "2026-11-19")
    assert voor["aandelen"] == pytest.approx(begin)
    assert voor["contant_usd"] == pytest.approx(bedrag), (
        "Zolang er geen slotkoers is, staat het geld contant."
    )

    na = div.spy_stand_op(begin, events, "2026-11-20")
    assert na["contant_usd"] == 0.0
    assert na["aandelen"] == pytest.approx(begin + bedrag / 800.0)

    waarde_voor = voor["aandelen"] * 800.0 + voor["contant_usd"]
    waarde_na = na["aandelen"] * 800.0 + na["contant_usd"]
    assert waarde_voor == pytest.approx(waarde_na, abs=1e-6), (
        "Herbeleggen verandert de waarde niet, alleen de vorm."
    )


def test_voor_de_betaaldag_is_er_nog_niets(instap):
    events = div.spy_dividenden(
        [instap], [rij("SPY", "2026-10-20", "2026-11-18", 2.00)], spy_koersen())
    stand = div.spy_stand_op(float(instap["benchmark"]["shares"]), events, "2026-10-21")
    assert stand["contant_usd"] == 0.0, "Op de ex-datum is er nog geen geld."
    assert stand["aandelen"] == pytest.approx(float(instap["benchmark"]["shares"]))


def test_het_volgende_dividend_rekent_met_de_bijgekochte_aandelen(instap):
    """Herbelegging werkt samengesteld: meer aandelen geeft meer dividend."""
    events = div.spy_dividenden(
        [instap],
        [rij("SPY", "2026-10-20", "2026-10-26", 2.00),
         rij("SPY", "2026-11-20", "2026-11-26", 2.00)],
        spy_koersen(800.0),
    )
    assert events[1]["shares"] > events[0]["shares"]
    assert events[1]["bedrag_usd"] > events[0]["bedrag_usd"]


def test_spy_dividend_van_voor_de_instap_telt_niet(instap):
    events = div.spy_dividenden(
        [instap], [rij("SPY", "2026-10-06", "2026-10-30", 2.00)], spy_koersen())
    assert events == [], (
        "SPY wordt op de slotkoers van 6 oktober gekocht; een ex-datum op die dag "
        "geeft geen recht."
    )


# ------------------------------------------- het geheel, zoals het script doet
def test_een_wissel_met_dividend_laat_geen_geld_ontstaan_of_verdwijnen(instap):
    """Dezelfde volgorde als scripts/leg_herbalans_vast.py, met getallen erbij.

    Dit is de integratietest: de losse regels kloppen hierboven, maar pas als ze
    samen door een wissel gaan, blijkt of er onderweg geld bijkomt of verdwijnt.
    """
    koersen = pd.Series(
        [800.0] * len(pd.bdate_range("2026-10-06", "2026-12-31")),
        index=pd.bdate_range("2026-10-06", "2026-12-31"))

    dividenden = [
        rij("MPC", "2026-10-20", "2026-11-02", 1.00),   # betaald voor de wissel
        rij("VLO", "2026-10-27", "2026-12-01", 2.00),   # betaald erna
        rij("SPY", "2026-10-15", "2026-10-29", 1.50),   # herbelegd voor de wissel
    ]
    uitvoeringsdag = pd.Timestamp("2026-11-04")

    onze = div.portefeuille_dividenden([instap], dividenden)
    spy = div.spy_dividenden([instap], dividenden, koersen)

    mee = div.betaald_tussen(onze, instap["execution_date"], uitvoeringsdag)
    spy_mee = div.betaald_tussen(spy, instap["execution_date"], uitvoeringsdag)
    begin_aandelen = float(instap["benchmark"]["shares"])
    voor = div.spy_stand_op(begin_aandelen, spy, instap["execution_date"])
    na = div.spy_stand_op(begin_aandelen, spy, uitvoeringsdag)

    slotkoersen = {t: k for t, k in INSTAPKOERSEN.items()}
    slotkoersen.update({t: 100.0 for t in NIEUWE_TOP5})
    slotkoersen["SPY"] = 800.0

    herb = hb.bereken_herbalans(
        entry_hash="signaal-2", execution_date=str(uitvoeringsdag.date()),
        vorige_uitvoering=instap, nieuwe_tickers=NIEUWE_TOP5,
        koersen_usd=slotkoersen, fx_eurusd=FX, spy_koers_usd=800.0,
        fx_source="test", fx_asof="2026-11-04T21:00:00+00:00",
        dividend_cash_usd=div.som(mee), dividend_detail=div.detail(mee),
        spy_dividend_cash_usd=div.som(spy_mee),
        spy_dividend_detail=div.detail(spy_mee),
        spy_extra_shares=round(na["aandelen"] - voor["aandelen"], 10),
        spy_herbelegd_usd=round(
            voor["contant_usd"] + div.som(spy_mee) - na["contant_usd"], 8),
        dividend_conventie=div.CONVENTIE_TEKST,
    )

    # 1. alleen MPC is uitbetaald vóór de wissel; VLO komt later
    mpc = next(p for p in instap["positions"] if p["ticker"] == "MPC")
    assert herb["opening"]["cash_usd"] == pytest.approx(mpc["shares"] * 1.00, abs=1e-6)
    assert [e["ticker"] for e in herb["opening"]["dividend_detail"]] == ["MPC"]

    # 2. het geld van VLO gaat mee in de WISSEL DAARNA, ook al is VLO verkocht
    later = div.betaald_tussen(onze, uitvoeringsdag, "2026-12-31")
    assert [e["ticker"] for e in later] == ["VLO"]
    assert "VLO" not in [p["ticker"] for p in herb["positions"]]

    # 3. SPY heeft bijgekocht en houdt niets contant
    assert herb["benchmark"]["shares"] > begin_aandelen
    assert herb["benchmark"]["cash_usd"] == 0.0

    # 4. er is geen dollar bijgekomen of verdwenen
    posities_usd = sum(p["shares"] * slotkoersen[p["ticker"]]
                       for p in instap["positions"])
    verwacht = posities_usd + mpc["shares"] * 1.00
    assert herb["opening"]["total_usd"] == pytest.approx(verwacht, abs=1e-6)
    assert herb["opening"]["total_usd"] - herb["cost_usd"] == pytest.approx(
        herb["invested_usd"], abs=1e-6)

    # 5. de waarde van SPY verandert niet door het herbeleggen zelf
    spy_waarde = herb["benchmark"]["shares"] * 800.0 + herb["benchmark"]["cash_usd"]
    assert spy_waarde == pytest.approx(
        begin_aandelen * 800.0 + div.som(spy_mee), abs=1e-6)
