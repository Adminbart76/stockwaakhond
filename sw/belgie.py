"""De Belgische laag: wat een particulier hier werkelijk van zou overhouden.

Waarom deze laag naast de twee bestaande curves staat
=====================================================
Er zijn nu drie berekeningen, en ze meten elk iets anders:

    A  de officiele forward-test   de bevroren Strategie A, onaangeroerd
    B  de realistische marktcurve  dezelfde trades, kosten over de werkelijk
                                   verhandelde notional (sw/realistisch.py)
    C  de Belgische simulatie      dezelfde trades, plus de beurstaks, de
                                   brokerkosten, de wisselkosten en de
                                   Belgische belasting op dividend en op
                                   gerealiseerde winst

A blijft de primaire wetenschappelijke curve. C is een AFGELEIDE simulatie en
beantwoordt een andere vraag: "wat zou er ongeveer overblijven als een Belgische
particuliere belegger dezelfde trades werkelijk uitvoerde?"

C kan nooit terugschrijven naar A of B
======================================
Net als sw/realistisch.py zit er in dit bestand geen enkele schrijfweg. De
Belgische keten wordt elke keer opnieuw gerekend uit de officiele records
(`executions`), de vastgelegde koersen, de tabel `dividends`, de wisselkoersen en
een vaste, versienummerde configuratie. Er komt niets van terecht in
`executions`, in `forward_log/`, in `bewijs/` of in welke hash dan ook.

De configuratie heeft een versienaam (`BE_TAX_RULES_2026_V1`). Verandert de wet
in 2027, dan komt er een nieuwe versie naast; zo kan een latere wijziging nooit
stil de cijfers van 2026 veranderen.

Wat wel en wat niet uit de portefeuille gaat
============================================
Dat onderscheid is de kern van dit bestand.

    gaat er METEEN uit       de beurstaks (TOB), de brokerkosten, de
                             wisselkosten en de belasting die bij een
                             dividenduitkering wordt ingehouden
    is een JAARLIJKSE RAMING de belasting op gerealiseerde meerwaarde

De tweede groep wordt met opzet NIET per verkoop uit de portefeuille gehaald.
Geen enkele broker houdt die belasting per trade in; ze wordt achteraf aangegeven
en betaald. Zou ze hier toch per trade afgaan, dan toont de curve een verloop dat
nooit iemands rekening is geweest. Daarom staat ze apart, per kalenderjaar, als
"geschatte Belgische meerwaardebelasting" - een FISCALE RAMING en geen aangifte.

Hoe de orders bepaald worden
============================
De beurstaks wordt per order geheven, op het bedrag van dat order. Daarom kan
deze laag niet met een gemiddeld kostenpercentage werken: ze moet weten welke
orders er werkelijk zijn.

Een order is het verschil tussen wat een positie moet worden en wat ze is. Blijft
een aandeel in de Top-5 staan en is het bedrag al bijna goed, dan is er geen
order en dus geen taks. Gaat een aandeel eruit, dan wordt het volledig verkocht.

De kosten bepalen hoeveel er te beleggen valt, en wat er te beleggen valt bepaalt
de orders. Dat is een kringetje. Het wordt opgelost door het een paar keer door
te rekenen tot het niet meer beweegt (`_los_kosten_op`). Dat convergeert in drie
of vier rondes - de kosten zijn een half procent van de omzet - en geeft voor
iedereen hetzelfde getal. Zo kloppen drie dingen tegelijk: de taks staat op het
bedrag dat werkelijk verhandeld is, de aandelen die overblijven kloppen met die
orders, en er verdwijnt of ontstaat geen geld.

Dat is een klein verschil met sw/realistisch.py, dat de doelbedragen op de waarde
VOOR de kosten bepaalt. Daar kan dat, want daar hangt niets van het exacte
orderbedrag af. Hier wel: de beurstaks en de gerealiseerde winst hangen er
allebei van af.

FIFO
====
De gerealiseerde meerwaarde wordt per aandeel met FIFO bepaald: wat het eerst
gekocht is, wordt het eerst verkocht. Dat is nodig zodra een aandeel in de Top-5
blijft staan en er alleen bijgesteld wordt - dan liggen er meerdere pakketjes met
een verschillende aankoopprijs.

De aankoopprijs en de verkoopprijs worden in EURO bewaard, tegen de wisselkoers
van die dag. Het wisselkoerseffect zit dus in de meerwaarde, en dat is ook wat
een Belgische aangifte doet: de meerwaarde van een Amerikaans aandeel is het
verschil tussen twee eurobedragen.

Wat hier GEEN benchmark is
==========================
SPY blijft de wetenschappelijke maatstaf van de forward-test, en blijft daar
onaangeroerd staan. In deze laag wordt SPY met opzet NIET als Belgische
praktijkbenchmark meegerekend. Een Amerikaanse ETF heeft voor een Europese
particulier meestal geen KID (de informatiefiche die de PRIIPs-regels eisen),
waardoor hij er bij veel brokers niet rechtstreeks in kan. Een "Belgische
praktijkbenchmark" hoort dus een UCITS-instrument te zijn, met zijn eigen
beurstaks, kosten, dividendbeleid, valuta en brokerkosten.

Dat instrument is nog niet gekozen. De plaats ervoor staat klaar
(`PraktijkBenchmark`, `BELGISCHE_PRAKTIJKBENCHMARK = None`) en de keuze gebeurt
pas als broker en instrument onderzocht zijn.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from . import dividend as div
from .herbalans import sorteer_keten, uitvoering_op

# Een order kleiner dan een eurocent is geen order. Zonder deze drempel zou een
# aandeel dat in de Top-5 blijft staan en al bijna op gewicht zit, toch een vaste
# brokerkost en een beurstaks krijgen over een bedrag van niets.
MINIMUM_ORDER_EUR = 0.01

# De iteratie hieronder mag nooit eindeloos doorlopen. Bij een halve procent
# kosten is ze na drie of vier rondes stil; vijftig is dus ruim, en een fout als
# ze dan nog beweegt is beter dan een getal dat van het aantal rondes afhangt.
#
# De marge staat op een miljoenste dollar. Lager kan niet: de bedragen worden op
# acht cijfers afgerond, en dan kan de laatste ronde eeuwig een honderdmiljoenste
# heen en terug blijven springen. Een miljoenste dollar is nog altijd tienduizend
# keer kleiner dan een cent.
MAX_RONDES = 50
NAUWKEURIG_USD = 1e-6


# ====================================================================== regels
@dataclass(frozen=True)
class TobTarief:
    """Het tarief van de taks op beursverrichtingen, met het maximum per order.

    Het maximum is wettelijk en geldt per verrichting. Bij onze orders van
    ongeveer 200 euro komt het nooit in de buurt, maar het hoort er wel in te
    staan: zonder dat maximum zou een latere, grotere portefeuille een taks
    krijgen die niemand betaalt.
    """
    pct: float
    max_eur: float


TOB_AANDEEL = TobTarief(pct=0.35, max_eur=1600.0)
TOB_OBLIGATIE = TobTarief(pct=0.12, max_eur=1300.0)
TOB_FONDS_DISTRIBUTIE = TobTarief(pct=0.12, max_eur=1300.0)
TOB_FONDS_KAPITALISATIE_BE = TobTarief(pct=1.32, max_eur=4000.0)


@dataclass(frozen=True)
class PraktijkBenchmark:
    """De plaats voor een latere Belgische praktijkbenchmark.

    Nog niet gekozen. Zodra er een UCITS-instrument gekozen is, hoort het hier
    met al zijn eigen eigenschappen te staan - niet alleen met een ticker, want
    de beurstaks en het dividendbeleid van een fonds verschillen van die van een
    gewoon aandeel.
    """
    ticker: str
    naam: str
    instrumenttype: str
    valuta: str
    dividendbeleid: str            # "distributie" of "kapitalisatie"
    lopende_kosten_pct_per_jaar: float
    bronheffing_pct: float


# Met opzet leeg. Zie de moduledocstring: SPY is de wetenschappelijke maatstaf en
# geen Belgische praktijkbenchmark.
BELGISCHE_PRAKTIJKBENCHMARK: Optional[PraktijkBenchmark] = None


@dataclass(frozen=True)
class BelgischeRegels:
    """Alle Belgische parameters op een plek, met een versienaam.

    Alles wat van de wet, van de broker of van de persoonlijke situatie afhangt,
    staat hier - en nergens anders in de code. Zo is in een oogopslag te zien
    welke aannames er in een cijfer zitten, en kan een wetswijziging een nieuwe
    versie krijgen in plaats van een stille aanpassing.

    `HERKOMST` hieronder zegt per parameter of hij exact is, een aanname, nog te
    bevestigen, of nog niet ingesteld.
    """
    naam: str

    # ---- beurstaks (TOB)
    tob: Mapping[str, TobTarief]
    instrumenttype_standaard: str = "aandeel"
    instrumenttype_per_ticker: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({}))

    # ---- broker; alles nul tot er een broker gekozen is
    broker_fixed_fee_per_order_eur: float = 0.0
    broker_variable_fee_pct: float = 0.0
    broker_minimum_fee_eur: float = 0.0
    fx_conversion_fee_pct: float = 0.0
    fx_conversie_bij_elke_order: bool = False

    # ---- de basistransactiekost van de forward-test (0,15 %)
    # None betekent: neem het tarief van de officiele keten over. Wordt er later
    # een echte broker ingesteld, dan hoort dit op 0.0 te staan, anders wordt
    # dezelfde kost twee keer gerekend.
    basiskost_pct: Optional[float] = None

    # ---- dividend
    roerende_voorheffing_pct: float = 30.0
    dividend_vrijstelling_eur: float = 833.0
    external_dividend_exemption_used_eur: float = 0.0
    foreign_withholding_pct: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType({"US": 15.0}))
    land_standaard: str = "US"
    land_per_ticker: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({}))

    # ---- meerwaarde
    meerwaarde_pct: float = 10.0
    meerwaarde_vrijstelling_eur: float = 4855.0
    external_capital_gain_exemption_used_eur: float = 0.0
    # Of de transactiekosten in de meerwaardebasis mogen. Standaard niet: de
    # meerwaarde wordt gerekend op de orderbedragen zelf. Zie BELGIE.md.
    kosten_in_meerwaardebasis: bool = False

    @property
    def broker_ingesteld(self) -> bool:
        return bool(
            self.broker_fixed_fee_per_order_eur
            or self.broker_variable_fee_pct
            or self.broker_minimum_fee_eur
        )

    @property
    def fx_kosten_ingesteld(self) -> bool:
        return bool(self.fx_conversion_fee_pct)


BE_TAX_RULES_2026_V1 = BelgischeRegels(
    naam="BE_TAX_RULES_2026_V1",
    tob=MappingProxyType({
        "aandeel": TOB_AANDEEL,
        "obligatie": TOB_OBLIGATIE,
        "fonds_distributie": TOB_FONDS_DISTRIBUTIE,
        "fonds_kapitalisatie_be": TOB_FONDS_KAPITALISATIE_BE,
    }),
)

REGELS_NU = BE_TAX_RULES_2026_V1

# Per parameter: is het een vaststaand tarief, een aanname, nog te bevestigen, of
# nog niet ingesteld? Het dashboard en BELGIE.md lezen hier uit, zodat een
# aanname nooit als zekerheid op het scherm komt.
STATUS_EXACT = "exact"
STATUS_AANNAME = "aanname"
STATUS_TE_BEVESTIGEN = "te bevestigen"
STATUS_NIET_INGESTELD = "nog niet ingesteld"

HERKOMST: Mapping[str, dict] = MappingProxyType({
    "tob": {
        "naam": "Beurstaks (TOB) op gewone aandelen",
        "status": STATUS_EXACT,
        "waarde": "0,35 % per order, hoogstens 1.600 euro",
        "bron": "FOD Financiën, circulaire 2026/C/42 (FAQ beurstaks)",
        "gecontroleerd_op": "2026-10-07",
        "uitleg": "0,35 % is in deze simulatie de conventie voor gewone aandelen.",
    },
    "roerende_voorheffing_pct": {
        "naam": "Belgische belasting op dividend (roerende voorheffing)",
        "status": STATUS_EXACT,
        "waarde": "30 %",
        "bron": "Belgisch basistarief op roerende inkomsten",
        "gecontroleerd_op": "2026-10-07",
        "uitleg": "Geheven op het bedrag na aftrek van de buitenlandse bronheffing.",
    },
    "dividend_vrijstelling_eur": {
        "naam": "Vrijstelling op dividend, per persoon per jaar",
        "status": STATUS_TE_BEVESTIGEN,
        "waarde": "833 euro",
        "bron": "doorgegeven door Bart op 7 oktober 2026",
        "gecontroleerd_op": "2026-10-07",
        "uitleg": (
            "833 euro is het bedrag voor inkomstenjaar 2025 (aanslagjaar 2026). "
            "Voor inkomstenjaar 2026 noemen publieke bronnen 859 euro. Nog te "
            "bevestigen. De vrijstelling geldt over ALLE gewone dividenden van "
            "de belastingplichtige, niet alleen die van StockWaakhond."
        ),
    },
    "foreign_withholding_pct": {
        "naam": "Buitenlandse bronheffing op dividend",
        "status": STATUS_AANNAME,
        "waarde": "15 % voor Amerikaanse gewone aandelen",
        "bron": "verdragstarief België-VS; hangt af van broker en documenten",
        "gecontroleerd_op": "2026-10-07",
        "uitleg": (
            "Het verdragstarief geldt alleen als de broker de juiste "
            "documenten heeft ingediend (W-8BEN). Zonder dat is het 30 %. "
            "Instelbaar per land."
        ),
    },
    "meerwaarde_pct": {
        "naam": "Tarief van de belasting op winst bij verkoop",
        "status": STATUS_EXACT,
        "waarde": "10 %",
        "bron": "meerwaardebelasting op financiële activa, sinds 1 januari 2026",
        "gecontroleerd_op": "2026-10-07",
    },
    "meerwaarde_vrijstelling_eur": {
        "naam": "Vrijstelling op winst bij verkoop, per persoon per jaar",
        "status": STATUS_TE_BEVESTIGEN,
        "waarde": "4.855 euro",
        "bron": "doorgegeven door Bart op 7 oktober 2026",
        "gecontroleerd_op": "2026-10-07",
        "uitleg": (
            "Publieke bronnen noemen 10.000 euro per jaar per persoon, "
            "jaarlijks geïndexeerd. Dit bedrag is dus nog te bevestigen. Het "
            "staat hier zoals opgedragen; een wijziging hoort een nieuwe "
            "regelversie te krijgen in plaats van een stille aanpassing."
        ),
    },
    "broker_fixed_fee_per_order_eur": {
        "naam": "Vaste brokerkost per order",
        "status": STATUS_NIET_INGESTELD,
        "waarde": "0 euro",
        "bron": "er is nog geen broker gekozen",
        "gecontroleerd_op": "2026-10-07",
    },
    "broker_variable_fee_pct": {
        "naam": "Brokerkost in procent van het orderbedrag",
        "status": STATUS_NIET_INGESTELD,
        "waarde": "0 %",
        "bron": "er is nog geen broker gekozen",
        "gecontroleerd_op": "2026-10-07",
    },
    "broker_minimum_fee_eur": {
        "naam": "Laagste brokerkost per order",
        "status": STATUS_NIET_INGESTELD,
        "waarde": "0 euro",
        "bron": "er is nog geen broker gekozen",
        "gecontroleerd_op": "2026-10-07",
    },
    "fx_conversion_fee_pct": {
        "naam": "Wisselkost van de broker",
        "status": STATUS_NIET_INGESTELD,
        "waarde": "0 %",
        "bron": "er is nog geen broker gekozen",
        "gecontroleerd_op": "2026-10-07",
    },
    "basiskost_pct": {
        "naam": "Transactiekost van de forward-test",
        "status": STATUS_AANNAME,
        "waarde": "0,15 % over wat er verhandeld is",
        "bron": "de kostenaanname van de forward-test zelf",
        "gecontroleerd_op": "2026-10-07",
        "uitleg": (
            "Dit is de bestaande transactiekost van de forward-test, hier "
            "gerekend over wat er werkelijk verhandeld is. Ze staat op de "
            "plaats van de brokerkosten zolang er geen broker gekozen is. Komt "
            "er een echte brokerconfiguratie, dan hoort dit op 0 te staan."
        ),
    },
    "kosten_in_meerwaardebasis": {
        "naam": "Tellen de kosten mee bij het berekenen van de winst?",
        "status": STATUS_AANNAME,
        "waarde": "nee: de winst wordt op de orderbedragen gerekend",
        "bron": "aanname, nog na te gaan",
        "gecontroleerd_op": "2026-10-07",
    },
})


def met(regels: BelgischeRegels, **wijzigingen) -> BelgischeRegels:
    """Een kopie van de regels met andere parameters.

    De versienaam verandert hier niet automatisch mee: wie een parameter
    aanpast, hoort zelf te zeggen welke versie dat dan is.
    """
    return replace(regels, **wijzigingen)


# ============================================================== kosten per order
def instrumenttype(regels: BelgischeRegels, ticker: str) -> str:
    return regels.instrumenttype_per_ticker.get(ticker, regels.instrumenttype_standaard)


def tob_tarief(regels: BelgischeRegels, ticker: str) -> TobTarief:
    soort = instrumenttype(regels, ticker)
    if soort not in regels.tob:
        raise ValueError(
            f"Geen beurstakstarief bekend voor instrumenttype '{soort}' "
            f"(ticker {ticker}). Vul het aan in de regels; er wordt er geen "
            "verzonnen."
        )
    return regels.tob[soort]


def tob_eur(regels: BelgischeRegels, ticker: str, bedrag_eur: float) -> float:
    """De beurstaks op een order, aan beide kanten even hoog.

    Zowel een aankoop als een verkoop wordt belast, elk op zijn eigen bedrag.
    200 euro verkopen en 200 euro kopen is dus twee keer de taks op 200 euro, en
    niet een keer op 400.
    """
    tarief = tob_tarief(regels, ticker)
    return round(min(abs(float(bedrag_eur)) * tarief.pct / 100.0, tarief.max_eur), 8)


def brokerkost_eur(regels: BelgischeRegels, bedrag_eur: float) -> float:
    """De brokerkost van een order: vast plus variabel, met een minimum.

    Staat er niets ingesteld, dan is dit nul - en dan zegt het dashboard dat de
    brokerkosten nog niet ingesteld zijn, in plaats van te doen alsof er geen
    zijn.
    """
    if not regels.broker_ingesteld:
        return 0.0
    kost = (float(regels.broker_fixed_fee_per_order_eur)
            + abs(float(bedrag_eur)) * float(regels.broker_variable_fee_pct) / 100.0)
    return round(max(kost, float(regels.broker_minimum_fee_eur)), 8)


def fx_kost_eur(regels: BelgischeRegels, bedrag_eur: float) -> float:
    """De wisselkost op een bedrag dat van munt wisselt."""
    if not regels.fx_conversion_fee_pct:
        return 0.0
    return round(abs(float(bedrag_eur)) * float(regels.fx_conversion_fee_pct) / 100.0, 8)


def basiskost_pct_van(regels: BelgischeRegels, keten_cost_pct: float) -> float:
    """Het basistarief: dat van de regels, of dat van de officiele keten."""
    if regels.basiskost_pct is None:
        return float(keten_cost_pct)
    return float(regels.basiskost_pct)


def orderkosten(
    regels: BelgischeRegels,
    ticker: str,
    bedrag_eur: float,
    basiskost_pct: float,
) -> dict:
    """Alle kosten van een order, uitgesplitst. Alles in euro."""
    bedrag = abs(float(bedrag_eur))
    taks = tob_eur(regels, ticker, bedrag)
    broker = brokerkost_eur(regels, bedrag)
    wissel = fx_kost_eur(regels, bedrag) if regels.fx_conversie_bij_elke_order else 0.0
    basis = round(bedrag * float(basiskost_pct) / 100.0, 8)
    return {
        "tob_eur": taks,
        "broker_eur": broker,
        "fx_eur": wissel,
        "basis_eur": basis,
        "totaal_eur": round(taks + broker + wissel + basis, 8),
    }


def _leeg_kostenblok() -> dict:
    return {"tob_eur": 0.0, "broker_eur": 0.0, "fx_eur": 0.0,
            "basis_eur": 0.0, "totaal_eur": 0.0}


def _tel_op(doel: dict, bij: dict) -> None:
    for sleutel in ("tob_eur", "broker_eur", "fx_eur", "basis_eur", "totaal_eur"):
        doel[sleutel] = round(doel[sleutel] + float(bij.get(sleutel) or 0.0), 8)


# ============================================================== FIFO per aandeel
@dataclass
class Lot:
    """Een pakketje aandelen met zijn eigen aankoopprijs, in euro."""
    datum: str
    shares: float
    kost_eur: float

    @property
    def kost_per_aandeel_eur(self) -> float:
        return self.kost_eur / self.shares if self.shares else 0.0


class Posities:
    """De pakketjes per aandeel, in de volgorde waarin ze gekocht zijn.

    Verkopen gaat met FIFO: wat het eerst gekocht is, gaat het eerst weg. Dat is
    nodig zodra een aandeel in de Top-5 blijft staan en er alleen bijgesteld
    wordt - dan liggen er meerdere pakketjes met een verschillende prijs.
    """

    def __init__(self) -> None:
        self._lots: Dict[str, List[Lot]] = {}

    def aantal(self, ticker: str) -> float:
        return round(sum(l.shares for l in self._lots.get(ticker, [])), 10)

    def tickers(self) -> List[str]:
        return sorted(t for t, lots in self._lots.items() if sum(l.shares for l in lots) > 0)

    def kostprijs_eur(self, ticker: str) -> float:
        return round(sum(l.kost_eur for l in self._lots.get(ticker, [])), 8)

    def koop(self, ticker: str, datum: str, shares: float, kost_eur: float) -> None:
        if shares <= 0:
            return
        self._lots.setdefault(ticker, []).append(
            Lot(datum=str(datum), shares=float(shares), kost_eur=float(kost_eur)))

    def verkoop(
        self,
        ticker: str,
        datum: str,
        shares: float,
        opbrengst_eur: float,
    ) -> List[dict]:
        """Verkoopt FIFO en geeft per pakketje terug wat er gerealiseerd is.

        De opbrengst wordt over de pakketjes verdeeld naar rato van het aantal
        aandelen. Zo kan de som van de delen nooit afwijken van het geheel.
        """
        if shares <= 0:
            return []

        lots = self._lots.get(ticker, [])
        beschikbaar = sum(l.shares for l in lots)
        if shares > beschikbaar + 1e-8:
            raise ValueError(
                f"Er zouden {shares:.6f} aandelen {ticker} verkocht worden "
                f"terwijl er maar {beschikbaar:.6f} in de portefeuille zitten. "
                "De Belgische laag mag niet shorten."
            )
        shares = min(float(shares), beschikbaar)

        prijs_per_aandeel = float(opbrengst_eur) / shares
        te_gaan = shares
        gerealiseerd: List[dict] = []

        for lot in list(lots):
            if te_gaan <= 1e-12:
                break
            uit_dit_lot = min(lot.shares, te_gaan)
            deel = uit_dit_lot / lot.shares if lot.shares else 0.0
            kost = round(lot.kost_eur * deel, 8)
            opbrengst = round(prijs_per_aandeel * uit_dit_lot, 8)

            gerealiseerd.append({
                "ticker": ticker,
                "koop_datum": lot.datum,
                "verkoop_datum": str(datum),
                "shares": round(uit_dit_lot, 10),
                "kostprijs_eur": kost,
                "opbrengst_eur": opbrengst,
                "resultaat_eur": round(opbrengst - kost, 8),
            })

            lot.shares = round(lot.shares - uit_dit_lot, 10)
            lot.kost_eur = round(lot.kost_eur - kost, 8)
            te_gaan = round(te_gaan - uit_dit_lot, 12)

        self._lots[ticker] = [l for l in lots if l.shares > 1e-12]
        return gerealiseerd


# ================================================================== wisselkoers
def fx_op(
    datum,
    fx: Optional[pd.Series] = None,
    uitvoeringen: Optional[Sequence[dict]] = None,
) -> float:
    """De wisselkoers van een dag, voor een bedrag dat in euro moet.

    Eerst de dagreeks `fx_snapshots` (de laatste koers op of voor die dag). Is
    die er niet, dan de wisselkoers van de uitvoering die op die dag gold - die
    staat in het gehashte record en is dus even narekenbaar.

    Er wordt nooit een koers verzonnen: is er geen van beide, dan stopt het.
    """
    dag = pd.Timestamp(datum).normalize()

    if fx is not None and len(fx):
        reeks = fx.dropna()
        reeks = reeks[reeks > 0]
        if len(reeks):
            waarde = reeks.asof(dag)
            if waarde == waarde and waarde and float(waarde) > 0:
                return float(waarde)

    keten = sorteer_keten(list(uitvoeringen or []))
    if keten:
        geldig = uitvoering_op(keten, dag) or keten[0]
        koers = float(geldig["fx_rate"])
        if koers > 0:
            return koers

    raise ValueError(
        f"Geen wisselkoers bekend voor {dag.date()}. Zonder koers is er geen "
        "eurobedrag, en dan wordt er geen belasting geraamd."
    )


# ============================================================ dividendbelasting
def land_van(regels: BelgischeRegels, ticker: str) -> str:
    return regels.land_per_ticker.get(ticker, regels.land_standaard)


def bronheffing_pct_van(regels: BelgischeRegels, ticker: str) -> float:
    land = land_van(regels, ticker)
    if land not in regels.foreign_withholding_pct:
        raise ValueError(
            f"Geen buitenlandse bronheffing bekend voor land '{land}' "
            f"(ticker {ticker}). Vul het aan in de regels; er wordt er geen "
            "verzonnen."
        )
    return float(regels.foreign_withholding_pct[land])


def belast_dividend(regels: BelgischeRegels, ticker: str, bruto: float) -> dict:
    """Wat er van een uitkering overblijft, in dezelfde munt als `bruto`.

    Twee heffingen na elkaar, en met opzet niet twee keer op hetzelfde bedrag:

        1. het bronland houdt zijn deel in          (voor de VS: 15 %)
        2. Belgie heft 30 % op WAT ER OVERBLIJFT    (het netto grensbedrag)

    Zou de Belgische voorheffing op het brutobedrag gerekend worden, dan werd de
    buitenlandse bronheffing een tweede keer belast. Op een Amerikaans dividend
    blijft er zo ongeveer 59,5 % over.
    """
    bruto = float(bruto)
    if bruto < 0:
        raise ValueError("Een dividend kan niet negatief zijn.")

    bron_pct = bronheffing_pct_van(regels, ticker)
    bronheffing = round(bruto * bron_pct / 100.0, 8)
    basis = round(bruto - bronheffing, 8)
    rv = round(basis * float(regels.roerende_voorheffing_pct) / 100.0, 8)

    return {
        "bruto": round(bruto, 8),
        "bronheffing_pct": bron_pct,
        "bronheffing": bronheffing,
        "belgische_basis": basis,
        "rv_pct": float(regels.roerende_voorheffing_pct),
        "rv": rv,
        "netto": round(basis - rv, 8),
    }


def dividendjaren(
    uitkeringen: Sequence[dict],
    regels: BelgischeRegels = REGELS_NU,
) -> Dict[int, dict]:
    """De dividendbelasting per kalenderjaar, met de vrijstelling erin.

    De vrijstelling werkt niet aan de bron: de voorheffing wordt altijd eerst
    ingehouden, en je vraagt ze daarna terug via je belastingaangifte. Daarom
    staat ze hier als een bedrag dat je nog TERUG MOET KRIJGEN, en niet als geld
    dat al in de portefeuille zit.

    De vrijstelling geldt over ALLE gewone dividenden van de belastingplichtige.
    Wat er buiten StockWaakhond al van gebruikt is, komt binnen via
    `external_dividend_exemption_used_eur`.
    """
    per_jaar: Dict[int, dict] = {}

    for u in uitkeringen or []:
        jaar = int(pd.Timestamp(u["pay_date"]).year)
        blok = per_jaar.setdefault(jaar, {
            "jaar": jaar,
            "bruto_eur": 0.0,
            "buitenlandse_bronheffing_eur": 0.0,
            "belgische_basis_eur": 0.0,
            "rv_eur": 0.0,
            "netto_ontvangen_eur": 0.0,
            "aantal_uitkeringen": 0,
        })
        blok["bruto_eur"] = round(blok["bruto_eur"] + float(u["bruto_eur"]), 8)
        blok["buitenlandse_bronheffing_eur"] = round(
            blok["buitenlandse_bronheffing_eur"] + float(u["bronheffing_eur"]), 8)
        blok["belgische_basis_eur"] = round(
            blok["belgische_basis_eur"] + float(u["belgische_basis_eur"]), 8)
        blok["rv_eur"] = round(blok["rv_eur"] + float(u["rv_eur"]), 8)
        blok["netto_ontvangen_eur"] = round(
            blok["netto_ontvangen_eur"] + float(u["netto_eur"]), 8)
        blok["aantal_uitkeringen"] += 1

    vrij_totaal = float(regels.dividend_vrijstelling_eur)
    extern = float(regels.external_dividend_exemption_used_eur)
    beschikbaar = max(0.0, vrij_totaal - extern)

    for blok in per_jaar.values():
        bruto = blok["bruto_eur"]
        vrijgesteld = round(min(bruto, beschikbaar), 8)
        # De terugvordering is de Belgische voorheffing die op dat vrijgestelde
        # deel geheven is - niet 30 % van het brutobedrag. Op een buitenlands
        # dividend is de voorheffing immers op het netto grensbedrag geheven, dus
        # minder dan 30 % van bruto. Meer terugvragen dan er ingehouden is, kan
        # niet.
        deel = (vrijgesteld / bruto) if bruto > 0 else 0.0
        terug = round(blok["rv_eur"] * deel, 8)

        blok.update({
            "vrijstelling_totaal_eur": round(vrij_totaal, 8),
            "vrijstelling_extern_gebruikt_eur": round(extern, 8),
            "vrijstelling_beschikbaar_eur": round(beschikbaar, 8),
            "vrijgesteld_deel_eur": vrijgesteld,
            "terug_te_vorderen_eur": terug,
            "netto_na_terugvordering_eur": round(
                blok["netto_ontvangen_eur"] + terug, 8),
        })

    return dict(sorted(per_jaar.items()))


# ========================================================== meerwaardebelasting
def meerwaardejaren(
    verkopen: Sequence[dict],
    regels: BelgischeRegels = REGELS_NU,
) -> Dict[int, dict]:
    """De geschatte meerwaardebelasting per kalenderjaar.

    Dit is een RAMING en geen aangifte. De regels die hier gevolgd worden:

      * gerealiseerde minderwaarden van hetzelfde jaar gaan af van de
        gerealiseerde meerwaarden van dat jaar;
      * een verlies gaat niet over naar een volgend jaar;
      * van wat er dan overblijft is de eerste schijf vrijgesteld;
      * op de rest komt het tarief.

    De persoonlijke vrijstelling geldt per belastingplichtige, dus ook voor
    beleggingen buiten StockWaakhond. Wat daar al van gebruikt is, komt binnen
    via `external_capital_gain_exemption_used_eur`.
    """
    per_jaar: Dict[int, dict] = {}

    for v in verkopen or []:
        jaar = int(pd.Timestamp(v["verkoop_datum"]).year)
        blok = per_jaar.setdefault(jaar, {
            "jaar": jaar,
            "meerwaarden_eur": 0.0,
            "minderwaarden_eur": 0.0,
            "aantal_verkopen": 0,
        })
        resultaat = float(v["resultaat_eur"])
        if resultaat >= 0:
            blok["meerwaarden_eur"] = round(blok["meerwaarden_eur"] + resultaat, 8)
        else:
            blok["minderwaarden_eur"] = round(blok["minderwaarden_eur"] - resultaat, 8)
        blok["aantal_verkopen"] += 1

    vrij_totaal = float(regels.meerwaarde_vrijstelling_eur)
    extern = float(regels.external_capital_gain_exemption_used_eur)
    beschikbaar = max(0.0, vrij_totaal - extern)
    tarief = float(regels.meerwaarde_pct)

    for blok in per_jaar.values():
        netto = round(blok["meerwaarden_eur"] - blok["minderwaarden_eur"], 8)
        belastbaar_voor_vrijstelling = max(0.0, netto)
        gebruikt = round(min(belastbaar_voor_vrijstelling, beschikbaar), 8)
        basis = round(max(0.0, belastbaar_voor_vrijstelling - gebruikt), 8)

        blok.update({
            "netto_gerealiseerd_eur": netto,
            "vrijstelling_totaal_eur": round(vrij_totaal, 8),
            "vrijstelling_extern_gebruikt_eur": round(extern, 8),
            "vrijstelling_beschikbaar_eur": round(beschikbaar, 8),
            "gebruikte_vrijstelling_eur": gebruikt,
            "belastbare_basis_eur": basis,
            "tarief_pct": tarief,
            "belasting_eur": round(basis * tarief / 100.0, 8),
        })

    return dict(sorted(per_jaar.items()))


# ================================================================== de orders
def _orders_van(
    huidige_waarden_usd: Mapping[str, float],
    doelen_usd: Mapping[str, float],
) -> Dict[str, float]:
    """Per aandeel het verschil tussen wat het moet worden en wat het is.

    Positief is kopen, negatief is verkopen. Nul betekent: geen order.
    """
    namen = set(huidige_waarden_usd) | set(doelen_usd)
    return {
        t: round(float(doelen_usd.get(t, 0.0)) - float(huidige_waarden_usd.get(t, 0.0)), 8)
        for t in sorted(namen)
    }


def _kosten_van_orders(
    regels: BelgischeRegels,
    orders_usd: Mapping[str, float],
    fx_rate: float,
    basiskost_pct: float,
    alleen: Optional[Sequence[str]] = None,
) -> Tuple[dict, List[dict]]:
    """De kosten van een hele reeks orders, plus de regels van het logboek.

    `alleen` beperkt het tot de aandelen waarvoor er werkelijk een order is. Dat
    wordt één keer vooraf bepaald en daarna vastgehouden; zie `_los_kosten_op`.
    """
    totaal = _leeg_kostenblok()
    log: List[dict] = []
    toegestaan = None if alleen is None else set(alleen)

    for ticker in sorted(orders_usd):
        bedrag_usd = float(orders_usd[ticker])
        bedrag_eur = abs(bedrag_usd) / float(fx_rate)
        if toegestaan is None:
            if bedrag_eur < MINIMUM_ORDER_EUR:
                continue
        elif ticker not in toegestaan:
            continue

        kosten = orderkosten(regels, ticker, bedrag_eur, basiskost_pct)
        _tel_op(totaal, kosten)
        log.append({
            "ticker": ticker,
            "kant": "koop" if bedrag_usd > 0 else "verkoop",
            "bedrag_usd": round(abs(bedrag_usd), 8),
            "bedrag_eur": round(bedrag_eur, 8),
            "instrumenttype": instrumenttype(regels, ticker),
            **kosten,
        })

    return totaal, log


def _los_kosten_op(
    regels: BelgischeRegels,
    huidige_waarden_usd: Mapping[str, float],
    nieuwe_tickers: Sequence[str],
    totaal_usd: float,
    fx_rate: float,
    basiskost_pct: float,
) -> dict:
    """Zoekt de kosten die bij hun eigen orders passen.

    De kosten bepalen hoeveel er te beleggen valt, en dat bepaalt de orders, en
    die bepalen de kosten. Dat kringetje wordt hier doorgerekend tot het stil
    staat. Bij een halve procent kosten is dat na drie of vier rondes het geval.

    WELKE aandelen er een order krijgen, wordt één keer vooraf bepaald en daarna
    niet meer gewijzigd. Zonder die afspraak kan een aandeel dat bijna op gewicht
    staat bij elke ronde in en uit de lijst springen - de kost verandert dan met
    een sprongetje in plaats van vloeiend, en dan komt de berekening nooit tot
    rust. Het aandeel dat daardoor net wel of net niet meedoet, gaat over een
    bedrag van een cent.
    """
    if not nieuwe_tickers:
        raise ValueError("Geen nieuwe aandelen opgegeven.")

    # Eerst een proefronde, alleen om te bepalen WELKE aandelen een order
    # krijgen. Die lijst mag niet op de waarde VOOR de kosten gebaseerd worden:
    # een aandeel dat dan precies op gewicht staat, krijgt door de kosten alsnog
    # een klein order. Zou het daardoor buiten de lijst vallen, dan klopt het
    # geld niet meer - er wordt dan meer belegd dan er is.
    proef_doelen = {
        t: float(totaal_usd) / len(nieuwe_tickers) for t in nieuwe_tickers}
    proef_kosten, _ = _kosten_van_orders(
        regels, _orders_van(huidige_waarden_usd, proef_doelen),
        fx_rate, basiskost_pct)
    schatting_usd = round(proef_kosten["totaal_eur"] * float(fx_rate), 8)

    na_schatting = {
        t: (float(totaal_usd) - schatting_usd) / len(nieuwe_tickers)
        for t in nieuwe_tickers}
    actief = sorted(
        t for t, bedrag in _orders_van(huidige_waarden_usd, na_schatting).items()
        if abs(bedrag) / float(fx_rate) >= MINIMUM_ORDER_EUR
    )

    kosten_usd = 0.0
    doelen: Dict[str, float] = {}
    orders: Dict[str, float] = {}
    kosten = _leeg_kostenblok()
    log: List[dict] = []

    for _ in range(MAX_RONDES):
        per_stuk = (float(totaal_usd) - kosten_usd) / len(nieuwe_tickers)
        if per_stuk <= 0:
            raise ValueError("Na de kosten blijft er niets over om te beleggen.")
        doelen = {t: per_stuk for t in nieuwe_tickers}
        orders = _orders_van(huidige_waarden_usd, doelen)
        kosten, log = _kosten_van_orders(
            regels, orders, fx_rate, basiskost_pct, alleen=actief)
        nieuw_usd = round(kosten["totaal_eur"] * float(fx_rate), 8)
        if abs(nieuw_usd - kosten_usd) < NAUWKEURIG_USD:
            kosten_usd = nieuw_usd
            break
        kosten_usd = nieuw_usd
    else:
        raise ValueError(
            "De Belgische kosten komen niet tot rust. Dat hoort niet te kunnen "
            "bij kosten van minder dan een procent; er is iets mis met de "
            "ingestelde tarieven."
        )

    return {
        "kosten_usd": kosten_usd,
        "kosten": kosten,
        "orders": orders,
        "orderlog": log,
        "doelen_usd": doelen,
        "actief": actief,
    }


# ============================================================== de hele keten
def _koersen_van(uitvoering: dict) -> Dict[str, float]:
    """De slotkoersen van die uitvoeringsdag, uit het officiele record zelf.

    Niets wordt opnieuw opgehaald. Daardoor kan de Belgische curve nooit op
    andere koersen rusten dan de officiele.
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


def _stap_record(
    nummer: int,
    uitvoering: dict,
    posities_shares: Mapping[str, float],
    koersen: Mapping[str, float],
    contant_usd: float,
) -> dict:
    """Eén stap van de Belgische keten, in de vorm van een uitvoering.

    Dezelfde vorm, zodat het verloop en de dividendregels met dezelfde functies
    gerekend kunnen worden en er geen tweede rekenwijze naast de eerste ontstaat.
    De controlegetallen zijn met opzet leesbare namen ("belgie-1") en geen
    hashes: dit is geen bewijsmateriaal en het hoort er ook niet op te lijken.
    """
    return {
        "nummer": nummer,
        "exec_hash": f"belgie-{nummer}",
        "prev_exec_hash": f"belgie-{nummer - 1}" if nummer > 1 else None,
        "officieel_exec_hash": uitvoering["exec_hash"],
        "execution_date": str(uitvoering["execution_date"]),
        "fx_rate": float(uitvoering["fx_rate"]),
        "start_capital_eur": float(uitvoering["start_capital_eur"]),
        "cost_pct": float(uitvoering["cost_pct"]),
        # `buy_price_usd` is hier de SLOTKOERS van die uitvoeringsdag en niet de
        # prijs waarvoor dit pakketje ooit gekocht is. Het veld heet zo omdat de
        # vorm gelijk moet blijven aan die van een uitvoering; de echte
        # aankoopprijzen staan per pakketje in `Posities`, want alleen die
        # kunnen de meerwaarde bepalen.
        "positions": [
            {"ticker": t, "shares": round(float(n), 10),
             "buy_price_usd": float(koersen[t]), "close_usd": float(koersen[t])}
            for t, n in sorted(posities_shares.items()) if n > 0
        ],
        "cash_usd": round(float(contant_usd), 8),
        # De maatstaf wordt letterlijk overgenomen en NIET Belgisch gerekend.
        # Zie de moduledocstring: SPY is de wetenschappelijke maatstaf, geen
        # Belgische praktijkbenchmark.
        "benchmark": dict(uitvoering["benchmark"]),
    }


def _dividenden_in_venster(
    regels: BelgischeRegels,
    stappen: List[dict],
    rijen: Sequence[dict],
    na,
    tot_en_met,
    fx: Optional[pd.Series],
    uitvoeringen: Sequence[dict],
    benchmark_ticker: str,
) -> List[dict]:
    """De uitkeringen waarvan het geld in dat venster beschikbaar kwam.

    Het RECHT wordt bepaald met het aantal aandelen dat de Belgische
    portefeuille vóór de ex-dag had - dus met haar eigen, kleinere aantallen.
    Het bedrag per aandeel komt uit de tabel `dividends` en is voor alle drie de
    curves hetzelfde.
    """
    van = pd.Timestamp(na).normalize() if na is not None else None
    tot = pd.Timestamp(tot_en_met).normalize() if tot_en_met is not None else None

    uit: List[dict] = []
    for rij in rijen:
        if rij["ticker"] == benchmark_ticker:
            continue
        betaald = pd.Timestamp(rij["pay_date"]).normalize()
        if van is not None and betaald <= van:
            continue
        if tot is not None and betaald > tot:
            continue

        stuks = div.recht_op(stappen, rij["ticker"], rij["ex_date"], benchmark_ticker)
        if stuks <= 0:
            continue

        bruto_usd = round(stuks * float(rij["per_share_usd"]), 8)
        heffing = belast_dividend(regels, rij["ticker"], bruto_usd)
        koers = fx_op(betaald, fx, uitvoeringen)

        uit.append({
            "ticker": rij["ticker"],
            "ex_date": str(pd.Timestamp(rij["ex_date"]).date()),
            "pay_date": str(betaald.date()),
            "per_share_usd": float(rij["per_share_usd"]),
            "shares": round(stuks, 10),
            "fx_eurusd": koers,
            "bronheffing_pct": heffing["bronheffing_pct"],
            "rv_pct": heffing["rv_pct"],
            "bruto_usd": heffing["bruto"],
            "bronheffing_usd": heffing["bronheffing"],
            "rv_usd": heffing["rv"],
            "netto_usd": heffing["netto"],
            "bruto_eur": round(heffing["bruto"] / koers, 8),
            "bronheffing_eur": round(heffing["bronheffing"] / koers, 8),
            "belgische_basis_eur": round(heffing["belgische_basis"] / koers, 8),
            "rv_eur": round(heffing["rv"] / koers, 8),
            "netto_eur": round(heffing["netto"] / koers, 8),
        })

    return sorted(uit, key=lambda e: (e["pay_date"], e["ex_date"], e["ticker"]))


def belgische_keten(
    uitvoeringen: List[dict],
    dividenden: Optional[Sequence[dict]] = None,
    fx: Optional[pd.Series] = None,
    regels: BelgischeRegels = REGELS_NU,
) -> dict:
    """De hele Belgische simulatie, opnieuw gerekend uit de officiele records.

    Schrijft niets weg. Geeft terug: de stappen (in de vorm van uitvoeringen),
    elk order met zijn kosten, elke verkoop met haar gerealiseerde resultaat,
    elke dividenduitkering met haar belasting, en de jaarlijkse fiscale raming.
    """
    keten = sorteer_keten(list(uitvoeringen or []))
    if not keten:
        return {
            "regels": regels.naam,
            "stappen": [],
            "orders": [],
            "verkopen": [],
            "dividenden": [],
            "kosten_totaal": _leeg_kostenblok(),
            "dividend_per_jaar": {},
            "meerwaarde_per_jaar": {},
            "posities": Posities(),
            "contant_usd": 0.0,
        }

    rijen = div.lees_rijen(dividenden)
    benchmark_ticker = keten[0]["benchmark"]["ticker"]
    basis_pct = basiskost_pct_van(regels, float(keten[0]["cost_pct"]))

    posities = Posities()
    kosten_totaal = _leeg_kostenblok()
    orders_log: List[dict] = []
    verkoop_log: List[dict] = []
    dividend_log: List[dict] = []
    stappen: List[dict] = []

    # ---- stap 1: de instap. Alles stond nog in euro en moest eerst naar dollar.
    eerste = keten[0]
    fx_rate = float(eerste["fx_rate"])
    koersen = _koersen_van(eerste)
    inleg_eur = float(eerste["start_capital_eur"])

    wisselkost_eur = fx_kost_eur(regels, inleg_eur)
    totaal_usd = round((inleg_eur - wisselkost_eur) * fx_rate, 8)
    _tel_op(kosten_totaal, {"fx_eur": wisselkost_eur, "totaal_eur": wisselkost_eur})
    if wisselkost_eur:
        orders_log.append({
            "datum": str(eerste["execution_date"]),
            "ticker": "EUR/USD",
            "kant": "wisselen",
            "bedrag_usd": round(inleg_eur * fx_rate, 8),
            "bedrag_eur": round(inleg_eur, 8),
            "instrumenttype": "valuta",
            **{**_leeg_kostenblok(), "fx_eur": wisselkost_eur,
               "totaal_eur": wisselkost_eur},
        })

    tickers = [p["ticker"] for p in eerste["positions"]]
    uit = _los_kosten_op(regels, {}, tickers, totaal_usd, fx_rate, basis_pct)
    _tel_op(kosten_totaal, uit["kosten"])
    for regel in uit["orderlog"]:
        orders_log.append({"datum": str(eerste["execution_date"]), **regel})

    shares: Dict[str, float] = {}
    for t, bedrag in uit["doelen_usd"].items():
        aantal = bedrag / float(koersen[t])
        shares[t] = round(aantal, 10)
        posities.koop(t, str(eerste["execution_date"]), aantal, bedrag / fx_rate)

    belegd_usd = round(sum(shares[t] * float(koersen[t]) for t in shares), 8)
    contant_usd = round(totaal_usd - belegd_usd - uit["kosten_usd"], 8)
    stappen.append(_stap_record(1, eerste, shares, koersen, contant_usd))

    # ---- elke wissel daarna
    for nummer, u in enumerate(keten[1:], start=2):
        fx_rate = float(u["fx_rate"])
        koersen = _koersen_van(u)
        vorige_datum = stappen[-1]["execution_date"]
        datum = str(u["execution_date"])

        uitkeringen = _dividenden_in_venster(
            regels, stappen, rijen, vorige_datum, datum, fx, keten, benchmark_ticker)
        dividend_log.extend(uitkeringen)
        contant_usd = round(
            contant_usd + sum(float(e["netto_usd"]) for e in uitkeringen), 8)

        huidige_waarden = {}
        for t, n in shares.items():
            if t not in koersen or float(koersen[t]) <= 0:
                raise ValueError(
                    f"Geen slotkoers voor {t} in de uitvoering van {datum}. "
                    "Zonder koers is er geen waarde, en dan wordt er niets geraamd."
                )
            huidige_waarden[t] = round(n * float(koersen[t]), 8)

        totaal_usd = round(sum(huidige_waarden.values()) + contant_usd, 8)
        if totaal_usd <= 0:
            raise ValueError("De Belgische portefeuille is niets waard.")

        nieuwe = [p["ticker"] for p in u["positions"]]
        uit = _los_kosten_op(
            regels, huidige_waarden, nieuwe, totaal_usd, fx_rate, basis_pct)
        _tel_op(kosten_totaal, uit["kosten"])
        for regel in uit["orderlog"]:
            orders_log.append({"datum": datum, **regel})

        # Eerst verkopen (dat bepaalt de gerealiseerde meerwaarde), dan kopen.
        nieuwe_shares = dict(shares)
        for t in uit["actief"]:
            bedrag_usd = uit["orders"][t]
            bedrag_eur = abs(bedrag_usd) / fx_rate
            koers = float(koersen[t])
            aantal = abs(bedrag_usd) / koers

            if bedrag_usd < 0:
                # Gaat een aandeel er volledig uit, dan gaat het ook volledig
                # uit de boekhouding. Anders blijft er een pakketje van een
                # miljardste aandeel liggen dat bij een volgende verkoop opduikt.
                if round(nieuwe_shares.get(t, 0.0) - aantal, 10) <= 1e-10:
                    aantal = posities.aantal(t)
                verkoop_log.extend(
                    posities.verkoop(t, datum, aantal, bedrag_eur))
                nieuwe_shares[t] = round(nieuwe_shares.get(t, 0.0) - aantal, 10)
            else:
                posities.koop(t, datum, aantal, bedrag_eur)
                nieuwe_shares[t] = round(nieuwe_shares.get(t, 0.0) + aantal, 10)

        shares = {t: n for t, n in nieuwe_shares.items() if n > 1e-10}

        # De aandelen van de boekhouding en die van de portefeuille horen gelijk
        # te zijn. Lopen ze uiteen, dan is de FIFO-boekhouding niet meer de
        # portefeuille en zegt de geraamde belasting niets.
        for t, n in shares.items():
            if abs(posities.aantal(t) - n) > 1e-6:
                raise ValueError(
                    f"De boekhouding van {t} klopt niet met de portefeuille: "
                    f"{posities.aantal(t):.6f} tegen {n:.6f} aandelen."
                )

        belegd_usd = round(sum(shares[t] * float(koersen[t]) for t in shares), 8)
        contant_usd = round(totaal_usd - belegd_usd - uit["kosten_usd"], 8)
        # Een aandeel waarvoor er geen order is, blijft staan waar het staat en
        # komt dus niet precies op zijn doelbedrag. Dat verschil is per aandeel
        # kleiner dan een cent (dat is immers de drempel) en komt hier als
        # contant geld terug.
        #
        # De marge telt alleen de aandelen die GEEN order kregen, plus een cent
        # voor het afronden. Zou ze over alle orders gerekend worden, dan zou ze
        # bij een volledige wissel ruim genoeg zijn om een echte rekenfout van
        # tien cent te verbergen.
        overgeslagen = len(uit["orders"]) - len(uit["actief"])
        marge_usd = (overgeslagen + 1) * MINIMUM_ORDER_EUR * fx_rate
        if contant_usd < -marge_usd:
            raise ValueError(
                "De Belgische wissel zou meer uitgeven dan er is "
                f"({contant_usd:.6f} dollar tekort)."
            )
        contant_usd = max(contant_usd, 0.0)
        stappen.append(_stap_record(nummer, u, shares, koersen, contant_usd))

    # ---- uitkeringen na de laatste wissel: die staan nog contant
    na_laatste = _dividenden_in_venster(
        regels, stappen, rijen, stappen[-1]["execution_date"], None,
        fx, keten, benchmark_ticker)
    dividend_log.extend(na_laatste)

    return {
        "regels": regels.naam,
        "stappen": stappen,
        "orders": orders_log,
        "verkopen": verkoop_log,
        "dividenden": dividend_log,
        "kosten_totaal": kosten_totaal,
        "dividend_per_jaar": dividendjaren(dividend_log, regels),
        "meerwaarde_per_jaar": meerwaardejaren(verkoop_log, regels),
        "posities": posities,
        "contant_usd": round(contant_usd + sum(
            float(e["netto_usd"]) for e in na_laatste), 8),
        "basiskost_pct": basis_pct,
    }


# ====================================================================== verloop
def netto_dividend_per_betaaldag(uitkeringen: Sequence[dict]) -> pd.Series:
    """Het NETTO dividendgeld per betaaldag, in dollar.

    Netto, want de ingehouden belasting komt nooit op de rekening. Dat is het
    verschil met de officiele curve, die bruto rekent.
    """
    bedragen: Dict[pd.Timestamp, float] = {}
    for e in uitkeringen or []:
        dag = pd.Timestamp(e["pay_date"]).normalize()
        bedragen[dag] = bedragen.get(dag, 0.0) + float(e["netto_usd"])
    if not bedragen:
        return pd.Series(dtype=float)
    return pd.Series(bedragen).sort_index()


def bouw_verloop_belgie(
    uitvoeringen: List[dict],
    koersen: pd.DataFrame,
    fx: pd.Series,
    dividenden: Optional[Sequence[dict]] = None,
    regels: BelgischeRegels = REGELS_NU,
    resultaat: Optional[dict] = None,
) -> pd.DataFrame:
    """Het dagelijkse verloop van de Belgische portefeuille, in euro.

    Gebruikt dezelfde tekenfunctie als de officiele curve, zodat er geen tweede
    rekenwijze naast de eerste kan ontstaan.

    De kolommen van de maatstaf worden met opzet weggelaten. SPY is in deze laag
    geen Belgische praktijkbenchmark (zie de moduledocstring), en een kolom
    `spy_eur` zou vroeg of laat als zo'n benchmark gelezen worden.

    De geraamde meerwaardebelasting zit NIET in deze curve: die wordt niet per
    trade ingehouden. Ze staat apart, per kalenderjaar.
    """
    from .herbalans import bouw_verloop_keten

    uit = resultaat or belgische_keten(uitvoeringen, dividenden, fx, regels)
    stappen = uit["stappen"]
    if not stappen:
        return pd.DataFrame()

    verloop = bouw_verloop_keten(
        stappen, koersen, fx,
        dividend_usd_per_dag=netto_dividend_per_betaaldag(uit["dividenden"]),
        spy_events=None,
    )
    if verloop.empty:
        return verloop

    return verloop.drop(
        columns=[k for k in ("spy_eur", "spy_aandelen", "spy_dividend_eur",
                             "spy_resultaat_pct", "voorsprong_pct")
                 if k in verloop.columns])


# =================================================================== waarderen
def waardeer_belgisch(
    resultaat: dict,
    koersen_usd: Mapping[str, float],
    fx_eurusd: float,
    officiele_waarde_eur: Optional[float] = None,
    realistische_waarde_eur: Optional[float] = None,
) -> dict:
    """Wat de Belgische portefeuille nu waard is, en wat er nog aan vasthangt.

    Twee bedragen die niet door elkaar mogen:

        portefeuille_eur   wat er op de rekening staat. Hier zijn de beurstaks,
                           de brokerkosten, de wisselkosten en de ingehouden
                           dividendbelasting al af.
        netto_eur          datzelfde bedrag min de geraamde belasting op de
                           winst die al gerealiseerd is. Dat is een RESERVE, geen
                           inhouding: de broker haalt die belasting niet van je
                           rekening.

    Op de winst die nog in de portefeuille zit, staat nog geen belasting. Die
    ontstaat pas bij een verkoop; ze staat hier als `latente_meerwaarde_eur`.
    """
    if fx_eurusd is None or float(fx_eurusd) <= 0:
        raise ValueError("De wisselkoers moet groter dan nul zijn.")
    fx_rate = float(fx_eurusd)

    stappen = resultaat.get("stappen") or []
    if not stappen:
        raise ValueError("Er is nog geen Belgische stap om te waarderen.")

    laatste = stappen[-1]
    ontbreekt = [
        p["ticker"] for p in laatste["positions"]
        if not koersen_usd.get(p["ticker"]) or float(koersen_usd[p["ticker"]]) <= 0
    ]
    if ontbreekt:
        raise ValueError("Geen bruikbare koers voor: " + ", ".join(sorted(ontbreekt)))

    posities: Posities = resultaat["posities"]
    regels_naam = resultaat.get("regels")

    rijen = []
    waarde_usd = float(resultaat.get("contant_usd") or 0.0)
    latent_eur = 0.0
    for p in laatste["positions"]:
        t = p["ticker"]
        koers = float(koersen_usd[t])
        stuk_usd = float(p["shares"]) * koers
        waarde_usd += stuk_usd
        kostprijs_eur = posities.kostprijs_eur(t)
        waarde_eur = stuk_usd / fx_rate
        latent_eur += waarde_eur - kostprijs_eur
        rijen.append({
            "ticker": t,
            "aandelen": float(p["shares"]),
            "koers_usd": koers,
            "waarde_eur": round(waarde_eur, 8),
            "kostprijs_eur": round(kostprijs_eur, 8),
            "latente_meerwaarde_eur": round(waarde_eur - kostprijs_eur, 8),
        })

    portefeuille_eur = round(waarde_usd / fx_rate, 8)
    kosten = resultaat["kosten_totaal"]
    inleg_eur = float(stappen[0]["start_capital_eur"])

    dividend_jaren = resultaat.get("dividend_per_jaar") or {}
    meerwaarde_jaren = resultaat.get("meerwaarde_per_jaar") or {}

    dividend_netto_eur = round(
        sum(float(b["netto_ontvangen_eur"]) for b in dividend_jaren.values()), 8)
    dividend_bruto_eur = round(
        sum(float(b["bruto_eur"]) for b in dividend_jaren.values()), 8)
    dividendbelasting_eur = round(
        sum(float(b["buitenlandse_bronheffing_eur"]) + float(b["rv_eur"])
            for b in dividend_jaren.values()), 8)
    terug_te_vorderen_eur = round(
        sum(float(b["terug_te_vorderen_eur"]) for b in dividend_jaren.values()), 8)

    meerwaardebelasting_eur = round(
        sum(float(b["belasting_eur"]) for b in meerwaarde_jaren.values()), 8)
    gerealiseerd_eur = round(
        sum(float(b["netto_gerealiseerd_eur"]) for b in meerwaarde_jaren.values()), 8)

    netto_eur = round(portefeuille_eur - meerwaardebelasting_eur, 8)

    uit = {
        "regels": regels_naam,
        "fx_eurusd": fx_rate,
        "inleg_eur": round(inleg_eur, 8),
        "posities": rijen,
        "contant_eur": round(float(resultaat.get("contant_usd") or 0.0) / fx_rate, 8),
        "portefeuille_eur": portefeuille_eur,
        "resultaat_eur": round(portefeuille_eur - inleg_eur, 8),
        "resultaat_pct": round((portefeuille_eur / inleg_eur - 1.0) * 100, 6),
        "tob_eur": round(float(kosten["tob_eur"]), 8),
        "broker_eur": round(float(kosten["broker_eur"]), 8),
        "fx_kosten_eur": round(float(kosten["fx_eur"]), 8),
        "basiskost_eur": round(float(kosten["basis_eur"]), 8),
        "transactiekosten_eur": round(float(kosten["totaal_eur"]), 8),
        "dividend_bruto_eur": dividend_bruto_eur,
        "dividend_netto_eur": dividend_netto_eur,
        "dividendbelasting_eur": dividendbelasting_eur,
        "dividend_terug_te_vorderen_eur": terug_te_vorderen_eur,
        "gerealiseerde_meerwaarde_eur": gerealiseerd_eur,
        "meerwaardebelasting_eur": meerwaardebelasting_eur,
        "latente_meerwaarde_eur": round(latent_eur, 8),
        "netto_eur": netto_eur,
        "netto_resultaat_eur": round(netto_eur - inleg_eur, 8),
        "netto_resultaat_pct": round((netto_eur / inleg_eur - 1.0) * 100, 6),
        "totale_last_eur": round(
            float(kosten["totaal_eur"]) + dividendbelasting_eur
            + meerwaardebelasting_eur, 8),
    }

    if officiele_waarde_eur is not None:
        verschil = round(portefeuille_eur - float(officiele_waarde_eur), 8)
        uit["officiele_waarde_eur"] = round(float(officiele_waarde_eur), 8)
        uit["verschil_officieel_eur"] = verschil
        uit["verschil_officieel_pct"] = round(
            verschil / float(officiele_waarde_eur) * 100, 6
        ) if float(officiele_waarde_eur) else 0.0
        netto_verschil = round(netto_eur - float(officiele_waarde_eur), 8)
        uit["verschil_officieel_netto_eur"] = netto_verschil
        uit["verschil_officieel_netto_pct"] = round(
            netto_verschil / float(officiele_waarde_eur) * 100, 6
        ) if float(officiele_waarde_eur) else 0.0

    if realistische_waarde_eur is not None:
        uit["realistische_waarde_eur"] = round(float(realistische_waarde_eur), 8)
        uit["verschil_realistisch_eur"] = round(
            portefeuille_eur - float(realistische_waarde_eur), 8)

    return uit
