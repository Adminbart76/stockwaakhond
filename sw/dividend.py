"""Dividend: wie er recht op heeft, en wanneer het geld er werkelijk is.

De conventie ligt vast: BRUTO
=============================
Voor de officiële forward-test wordt het volledige uitgekeerde bedrag
meegerekend, voor belasting. Beslist op 7 oktober 2026, en vanaf dan geldt ze
altijd - er is geen keuze meer te maken bij een wissel.

Waarom bruto en niet netto: wat een belegger netto overhoudt, hangt af van zijn
woonplaats, zijn broker, zijn belastingverdrag en van regels die in de loop van
een forward-test veranderen. Een curve die daarvan afhangt, meet niet meer de
strategie. Bruto is bij beide kanten hetzelfde en voor iedereen narekenbaar.
Het nettobedrag blijft wel in de tabel `dividends` staan: het is informatie,
geen rekenbasis.

Twee datums die niet door elkaar mogen
======================================
    ex_date    de dag waarop het recht ontstaat. Wie het aandeel vóór die dag
               bezat, krijgt het dividend. Wie het op de ex-dag koopt, niet.
    pay_date   de dag waarop het geld op de rekening staat.

Daar zitten normaal twee tot zes weken tussen, en dat is geen detail:

  * valt er een wissel tussen de twee, dan hebben we recht op een dividend van
    een aandeel dat we op de betaaldag niet meer bezitten. Dat geld komt toch
    binnen. Het weglaten zou de strategie bestelen.
  * het geld is op de ex-dag nog niet beschikbaar. Zou je het op de ex-dag als
    contant geld meebeleggen, dan belegt de portefeuille geld dat er nog niet
    is - en bij een stijgende markt rekent ze zich daarmee rijk.

Daarom: het RECHT wordt bepaald op de ex-dag, met het aantal aandelen dat we
toen hadden. Het GELD komt op de betaaldag.

Waarom "het aantal aandelen vóór de ex-dag"
===========================================
Een aandeel dat je op de ex-dag zelf koopt, geeft geen recht op dat dividend.
Onze wissels gebeuren tegen de slotkoers van de uitvoeringsdag. Valt een ex-dag
op een uitvoeringsdag, dan was het oude mandje die dag in bezit en het nieuwe
nog niet. De functies hieronder kijken daarom naar de laatste uitvoering die
STRIKT VOOR de ex-dag ligt.

Dezelfde regel geldt voor de SPY-aandelen die met herbelegd dividend gekocht
zijn. Die worden gekocht tegen de slotkoers van de herbelegdag, dus een
herbelegging die op een ex-dag valt, geeft geen recht op het dividend van die
ex-dag. Komt een betaaldag van het ene dividend toevallig op de ex-dag van het
volgende, dan tellen de nieuwe aandelen pas vanaf het dividend daarna mee.

SPY herbelegt, wij ook - maar op een andere manier
==================================================
Aan onze kant blijft het dividend contant staan tot de volgende wissel en wordt
het dan meebelegd; dat volgt uit de doorlopende portefeuille. SPY wisselt nooit
en zou het dividend dus voor altijd contant houden. Dat is een systematisch
verschil in ons voordeel, en daarom herbelegt SPY zijn dividend in SPY zelf,
tegen de eerstvolgende geldige slotkoers op of na de betaaldag, zonder kosten.

Noem dat niet zonder meer een "total return index": de officiële
total-return-reeksen herbeleggen vaak op de ex-dag of met een andere
belastingconventie. Wat hier gebeurt is:

    SPY buy-and-hold met bruto dividendherbelegging op betaaldatum.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import pandas as pd

from .herbalans import sorteer_keten, uitvoering_voor

CONVENTIE = "bruto"
CONVENTIE_TEKST = (
    "bruto: het volledige uitgekeerde bedrag, voor belasting, aan beide kanten "
    "hetzelfde (vastgelegd 7 oktober 2026)"
)
BEDRAG_VELD = "gross_per_share_usd"


# --------------------------------------------------------------- één rij lezen
def lees_rij(rij: dict) -> dict:
    """Leest één rij uit de tabel `dividends` en weigert te raden.

    Ontbreekt de betaaldatum, dan kan er niet gerekend worden: dan is niet
    bekend wanneer het geld beschikbaar is, en dat bepaalt bij welke wissel het
    meegaat. Een betaaldatum zelf verzinnen (bijvoorbeeld "de ex-dag") zou een
    wissel met een verkeerd bedrag voor altijd vastleggen.
    """
    ticker = rij.get("ticker")
    if not ticker:
        raise ValueError("Een dividendrij zonder ticker.")

    if rij.get("ex_date") in (None, ""):
        raise ValueError(f"Het dividend van {ticker} heeft geen ex-datum.")
    if rij.get("pay_date") in (None, ""):
        raise ValueError(
            f"Het dividend van {ticker} op {rij['ex_date']} heeft geen "
            "betaaldatum. Zonder die datum is niet bekend wanneer het geld "
            "beschikbaar is, en dus bij welke wissel het meegaat. Vul de "
            "betaaldatum in met scripts/leg_dividend_vast.py; er wordt er geen "
            "verzonnen."
        )

    bedrag = rij.get(BEDRAG_VELD)
    if bedrag is None:
        raise ValueError(
            f"Het dividend van {ticker} op {rij['ex_date']} heeft geen "
            "brutobedrag per aandeel. De officiële curve rekent bruto; er wordt "
            "geen percentage verzonnen."
        )

    ex = pd.Timestamp(rij["ex_date"]).normalize()
    pay = pd.Timestamp(rij["pay_date"]).normalize()
    if pay < ex:
        raise ValueError(
            f"Het dividend van {ticker} zou betaald zijn op {pay.date()}, voor "
            f"de ex-datum {ex.date()}. Een van de twee datums is verkeerd."
        )
    if float(bedrag) < 0:
        raise ValueError(f"Het dividend van {ticker} op {ex.date()} is negatief.")

    return {
        "ticker": str(ticker),
        "ex_date": ex,
        "pay_date": pay,
        "per_share_usd": float(bedrag),
        "conventie": CONVENTIE,
        "source": rij.get("source") or "",
    }


def lees_rijen(dividenden: Optional[Sequence[dict]]) -> List[dict]:
    """Alle rijen gelezen en op ex-datum gezet. Eén foute rij stopt alles."""
    rijen = [lees_rij(r) for r in (dividenden or [])]
    return sorted(rijen, key=lambda r: (r["ex_date"], r["pay_date"], r["ticker"]))


def recht_op(
    uitvoeringen: List[dict],
    ticker: str,
    ex_date,
    benchmark_ticker: str = "SPY",
) -> float:
    """Hoeveel aandelen we van dat ticker hadden vlak voor die ex-dag.

    Nul betekent: geen recht op dat dividend. Deze ene regel wordt overal
    gebruikt - bij het berekenen én bij de controle of er een uitkering gemist
    is - zodat die twee niet uit elkaar kunnen lopen.

    Voor de maatstaf telt alleen het aantal uit de eerste uitvoering; wat er
    sinds de herbeleggingen is bijgekomen, rekent spy_dividenden() er zelf bij.
    """
    keten = sorteer_keten(list(uitvoeringen or []))
    if not keten:
        return 0.0

    if ticker == benchmark_ticker:
        begin = pd.Timestamp(keten[0]["execution_date"]).normalize()
        if pd.Timestamp(ex_date).normalize() <= begin:
            return 0.0
        return float(keten[0]["benchmark"]["shares"])

    bezit = uitvoering_voor(keten, ex_date)
    if bezit is None:
        return 0.0
    return float(
        {p["ticker"]: float(p["shares"]) for p in bezit["positions"]}.get(ticker, 0.0))


# ------------------------------------------------------- onze eigen vijf
def portefeuille_dividenden(
    uitvoeringen: List[dict],
    dividenden: Optional[Sequence[dict]],
    benchmark_ticker: str = "SPY",
) -> List[dict]:
    """Wat de vijf aandelen ons opleveren, per uitkering.

    Het recht wordt bepaald op de ex-dag met het aantal aandelen dat we toen
    hadden - ook als dat aandeel er bij een latere wissel uit is gegaan. Het
    geld staat op de betaaldag in de kas.

    Hadden we het aandeel op de ex-dag niet, dan staat er niets: geen bezit,
    geen dividend.
    """
    keten = sorteer_keten(list(uitvoeringen or []))
    uit: List[dict] = []

    for rij in lees_rijen(dividenden):
        if rij["ticker"] == benchmark_ticker:
            continue

        stuks = recht_op(keten, rij["ticker"], rij["ex_date"], benchmark_ticker)
        if stuks <= 0:
            continue

        bezit = uitvoering_voor(keten, rij["ex_date"])
        uit.append({
            **rij,
            "shares": stuks,
            "bedrag_usd": round(stuks * rij["per_share_usd"], 8),
            "recht_uit_uitvoering": bezit["exec_hash"] if bezit else None,
        })
    return uit


# ------------------------------------------------------------------ de maatstaf
def eerste_koers_vanaf(koersen: Optional[pd.Series], datum) -> tuple:
    """De eerstvolgende geldige slotkoers op of na die dag.

    Geeft (datum, koers) terug, of (None, None) als die dag nog niet bestaat.
    Dat laatste is geen fout: een dividend dat vandaag betaald wordt terwijl de
    beurs nog niet gesloten is, wordt morgen herbelegd.
    """
    if koersen is None or len(koersen) == 0:
        return None, None
    vanaf = pd.Timestamp(datum).normalize()
    reeks = koersen.dropna()
    reeks = reeks[reeks > 0]
    reeks = reeks[reeks.index >= vanaf]
    if len(reeks) == 0:
        return None, None
    return pd.Timestamp(reeks.index[0]), float(reeks.iloc[0])


def spy_dividenden(
    uitvoeringen: List[dict],
    dividenden: Optional[Sequence[dict]],
    spy_koersen: Optional[pd.Series] = None,
    benchmark_ticker: str = "SPY",
) -> List[dict]:
    """Het dividend van SPY, en wanneer het herbelegd is.

    Per uitkering: het aantal SPY-aandelen op de ex-dag (inclusief wat er bij
    eerdere herbeleggingen is bijgekomen, zolang die STRIKT VOOR de ex-dag
    plaatsvonden), het bedrag, en de dag waarop dat bedrag tegen de slotkoers in
    SPY is omgezet.

    Is er nog geen slotkoers op of na de betaaldag, dan staat het bedrag contant
    en wacht het. Zo kan er nooit herbelegd worden tegen een koers die nog niet
    bestond.
    """
    keten = sorteer_keten(list(uitvoeringen or []))
    if not keten:
        return []

    begin_dag = pd.Timestamp(keten[0]["execution_date"]).normalize()
    aandelen = float(keten[0]["benchmark"]["shares"])
    uit: List[dict] = []

    for rij in lees_rijen(dividenden):
        if rij["ticker"] != benchmark_ticker:
            continue
        # SPY wordt gekocht op de slotkoers van de eerste uitvoeringsdag. Een
        # ex-dag op of voor die dag geeft dus geen recht.
        if rij["ex_date"] <= begin_dag:
            continue

        # STRIKT voor de ex-dag, met dezelfde reden als bij onze eigen vijf:
        # aandelen die pas op de ex-dag zelf tegen de slotkoers gekocht zijn,
        # geven geen recht op het dividend van die ex-dag. Een herbelegging
        # gebeurt tegen de slotkoers van de herbelegdag, dus een herbelegging op
        # de ex-dag valt buiten het recht. Stond hier "<=", dan kreeg SPY een
        # dividend over aandelen die het die dag nog niet had.
        stuks = aandelen + sum(
            e["aandelen_bij"] for e in uit
            if e["herbeleg_datum"] is not None and e["herbeleg_datum"] < rij["ex_date"]
        )
        bedrag = round(stuks * rij["per_share_usd"], 8)
        koersdag, koers = eerste_koers_vanaf(spy_koersen, rij["pay_date"])

        uit.append({
            **rij,
            "shares": stuks,
            "bedrag_usd": bedrag,
            "herbeleg_datum": koersdag,
            "herbeleg_koers_usd": koers,
            "aandelen_bij": round(bedrag / koers, 10) if koers else 0.0,
            "wacht_op_koers": koers is None,
        })
    return uit


def spy_stand_op(
    begin_aandelen: float,
    spy_events: Optional[Sequence[dict]],
    datum,
) -> Dict[str, float]:
    """Hoeveel SPY-aandelen en hoeveel contant SPY-dividend er op die dag zijn.

    Contant is het bedrag dat al betaald is maar nog niet herbelegd. Zo telt een
    uitkering nooit dubbel: ze is contant óf ze zit in de aandelen.
    """
    dag = pd.Timestamp(datum).normalize()
    aandelen = float(begin_aandelen)
    contant = 0.0

    for e in spy_events or []:
        if e["pay_date"] > dag:
            continue
        herbelegd = e["herbeleg_datum"] is not None and e["herbeleg_datum"] <= dag
        if herbelegd:
            aandelen += float(e["aandelen_bij"])
        else:
            contant += float(e["bedrag_usd"])

    return {"aandelen": aandelen, "contant_usd": round(contant, 8)}


# ------------------------------------------------------------------ in vensters
def contant_per_betaaldag(events: Optional[Sequence[dict]]) -> pd.Series:
    """Het dividendgeld in dollar per betaaldag, opgeteld per dag.

    Dit is de reeks die het verloop nodig heeft: op de betaaldag komt het geld
    erbij, niet op de ex-dag.
    """
    bedragen: Dict[pd.Timestamp, float] = {}
    for e in events or []:
        dag = pd.Timestamp(e["pay_date"]).normalize()
        bedragen[dag] = bedragen.get(dag, 0.0) + float(e["bedrag_usd"])
    if not bedragen:
        return pd.Series(dtype=float)
    return pd.Series(bedragen).sort_index()


def betaald_tussen(
    events: Optional[Sequence[dict]],
    na,
    tot_en_met,
) -> List[dict]:
    """De uitkeringen waarvan het geld tussen twee dagen beschikbaar kwam.

    `na` is exclusief en `tot_en_met` inclusief, en dat is met opzet: het geld
    van een betaaldag die precies op een uitvoeringsdag valt, staat die avond in
    de kas en gaat dus mee in die wissel. Een betaaldag die gelijk is aan de
    VORIGE uitvoeringsdag is toen al meegegaan en mag niet nog eens meetellen.
    """
    van = pd.Timestamp(na).normalize()
    tot = pd.Timestamp(tot_en_met).normalize()
    return [
        e for e in events or []
        if van < pd.Timestamp(e["pay_date"]).normalize() <= tot
    ]


def som(events: Optional[Sequence[dict]]) -> float:
    return round(sum(float(e["bedrag_usd"]) for e in events or []), 8)


def detail(events: Optional[Sequence[dict]]) -> List[dict]:
    """De uitkeringen zoals ze in het gehashte record komen te staan.

    Met opzet per aandeel en per aandeel-bedrag, niet alleen een totaal: zonder
    die uitsplitsing kan een latere lezer (of de realistische tweede curve, die
    met andere aantallen rekent) het bedrag niet narekenen.
    """
    uit = []
    for e in sorted(events or [], key=lambda x: (x["pay_date"], x["ex_date"], x["ticker"])):
        uit.append({
            "ticker": e["ticker"],
            "ex_date": str(pd.Timestamp(e["ex_date"]).date()),
            "pay_date": str(pd.Timestamp(e["pay_date"]).date()),
            "per_share_usd": round(float(e["per_share_usd"]), 8),
            "shares": round(float(e["shares"]), 10),
            "bedrag_usd": round(float(e["bedrag_usd"]), 8),
            "conventie": CONVENTIE,
        })
    return uit
