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
DIVIDEND_FX = PROJECT / "sql" / "04_dividend_en_fx.sql"
FX_BEWIJS = PROJECT / "sql" / "05_fx_bewijs_verplicht.sql"


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
    assert komt_voor(meldingen["stop"], "venster om de wisselkoers")
    assert komt_voor(meldingen["stop"], "beheershandeling")


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


# --------------------------------- het verplichte wisselkoersbewijs (ronde 5)
def test_het_wisselkoersbewijs_is_in_de_database_verplicht():
    """De bevinding van ronde 5.

    04 rekent de minuutbalk alleen na als het record die velden zelf meebrengt
    ("if inhoud ? 'fx_bar_end'"). Een wissel die ze wegliet, kwam nergens langs
    die controles. 05 maakt ze verplicht zodra er een voorganger is.
    """
    assert FX_BEWIJS.exists(), "sql/05_fx_bewijs_verplicht.sql ontbreekt."
    tekst = FX_BEWIJS.read_text(encoding="utf-8").lower()
    for regel in (
        "prev_exec_hash",                 # alleen een wissel, niet de instap
        "fx_bar_start",
        "fx_bar_end",
        "fx_bar_normaal",
        "fx_control_source",
        "fx_control_date",
        "fx_control_rate",
        "fx_control_same_day",
        "fx_control_deviation_pct",
        "draagt haar wisselkoersbewijs niet mee",   # de weigering zelf
        "interval '1 minute'",            # de balk duurt precies een minuut
        "interval '5 minutes'",           # hoogstens vijf minuten terugval
        "na de slotbel",                  # nooit een balk daarna
        "na de uitvoeringsdag",           # controlegetal niet van later
        "round((new.fx_rate / controle - 1) * 100, 6)",  # afwijking nagerekend
        "'deur_versie', 5",
    ):
        assert regel in tekst, f"sql/05_fx_bewijs_verplicht.sql mist '{regel}'."


def test_de_instap_van_6_oktober_valt_buiten_de_nieuwe_eis():
    """Er is maar een manier waarop die uitvoering erbuiten kan vallen.

    Faalt deze test, dan is de vrijstelling van de eerste schakel verdwenen en
    kan de vastgelegde uitvoering niet meer opnieuw geimporteerd worden.
    """
    tekst = FX_BEWIJS.read_text(encoding="utf-8")
    assert "coalesce(new.prev_exec_hash, inhoud->>'prev_exec_hash') is null" in tekst
    assert "before insert on public.executions" in tekst, (
        "De wachter hoort alleen bij een nieuwe rij te draaien; bestaande rijen "
        "blijven onaangeroerd."
    )


def test_de_code_en_de_database_hebben_dezelfde_bewijsvelden():
    """Lopen die twee lijsten uit elkaar, dan is er een gat of een valse eis."""
    from sw.fx import BEWIJSVELDEN

    tekst = FX_BEWIJS.read_text(encoding="utf-8")
    for veld in BEWIJSVELDEN:
        assert f"'{veld}'" in tekst, (
            f"{veld} staat in sw/fx.py maar wordt in sql/05 niet geeist."
        )


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


def test_een_gemist_dividend_stopt_de_wissel():
    """De conventie is sinds 7 oktober 2026 bruto en dus geen keuze meer.

    Daarmee verviel de oude blokkade ("kies eerst bruto of netto"). Het gevaar
    dat die blokkade dekte, is er nog wel: een uitkering die Yahoo kent en onze
    tabel niet. Dan zou de wissel met te weinig geld vastgelegd worden, en dat
    ligt daarna voor altijd vast. Daarom hoort dat nu de stopregel te zijn.
    """
    meldingen = meldingen_per_afloop(WISSEL)
    assert komt_voor(meldingen["stop"], "niet in onze tabel staan"), (
        "Een dividend dat Yahoo kent en wij niet, hoort de wissel te stoppen."
    )
    assert komt_voor(meldingen["stop"], "leg_dividend_vast"), (
        "De melding hoort te zeggen waarmee je dat dividend vastlegt."
    )

    tekst = WISSEL.read_text(encoding="utf-8")
    assert "--dividend=" not in tekst, (
        "Bruto staat vast; er valt bij een wissel niets meer te kiezen."
    )
    assert "net_per_share_usd" not in tekst, (
        "De officiele curve rekent bruto. Het nettobedrag is informatie."
    )


def test_het_dividend_gaat_op_de_betaaldatum_mee_en_niet_op_de_exdatum():
    """Op de ex-datum ontstaat het recht; het geld is er pas op de betaaldatum.

    Zou de wissel op de ex-datum rekenen, dan belegt de portefeuille geld dat ze
    nog niet heeft - en bij een stijgende markt rekent ze zich daarmee rijk.
    """
    tekst = WISSEL.read_text(encoding="utf-8")
    assert "betaald_tussen" in tekst, (
        "De selectie hoort op de betaaldatum te gebeuren."
    )
    assert "ex_date=gt." not in tekst, (
        "De oude selectie op ex-datum hoort weg te zijn."
    )


def test_de_wisselkoers_komt_uit_de_minuutbalk_met_een_controlegetal():
    tekst = WISSEL.read_text(encoding="utf-8")
    assert "wisselkoers_van" in tekst, (
        "De wisselkoers hoort uit sw/fx.py te komen: de afgesloten minuutbalk "
        "van de slotbel."
    )
    assert "haal_wisselkoers" not in tekst, (
        "De oude dagbalk hing af van het moment van klikken."
    )
    meldingen = meldingen_per_afloop(WISSEL)
    assert komt_voor(meldingen["stop"], "controlegetal"), (
        "Zonder het onafhankelijke controlegetal van de ECB hoort er niets "
        "vastgelegd te worden."
    )


def test_een_geweigerde_database_zegt_niet_dat_er_niets_vastligt():
    """Lokaal eerst, database daarna. Dan kan die tweede stap mislukken.

    Als dat gebeurt, staat de wissel wél lokaal. "Er is niets vastgelegd" zou
    dan een onwaarheid zijn waardoor iemand opnieuw begint te rekenen - en dan
    hangt de uitkomst af van de koersen van dat latere moment.
    """
    tekst = WISSEL.read_text(encoding="utf-8")
    assert "stop_maar_lokaal_staat_het" in tekst
    assert "--alleen-database" in tekst, (
        "Er hoort een weg te zijn om de database bij te halen zonder iets "
        "opnieuw te berekenen."
    )


def test_een_tweede_instap_met_vers_geld_bestaat_niet():
    """De eerste keer is een instap, daarna is het altijd een wissel."""
    tekst = WISSEL.read_text(encoding="utf-8")
    assert "bereken_herbalans" in tekst
    assert "bereken_instap" not in tekst, (
        "bereken_instap() begint met 1.000 euro. Vanaf het tweede signaal mag "
        "dat nooit meer gebeuren."
    )
