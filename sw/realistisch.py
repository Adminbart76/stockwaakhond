"""De tweede curve: dezelfde strategie, met de kosten die je echt betaalt.

Waarom er twee curves zijn
==========================
De officiële forward-test rekent de transactiekost over de EENZIJDIGE omzet:
0,5 x de som van de gewichtsverschillen, letterlijk de formule van de bevroren
simulatie in `app.py`. Bij een volledige wissel van vijf aandelen verkoop je én
koop je, dus gaat er twee keer de portefeuillewaarde over de toonbank, en rekent
die formule toch 0,15 procent in plaats van 0,30 procent.

Dat is geen programmeerfout - het is de gangbare conventie - maar het is wel
optimistisch. Op 7 oktober 2026 is beslist: de officiële curve blijft exact zoals
ze is en er wordt niets herrekend, en hiernaast komt een tweede curve die de
kosten rekent over wat er WERKELIJK verhandeld is.

De officiële curve wordt hierdoor nooit vervangen. Dat is niet alleen een
afspraak maar ook hoe dit bestand gebouwd is: er zit geen enkele schrijfweg in.
De papieren keten wordt elke keer opnieuw gerekend uit de officiële records en
komt nergens in `executions`, in `forward_log/` of in een hash terecht.

Hoe de realistische kost gerekend wordt
=======================================
    verhandeld = som van de absolute dollarbedragen van alle echte orders
    kost       = verhandeld x 0,15 %

Een order is het verschil tussen wat een positie moet worden en wat ze is. Dus:

  * volledige wissel van vijf naar vijf andere aandelen: je verkoopt alles en
    koopt alles, verhandeld is ongeveer 200 % van de portefeuille, kost ongeveer
    0,30 %;
  * dezelfde vijf aandelen, alleen wat uit elkaar gelopen: er wordt alleen
    bijgesteld, dus verhandeld is een paar procent;
  * 5 % contant geld dat alleen gebruikt wordt om de bestaande vijf bij te
    kopen: dan is er 5 % verhandeld en geen 10 %. Er wordt niets verkocht, dus er
    valt ook niets dubbel te rekenen.

Dat laatste is precies waarom hier niet gewoon `omzet_factor=2` staat. Twee keer
de eenzijdige omzet nemen klopt bij een volledige wissel en is fout bij elke
wissel waar een deel van de posities blijft staan of waar alleen contant geld
belegd wordt.

Wat de twee curves gemeen hebben
================================
Dezelfde dagen, dezelfde aandelen, dezelfde slotkoersen, dezelfde wisselkoers,
dezelfde dividendconventie (bruto) en dezelfde maatstaf. Alleen de kost bij een
wissel verschilt. De instap van 6 oktober 2026 is in beide curves identiek: alles
stond contant, er werd alleen gekocht, en dan geven de twee formules hetzelfde
getal (1,50 euro op 1.000 euro). De curves lopen dus pas uit elkaar bij de eerste
echte wissel.

SPY is in beide curves hetzelfde fonds: het koopt een keer, met dezelfde kost op
dezelfde dag, en herbelegt daarna alleen zijn eigen dividend. Er is geen wissel,
dus er is ook geen verschil in wisselkosten.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import pandas as pd

from . import dividend as div
from .herbalans import sorteer_keten

KOSTENMODEL = (
    "werkelijk verhandelde notional: de som van de absolute dollarbedragen van "
    "alle koop- en verkooporders, maal het kostenpercentage"
)


# -------------------------------------------------------------- de rekenregel
def verhandeld_usd(
    huidige_waarden: Dict[str, float],
    doelwaarden: Dict[str, float],
) -> float:
    """De som van de absolute dollarbedragen van alle orders.

    Een aandeel dat blijft staan met hetzelfde bedrag geeft geen order en dus
    geen kost. Een aandeel dat eruit gaat, wordt volledig verkocht. Een aandeel
    dat erbij komt, wordt volledig gekocht. Contant geld dat belegd wordt, zit in
    de koopkant - en nergens anders, want anders zou het twee keer kosten.
    """
    namen = set(huidige_waarden) | set(doelwaarden)
    return round(sum(
        abs(float(doelwaarden.get(t, 0.0)) - float(huidige_waarden.get(t, 0.0)))
        for t in namen
    ), 8)


def kost_usd(
    huidige_waarden: Dict[str, float],
    doelwaarden: Dict[str, float],
    cost_pct: float,
) -> float:
    return round(verhandeld_usd(huidige_waarden, doelwaarden) * float(cost_pct) / 100.0, 8)


def stap(
    posities: Dict[str, float],
    koersen_usd: Dict[str, float],
    nieuwe_tickers: Sequence[str],
    contant_usd: float,
    cost_pct: float,
) -> dict:
    """Eén wissel van de papieren portefeuille.

    `posities` is aantal aandelen per ticker, `koersen_usd` de slotkoers van de
    uitvoeringsdag van elk aandeel dat je hebt en elk aandeel dat je krijgt.

    De doelbedragen worden - net als bij de officiële curve - bepaald op de
    waarde VOOR de kosten. Zo hoeft er niet rondgerekend te worden (de kost
    bepaalt de doelen, de doelen bepalen de kost) en blijft de uitkomst voor
    iedereen hetzelfde.
    """
    ontbreekt = sorted(
        {t for t in list(posities) + list(nieuwe_tickers)
         if not koersen_usd.get(t) or float(koersen_usd[t]) <= 0}
    )
    if ontbreekt:
        raise ValueError("Geen bruikbare koers voor: " + ", ".join(ontbreekt))

    waarden = {t: float(n) * float(koersen_usd[t]) for t, n in posities.items()}
    totaal = round(sum(waarden.values()) + float(contant_usd), 8)
    if totaal <= 0:
        raise ValueError("De papieren portefeuille is niets waard.")

    doel_per_stuk = totaal / len(nieuwe_tickers)
    doelen = {t: doel_per_stuk for t in nieuwe_tickers}

    verhandeld = verhandeld_usd(waarden, doelen)
    kost = round(verhandeld * float(cost_pct) / 100.0, 8)
    belegd = round(totaal - kost, 8)
    if belegd <= 0:
        raise ValueError("Na de kosten blijft er niets over om te beleggen.")

    nieuw = {
        t: round((belegd / len(nieuwe_tickers)) / float(koersen_usd[t]), 10)
        for t in nieuwe_tickers
    }
    return {
        "posities": nieuw,
        "waarde_voor_usd": totaal,
        "verhandeld_usd": verhandeld,
        "verhandeld_deel": round(verhandeld / totaal, 10),
        "kost_usd": kost,
        "belegd_usd": belegd,
        "kostenmodel": KOSTENMODEL,
    }


# --------------------------------------------------- de hele papieren keten
def _koersen_van(uitvoering: dict) -> Dict[str, float]:
    """De slotkoersen van de uitvoeringsdag, uit het officiële record zelf.

    Niets wordt opnieuw opgehaald: de koersen waarmee de officiële wissel
    gerekend is, staan in het gehashte record. Daardoor kan de papieren curve
    nooit op andere koersen rusten dan de officiële.
    """
    koersen: Dict[str, float] = {}
    for p in (uitvoering.get("opening", {}) or {}).get("positions", []):
        koersen[p["ticker"]] = float(p["close_usd"])
    for p in uitvoering["positions"]:
        koersen[p["ticker"]] = float(p["buy_price_usd"])
    bm = uitvoering["benchmark"]
    opening = uitvoering.get("opening") or {}
    if opening.get("benchmark_close_usd"):
        koersen[bm["ticker"]] = float(opening["benchmark_close_usd"])
    else:
        koersen[bm["ticker"]] = float(bm["buy_price_usd"])
    return koersen


def papieren_keten(uitvoeringen: List[dict]) -> List[dict]:
    """De papieren portefeuille, stap voor stap, uit de officiële keten.

    Elke stap heeft dezelfde vorm als een uitvoering, zodat het verloop met
    dezelfde functie getekend kan worden. De controlegetallen zijn met opzet
    leesbare namen ("papier-1") en geen hashes: dit is geen bewijsmateriaal en
    het hoort er ook niet op te lijken.
    """
    keten = sorteer_keten(list(uitvoeringen or []))
    if not keten:
        return []

    eerste = keten[0]
    cost_pct = float(eerste["cost_pct"])
    koersen = _koersen_van(eerste)

    # De instap: alles stond contant en er werd alleen gekocht. De officiële en
    # de realistische formule geven hier hetzelfde bedrag.
    inleg_eur = float(eerste["start_capital_eur"])
    fx = float(eerste["fx_rate"])
    tickers = [p["ticker"] for p in eerste["positions"]]
    totaal_usd = round(inleg_eur * fx, 8)
    verhandeld = verhandeld_usd({}, {t: totaal_usd / len(tickers) for t in tickers})
    kost = round(verhandeld * cost_pct / 100.0, 8)
    belegd = round(totaal_usd - kost, 8)
    posities = {
        t: round((belegd / len(tickers)) / float(koersen[t]), 10) for t in tickers
    }

    stappen = [{
        "nummer": 1,
        "exec_hash": "papier-1",
        "prev_exec_hash": None,
        "execution_date": str(eerste["execution_date"]),
        "officieel_exec_hash": eerste["exec_hash"],
        "fx_rate": fx,
        "start_capital_eur": inleg_eur,
        "cost_pct": cost_pct,
        "cost_usd": kost,
        "cost_eur": round(kost / fx, 8),
        "verhandeld_usd": verhandeld,
        "verhandeld_deel": round(verhandeld / totaal_usd, 10),
        "invested_usd": belegd,
        "invested_eur": round(belegd / fx, 8),
        "positions": [
            {"ticker": t, "shares": n, "buy_price_usd": float(koersen[t])}
            for t, n in posities.items()
        ],
        "cash_usd": 0.0,
        "benchmark": dict(eerste["benchmark"]),
        "kostenmodel": KOSTENMODEL,
    }]

    for nummer, u in enumerate(keten[1:], start=2):
        koersen = _koersen_van(u)
        nieuwe = [p["ticker"] for p in u["positions"]]
        contant = _papieren_dividend(u, stappen)

        uit = stap(posities, koersen, nieuwe, contant, cost_pct)
        posities = uit["posities"]
        stappen.append({
            "nummer": nummer,
            "exec_hash": f"papier-{nummer}",
            "prev_exec_hash": f"papier-{nummer - 1}",
            "execution_date": str(u["execution_date"]),
            "officieel_exec_hash": u["exec_hash"],
            "fx_rate": float(u["fx_rate"]),
            "start_capital_eur": inleg_eur,
            "cost_pct": cost_pct,
            "cost_usd": uit["kost_usd"],
            "cost_eur": round(uit["kost_usd"] / float(u["fx_rate"]), 8),
            "verhandeld_usd": uit["verhandeld_usd"],
            "verhandeld_deel": uit["verhandeld_deel"],
            "invested_usd": uit["belegd_usd"],
            "invested_eur": round(uit["belegd_usd"] / float(u["fx_rate"]), 8),
            "dividend_cash_usd": round(float(contant), 8),
            "positions": [
                {"ticker": t, "shares": n, "buy_price_usd": float(koersen[t])}
                for t, n in posities.items()
            ],
            "cash_usd": 0.0,
            "benchmark": dict(u["benchmark"]),
            "kostenmodel": KOSTENMODEL,
        })

    return stappen


def _papieren_dividend(uitvoering: dict, stappen: List[dict]) -> float:
    """Het dividend dat de PAPIEREN portefeuille bij deze wissel ontvangt.

    De papieren portefeuille heeft andere aantallen aandelen dan de officiële
    (ze betaalt hogere kosten), dus het bedrag uit het officiële record kan niet
    overgenomen worden. Het bedrag per aandeel wel: dat staat in de uitsplitsing
    die bij elke wissel in het gehashte record komt.

    Staat die uitsplitsing er niet terwijl er wel dividend meegerekend is, dan
    wordt er niets geschat: dan stopt het. Een papieren curve die stilletjes een
    ander dividend meeneemt dan ze verdient, is net zo misleidend als een
    officiele curve die dat doet.
    """
    opening = uitvoering.get("opening") or {}
    totaal = float(opening.get("dividend_cash_usd") or 0.0)
    if totaal <= 0:
        return 0.0

    detail = opening.get("dividend_detail") or []
    if not detail:
        raise ValueError(
            f"De wissel van {uitvoering['execution_date']} rekent "
            f"{totaal:.2f} dollar dividend mee zonder uitsplitsing per aandeel. "
            "Dan is het bedrag voor de papieren portefeuille niet na te rekenen."
        )

    bedrag = 0.0
    for rij in detail:
        ex = pd.Timestamp(rij["ex_date"]).normalize()
        bezit = None
        for s in stappen:
            if pd.Timestamp(s["execution_date"]).normalize() < ex:
                bezit = s
        if bezit is None:
            continue
        aandelen = {p["ticker"]: float(p["shares"]) for p in bezit["positions"]}
        stuks = aandelen.get(rij["ticker"], 0.0)
        if stuks > 0:
            bedrag += stuks * float(rij["per_share_usd"])
    return round(bedrag, 8)


def bouw_verloop_papier(
    uitvoeringen: List[dict],
    koersen: pd.DataFrame,
    fx: pd.Series,
    dividenden: Optional[Sequence[dict]] = None,
    spy_events: Optional[List[dict]] = None,
) -> pd.DataFrame:
    """Het dagelijkse verloop van de papieren portefeuille, in euro.

    Gebruikt dezelfde tekenfunctie als de officiële curve, zodat er geen tweede
    rekenwijze naast de eerste kan ontstaan.
    """
    from .herbalans import bouw_verloop_keten

    stappen = papieren_keten(uitvoeringen)
    if not stappen:
        return pd.DataFrame()

    dividend_per_dag = pd.Series(dtype=float)
    if dividenden:
        events = []
        for e in div.portefeuille_dividenden(stappen, dividenden):
            events.append(e)
        dividend_per_dag = div.contant_per_betaaldag(events)

    return bouw_verloop_keten(
        stappen, koersen, fx,
        dividend_usd_per_dag=dividend_per_dag,
        spy_events=spy_events,
    )
