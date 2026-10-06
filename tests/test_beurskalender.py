"""Wachters op de klokregels: wanneer is een koers definitief?

Hier wordt niets opgehaald. Elke test geeft een moment mee, zodat de uitkomst
niet afhangt van het uur waarop de test draait. Dat is precies waarom deze
regels in een eigen bestand staan.

Twee dingen worden bewezen:

  1. de beurs moet echt gesloten zijn voordat een koers van die dag meetelt
     (zomertijd en wintertijd verschillen een uur, dus beide gevallen staan erin)

  2. een wisselkoers mag alleen op de dag zelf vastgelegd worden, na de
     slotbel en voor de valutadag van Yahoo omslaat. Buiten dat venster
     rapporteert Yahoo voor dezelfde datum een ander getal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sw import beurskalender as bk


def utc(tekst: str) -> datetime:
    return datetime.fromisoformat(tekst).astimezone(timezone.utc)


# ------------------------------------------------------------- de slotbel zelf
def test_slotmoment_in_de_zomertijd():
    """Oktober: New York staat op UTC-4, dus de slotbel is 20:00 UTC."""
    assert bk.slotmoment("2026-10-06") == utc("2026-10-06T20:00:00+00:00")


def test_slotmoment_in_de_wintertijd():
    """December: New York staat op UTC-5, dus de slotbel is 21:00 UTC."""
    assert bk.slotmoment("2026-12-15") == utc("2026-12-15T21:00:00+00:00")


def test_een_moment_zonder_tijdzone_wordt_geweigerd():
    """Zonder tijdzone is 20:00 dubbelzinnig, en dubbelzinnig is hier fout."""
    with pytest.raises(ValueError):
        bk.nu_utc(datetime(2026, 10, 6, 20, 0))


# ------------------------------------------------- welke beursdag loopt er?
def test_na_middernacht_bij_ons_is_het_in_new_york_nog_gisteren():
    """De val die hier vermeden moet worden: de Belgische datum gebruiken.

    Om 00.30 bij ons is het in New York 18.30 van de dag ervoor. Dat is de dag
    waarvan de slotkoers net definitief is - niet de dag die hier al begonnen is.
    """
    assert bk.handelsdag_nu(
        nu=utc("2026-10-07T22:30:00+00:00")) == pd.Timestamp("2026-10-07")


def test_midden_op_de_dag_lopen_de_datums_gelijk():
    assert bk.handelsdag_nu(
        nu=utc("2026-10-07T14:00:00+00:00")) == pd.Timestamp("2026-10-07")


# --------------------------------------------------------- is de beurs dicht?
def test_tijdens_de_handelsdag_is_de_koers_niet_definitief():
    dicht, uitleg = bk.beurs_is_gesloten_voor(
        "2026-10-06", nu=utc("2026-10-06T18:00:00+00:00"))
    assert not dicht
    assert "sluit pas" in uitleg


def test_vlak_na_de_slotbel_wachten_we_nog():
    """De marge dekt de slotveiling. Tien minuten na de bel is te vroeg."""
    dicht, uitleg = bk.beurs_is_gesloten_voor(
        "2026-10-06", nu=utc("2026-10-06T20:10:00+00:00"))
    assert not dicht
    assert "net gesloten" in uitleg


def test_na_de_marge_is_de_koers_definitief():
    dicht, _ = bk.beurs_is_gesloten_voor(
        "2026-10-06", nu=utc("2026-10-06T20:21:00+00:00"))
    assert dicht


def test_in_de_wintertijd_schuift_het_venster_een_uur_mee():
    """Hetzelfde tijdstip in UTC is in december nog volop handelstijd."""
    dicht, _ = bk.beurs_is_gesloten_voor(
        "2026-12-15", nu=utc("2026-12-15T20:21:00+00:00"))
    assert not dicht

    dicht, _ = bk.beurs_is_gesloten_voor(
        "2026-12-15", nu=utc("2026-12-15T21:21:00+00:00"))
    assert dicht


# ------------------------------------------- de laatste voltooide handelsdag
DAGEN = pd.DatetimeIndex(["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"])


def test_een_lopende_dag_telt_niet_als_handelsdag():
    """Dit is de kern van de wachter: vandaag loopt nog, dus geldt gisteren."""
    assert bk.laatste_voltooide_handelsdag(
        DAGEN, nu=utc("2026-10-06T18:00:00+00:00")) == pd.Timestamp("2026-10-05")


def test_na_de_slotbel_telt_vandaag_wel_mee():
    assert bk.laatste_voltooide_handelsdag(
        DAGEN, nu=utc("2026-10-06T20:30:00+00:00")) == pd.Timestamp("2026-10-06")


def test_zonder_enkele_voltooide_dag_komt_er_niets_terug():
    assert bk.laatste_voltooide_handelsdag(
        DAGEN, nu=utc("2026-09-30T12:00:00+00:00")) is None


def test_de_volgorde_van_de_reeks_maakt_niet_uit():
    rommelig = pd.DatetimeIndex(["2026-10-06", "2026-10-01", "2026-10-05"])
    assert bk.laatste_voltooide_handelsdag(
        rommelig, nu=utc("2026-10-06T18:00:00+00:00")) == pd.Timestamp("2026-10-05")


# ------------------------------------------------------------- de wisselkoers
def test_wisselkoers_te_vroeg_is_gewoon_wachten():
    mag, stand, uitleg = bk.wisselkoers_is_definitief(
        "2026-10-06", nu=utc("2026-10-06T18:00:00+00:00"))
    assert not mag
    assert stand == "te_vroeg"
    assert "nog niet vast" in uitleg


def test_wisselkoers_mag_na_de_slotbel_op_de_dag_zelf():
    mag, stand, _ = bk.wisselkoers_is_definitief(
        "2026-10-06", nu=utc("2026-10-06T20:30:00+00:00"))
    assert mag and stand == "goed"


def test_de_hele_avond_hier_valt_nog_binnen_het_venster():
    """Bart legt vast tussen 22.20 en 01.00 bij ons. Dat moet allemaal mogen."""
    for moment in ("2026-10-06T20:25:00+00:00",   # 22.25 bij ons
                   "2026-10-06T21:30:00+00:00",   # 23.30 bij ons
                   "2026-10-06T22:55:00+00:00"):  # 00.55 bij ons
        mag, stand, _ = bk.wisselkoers_is_definitief("2026-10-06", nu=utc(moment))
        assert mag and stand == "goed", moment


def test_na_middernacht_in_londen_is_het_te_laat():
    """De valutadag van Yahoo is dan omgeslagen, en dan verandert het getal."""
    mag, stand, uitleg = bk.wisselkoers_is_definitief(
        "2026-10-06", nu=utc("2026-10-06T23:30:00+00:00"))
    assert not mag
    assert stand == "te_laat"
    assert "Te laat" in uitleg


def test_een_dag_later_is_ook_te_laat():
    mag, stand, _ = bk.wisselkoers_is_definitief(
        "2026-10-06", nu=utc("2026-10-07T20:30:00+00:00"))
    assert not mag and stand == "te_laat"


def test_een_dag_die_nog_moet_komen_kan_geen_wisselkoers_hebben():
    mag, stand, _ = bk.wisselkoers_is_definitief(
        "2026-10-08", nu=utc("2026-10-06T20:30:00+00:00"))
    assert not mag and stand == "toekomst"


def test_het_venster_past_binnen_de_regel_in_de_database():
    """De database en de code mogen niet verschillend streng zijn.

    sql/02_hardening.sql weigert een uitvoering waarvan fx_asof niet tussen de
    slotbel en acht uur daarna ligt. Elk moment dat hier mag, hoort daar dus
    ook door te kunnen - anders weigert de database iets wat dit script net
    heeft goedgekeurd.
    """
    for datum in ("2026-10-06", "2026-12-15"):
        slot = bk.slotmoment(datum)
        toegestaan = 0
        for minuten in range(0, 24 * 60, 15):
            moment = slot + timedelta(minutes=minuten)
            mag, _, _ = bk.wisselkoers_is_definitief(datum, nu=moment)
            if mag:
                toegestaan += 1
                assert slot <= moment < slot + timedelta(hours=8), (
                    f"{moment} mag hier wel en in de database niet."
                )
        assert toegestaan > 0, f"Op {datum} zou nooit iets mogen. Dat kan niet."


def test_het_venster_in_belgische_tijd_klopt_met_het_bat_bestand():
    """Het bestand heet "LEG INSTAP VAST (na 22u20)". Dat hoort te kloppen."""
    vanaf, tot = bk.venster_in_het_hier("2026-10-06")
    assert vanaf == "22.20"
    assert tot == "01.00"
