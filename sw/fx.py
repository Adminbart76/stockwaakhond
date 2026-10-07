"""De wisselkoers van een uitvoeringsdag: één regel, voor iedereen hetzelfde.

Wat hier beslist is (7 oktober 2026)
====================================
De wisselkoers van een uitvoeringsdag is de koers uit de LAATSTE VOLLEDIG
AFGESLOTEN 1-minuutbalk van `EURUSD=X` waarvan het interval eindigt op of vóór
16:00:00 in New York - het moment van de slotbel. Normaal is dat de balk van
15:59 tot 16:00.

    ontbreekt die balk   dan de laatste afgesloten balk daarvoor, tot maximaal
                         vijf minuten eerder (dus een interval dat eindigt op of
                         na 15:55:00)
    nooit                een balk die na 16:00:00 eindigt
    ontbreekt alles      dan stopt het, en kijkt er een mens naar

Waarom dit de oude regel vervangt
=================================
Tot nu toe werd de DAGBALK van `EURUSD=X` gelezen op het moment dat Bart op het
BAT-bestand klikte. Die balk klikt nooit vast: zolang de valutadag loopt volgt
hij de koers van dit moment (gemeten op 6 oktober 2026: om 22.54 stond er
1,126253, twee uur later 1,126380), en is die dag voorbij dan rapporteert Yahoo
voor diezelfde datum een heel ander getal (0,3 procent verschil). Twee mensen die
dezelfde avond hetzelfde doen, kregen dus een ander getal.

Een 1-minuutbalk die is afgesloten, verandert niet meer. Wie om 22.30 kijkt en
wie om 00.30 kijkt, krijgt hetzelfde getal. En de balk hoort bij dezelfde minuut
als de slotkoersen waarmee hij in hetzelfde record staat.

Waarom het interval moet EINDIGEN op of voor 16:00
==================================================
Yahoo zet op een minuutbalk het tijdstempel van het BEGIN van de minuut. De balk
met tijdstempel 15:59 dekt dus 15:59:00 tot 16:00:00 en is precies de laatste
minuut voor de slotbel. De balk met tijdstempel 16:00 dekt 16:00:00 tot 16:01:00
en bevat dus handel NA de slotbel. Die mag niet gebruikt worden: dan zou de
wisselkoers informatie bevatten die de slotkoersen niet hebben.

Twee tijdstempels, want ze zeggen iets anders
=============================================
    fx_bar_end    het moment waar de koers BIJ HOORT (16:00:00 in New York)
    fx_asof       het moment waarop wij hem GELEZEN hebben

Die tweede blijft nodig en blijft in de kolom `fx_asof` staan: de database eist
dat het lezen binnen het venster na de slotbel gebeurt, en een latere lezer kan
daarmee zien dat er niet dagen later een gunstig getal is opgezocht. Zie
beslissing 11 in CLAUDE.md.

Het controlegetal van de ECB
============================
Yahoo bewaart minuutgegevens ongeveer dertig dagen. Een controleur die er een
jaar later naar kijkt, kan de balk niet meer ophalen. Daarom wordt dezelfde avond
een tweede, onafhankelijke koers vastgelegd: de ECB-referentiekoers van die dag,
gratis en permanent opvraagbaar door iedereen.

Die koers is de controle, niet de bron: hij wordt rond 16:00 in Frankfurt
vastgesteld, zes uur voor de Amerikaanse slotbel, en past dus slechter bij de
slotkoersen. Wijken de twee meer dan 1 procent af, dan stopt het en kijkt er een
mens naar: dat is geen normale dagbeweging maar een fout in de gegevens.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import timedelta
from typing import Dict, Optional

import pandas as pd

from .beurskalender import BEURS, SLOTBEL_UUR

SYMBOOL = "EURUSD=X"
BRON = (
    "Yahoo Finance EURUSD=X 1-minuutbalk, interval eindigend op of voor "
    "16:00:00 America/New_York"
)
TERUGVAL_MINUTEN = 5
ECB_BRON = "ECB referentiekoers EUR/USD (data-api.ecb.europa.eu, EXR D.USD.EUR.SP00.A)"
ECB_GRENS_PCT = 1.0

# De velden die mee in de gehashte tekst van een uitvoering gaan. Dezelfde namen
# staan in sql/04_dividend_en_fx.sql, waar de database narekent dat de balk op of
# voor de slotbel eindigt en dat het controlegetal niet meer dan een procent
# afwijkt. Alleen deze namen mogen erin: zo kan er via het wisselkoersbewijs
# niets anders in het bewijsmateriaal belanden.
BEWIJSVELDEN = {
    "fx_bar_start",
    "fx_bar_end",
    "fx_bar_normaal",
    "fx_control_source",
    "fx_control_date",
    "fx_control_rate",
    "fx_control_same_day",
    "fx_control_deviation_pct",
}


class GeenWisselkoers(ValueError):
    """Er is geen bruikbare minuutbalk, dus er wordt geen koers gekozen.

    Met opzet een harde fout. De vorige regel kon altijd een getal geven, en
    juist daardoor kon ze een getal geven dat bij een ander moment hoorde.
    """


# ------------------------------------------------------------- de balk kiezen
def _naar_beurstijd(index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Index(index)))
    if idx.tz is None:
        # Yahoo levert minuutbalken met tijdzone. Staat die er niet, dan is UTC
        # de enige lezing die niet van de instellingen van deze computer afhangt.
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(BEURS)


def slotbel_op(datum) -> pd.Timestamp:
    """16:00:00 in New York op die dag, met de juiste zomer- of wintertijd."""
    d = pd.Timestamp(datum).normalize()
    return pd.Timestamp(
        year=d.year, month=d.month, day=d.day, hour=SLOTBEL_UUR, tz=BEURS)


def kies_balk(
    balken,
    uitvoeringsdag,
    terugval_minuten: int = TERUGVAL_MINUTEN,
) -> dict:
    """Kiest de minuutbalk waarvan de koers de wisselkoers van die dag is.

    `balken` is een reeks slotkoersen per minuut, met het tijdstempel van het
    BEGIN van elke minuut (zoals Yahoo ze levert). De tijdzone mag elke zijn:
    er wordt omgerekend naar New York, zodat zomer- en wintertijd geen rol
    spelen.

    Geeft een beschrijving terug: de koers, het interval van de balk, of het de
    normale balk was of een terugval, en hoeveel seconden voor de slotbel de balk
    eindigde.
    """
    if balken is None or len(balken) == 0:
        raise GeenWisselkoers(
            "Er zijn geen minuutbalken van EURUSD=X ontvangen. Yahoo bewaart ze "
            "ongeveer dertig dagen; voor een oudere dag bestaat deze regel niet."
        )

    reeks = balken.iloc[:, 0] if isinstance(balken, pd.DataFrame) else balken
    reeks = pd.Series(list(reeks.values), index=_naar_beurstijd(reeks.index))
    reeks = reeks.dropna()
    reeks = reeks[reeks > 0].sort_index()

    slotbel = slotbel_op(uitvoeringsdag)
    vroegste_eind = slotbel - timedelta(minutes=terugval_minuten)

    # Het interval van een balk met tijdstempel t loopt van t tot t + 1 minuut.
    einden = reeks.index + timedelta(minutes=1)
    bruikbaar = reeks[(einden <= slotbel) & (einden >= vroegste_eind)]

    if len(bruikbaar) == 0:
        na_de_bel = reeks[(reeks.index >= slotbel)]
        uitleg = (
            f"Er is geen afgesloten 1-minuutbalk van EURUSD=X die eindigt tussen "
            f"{vroegste_eind.strftime('%H:%M:%S')} en "
            f"{slotbel.strftime('%H:%M:%S')} in New York op "
            f"{pd.Timestamp(uitvoeringsdag).date()}."
        )
        if len(na_de_bel):
            uitleg += (
                " Er zijn wel balken van na de slotbel. Die mogen niet gebruikt "
                "worden: ze bevatten handel die de slotkoersen niet kennen."
            )
        raise GeenWisselkoers(
            uitleg + " Er wordt niets gekozen; hier hoort een mens naar te kijken."
        )

    begin = pd.Timestamp(bruikbaar.index[-1])
    eind = begin + timedelta(minutes=1)
    tekort = int((slotbel - eind).total_seconds())

    return {
        "koers": float(bruikbaar.iloc[-1]),
        "bar_start": begin,
        "bar_end": eind,
        "bar_start_iso": begin.isoformat(),
        "bar_end_iso": eind.isoformat(),
        "slotbel_iso": slotbel.isoformat(),
        "seconden_voor_slotbel": tekort,
        "normaal": tekort == 0,
        "bron": BRON,
    }


# --------------------------------------------------------- het controlegetal
def lees_ecb_csv(tekst: str) -> Dict[str, float]:
    """Leest de CSV van de ECB: datum naar koers.

    Apart van het ophalen, zodat de regel zonder internet te testen is.
    """
    uit: Dict[str, float] = {}
    for rij in csv.DictReader(io.StringIO(tekst)):
        datum = (rij.get("TIME_PERIOD") or "").strip()
        waarde = (rij.get("OBS_VALUE") or "").strip()
        if not datum or not waarde:
            continue
        try:
            koers = float(waarde)
        except ValueError:
            continue
        if koers > 0:
            uit[datum] = koers
    return uit


def haal_ecb_referentiekoers(datum, dagen_terug: int = 10) -> dict:
    """De ECB-referentiekoers van die dag, of de laatste ervoor.

    De ECB publiceert niets op een dag dat het eurosysteem gesloten is terwijl
    Wall Street open is. Dan is de laatste eerdere koers nog steeds een
    onafhankelijk controlegetal, zolang erbij staat van welke dag hij is.
    """
    dag = pd.Timestamp(datum).normalize()
    begin = (dag - pd.Timedelta(days=dagen_terug)).date()
    url = (
        "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
        f"?startPeriod={begin}&endPeriod={dag.date()}&format=csvdata"
    )
    with urllib.request.urlopen(url, timeout=30) as antwoord:
        tekst = antwoord.read().decode("utf-8")

    koersen = lees_ecb_csv(tekst)
    if not koersen:
        raise ValueError(
            "De ECB gaf geen enkele referentiekoers terug voor de dagen rond "
            f"{dag.date()}."
        )

    bruikbaar = [k for k in koersen if k <= str(dag.date())]
    if not bruikbaar:
        raise ValueError(
            f"De ECB heeft voor {dag.date()} en de dagen ervoor geen "
            "referentiekoers gepubliceerd."
        )
    gekozen = max(bruikbaar)
    return {
        "koers": koersen[gekozen],
        "datum": gekozen,
        "zelfde_dag": gekozen == str(dag.date()),
        "bron": ECB_BRON,
    }


def vergelijk(koers: float, controle: float, grens_pct: float = ECB_GRENS_PCT) -> dict:
    """Hoeveel de gekozen koers van het controlegetal afwijkt.

    Geeft het verschil terug en of het binnen de grens blijft. Buiten de grens is
    geen marktbeweging meer maar een fout in de gegevens, en dan hoort er niets
    vastgelegd te worden.
    """
    if controle <= 0:
        raise ValueError("Het controlegetal moet groter dan nul zijn.")
    # Afronden voor het vergelijken, en niet erna: zonder dat is een verschil
    # van precies een procent in binaire getallen soms 1,0000000000000009 en dan
    # zou de grens van de rekenmachine afhangen in plaats van van de afspraak.
    afwijking = round((float(koers) / float(controle) - 1.0) * 100.0, 6)
    return {
        "afwijking_pct": afwijking,
        "grens_pct": float(grens_pct),
        "binnen_grens": abs(afwijking) <= float(grens_pct),
    }


# ------------------------------------------------------------------- ophalen
def haal_minuutbalken(datum, symbool: str = SYMBOOL):
    """De 1-minuutbalken van EURUSD=X rond die dag, bij Yahoo.

    Alleen het ophalen zit hier; de keuze staat in kies_balk(), zonder internet.
    """
    import yfinance as yf

    dag = pd.Timestamp(datum).normalize()
    ruw = yf.download(
        symbool,
        start=(dag - pd.Timedelta(days=1)).date(),
        end=(dag + pd.Timedelta(days=2)).date(),
        interval="1m",
        auto_adjust=False,
        progress=False,
        actions=False,
        threads=False,
    )
    if ruw is None or ruw.empty:
        raise GeenWisselkoers(
            f"Yahoo gaf geen minuutbalken van {symbool} rond {dag.date()}. "
            "Die gegevens worden ongeveer dertig dagen bewaard."
        )

    sluit = ruw["Close"]
    if isinstance(sluit, pd.DataFrame):
        sluit = sluit.iloc[:, 0]
    return sluit.dropna()


def wisselkoers_van(datum, gelezen_op: Optional[pd.Timestamp] = None) -> dict:
    """De volledige wisselkoers van een uitvoeringsdag, met controlegetal.

    Dit is wat er in het gehashte record komt te staan. Het haalt twee bronnen
    op: de minuutbalk bij Yahoo en de referentiekoers bij de ECB. Wijken ze meer
    dan 1 procent af, dan komt er een fout en wordt er niets gekozen.
    """
    balk = kies_balk(haal_minuutbalken(datum), datum)
    ecb = haal_ecb_referentiekoers(datum)
    verschil = vergelijk(balk["koers"], ecb["koers"])

    if not verschil["binnen_grens"]:
        raise GeenWisselkoers(
            f"De minuutbalk geeft {balk['koers']:.6f} dollar voor een euro en de "
            f"ECB-referentiekoers van {ecb['datum']} geeft {ecb['koers']:.6f}. "
            f"Dat is {verschil['afwijking_pct']:.2f} procent verschil, meer dan "
            f"de grens van {verschil['grens_pct']:.0f} procent. Zo groot is geen "
            "dagbeweging; dit is een fout in de gegevens en hier hoort een mens "
            "naar te kijken."
        )

    gelezen = pd.Timestamp(gelezen_op) if gelezen_op is not None \
        else pd.Timestamp.now(tz="UTC")

    return {
        "fx_rate": balk["koers"],
        "fx_source": BRON,
        "fx_asof": gelezen.isoformat(),
        "fx_bar_start": balk["bar_start_iso"],
        "fx_bar_end": balk["bar_end_iso"],
        "fx_bar_normaal": balk["normaal"],
        "fx_control_source": ecb["bron"],
        "fx_control_date": ecb["datum"],
        "fx_control_rate": ecb["koers"],
        "fx_control_same_day": ecb["zelfde_dag"],
        "fx_control_deviation_pct": verschil["afwijking_pct"],
        "balk": balk,
        "ecb": ecb,
    }


# ------------------------------------------- het bewijs achteraf narekenen
class WisselkoersbewijsOntbreekt(ValueError):
    """Een wissel zonder volledig wisselkoersbewijs wordt niet gebouwd.

    Dit is de tegenhanger van GeenWisselkoers. Daar is er geen bruikbare balk;
    hier is er wel een record, maar het draagt zijn bewijs niet mee. Allebei
    hard, en om dezelfde reden: een uitvoering is voorgoed vastgelegd, en wat er
    op dat moment niet in staat, kan later niemand nog narekenen. Yahoo bewaart
    minuutgegevens ongeveer dertig dagen.
    """


def _tijdstip(bewijs: dict, naam: str) -> pd.Timestamp:
    waarde = bewijs.get(naam)
    stempel = pd.Timestamp(waarde)
    if stempel.tz is None:
        raise WisselkoersbewijsOntbreekt(
            f"'{naam}' ({waarde}) heeft geen tijdzone. Zonder tijdzone hangt "
            "het moment af van de instellingen van de computer die het leest, "
            "en dan hoort de koers bij een andere minuut voor iedere lezer."
        )
    return stempel.tz_convert(BEURS)


def controleer_bewijs(
    bewijs: Optional[Dict[str, object]],
    uitvoeringsdag,
    fx_rate: float,
    terugval_minuten: int = TERUGVAL_MINUTEN,
    grens_pct: float = ECB_GRENS_PCT,
) -> dict:
    """Rekent het wisselkoersbewijs van een uitvoering na, zonder internet.

    Dit is dezelfde lijst controles als in sql/05_fx_bewijs_verplicht.sql, zodat
    de code en de database niet uit elkaar kunnen lopen. Hier staat ze zodat een
    wissel al op de computer van Bart strandt en er geen record ontstaat dat de
    database daarna weigert - het lokale bestand is de bron van waarheid, en een
    regel die daar wel in staat en in de database niet, is niet meer te herstellen.

    Geeft de nagerekende feiten terug. Weigert bij het kleinste gat.
    """
    bewijs = dict(bewijs or {})

    ontbreekt = sorted(
        naam for naam in BEWIJSVELDEN
        if bewijs.get(naam) is None or bewijs.get(naam) == ""
    )
    if ontbreekt:
        raise WisselkoersbewijsOntbreekt(
            "Het wisselkoersbewijs van deze uitvoering is niet volledig. "
            "Ontbreekt: " + ", ".join(ontbreekt) + ". Een wissel hoort de "
            "minuutbalk van de slotbel en het ECB-controlegetal mee te dragen; "
            "haal ze op met sw.fx.wisselkoers_van()."
        )
    vreemd = sorted(set(bewijs) - BEWIJSVELDEN)
    if vreemd:
        raise WisselkoersbewijsOntbreekt(
            "Dit hoort niet bij het wisselkoersbewijs: " + ", ".join(vreemd)
        )

    begin = _tijdstip(bewijs, "fx_bar_start")
    eind = _tijdstip(bewijs, "fx_bar_end")
    slotbel = slotbel_op(uitvoeringsdag)

    if eind <= begin:
        raise WisselkoersbewijsOntbreekt(
            f"De minuutbalk loopt van {begin} tot {eind}; het einde ligt niet "
            "na het begin."
        )
    if eind - begin != timedelta(minutes=1):
        raise WisselkoersbewijsOntbreekt(
            f"De balk van {begin} tot {eind} duurt geen minuut. De regel gaat "
            "over 1-minuutbalken; een langer interval is een andere koers."
        )
    if eind > slotbel:
        raise WisselkoersbewijsOntbreekt(
            f"De balk eindigt om {eind} en dat is na de slotbel van "
            f"{slotbel}. Zo'n balk bevat handel die de slotkoersen niet kennen."
        )
    if eind < slotbel - timedelta(minutes=terugval_minuten):
        raise WisselkoersbewijsOntbreekt(
            f"De balk eindigt om {eind}, meer dan {terugval_minuten} minuten "
            f"voor de slotbel van {slotbel}. Daarbuiten hoort een mens ernaar "
            "te kijken."
        )

    normaal = bewijs["fx_bar_normaal"]
    if not isinstance(normaal, bool):
        raise WisselkoersbewijsOntbreekt(
            "fx_bar_normaal hoort waar of niet waar te zijn, niet "
            f"'{normaal}'."
        )
    if normaal is not (eind == slotbel):
        raise WisselkoersbewijsOntbreekt(
            f"fx_bar_normaal zegt {normaal}, terwijl de balk om {eind} eindigt "
            f"en de slotbel om {slotbel} klinkt. Het ene zegt dat het de "
            "normale balk was en het andere niet."
        )

    bron = bewijs["fx_control_source"]
    if not isinstance(bron, str) or not bron.strip():
        raise WisselkoersbewijsOntbreekt(
            "Er staat geen bron bij het controlegetal. Zonder bron kan een "
            "latere lezer het niet opnieuw opvragen."
        )

    controle = float(bewijs["fx_control_rate"])
    if controle <= 0:
        raise WisselkoersbewijsOntbreekt(
            f"Het controlegetal van de wisselkoers is geen koers ({controle})."
        )

    dag = pd.Timestamp(uitvoeringsdag).normalize()
    controledag = pd.Timestamp(bewijs["fx_control_date"]).normalize()
    if controledag > dag:
        raise WisselkoersbewijsOntbreekt(
            f"Het controlegetal is van {controledag.date()} en dat is na de "
            f"uitvoeringsdag {dag.date()}. Een koers van later kan de koers van "
            "die dag niet controleren."
        )

    zelfde = bewijs["fx_control_same_day"]
    if not isinstance(zelfde, bool):
        raise WisselkoersbewijsOntbreekt(
            "fx_control_same_day hoort waar of niet waar te zijn, niet "
            f"'{zelfde}'."
        )
    if zelfde is not (controledag == dag):
        raise WisselkoersbewijsOntbreekt(
            f"fx_control_same_day zegt {zelfde}, terwijl het controlegetal van "
            f"{controledag.date()} is en de uitvoering van {dag.date()}."
        )

    opgeslagen = float(bewijs["fx_control_deviation_pct"])
    opnieuw = vergelijk(float(fx_rate), controle, grens_pct)
    if abs(opgeslagen - opnieuw["afwijking_pct"]) > 1e-5:
        raise WisselkoersbewijsOntbreekt(
            f"Er staat {opgeslagen:+.6f} procent afwijking in het bewijs, maar "
            f"{fx_rate} tegen {controle} geeft "
            f"{opnieuw['afwijking_pct']:+.6f} procent. Het opgeslagen getal "
            "klopt niet met de twee koersen waar het tussen staat."
        )
    if not opnieuw["binnen_grens"]:
        raise WisselkoersbewijsOntbreekt(
            f"De wisselkoers wijkt {opnieuw['afwijking_pct']:+.3f} procent af "
            f"van het controlegetal, meer dan de grens van {grens_pct:.0f} "
            "procent. Zo groot is geen dagbeweging."
        )

    return {
        "bar_start": begin,
        "bar_end": eind,
        "slotbel": slotbel,
        "seconden_voor_slotbel": int((slotbel - eind).total_seconds()),
        "normaal": normaal,
        "controle_koers": controle,
        "controle_datum": str(controledag.date()),
        "controle_zelfde_dag": zelfde,
        "afwijking_pct": opnieuw["afwijking_pct"],
    }
