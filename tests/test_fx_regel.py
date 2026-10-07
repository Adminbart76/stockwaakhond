"""Wachters op de wisselkoers van een uitvoeringsdag.

De regel: de laatste volledig afgesloten 1-minuutbalk van EURUSD=X waarvan het
interval eindigt op of voor 16:00:00 in New York. Nooit een balk daarna.

Wat hier bewaakt wordt
======================
  1. de normale balk is die van 15:59 tot 16:00;
  2. ontbreekt die, dan mag het tot vijf minuten eerder - en niet verder;
  3. een balk die NA de slotbel eindigt wordt nooit gebruikt, ook niet als het
     de enige is. Zo'n balk bevat handel die de slotkoersen niet kennen;
  4. zomer- en wintertijd: 16:00 in New York is in oktober 20:00 UTC en in
     november 21:00 UTC. Een vaste UTC-tijd zou een uur ernaast zitten;
  5. het controlegetal van de ECB: meer dan 1 procent verschil is geen
     marktbeweging maar een fout in de gegevens.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datetime import timedelta

from sw import beurskalender as bk
from sw import fx


def balken(stempels_utc, koers_vanaf: float = 1.16) -> pd.Series:
    """Minuutbalken met het tijdstempel van het BEGIN van de minuut, in UTC."""
    index = pd.DatetimeIndex(
        [pd.Timestamp(s) if isinstance(s, pd.Timestamp) else pd.Timestamp(s, tz="UTC")
         for s in stempels_utc]
    )
    return pd.Series(
        [koers_vanaf + i / 10000 for i in range(len(index))], index=index)


def reeks_rond_de_bel(dag: str, bel_utc: str, van: int = 10, tot: int = 3) -> pd.Series:
    """Balken rond de slotbel: `van` minuten ervoor tot `tot` minuten erna."""
    bel = pd.Timestamp(f"{dag} {bel_utc}", tz="UTC")
    stempels = [bel - pd.Timedelta(minutes=m) for m in range(van, 0, -1)]
    stempels += [bel + pd.Timedelta(minutes=m) for m in range(0, tot)]
    return balken(stempels)


# ---------------------------------------------------------------- de normale balk
def test_de_balk_van_1559_tot_1600_wordt_gekozen():
    reeks = reeks_rond_de_bel("2026-11-04", "21:00")
    gekozen = fx.kies_balk(reeks, "2026-11-04")

    assert gekozen["bar_start"] == pd.Timestamp("2026-11-04 20:59", tz="UTC")
    assert gekozen["bar_end"] == pd.Timestamp("2026-11-04 21:00", tz="UTC")
    assert gekozen["seconden_voor_slotbel"] == 0
    assert gekozen["normaal"] is True
    assert gekozen["koers"] == pytest.approx(float(reeks.loc["2026-11-04 20:59+00:00"]))


def test_het_tijdstempel_van_de_balk_staat_in_de_tijd_van_de_beurs():
    gekozen = fx.kies_balk(reeks_rond_de_bel("2026-11-04", "21:00"), "2026-11-04")
    assert gekozen["bar_end_iso"].startswith("2026-11-04T16:00:00"), (
        "Het interval hoort te eindigen op de slotbel, in de tijd van New York."
    )


# ------------------------------------------------------------------ zomer en winter
def test_zomertijd_de_bel_valt_op_20_uur_utc():
    """6 oktober 2026: New York staat op UTC-4, dus 16:00 daar is 20:00 UTC."""
    gekozen = fx.kies_balk(reeks_rond_de_bel("2026-10-06", "20:00"), "2026-10-06")
    assert gekozen["bar_end"] == pd.Timestamp("2026-10-06 20:00", tz="UTC")
    assert gekozen["normaal"] is True


def test_wintertijd_de_bel_valt_op_21_uur_utc():
    """4 november 2026: de zomertijd is op 1 november afgelopen, dus UTC-5."""
    gekozen = fx.kies_balk(reeks_rond_de_bel("2026-11-04", "21:00"), "2026-11-04")
    assert gekozen["bar_end"] == pd.Timestamp("2026-11-04 21:00", tz="UTC")


def test_een_vaste_utc_tijd_zou_in_november_een_uur_ernaast_zitten():
    """De balken van een novemberdag rond 20:00 UTC liggen een uur te vroeg."""
    reeks = reeks_rond_de_bel("2026-11-04", "20:00", van=10, tot=3)
    with pytest.raises(fx.GeenWisselkoers):
        fx.kies_balk(reeks, "2026-11-04")


# -------------------------------------------------------------------- terugval
def test_zonder_de_balk_van_1559_wordt_de_vorige_genomen():
    bel = pd.Timestamp("2026-11-04 21:00", tz="UTC")
    stempels = [bel - pd.Timedelta(minutes=m) for m in (5, 4, 3, 2)]  # 15:55..15:58
    gekozen = fx.kies_balk(balken(stempels), "2026-11-04")

    assert gekozen["bar_end"] == pd.Timestamp("2026-11-04 20:59", tz="UTC")
    assert gekozen["seconden_voor_slotbel"] == 60
    assert gekozen["normaal"] is False


def test_verder_dan_vijf_minuten_voor_de_bel_mag_niet():
    bel = pd.Timestamp("2026-11-04 21:00", tz="UTC")
    stempels = [bel - pd.Timedelta(minutes=m) for m in (20, 19, 18)]
    with pytest.raises(fx.GeenWisselkoers, match="mens"):
        fx.kies_balk(balken(stempels), "2026-11-04")


def test_de_grens_van_vijf_minuten_ligt_op_1555():
    bel = pd.Timestamp("2026-11-04 21:00", tz="UTC")
    net_goed = fx.kies_balk(balken([bel - pd.Timedelta(minutes=6)]), "2026-11-04")
    assert net_goed["bar_end"] == bel - pd.Timedelta(minutes=5)

    with pytest.raises(fx.GeenWisselkoers):
        fx.kies_balk(balken([bel - pd.Timedelta(minutes=7)]), "2026-11-04")


# --------------------------------------------------------- nooit na de slotbel
def test_een_balk_na_de_slotbel_wordt_nooit_gebruikt():
    bel = pd.Timestamp("2026-11-04 21:00", tz="UTC")
    stempels = [bel + pd.Timedelta(minutes=m) for m in (0, 1, 2)]
    with pytest.raises(fx.GeenWisselkoers, match="na de slotbel"):
        fx.kies_balk(balken(stempels), "2026-11-04")


def test_de_balk_van_1600_dekt_handel_na_de_bel_en_valt_dus_af():
    """De balk met tijdstempel 16:00 loopt tot 16:01 en mag niet."""
    bel = pd.Timestamp("2026-11-04 21:00", tz="UTC")
    reeks = balken([bel - pd.Timedelta(minutes=1), bel])
    gekozen = fx.kies_balk(reeks, "2026-11-04")
    assert gekozen["bar_start"] == bel - pd.Timedelta(minutes=1)


def test_zonder_balken_wordt_er_niets_gekozen():
    with pytest.raises(fx.GeenWisselkoers):
        fx.kies_balk(pd.Series(dtype=float), "2026-11-04")


def test_balken_van_een_andere_dag_tellen_niet():
    reeks = reeks_rond_de_bel("2026-11-03", "21:00")
    with pytest.raises(fx.GeenWisselkoers):
        fx.kies_balk(reeks, "2026-11-04")


def test_een_nul_of_leeg_getal_is_geen_koers():
    bel = pd.Timestamp("2026-11-04 21:00", tz="UTC")
    reeks = pd.Series(
        [0.0, float("nan")],
        index=pd.DatetimeIndex([bel - pd.Timedelta(minutes=2),
                                bel - pd.Timedelta(minutes=1)]),
    )
    with pytest.raises(fx.GeenWisselkoers):
        fx.kies_balk(reeks, "2026-11-04")


# ------------------------------------------------------- het controlegetal
def test_de_ecb_csv_wordt_gelezen():
    tekst = (
        "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-11-03,1.1612\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-11-04,1.1634\n"
    )
    koersen = fx.lees_ecb_csv(tekst)
    assert koersen == {"2026-11-03": 1.1612, "2026-11-04": 1.1634}


def test_een_lege_waarde_in_de_ecb_csv_wordt_overgeslagen():
    tekst = "TIME_PERIOD,OBS_VALUE\n2026-11-04,\n2026-11-03,1.1612\n"
    assert fx.lees_ecb_csv(tekst) == {"2026-11-03": 1.1612}


def test_een_klein_verschil_met_de_ecb_is_gewoon_de_dag():
    uitslag = fx.vergelijk(1.1634, 1.1612)
    assert uitslag["binnen_grens"] is True
    assert uitslag["afwijking_pct"] == pytest.approx(0.1894, abs=1e-3)


def test_meer_dan_een_procent_verschil_met_de_ecb_is_een_fout():
    uitslag = fx.vergelijk(1.1800, 1.1612)
    assert uitslag["binnen_grens"] is False, (
        "Zo groot is geen dagbeweging tussen Frankfurt en New York; dan hoort er "
        "een mens naar te kijken in plaats van iets vast te leggen."
    )


def test_de_grens_ligt_precies_op_een_procent():
    assert fx.vergelijk(1.01, 1.00)["binnen_grens"] is True
    assert fx.vergelijk(1.0101, 1.00)["binnen_grens"] is False


# ------------------------------------------------------------- het leesvenster
def utc(tekst: str):
    return pd.Timestamp(tekst).to_pydatetime()


def test_voor_de_slotbel_mag_er_niets_vastgelegd_worden():
    mag, stand, _ = bk.leesvenster("2026-11-04", nu=utc("2026-11-04T18:00:00+00:00"))
    assert not mag and stand == "te_vroeg", (
        "Voor de slotbel bestaat de balk van 15:59 nog niet."
    )


def test_een_half_uur_na_de_slotbel_mag_het():
    mag, stand, _ = bk.leesvenster("2026-11-04", nu=utc("2026-11-04T21:30:00+00:00"))
    assert mag and stand == "goed"


def test_de_hele_avond_en_nacht_hier_valt_binnen_het_leesvenster():
    """De minuutbalk verandert niet meer, dus later op de avond is geen probleem.

    Dat was bij de oude dagbalk anders: die moest voor middernacht in Londen
    gelezen zijn. Juist dat liep op 7 oktober 2026 mis toen GitHub de taak van
    21:30 UTC pas om 00:57 UTC startte.
    """
    for moment in ("2026-11-04T21:25:00+00:00", "2026-11-04T23:30:00+00:00",
                   "2026-11-05T00:57:00+00:00", "2026-11-05T03:00:00+00:00"):
        mag, stand, _ = bk.leesvenster("2026-11-04", nu=utc(moment))
        assert mag and stand == "goed", moment


def test_meer_dan_acht_uur_na_de_slotbel_is_het_te_laat():
    """Niet omdat het getal verandert, maar omdat de database het niet toelaat."""
    mag, stand, uitleg = bk.leesvenster(
        "2026-11-04", nu=utc("2026-11-05T06:00:00+00:00"))
    assert not mag and stand == "te_laat"
    assert "acht uur" in uitleg


def test_het_leesvenster_past_binnen_de_regel_in_de_database():
    """De code en de database mogen niet verschillend streng zijn."""
    for datum in ("2026-10-06", "2026-11-04"):
        slot = bk.slotmoment(datum)
        for uur in range(-2, 12):
            moment = slot + timedelta(hours=uur)
            mag, _, _ = bk.leesvenster(datum, nu=moment)
            if mag:
                assert slot <= moment < slot + timedelta(hours=8), (
                    f"{moment} mag hier wel en in de database niet."
                )
