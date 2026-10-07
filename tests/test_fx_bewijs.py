"""Het wisselkoersbewijs is verplicht bij een wissel (auditronde 5).

De bevinding van 7 oktober 2026: `sql/04_dividend_en_fx.sql` rekende de
minuutbalk en het ECB-controlegetal alleen na ZODRA het record die velden zelf
meebracht:

    if inhoud ? 'fx_bar_end' then ... end if;

Een wissel die ze gewoon wegliet, kwam dus nergens langs die controles. De
wachter bewaakte in die vorm alleen wie eerlijk was over wat hij meebracht.

Vanaf nu moeten de acht bewijsvelden er bij elke wissel zijn, en wordt elk van
de regels hieronder nagerekend. Dat gebeurt op twee plaatsen met dezelfde
grenzen: in `sw/fx.py` (zodat een wissel al op de computer van Bart strandt en
er geen record ontstaat dat de database daarna weigert - het lokale bestand is
de bron van waarheid) en in `sql/05_fx_bewijs_verplicht.sql`.

De instap van 6 oktober 2026 valt er expliciet buiten: die is de eerste schakel,
heeft geen voorganger, kende de regel van de minuutbalk nog niet en mag nooit
wijzigen.

Waarom dit niet alleen vorm is: Yahoo bewaart minuutgegevens ongeveer dertig
dagen. Wat op de avond van de wissel niet in de gehashte tekst staat, kan een
controleur een jaar later niet meer narekenen.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd
import pytest

from sw import fx
from sw import herbalans as hb
from sw import portfolio as pf
from sw.strategy import sha256_text
from tests.hulp_fx import bewijs_voor

WISSELDAG = "2026-11-04"
FX = 1.1262530088

INSTAPKOERSEN = {
    "MRNA": 187.46000671, "ILMN": 273.54000854, "MPC": 432.35998535,
    "HPE": 70.48000336, "VLO": 419.22000122,
}
SPY_INSTAP = 779.09002686
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


def maak_wissel(instap, bewijs):
    koersen = dict(INSTAPKOERSEN)
    koersen.update({t: 100.0 for t in NIEUWE_TOP5})
    koersen["SPY"] = SPY_INSTAP
    return hb.bereken_herbalans(
        entry_hash="signaal-2",
        execution_date=WISSELDAG,
        vorige_uitvoering=instap,
        nieuwe_tickers=NIEUWE_TOP5,
        koersen_usd=koersen,
        fx_eurusd=FX,
        spy_koers_usd=SPY_INSTAP,
        fx_source="test",
        fx_asof=WISSELDAG + "T21:00:00+00:00",
        fx_bewijs=bewijs,
    )


def goed() -> dict:
    return bewijs_voor(WISSELDAG, FX)


def controleer(bewijs, fx_rate: float = FX) -> dict:
    return fx.controleer_bewijs(bewijs, WISSELDAG, fx_rate)


# --------------------------------------------------- zonder bewijs geen wissel
def test_een_wissel_zonder_bewijs_wordt_niet_gebouwd(instap):
    """De bevinding zelf: weglaten mocht, en dan werd er niets nagerekend."""
    with pytest.raises(fx.WisselkoersbewijsOntbreekt) as fout:
        maak_wissel(instap, None)
    for veld in fx.BEWIJSVELDEN:
        assert veld in str(fout.value), (
            "De melding hoort te zeggen dat " + veld + " ontbreekt."
        )


def test_een_wissel_met_een_volledig_bewijs_komt_er_wel(instap):
    wissel = maak_wissel(instap, goed())
    for veld in fx.BEWIJSVELDEN:
        assert veld in wissel, veld + " hoort in het record te staan."
        assert veld in wissel["canonical_payload"], (
            "Het bewijs hoort in de GEHASHTE tekst te staan, niet alleen "
            "ernaast: alleen die tekst telt als bewijs."
        )
    ok, bericht = hb.verify_keten([instap, wissel])
    assert ok, bericht


@pytest.mark.parametrize("weggelaten", sorted(fx.BEWIJSVELDEN))
def test_elk_van_de_acht_velden_is_op_zichzelf_verplicht(instap, weggelaten):
    bewijs = goed()
    del bewijs[weggelaten]
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match=weggelaten):
        maak_wissel(instap, bewijs)


def test_een_leeg_veld_is_hetzelfde_als_geen_veld(instap):
    bewijs = goed()
    bewijs["fx_control_source"] = ""
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="fx_control_source"):
        maak_wissel(instap, bewijs)


def test_de_instap_van_6_oktober_blijft_zonder_bewijs_geldig(instap):
    """De eerste schakel kende de regel niet en mag nooit wijzigen.

    Dezelfde grens staat in sql/05: de wachter daar doet niets bij een record
    zonder prev_exec_hash.
    """
    assert "fx_bar_end" not in instap
    ok, bericht = hb.verify_keten([instap])
    assert ok, bericht


def test_de_vastgelegde_uitvoering_van_6_oktober_komt_nog_door_de_keten():
    """Niet de nabouw maar het echte record uit forward_log/."""
    from pathlib import Path

    pad = Path(__file__).resolve().parent.parent / "forward_log" / "executions.jsonl"
    regels = [json.loads(r) for r in
              pad.read_text(encoding="utf-8").splitlines() if r.strip()]
    ok, bericht = hb.verify_keten(regels)
    assert ok, bericht


def test_een_keten_met_een_wissel_zonder_bewijs_wordt_afgekeurd(instap):
    """Ook als zo'n record van buiten komt, bijvoorbeeld uit de database.

    Het controlegetal van dit nagemaakte record klopt met zijn eigen inhoud; het
    strandt dus werkelijk op het ontbrekende bewijs en niet op de hash.
    """
    wissel = maak_wissel(instap, goed())
    inhoud = json.loads(wissel["canonical_payload"])
    del inhoud["fx_bar_end"]

    kaal = {k: v for k, v in wissel.items() if k != "fx_bar_end"}
    kaal["canonical_payload"] = json.dumps(
        inhoud, separators=(",", ":"), sort_keys=True)
    kaal["exec_hash"] = sha256_text(kaal["canonical_payload"])

    ok, bericht = hb.verify_keten([instap, kaal])
    assert not ok
    assert "fx_bar_end" in bericht


# ------------------------------------------------- de balk zelf moet kloppen
def test_de_balk_duurt_precies_een_minuut(instap):
    bewijs = goed()
    bewijs["fx_bar_start"] = (
        pd.Timestamp(bewijs["fx_bar_end"]) - timedelta(minutes=30)).isoformat()
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="duurt geen minuut"):
        maak_wissel(instap, bewijs)


def test_het_einde_van_de_balk_ligt_na_het_begin(instap):
    bewijs = goed()
    bewijs["fx_bar_start"], bewijs["fx_bar_end"] = (
        bewijs["fx_bar_end"], bewijs["fx_bar_start"])
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="niet na het begin"):
        maak_wissel(instap, bewijs)


def test_een_balk_die_na_de_slotbel_eindigt_wordt_geweigerd(instap):
    """Zo'n balk bevat handel die de slotkoersen niet kennen."""
    bewijs = bewijs_voor(WISSELDAG, FX, seconden_voor_slotbel=-60)
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="na de slotbel"):
        maak_wissel(instap, bewijs)


def test_hoogstens_vijf_minuten_terugval(instap):
    op_de_grens = bewijs_voor(WISSELDAG, FX, seconden_voor_slotbel=300)
    assert controleer(op_de_grens)["seconden_voor_slotbel"] == 300

    te_ver = bewijs_voor(WISSELDAG, FX, seconden_voor_slotbel=360)
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="minuten voor de slotbel"):
        maak_wissel(instap, te_ver)


def test_fx_bar_normaal_moet_kloppen_met_de_balk(instap):
    """Twee beweringen in hetzelfde record die elkaar tegenspreken."""
    liegt = bewijs_voor(WISSELDAG, FX, seconden_voor_slotbel=120)
    liegt["fx_bar_normaal"] = True
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="fx_bar_normaal"):
        maak_wissel(instap, liegt)

    andersom = goed()
    andersom["fx_bar_normaal"] = False
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="fx_bar_normaal"):
        maak_wissel(instap, andersom)


def test_een_tijdstempel_zonder_tijdzone_wordt_geweigerd(instap):
    """Zonder tijdzone hoort de koers voor elke lezer bij een andere minuut."""
    bewijs = goed()
    bewijs["fx_bar_start"] = "2026-11-04T15:59:00"
    bewijs["fx_bar_end"] = "2026-11-04T16:00:00"
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="tijdzone"):
        maak_wissel(instap, bewijs)


def test_dezelfde_minuut_in_utc_mag_wel(instap):
    """Het gaat om het moment, niet om de schrijfwijze."""
    bewijs = goed()
    for veld in ("fx_bar_start", "fx_bar_end"):
        bewijs[veld] = pd.Timestamp(bewijs[veld]).tz_convert("UTC").isoformat()
    assert controleer(bewijs)["normaal"] is True


def test_de_balk_van_de_wintertijd_schuift_mee():
    """16:00 in New York is in oktober 20:00 UTC en in november 21:00 UTC.

    Een bewijs dat voor de ene dag klopt, hoort voor de andere fout te zijn.
    """
    oktober = bewijs_voor("2026-10-20", FX)
    assert fx.controleer_bewijs(oktober, "2026-10-20", FX)["normaal"] is True
    with pytest.raises(fx.WisselkoersbewijsOntbreekt):
        fx.controleer_bewijs(oktober, "2026-11-04", FX)


# ------------------------------------------- het controlegetal van de ECB
def test_een_controlegetal_van_na_de_uitvoeringsdag_wordt_geweigerd(instap):
    bewijs = goed()
    bewijs["fx_control_date"] = "2026-11-05"
    bewijs["fx_control_same_day"] = False
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="na de uitvoeringsdag"):
        maak_wissel(instap, bewijs)


def test_een_controlegetal_van_een_eerdere_dag_mag_wel(instap):
    """De ECB publiceert niets op een dag dat het eurosysteem gesloten is."""
    bewijs = goed()
    bewijs["fx_control_date"] = "2026-11-03"
    bewijs["fx_control_same_day"] = False
    assert controleer(bewijs)["controle_datum"] == "2026-11-03"
    assert maak_wissel(instap, bewijs)["fx_control_date"] == "2026-11-03"


def test_fx_control_same_day_moet_kloppen_met_de_datum(instap):
    bewijs = goed()
    bewijs["fx_control_date"] = "2026-11-03"
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="fx_control_same_day"):
        maak_wissel(instap, bewijs)


def test_een_controlegetal_dat_geen_koers_is_wordt_geweigerd(instap):
    bewijs = goed()
    bewijs["fx_control_rate"] = -1.0
    bewijs["fx_control_deviation_pct"] = 0.0
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="geen koers"):
        maak_wissel(instap, bewijs)


def test_zonder_bron_bij_het_controlegetal_komt_er_geen_wissel(instap):
    bewijs = goed()
    bewijs["fx_control_source"] = "   "
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="geen bron"):
        maak_wissel(instap, bewijs)


def test_de_opgeslagen_afwijking_wordt_opnieuw_uitgerekend(instap):
    """Een verzonnen afwijking zou een verschil kunnen verbergen."""
    bewijs = goed()
    bewijs["fx_control_deviation_pct"] = 0.0
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="klopt niet"):
        maak_wissel(instap, bewijs)


def test_meer_dan_een_procent_verschil_stopt_ook_hier(instap):
    bewijs = bewijs_voor(WISSELDAG, FX, controle=round(FX / 1.02, 10))
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="grens"):
        maak_wissel(instap, bewijs)


def test_de_afwijking_wordt_tegen_de_koers_van_het_record_gerekend():
    """Wie fx_rate wijzigt, hoort de afwijking niet meer te laten kloppen."""
    with pytest.raises(fx.WisselkoersbewijsOntbreekt, match="klopt niet"):
        fx.controleer_bewijs(goed(), WISSELDAG, FX * 1.001)


def test_een_vreemd_veld_hoort_niet_in_het_bewijs(instap):
    bewijs = goed()
    bewijs["fx_opmerking"] = "zag er goed uit"
    with pytest.raises(ValueError, match="fx_opmerking"):
        maak_wissel(instap, bewijs)
