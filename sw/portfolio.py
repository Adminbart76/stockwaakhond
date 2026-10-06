"""De virtuele portefeuille van 1.000 euro.

De opzet in een notendop
========================
Op de eerste beursdag na een signaal wordt er ingestapt tegen de slotkoers van
die dag. Niet tegen de koers van de signaaldag zelf: die was op het moment van
kiezen al bekend, en daarmee zou je jezelf rijk rekenen met informatie die je
toen niet had.

Wat er een keer wordt vastgelegd en daarna nooit meer verandert:
  - de aankoopkoers per aandeel
  - het aantal aandelen
  - de wisselkoers van dat moment

Waarom dat moet: Yahoo verlaagt oude koersen zodra er dividend wordt
uitgekeerd. Zou je het aantal aandelen elke keer opnieuw berekenen, dan zou je
aankoopprijs maanden later nog veranderen en zou je rendement meeschuiven.

Drie keuzes die hier gemaakt zijn
=================================
1. ECHTE KOERSEN, niet de voor dividend herrekende.
   De portefeuille toont wat hij waard is, zoals bij een broker. Dividend komt
   er apart bij als geld, niet verstopt in de koers. Die twee door elkaar
   gebruiken zou het dividend dubbel tellen.

2. FRACTIES VAN AANDELEN zijn toegestaan.
   Met 200 euro koop je geen heel aandeel MPC, ILMN of VLO: die kosten meer.
   Zonder fracties kan 1.000 euro niet gelijk over vijf verdeeld worden. Dit
   kan echt bij brokers als Trading 212 of Revolut, niet bij DEGIRO of Bolero.

3. DE BENCHMARK KRIJGT EXACT DEZELFDE BEHANDELING.
   Dezelfde 1.000 euro, dezelfde kosten, dezelfde wisselkoers, dezelfde dag -
   en ook hetzelfde dividend. SPY keert vier keer per jaar uit; zou alleen
   StockWaakhond zijn dividend meegeteld krijgen, dan zou de strategie elk jaar
   ongeveer een procent voorsprong krijgen die ze niet verdiend heeft. Daarom
   gaat dividend bij allebei via dezelfde functie en dezelfde fiscale
   conventie. Zie dividend_reeks().

Over de wisselkoers
===================
Alles wordt in dollar gerekend tot en met de waarde van de posities, en pas
op het allerlaatste moment een keer omgezet naar euro. Zo kan het
wisselkoerseffect nooit dubbel geteld worden.

Wie het toch uitgesplitst wil zien, gebruikt splits_resultaat(): die ontleedt
het totaal exact in een koersdeel en een valutadeel die samen weer het totaal
vormen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .strategy import canonical_json, sha256_text

STARTKAPITAAL_EUR = 1000.0
KOSTEN_PCT = 0.15  # zelfde tarief als de bevroren simulatie


# ---------------------------------------------------------------- instappen
def bereken_instap(
    entry_hash: str,
    execution_date: str,
    tickers: List[str],
    koersen_usd: Dict[str, float],
    fx_eurusd: float,
    spy_koers_usd: float,
    fx_source: str,
    fx_asof: str,
    start_capital_eur: float = STARTKAPITAAL_EUR,
    cost_pct: float = KOSTEN_PCT,
) -> dict:
    """Berekent de instap. Geeft een compleet record terug, schrijft niets weg.

    fx_eurusd is het aantal dollar voor een euro (bijvoorbeeld 1,1266).
    """
    if not tickers:
        raise ValueError("Geen aandelen opgegeven.")
    if fx_eurusd <= 0:
        raise ValueError("De wisselkoers moet groter dan nul zijn.")
    for t in tickers:
        if t not in koersen_usd or not koersen_usd[t] or koersen_usd[t] <= 0:
            raise ValueError(f"Geen bruikbare koers voor {t}.")
    if spy_koers_usd <= 0:
        raise ValueError("Geen bruikbare SPY-koers.")

    kosten_eur = round(start_capital_eur * cost_pct / 100.0, 8)
    belegd_eur = round(start_capital_eur - kosten_eur, 8)
    per_positie_eur = belegd_eur / len(tickers)
    per_positie_usd = per_positie_eur * fx_eurusd

    posities = []
    for t in tickers:
        koers = float(koersen_usd[t])
        aandelen = per_positie_usd / koers
        posities.append({
            "ticker": t,
            "buy_price_usd": round(koers, 8),
            "shares": round(aandelen, 10),
            "invested_eur": round(per_positie_eur, 8),
            "invested_usd": round(per_positie_usd, 8),
            "target_weight": round(1.0 / len(tickers), 10),
        })

    # De benchmark koopt hetzelfde bedrag, op dezelfde dag, met dezelfde kosten.
    spy_aandelen = (belegd_eur * fx_eurusd) / float(spy_koers_usd)
    benchmark = {
        "ticker": "SPY",
        "buy_price_usd": round(float(spy_koers_usd), 8),
        "shares": round(spy_aandelen, 10),
        "invested_eur": round(belegd_eur, 8),
        "invested_usd": round(belegd_eur * fx_eurusd, 8),
    }

    payload = {
        "entry_hash": entry_hash,
        "execution_date": execution_date,
        "fx_pair": "EURUSD",
        "fx_rate": round(float(fx_eurusd), 10),
        "fx_source": fx_source,
        "fx_asof": fx_asof,
        "start_capital_eur": round(float(start_capital_eur), 8),
        "cost_pct": round(float(cost_pct), 8),
        "cost_eur": kosten_eur,
        "invested_eur": belegd_eur,
        "positions": posities,
        "benchmark": benchmark,
    }

    canoniek = canonical_json(payload)
    volledig = dict(payload)
    volledig["canonical_payload"] = canoniek
    volledig["exec_hash"] = sha256_text(canoniek)
    return volledig


# ----------------------------------------------------------------- waarderen
class KoersOntbreekt(ValueError):
    """Er is geen bruikbare koers, dus er wordt geen totaal berekend.

    Dit is met opzet een harde fout en geen stille terugval. Vroeger werd bij
    een ontbrekende koers de aankoopkoers aangehouden; dan toont het scherm een
    bedrag dat eruitziet als "nu waard" terwijl het dat niet is, en dat is
    erger dan geen bedrag. Wie dit opvangt, hoort te vertellen dat de waarde
    onbekend is - niet een getal te verzinnen.
    """

    def __init__(self, ontbreekt: List[str]):
        self.ontbreekt = list(ontbreekt)
        super().__init__(
            "Geen bruikbare koers voor: " + ", ".join(self.ontbreekt)
        )


@dataclass
class Waardering:
    """Wat de portefeuille op een bepaald moment waard is."""
    datum: str
    fx_eurusd: float
    posities: List[dict]
    totaal_eur: float
    dividend_eur: float
    inleg_eur: float
    resultaat_eur: float
    resultaat_pct: float
    spy_waarde_eur: float
    spy_dividend_eur: float
    spy_resultaat_eur: float
    spy_resultaat_pct: float
    voorsprong_pct: float


def waardeer(
    instap: dict,
    koersen_usd: Dict[str, float],
    fx_eurusd: float,
    datum: str,
    spy_koers_usd: Optional[float] = None,
    dividend_eur: float = 0.0,
    spy_dividend_eur: float = 0.0,
) -> Waardering:
    """Waardeert de portefeuille tegen de opgegeven koersen.

    Alles wordt in dollar opgeteld en pas op het einde een keer omgezet.

    Ontbreekt er een koers, dan komt er geen getal maar een KoersOntbreekt.
    Dividend telt bij beide kanten mee: dividend_eur bij de portefeuille,
    spy_dividend_eur bij de benchmark. Beide horen met dezelfde conventie
    berekend te zijn - gebruik daarvoor dividend_reeks().
    """
    if fx_eurusd <= 0:
        raise ValueError("De wisselkoers moet groter dan nul zijn.")

    ontbreekt = [
        p["ticker"] for p in instap["positions"]
        if not koersen_usd.get(p["ticker"]) or koersen_usd[p["ticker"]] <= 0
    ]
    if not (spy_koers_usd and spy_koers_usd > 0):
        ontbreekt.append(instap["benchmark"]["ticker"])
    if ontbreekt:
        raise KoersOntbreekt(ontbreekt)

    inleg = float(instap["start_capital_eur"])
    posities = []
    totaal_usd = 0.0

    for p in instap["positions"]:
        t = p["ticker"]
        koers_nu = koersen_usd[t]

        waarde_usd = p["shares"] * float(koers_nu)
        totaal_usd += waarde_usd

        waarde_eur = waarde_usd / fx_eurusd
        inzet_eur = float(p["invested_eur"])
        koersrendement = float(koers_nu) / float(p["buy_price_usd"]) - 1.0

        posities.append({
            "ticker": t,
            "aandelen": p["shares"],
            "aankoopkoers_usd": p["buy_price_usd"],
            "koers_usd": round(float(koers_nu), 6),
            "koersrendement_pct": round(koersrendement * 100, 4),
            "inzet_eur": round(inzet_eur, 2),
            "waarde_eur": round(waarde_eur, 2),
            "resultaat_eur": round(waarde_eur - inzet_eur, 2),
            "resultaat_pct": round((waarde_eur / inzet_eur - 1.0) * 100, 4) if inzet_eur else 0.0,
        })

    totaal_eur = totaal_usd / fx_eurusd + dividend_eur
    for p in posities:
        p["aandeel_pct"] = round(100.0 * p["waarde_eur"] / totaal_eur, 2) if totaal_eur else 0.0

    bm = instap["benchmark"]
    spy_eur = (bm["shares"] * float(spy_koers_usd)) / fx_eurusd + spy_dividend_eur

    resultaat = totaal_eur - inleg
    spy_resultaat = spy_eur - inleg

    return Waardering(
        datum=datum,
        fx_eurusd=float(fx_eurusd),
        posities=posities,
        totaal_eur=round(totaal_eur, 2),
        dividend_eur=round(dividend_eur, 2),
        inleg_eur=round(inleg, 2),
        resultaat_eur=round(resultaat, 2),
        resultaat_pct=round(resultaat / inleg * 100, 4),
        spy_waarde_eur=round(spy_eur, 2),
        spy_dividend_eur=round(spy_dividend_eur, 2),
        spy_resultaat_eur=round(spy_resultaat, 2),
        spy_resultaat_pct=round(spy_resultaat / inleg * 100, 4),
        voorsprong_pct=round((resultaat - spy_resultaat) / inleg * 100, 4),
    )


def splits_resultaat(rendement_usd: float, fx_start: float, fx_nu: float) -> Dict[str, float]:
    """Splitst het totaalrendement in een koersdeel en een wisselkoersdeel.

    De twee delen tellen per definitie precies op tot het totaal, dus er kan
    niets dubbel geteld worden:

        totaal = koersdeel + (1 + koersdeel) x valutadeel

    Dit is puur om te tonen. De portefeuillewaarde wordt er niet mee berekend.
    """
    valuta = fx_start / fx_nu - 1.0
    totaal = (1.0 + rendement_usd) * (fx_start / fx_nu) - 1.0
    return {
        "koersdeel_pct": round(rendement_usd * 100, 4),
        "valutadeel_pct": round((1.0 + rendement_usd) * valuta * 100, 4),
        "totaal_pct": round(totaal * 100, 4),
    }


# ------------------------------------------------------------------- dividend
def dividend_reeks(
    dividenden: List[dict],
    aandelen: Dict[str, float],
    fx: pd.Series,
    netto: bool = True,
) -> pd.Series:
    """Zet uitgekeerde dividenden om in euro per dag, voor de aandelen die je hebt.

    Dezelfde functie wordt gebruikt voor de vijf aandelen van StockWaakhond en
    voor de SPY-aandelen van de benchmark. Dat is geen gemak maar een eis: zodra
    de ene kant zijn dividend anders berekend krijgt dan de andere, meet de
    grafiek niet meer het verschil tussen twee beleggingen.

    dividenden: rijen zoals in de tabel `dividends`, met ticker, ex_date en
                het bedrag per aandeel in dollar (bruto en netto)
    aandelen:   hoeveel aandelen je van elk ticker hebt
    fx:         wisselkoers euro-dollar per datum
    netto:      netto nemen (wat een Belgische belegger overhoudt) of bruto

    Ontbreekt het nettobedrag terwijl je netto vraagt, dan is dat een fout en
    geen reden om er zelf een percentage bij te verzinnen: de fiscale
    conventie is een beslissing, niet een aanname.
    """
    bedragen: Dict[pd.Timestamp, float] = {}

    for rij in dividenden:
        ticker = rij.get("ticker")
        if ticker not in aandelen:
            continue

        veld = "net_per_share_usd" if netto else "gross_per_share_usd"
        per_aandeel = rij.get(veld)
        if per_aandeel is None:
            raise ValueError(
                f"Voor {ticker} op {rij.get('ex_date')} staat er geen "
                f"{'netto' if netto else 'bruto'}bedrag in de dividendtabel. "
                "Vul dat eerst in; er wordt geen percentage verzonnen."
            )

        datum = pd.Timestamp(rij["ex_date"]).normalize()
        koers = fx.asof(datum) if len(fx) else float("nan")
        if koers != koers or koers <= 0:
            raise ValueError(
                f"Geen wisselkoers bekend op {datum.date()}, dus het dividend "
                f"van {ticker} kan niet in euro omgerekend worden."
            )

        bedragen[datum] = bedragen.get(datum, 0.0) + (
            float(aandelen[ticker]) * float(per_aandeel) / float(koers)
        )

    if not bedragen:
        return pd.Series(dtype=float)
    return pd.Series(bedragen).sort_index()


# ------------------------------------------------------------------- verloop
def bouw_verloop(
    instap: dict,
    koersen: pd.DataFrame,
    fx: pd.Series,
    dividend_per_dag: Optional[pd.Series] = None,
    spy_dividend_per_dag: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Bouwt het dagelijkse verloop in euro, vanaf de instapdag.

    koersen: kolommen per ticker (echte slotkoersen), index is de datum
    fx:      wisselkoers euro-dollar per datum

    Dividend telt bij beide kanten mee en wordt bij beide op dezelfde dag
    opgeteld als geld, nooit via herrekende koersen.
    """
    start = pd.Timestamp(instap["execution_date"])
    index = koersen.index[koersen.index >= start]
    if len(index) == 0:
        return pd.DataFrame()

    aandelen = {p["ticker"]: p["shares"] for p in instap["positions"]}
    bm = instap["benchmark"]
    inleg = float(instap["start_capital_eur"])

    rijen = []
    dividend_opgeteld = 0.0
    spy_dividend_opgeteld = 0.0
    for dt in index:
        koers_dag = fx.reindex([dt]).ffill().iloc[0] if dt in fx.index else fx.asof(dt)
        if not koers_dag or koers_dag != koers_dag or koers_dag <= 0:
            continue

        if dividend_per_dag is not None and dt in dividend_per_dag.index:
            dividend_opgeteld += float(dividend_per_dag.loc[dt])
        if spy_dividend_per_dag is not None and dt in spy_dividend_per_dag.index:
            spy_dividend_opgeteld += float(spy_dividend_per_dag.loc[dt])

        totaal_usd = 0.0
        compleet = True
        for t, n in aandelen.items():
            if t not in koersen.columns:
                compleet = False
                break
            koers = koersen.at[dt, t]
            if koers != koers or koers <= 0:
                compleet = False
                break
            totaal_usd += n * float(koers)
        if not compleet:
            continue

        spy_koers = koersen.at[dt, bm["ticker"]] if bm["ticker"] in koersen.columns else None
        if spy_koers is None or spy_koers != spy_koers or spy_koers <= 0:
            continue

        rijen.append({
            "datum": dt,
            "fx_eurusd": float(koers_dag),
            "portefeuille_eur": totaal_usd / float(koers_dag) + dividend_opgeteld,
            "spy_eur": (bm["shares"] * float(spy_koers)) / float(koers_dag)
                       + spy_dividend_opgeteld,
            "dividend_eur": dividend_opgeteld,
            "spy_dividend_eur": spy_dividend_opgeteld,
        })

    df = pd.DataFrame(rijen)
    if df.empty:
        return df

    df = df.set_index("datum")
    df["resultaat_eur"] = df["portefeuille_eur"] - inleg
    df["resultaat_pct"] = (df["portefeuille_eur"] / inleg - 1.0) * 100
    df["spy_resultaat_pct"] = (df["spy_eur"] / inleg - 1.0) * 100
    df["voorsprong_pct"] = df["resultaat_pct"] - df["spy_resultaat_pct"]
    return df


def max_daling(reeks: pd.Series) -> float:
    """Grootste terugval vanaf een eerder hoogtepunt, in procent."""
    if reeks is None or len(reeks) == 0:
        return float("nan")
    return float((reeks / reeks.cummax() - 1.0).min() * 100)
