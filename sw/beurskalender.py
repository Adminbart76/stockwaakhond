"""Wanneer is een koers definitief? De klokregels op één plek.

Dit bestand bevat geen enkele koers en haalt niets op. Het weet alleen iets
over tijd: of een beursdag voorbij is, en of een dagkoers daarmee definitief
geworden is of nog kan bewegen.

Waarom dat apart staat
======================
Een voorlopige koers die als definitief wordt vastgelegd, is de ergste fout
die deze opzet kan maken. Hij is onomkeerbaar (vastleggen is append-only) en
hij is onzichtbaar (het getal ziet er volkomen normaal uit). Daarom staan de
regels erover in één bestand, zonder afhankelijkheid van Yahoo of van de
database, zodat ze los te testen zijn.

Elke functie hier kan een `nu` meekrijgen. In het echte leven blijft die leeg
en wordt de klok gelezen; in een test geef je een moment mee, zodat de uitkomst
niet afhangt van het uur waarop de test draait.

De twee klokken die meespelen
=============================
  de beurs      New York. De slotbel is 16:00 daar. Twintig minuten later
                beschouwen we de slotkoers als definitief: dat dekt de
                slotveiling en de vertraging waarmee Yahoo de gegevens levert.

  de valutadag  Yahoo dateert de dagbalken van EURUSD=X in de tijd van Londen.
                Zolang die dag loopt, is de dagkoers die Yahoo teruggeeft de
                koers van dit moment. Is de dag voorbij, dan geeft Yahoo voor
                diezelfde datum een ander getal terug - gemeten op 6 oktober
                2026 week dat 0,3 procent af. Een wisselkoers mag dus alleen
                vastgelegd worden op de dag zelf, na de slotbel en voor
                middernacht in Londen.

Wat hier NIET waar is, en wat dat betekent
==========================================
Een aandelenkoers klikt vast: na de slotbel verandert de slotkoers van die dag
niet meer. De dagbalk van EURUSD=X doet dat niet. Hij volgt de koers van dit
moment zolang de valutadag loopt, en wordt daarna een ander getal dat bij een
ander moment hoort. Er bestaat dus geen tijdstip waarop die dagkoers "definitief
wordt".

Daarom staat er bij een vastgelegde uitvoering niet wanneer de koers definitief
werd, maar wanneer wij hem gelezen hebben - en dwingt de regel hieronder af dat
dat lezen binnen het enige venster gebeurt waarin die waarde bij die
handelsdag hoort. Een latere lezer kan de koers van dat moment narekenen; bij
een verzonnen "slotmoment" zou dat niet kloppen.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

BEURS = ZoneInfo("America/New_York")
VALUTADAG = ZoneInfo("Europe/London")

SLOTBEL_UUR = 16          # 16:00 in New York
MARGE_MINUTEN = 20        # zoveel wachten we na de slotbel


def nu_utc(nu: Optional[datetime] = None) -> datetime:
    """Het moment waarop we rekenen. Zonder opgave: de echte klok."""
    if nu is None:
        return datetime.now(timezone.utc)
    if nu.tzinfo is None:
        raise ValueError("Geef een moment met tijdzone mee, anders is het dubbelzinnig.")
    return nu.astimezone(timezone.utc)


def handelsdag_nu(nu: Optional[datetime] = None) -> pd.Timestamp:
    """De beursdag die op dit moment in New York loopt.

    Niet de kalenderdag van onze eigen klok. Om half een 's nachts bij ons is
    het in New York nog de vorige dag, en dat is de dag waarvan de slotkoers
    net bekend is geworden. Wie hier de Belgische datum gebruikt, vraagt om de
    koers van een dag die nog moet beginnen.
    """
    return pd.Timestamp(nu_utc(nu).astimezone(BEURS).date())


def slotmoment(datum) -> datetime:
    """Het moment van de slotbel van die beursdag, in UTC.

    Dit is het moment waar een slotkoers bij hoort. Niet het moment waarop wij
    hem opschrijven: dat kan uren later zijn en zegt niets over de koers.
    """
    d = pd.Timestamp(datum)
    return datetime(d.year, d.month, d.day, SLOTBEL_UUR, 0, tzinfo=BEURS).astimezone(timezone.utc)


def beurs_is_gesloten_voor(
    datum,
    marge_minuten: int = MARGE_MINUTEN,
    nu: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Is de Amerikaanse beurs voor die dag definitief gesloten?

    Zolang de beurs open is, geeft Yahoo een voorlopige koers die later die dag
    nog verandert. Een koers die we vastleggen mag nooit een voorlopige koers
    zijn: die wordt immers nooit meer herzien.

    De marge van twintig minuten dekt de slotveiling en de vertraging waarmee
    de gegevens binnenkomen.
    """
    moment = nu_utc(nu).astimezone(BEURS)
    slot = slotmoment(datum).astimezone(BEURS)
    verschil = (moment - slot).total_seconds() / 60.0

    if verschil < marge_minuten:
        if verschil < 0:
            wachten = int(-verschil)
            hoelang = f"{wachten} minuten" if wachten < 120 else f"{wachten // 60} uur"
            return False, (
                f"De beurs sluit pas om 16:00 in New York, dat is over "
                f"{hoelang}. Nu is het daar {moment.strftime('%H:%M')}."
            )
        return False, (
            f"De beurs is net gesloten ({int(verschil)} minuten geleden). "
            f"Wacht tot {marge_minuten} minuten na de slotbel, zodat de "
            f"slotkoers definitief is."
        )

    return True, f"De beurs is gesloten. In New York is het nu {moment.strftime('%H:%M')}."


def laatste_voltooide_handelsdag(
    index,
    marge_minuten: int = MARGE_MINUTEN,
    nu: Optional[datetime] = None,
) -> Optional[pd.Timestamp]:
    """De laatste datum in de reeks waarvan de beursdag echt voorbij is.

    Yahoo levert tijdens de handelsdag al een rij voor vandaag, met een koers
    die dezelfde dag nog verandert. Zo'n rij mag nooit de signaaldatum worden:
    dan zou een keuze vastgelegd worden op cijfers die achteraf nog bewegen,
    en precies dat is wat deze forward-test onmogelijk moet maken.

    Geeft None terug als er geen enkele voltooide dag in de reeks staat.
    """
    datums = pd.DatetimeIndex(pd.to_datetime(pd.Index(index))).sort_values()
    for datum in reversed(list(datums)):
        gesloten, _ = beurs_is_gesloten_voor(datum, marge_minuten, nu)
        if gesloten:
            return pd.Timestamp(datum)
    return None


def valutadag_van(nu: Optional[datetime] = None) -> pd.Timestamp:
    """De datum waarin de valutadag van Yahoo nu loopt (tijd van Londen)."""
    moment = nu_utc(nu).astimezone(VALUTADAG)
    return pd.Timestamp(moment.date())


def wisselkoers_is_definitief(
    datum,
    marge_minuten: int = MARGE_MINUTEN,
    nu: Optional[datetime] = None,
) -> Tuple[bool, str, str]:
    """Mag de wisselkoers van die dag nu vastgelegd worden?

    Geeft drie dingen terug: mag het, in welke stand we staan
    ("te_vroeg", "goed", "te_laat" of "toekomst") en de uitleg in gewone taal.
    Die stand doet ertoe: te vroeg is gewoon wachten, te laat is een probleem
    waar iemand naar moet kijken.

    Het venster is: vanaf twintig minuten na de slotbel in New York, tot
    middernacht in Londen. Binnen dat venster beweegt het getal nog licht -
    de valutamarkt handelt door - maar het hoort bij deze handelsdag. Buiten
    dat venster hoort het bij een andere.

    Er is maar één venster waarin het antwoord ja is: op de dag zelf, na de
    slotbel in New York. Daarvoor beweegt de koers nog, daarna geeft Yahoo voor
    diezelfde datum een ander getal terug.

    Dat laatste is gemeten en niet verzonnen. Op 6 oktober 2026 gaf Yahoo voor
    die dag 1,1263 terug terwijl de dag liep; voor afgelopen dagen geeft het
    voor dezelfde datum een getal dat bij het begin van die dag hoort en tot
    0,3 procent afwijkt. Wie een dag te laat vastlegt, schrijft dus een andere
    koers op dan die bij de slotkoersen van die dag hoort.
    """
    dag = pd.Timestamp(datum).normalize()
    vandaag = valutadag_van(nu)

    if dag > vandaag:
        return False, "toekomst", (
            f"{dag.date()} ligt in de toekomst: de valutadag van Yahoo is nu "
            f"{vandaag.date()}."
        )

    gesloten, uitleg = beurs_is_gesloten_voor(dag, marge_minuten, nu)
    if not gesloten:
        return False, "te_vroeg", (
            "De wisselkoers van vandaag staat nog niet vast. " + uitleg
        )

    if dag < vandaag:
        return False, "te_laat", (
            f"Te laat voor de wisselkoers van {dag.date()}: de valutadag van "
            f"Yahoo is inmiddels {vandaag.date()}. Vanaf dat moment geeft Yahoo "
            f"voor {dag.date()} een ander getal terug dan de koers die bij de "
            f"slotkoersen van die dag hoort."
        )

    return True, "goed", (
        f"De wisselkoers van {dag.date()} mag vastgelegd worden: de beurs is "
        f"gesloten en de valutadag loopt nog."
    )


def venster_in_het_hier(datum) -> Tuple[str, str]:
    """Het venster waarin vastleggen mag, in Belgische tijd en gewone taal.

    Bedoeld om in een foutmelding te zetten, zodat er niet uitgerekend hoeft
    te worden hoe laat het hier dan is.
    """
    hier = ZoneInfo("Europe/Brussels")
    vanaf = (slotmoment(datum) + timedelta(minutes=MARGE_MINUTEN)).astimezone(hier)
    tot = datetime.combine(
        (pd.Timestamp(datum) + pd.Timedelta(days=1)).date(),
        datetime.min.time(), tzinfo=VALUTADAG,
    ).astimezone(hier)
    return vanaf.strftime("%H.%M"), tot.strftime("%H.%M")
