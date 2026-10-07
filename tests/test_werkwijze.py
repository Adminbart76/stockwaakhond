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
WISSEL = PROJECT / "scripts" / "leg_herbalans_vast.py"
HERSTEL = PROJECT / "scripts" / "herstel_dagkoers.py"
HARDENING = PROJECT / "sql" / "02_hardening.sql"
SMALLE_DEUR = PROJECT / "sql" / "03_smalle_deur.sql"


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


# ------------------------------------------------- de smallere deur (ronde 3)
def test_de_smalle_deur_staat_in_het_project():
    assert SMALLE_DEUR.exists(), "sql/03_smalle_deur.sql ontbreekt."
    tekst = SMALLE_DEUR.read_text(encoding="utf-8").lower()
    for regel in (
        "beursdag van nu",            # geen willekeurige oude datum meer
        "20 minutes",                 # nooit voor de slotbel plus marge
        "isodow",                     # geen weekenddag
        "actieve_tickers",            # alleen de huidige portefeuille
        "niet compleet",              # alles of niets
        "huidige portefeuille",       # een vreemd aandeel wordt geweigerd
        "executions_een_opvolger",    # geen tweede keten van uitvoeringen
        "prev_exec_hash",             # de keten zelf
        "tgenabled",                  # staan de wachters ook aan
        "deur_versie",                # is 03 werkelijk uitgevoerd
        "mag_dagkoers_vastleggen",    # de deur bevragen zonder te schrijven
    ):
        assert regel in tekst, f"sql/03_smalle_deur.sql mist '{regel}'."


def test_de_dagtaak_volgt_de_huidige_portefeuille_en_niet_de_geschiedenis():
    tekst = SNAPSHOT.read_text(encoding="utf-8")
    assert "hb.actieve_tickers(" in tekst, (
        "De dagtaak hoort de aandelen van de ACTUELE uitvoering te volgen. "
        "Alles wat ooit gekozen is, wordt elke maand een langere lijst."
    )
    assert "for s in signalen:" not in tekst, (
        "Hier werd over alle signalen gelopen; dat is precies de te wijde lijst."
    )


def test_een_onvolledige_dag_is_een_fout():
    meldingen = meldingen_per_afloop(SNAPSHOT)
    assert komt_voor(meldingen["stop"], "niet compleet"), (
        "Een dag met een ontbrekende koers hoort de taak te laten falen, niet "
        "stil een gat in de grafiek achter te laten."
    )
    assert not komt_voor(meldingen["klaar"], "niet compleet")


def test_de_dagtaak_krijgt_meerdere_kansen_per_avond():
    """Het venster voor de wisselkoers is in de zomertijd nog geen drie uur.

    GitHub start een geplande taak geregeld later dan gevraagd - op
    7 oktober 2026 meteen de eerste keer, met ruim drie uur. Met een enkel
    tijdstip is zo'n vertraging meteen een dag zonder wisselkoers.
    """
    regels = WORKFLOW.read_text(encoding="utf-8").splitlines()
    tijden = [r for r in regels if r.strip().startswith("- cron:")]
    assert len(tijden) >= 3, (
        "Er hoort meer dan een starttijd te staan, anders is een vertraging van "
        "GitHub meteen een gemiste wisselkoers."
    )


def test_een_hik_bij_yahoo_is_nog_geen_ontbrekende_koers():
    tekst = SNAPSHOT.read_text(encoding="utf-8")
    assert "tweede poging" in tekst, (
        "Yahoo laat geregeld een enkel aandeel weg uit een verzoek om meerdere "
        "tegelijk. Dat hoort apart opnieuw gevraagd te worden voor de taak faalt."
    )


def test_een_ontbrekende_wisselkoers_binnen_het_venster_is_een_fout():
    meldingen = meldingen_per_afloop(SNAPSHOT)
    assert komt_voor(meldingen["stop"], "niet bruikbaar opgehaald"), (
        "Hoort de wisselkoers bij deze dag en levert Yahoo hem niet, dan is dat "
        "een probleem en geen reden om de dag half weg te schrijven."
    )


def test_herstellen_van_een_oude_dag_is_een_aparte_beheershandeling():
    assert HERSTEL.exists(), "scripts/herstel_dagkoers.py ontbreekt."
    tekst = HERSTEL.read_text(encoding="utf-8")
    assert "SUPABASE_SERVICE_KEY" in tekst, (
        "Herstellen hoort alleen te kunnen met de geheime sleutel, die niet in "
        "GitHub staat."
    )
    assert "audit_log" in tekst, "Een herstelactie hoort in het beheerslogboek."
    assert "herstel_dagkoers" not in WORKFLOW.read_text(encoding="utf-8"), (
        "Herstellen hoort nooit vanuit GitHub te gebeuren."
    )


# ------------------------------------------- de doorlopende portefeuille
def test_de_wissel_gebeurt_niet_vanuit_github():
    """Die schrijft in `executions`, en dat is bewijsmateriaal."""
    assert WISSEL.exists(), "scripts/leg_herbalans_vast.py ontbreekt."
    assert "leg_herbalans_vast" not in WORKFLOW.read_text(encoding="utf-8")


def test_dividend_zonder_conventie_stopt_de_wissel():
    meldingen = meldingen_per_afloop(WISSEL)
    assert komt_voor(meldingen["stop"], "conventie ligt niet vast"), (
        "Stil nul euro dividend meerekenen legt een wissel met een verkeerd "
        "bedrag voor altijd vast."
    )


def test_een_tweede_instap_met_vers_geld_bestaat_niet():
    """De eerste keer is een instap, daarna is het altijd een wissel."""
    tekst = WISSEL.read_text(encoding="utf-8")
    assert "bereken_herbalans" in tekst
    assert "bereken_instap" not in tekst, (
        "bereken_instap() begint met 1.000 euro. Vanaf het tweede signaal mag "
        "dat nooit meer gebeuren."
    )
