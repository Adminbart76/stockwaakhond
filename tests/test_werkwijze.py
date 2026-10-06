"""Wachters op de werkwijze: wat mag waar staan en wat hoort waar te falen.

Dit zijn geen rekentests. Ze bewaken afspraken die je niet in een formule kunt
gieten en die stil kunnen verdwijnen bij een latere wijziging:

  1. de geheime schrijfsleutel staat niet in een GitHub-workflow
  2. de dagelijkse taak verbergt geen fouten met "|| true"
  3. de instap van de portefeuille gebeurt niet vanuit GitHub
  4. "er is niets te doen" geeft exitcode 0, een echt probleem exitcode 1

Punt 4 is subtieler dan het lijkt. Zolang "de instap is al vastgelegd" als
fout gold, moest elke automatische taak de uitkomst negeren - en dan valt een
echte fout ook weg.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
WORKFLOW = PROJECT / ".github" / "workflows" / "dagelijks.yml"
SNAPSHOT = PROJECT / "scripts" / "dagelijkse_snapshot.py"
INSTAP = PROJECT / "scripts" / "leg_instap_vast.py"
HARDENING = PROJECT / "sql" / "02_hardening.sql"


def meldingen_per_afloop(bestand: Path) -> dict:
    """Welke meldingen horen bij netjes stoppen en welke bij falen?"""
    boom = ast.parse(bestand.read_text(encoding="utf-8"))
    uitkomst = {"klaar": [], "stop": []}
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call) or not isinstance(knoop.func, ast.Name):
            continue
        if knoop.func.id not in uitkomst:
            continue
        tekst = ""
        for arg in knoop.args:
            for deel in ast.walk(arg):
                if isinstance(deel, ast.Constant) and isinstance(deel.value, str):
                    tekst += deel.value + " "
        uitkomst[knoop.func.id].append(tekst.lower())
    return uitkomst


def komt_voor(meldingen: list, stuk: str) -> bool:
    return any(stuk.lower() in m for m in meldingen)


# ------------------------------------------------------- de GitHub-workflow
def test_de_geheime_sleutel_staat_niet_in_de_workflow():
    tekst = WORKFLOW.read_text(encoding="utf-8")
    assert "SUPABASE_SERVICE_KEY" not in tekst, (
        "De geheime schrijfsleutel hoort niet in GitHub te staan. De dagelijkse "
        "taak werkt met de leessleutel plus SNAPSHOT_WRITE_TOKEN."
    )


def test_de_workflow_gebruikt_het_schrijfteken():
    tekst = WORKFLOW.read_text(encoding="utf-8")
    assert "SNAPSHOT_WRITE_TOKEN" in tekst
    assert "SUPABASE_ANON_KEY" in tekst


def test_de_workflow_verbergt_geen_fouten():
    # Alleen de echte regels, niet de uitleg in de opmerkingen erboven.
    regels = [
        r for r in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith("#")
    ]
    assert "|| true" not in "\n".join(regels), (
        "Met '|| true' valt elke fout stil weg en wordt de taak nooit rood."
    )


def test_de_instap_gebeurt_niet_vanuit_github():
    """Die schrijft in `executions`, en dat is bewijsmateriaal."""
    tekst = WORKFLOW.read_text(encoding="utf-8")
    assert "leg_instap_vast" not in tekst


# ---------------------------------------------------------- de exitcodes
def test_al_vastgelegd_is_geen_fout():
    meldingen = meldingen_per_afloop(INSTAP)
    assert komt_voor(meldingen["klaar"], "de instap al vastgelegd")
    assert not komt_voor(meldingen["stop"], "de instap al vastgelegd")


def test_wachten_op_de_slotbel_is_geen_fout():
    meldingen = meldingen_per_afloop(INSTAP)
    assert komt_voor(meldingen["klaar"], "staat nog niet vast")
    assert komt_voor(meldingen["klaar"], "nog geen beursdag")


def test_een_kapot_logboek_is_wel_een_fout():
    meldingen = meldingen_per_afloop(INSTAP)
    assert komt_voor(meldingen["stop"], "logboek klopt niet")


def test_een_te_late_wisselkoers_is_wel_een_fout():
    """Te vroeg is wachten, te laat is een probleem voor een mens."""
    meldingen = meldingen_per_afloop(INSTAP)
    assert komt_voor(meldingen["stop"], "niet meer betrouwbaar")


def test_de_dagtaak_scheidt_niets_te_doen_van_een_echt_probleem():
    meldingen = meldingen_per_afloop(SNAPSHOT)
    assert komt_voor(meldingen["klaar"], "nog niet definitief gesloten")
    assert komt_voor(meldingen["klaar"], "feestdag of weekend")
    assert komt_voor(meldingen["stop"], "snapshot_write_token ontbreekt")


def test_een_te_late_wisselkoers_gooit_de_slotkoersen_niet_weg():
    """Die koersen staan wél vast. Alleen de wisselkoers wordt overgeslagen.

    De taak hoort daarna nog steeds te falen, want een ontbrekende dag in de
    wisselkoersen mag niet stilletjes voorbijgaan.
    """
    tekst = SNAPSHOT.read_text(encoding="utf-8")
    meldingen = meldingen_per_afloop(SNAPSHOT)
    assert not komt_voor(meldingen["stop"], "niet meer betrouwbaar"), (
        "De taak stopt bij een te late wisselkoers, en schrijft dan ook de "
        "slotkoersen niet meer weg."
    )
    assert "fx_gemist" in tekst and "sys.exit(1)" in tekst, (
        "Er wordt geen alarm meer geslagen over een ontbrekende wisselkoers."
    )


# ------------------------------------------------------- de verstevigingen
def test_de_hardening_sql_staat_in_het_project():
    assert HARDENING.exists(), "sql/02_hardening.sql ontbreekt."
    tekst = HARDENING.read_text(encoding="utf-8").lower()
    for regel in (
        "pg_advisory_xact_lock",     # geen twee ketens door twee gelijktijdige inserts
        "previous_hash",             # verwijst naar het echte laatste signaal
        "+ 28",                      # de wachttijd tussen twee signalen
        "created_at_utc",            # moment van vastleggen nagerekend
        "formula_spec",              # formule hoort bij de strategie
        "fx_source",                 # bron van de wisselkoers nagerekend
        "fx_asof",                   # moment van de wisselkoers nagerekend
        "leg_dagkoersen_vast",       # de smalle schrijfdeur
        "security definer",
    ):
        assert regel in tekst, f"sql/02_hardening.sql mist '{regel}'."


def test_de_dagtaak_roept_dezelfde_schrijfdeur_aan_als_de_sql_maakt():
    tekst = SNAPSHOT.read_text(encoding="utf-8")
    assert "leg_dagkoersen_vast" in tekst
    assert "Supabase.schrijver" not in tekst, (
        "De dagelijkse taak hoort zonder de geheime sleutel te werken."
    )
