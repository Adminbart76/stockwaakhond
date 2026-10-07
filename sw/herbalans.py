"""De doorlopende portefeuille: één keer 1.000 euro, daarna alleen wisselen.

Het verschil met portfolio.bereken_instap()
===========================================
`bereken_instap()` zet 1.000 euro klaar en verdeelt die over vijf aandelen. Dat
is juist voor het eerste signaal en fout voor elk signaal daarna. Zou elke maand
opnieuw met 1.000 euro begonnen worden, dan:

  * verdwijnt de winst of het verlies van de vorige maand uit de reeks;
  * komt er elke maand geld bij dat er nooit was;
  * wordt de transactiekost over een vers bedrag gerekend in plaats van over wat
    er werkelijk van hand verwisselt.

Daarom staat hier de tweede helft van het verhaal: bij een nieuw signaal wordt de
DAN GELDENDE waarde van de portefeuille herverdeeld over de nieuwe Top-5. Er
komt nooit geld bij.

De keten van uitvoeringen
=========================
    uitvoering 1   de instap van 6 oktober 2026, zonder `prev_exec_hash`
    uitvoering 2   een wissel, verwijst met `prev_exec_hash` naar uitvoering 1
    uitvoering 3   ...

Net zoals bij de signalen hangt elke schakel met een controlegetal aan de vorige.
De laatste schakel beschrijft de volledige huidige toestand: welke aandelen,
hoeveel stuks, hoeveel contant geld, en de onveranderde SPY-positie. Wie wil
weten wat er nu in de portefeuille zit, heeft niets anders nodig dan die ene
regel.

De omzetformule komt uit de bevroren simulatie
==============================================
`simulate_forward()` in app.py rekent de kost over de omzet:

    omzet = 0,5 x (som van alle |doelgewicht - huidig gewicht| + |contant|)
    kost  = omzet x kostenpercentage

Die formule is hier letterlijk overgenomen, en app.py is niet aangeraakt. Twee
eigenschappen die ze gratis meebrengt:

  * een aandeel dat in beide Top-5's staat, wordt alleen voor het VERSCHIL
    bijgesteld. Blijven alle vijf staan, dan is de kost bijna nul.
  * de eerste instap (alles nog contant) geeft omzet 1,0 en dus 0,15 % van
    1.000 euro = 1,50 euro. Exact wat er op 6 oktober 2026 vastgelegd is.

Bij een volledige wissel gaat er twee keer de portefeuillewaarde over de
toonbank, en rekent deze formule toch 0,15 % en niet 0,30 %. Dat is de conventie
van de bevroren opzet en wordt hier bewust niet gewijzigd; zie het openstaande
punt in CLAUDE.md. De parameter `omzet_factor` bestaat voor de realistische
tweede curve die daar later naast komt. Een vastgelegde wissel gebruikt altijd de
bevroren conventie.

SPY wordt nooit teruggezet
==========================
De maatstaf koopt één keer, op dezelfde dag, met dezelfde kost, en houdt dat
daarna vast. Bij een wissel wordt het SPY-blok letterlijk overgenomen uit de
vorige uitvoering, zodat er per constructie niets aan kan verschuiven. SPY
betaalt dus ook niet mee aan de wisselkosten van StockWaakhond. Alleen het
contante dividend van SPY kan groeien, met dezelfde conventie als de andere kant.

Dividend
========
Het contante dividendgeld is hier een getal dat de aanroeper MOET meegeven,
samen met de conventie waarmee het berekend is. Er wordt niets verzonnen: welk
deel van een dividend een Belgische belegger overhoudt, is een beslissing en geen
aanname. Zolang die beslissing niet genomen is, hoort er nul te staan en hoort
het scherm te zeggen dat de vergelijking alleen koerswinst is.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from .portfolio import KoersOntbreekt
from .strategy import canonical_json, sha256_text

SCHEMA_VERSIE = 2


# ------------------------------------------------------------------- de keten
def stand_na(uitvoering: dict) -> dict:
    """De toestand van de portefeuille na die uitvoering.

    Werkt voor de instap en voor een wissel, zodat de rest van de code het
    verschil niet hoeft te kennen.
    """
    return {
        "exec_hash": uitvoering["exec_hash"],
        "execution_date": str(uitvoering["execution_date"]),
        "positions": list(uitvoering["positions"]),
        "cash_usd": float(uitvoering.get("cash_usd") or 0.0),
        "benchmark": dict(uitvoering["benchmark"]),
        "start_capital_eur": float(uitvoering["start_capital_eur"]),
        "cost_pct": float(uitvoering["cost_pct"]),
    }


def sorteer_keten(uitvoeringen: List[dict]) -> List[dict]:
    """Zet de uitvoeringen in de volgorde van de keten zelf.

    Niet op datum sorteren: de keten bepaalt de volgorde, en als die niet
    sluitend is, hoort dat op te vallen in plaats van weggesorteerd te worden.
    """
    if not uitvoeringen:
        return []

    per_hash = {u["exec_hash"]: u for u in uitvoeringen}
    if len(per_hash) != len(uitvoeringen):
        raise ValueError("Er staan twee uitvoeringen met hetzelfde controlegetal.")

    begin = [u for u in uitvoeringen if not u.get("prev_exec_hash")]
    if len(begin) != 1:
        raise ValueError(
            "Er hoort precies één uitvoering zonder voorganger te zijn, "
            f"gevonden: {len(begin)}."
        )

    volgend: Dict[str, dict] = {}
    for u in uitvoeringen:
        vorige = u.get("prev_exec_hash")
        if not vorige:
            continue
        if vorige not in per_hash:
            raise ValueError(
                "Een uitvoering verwijst naar een voorganger die er niet is: "
                + str(vorige)[:16] + "..."
            )
        if vorige in volgend:
            raise ValueError(
                "Twee uitvoeringen verwijzen naar dezelfde voorganger: dan zijn "
                "er twee ketens en bewijst geen van beide nog iets."
            )
        volgend[vorige] = u

    keten = [begin[0]]
    while keten[-1]["exec_hash"] in volgend:
        keten.append(volgend[keten[-1]["exec_hash"]])

    if len(keten) != len(uitvoeringen):
        raise ValueError("Niet alle uitvoeringen hangen aan dezelfde keten.")
    return keten


def verify_keten(uitvoeringen: List[dict]) -> Tuple[bool, str]:
    """Controleert de keten van uitvoeringen.

    Per schakel: hoort het controlegetal bij de inhoud, verwijst ze naar de
    juiste voorganger, en ligt haar uitvoeringsdag na die van de voorganger.
    """
    if not uitvoeringen:
        return True, "Nog geen uitvoering."

    try:
        keten = sorteer_keten(uitvoeringen)
    except ValueError as fout:
        return False, str(fout)

    vorige_datum = None
    for nummer, u in enumerate(keten, start=1):
        canoniek = u.get("canonical_payload")
        if canoniek and sha256_text(canoniek) != u["exec_hash"]:
            return False, (
                f"Uitvoering {nummer}: het controlegetal klopt niet met de inhoud."
            )

        datum = pd.Timestamp(u["execution_date"])
        if vorige_datum is not None and datum <= vorige_datum:
            return False, (
                f"Uitvoering {nummer} is van {datum.date()} en dat is niet later "
                f"dan de vorige ({vorige_datum.date()})."
            )
        vorige_datum = datum

    return True, f"Keten van uitvoeringen intact ({len(keten)} schakel(s))."


def laatste_uitvoering(uitvoeringen: List[dict]) -> Optional[dict]:
    """De punt van de keten: de uitvoering die nu geldt."""
    keten = sorteer_keten(uitvoeringen)
    return keten[-1] if keten else None


def actieve_tickers(uitvoeringen: List[dict]) -> List[str]:
    """De aandelen die NU in de portefeuille zitten, plus de maatstaf.

    Dit is de lijst die de dagelijkse taak nodig heeft en die de smalle
    schrijfdeur in de database afdwingt. Met opzet niet "alles wat ooit gekozen
    is": een aandeel dat er vorige maand uit ging, hoort geen koersen meer te
    kunnen laten bijschrijven.
    """
    tip = laatste_uitvoering(uitvoeringen)
    if tip is None:
        return []
    namen = {p["ticker"] for p in tip["positions"]}
    namen.add(tip["benchmark"]["ticker"])
    return sorted(namen)


def tickers_in_keten(uitvoeringen: List[dict]) -> List[str]:
    """Alles wat ooit in de portefeuille gezeten heeft, plus de maatstaf.

    Nodig om het hele verloop te kunnen tekenen; niet om iets te mogen
    bijschrijven.
    """
    namen = set()
    for u in uitvoeringen:
        namen.update(p["ticker"] for p in u["positions"])
        namen.add(u["benchmark"]["ticker"])
    return sorted(namen)


# -------------------------------------------------------------------- de omzet
def bereken_omzet(
    huidige_gewichten: Dict[str, float],
    doelgewichten: Dict[str, float],
    cash_gewicht: float,
    omzet_factor: float = 1.0,
) -> float:
    """De omzet van een wissel, als deel van de portefeuille (1,0 = alles).

    Letterlijk de formule van de bevroren simulatie: de helft van de som van alle
    gewichtsverschillen, het contante geld meegerekend. De helft, omdat wat je
    verkoopt en wat je koopt samen twee keer hetzelfde verschil is.

    omzet_factor blijft 1,0 voor de bevroren conventie. Alleen een latere,
    realistische tweede curve mag daar 2,0 van maken; dat is een beslissing die
    nog niet genomen is.
    """
    namen = set(huidige_gewichten) | set(doelgewichten)
    aandelen = sum(
        abs(doelgewichten.get(t, 0.0) - huidige_gewichten.get(t, 0.0))
        for t in namen
    )
    return float(omzet_factor) * 0.5 * (aandelen + abs(float(cash_gewicht)))


# ------------------------------------------------------------------ de wissel
def bereken_herbalans(
    entry_hash: str,
    execution_date: str,
    vorige_uitvoering: dict,
    nieuwe_tickers: List[str],
    koersen_usd: Dict[str, float],
    fx_eurusd: float,
    spy_koers_usd: float,
    fx_source: str,
    fx_asof: str,
    dividend_cash_usd: float = 0.0,
    spy_dividend_cash_usd: float = 0.0,
    dividend_conventie: Optional[str] = None,
    cost_pct: Optional[float] = None,
    omzet_factor: float = 1.0,
) -> dict:
    """Herverdeelt de bestaande portefeuille over de nieuwe Top-5.

    Geeft een compleet record terug en schrijft niets weg. Er komt geen geld bij:
    alles vertrekt van de waarde die er op die dag werkelijk is.

    koersen_usd moet de slotkoers bevatten van elk aandeel dat je HEBT en van elk
    aandeel dat je KRIJGT. Ontbreekt er één, dan is er geen waarde en dus geen
    wissel: dat is een KoersOntbreekt en geen geschat getal.
    """
    vorige = stand_na(vorige_uitvoering)

    if not nieuwe_tickers:
        raise ValueError("Geen nieuwe aandelen opgegeven.")
    if len(set(nieuwe_tickers)) != len(nieuwe_tickers):
        raise ValueError("Er staat een aandeel dubbel in de nieuwe selectie.")
    if fx_eurusd <= 0:
        raise ValueError("De wisselkoers moet groter dan nul zijn.")
    if dividend_cash_usd < 0 or spy_dividend_cash_usd < 0:
        raise ValueError("Dividend kan niet negatief zijn.")
    if (dividend_cash_usd or spy_dividend_cash_usd) and not dividend_conventie:
        raise ValueError(
            "Er is dividend meegegeven zonder de conventie waarmee het berekend "
            "is (bruto of netto, en welke percentages). Die conventie is een "
            "beslissing en wordt hier niet verzonnen."
        )

    nieuwe_datum = pd.Timestamp(execution_date)
    if nieuwe_datum <= pd.Timestamp(vorige["execution_date"]):
        raise ValueError(
            f"De wissel van {nieuwe_datum.date()} ligt niet na de vorige "
            f"uitvoering van {vorige['execution_date']}."
        )

    gehouden = [p["ticker"] for p in vorige["positions"]]
    bm_ticker = vorige["benchmark"]["ticker"]
    beschikbaar = dict(koersen_usd)
    beschikbaar.setdefault(bm_ticker, spy_koers_usd)
    nodig = sorted(set(gehouden) | set(nieuwe_tickers) | {bm_ticker})
    ontbreekt = [
        t for t in nodig
        if not beschikbaar.get(t) or float(beschikbaar[t]) <= 0
    ]
    if ontbreekt:
        raise KoersOntbreekt(ontbreekt)

    # ---- 1. wat is de portefeuille waard, vlak voor de wissel (in dollar)
    opening_posities = []
    posities_usd = 0.0
    for p in sorted(vorige["positions"], key=lambda x: x["ticker"]):
        koers = round(float(beschikbaar[p["ticker"]]), 8)
        waarde = round(float(p["shares"]) * koers, 8)
        posities_usd += waarde
        opening_posities.append({
            "ticker": p["ticker"],
            "shares": p["shares"],
            "close_usd": koers,
            "value_usd": waarde,
        })
    posities_usd = round(posities_usd, 8)

    contant_usd = round(vorige["cash_usd"] + float(dividend_cash_usd), 8)
    totaal_usd = round(posities_usd + contant_usd, 8)
    if totaal_usd <= 0:
        raise ValueError("De portefeuille is niets waard; er valt niets te herverdelen.")

    spy_koers = round(float(spy_koers_usd), 8)
    bm_vorige = vorige["benchmark"]
    bm_contant = round(
        float(bm_vorige.get("cash_usd") or 0.0) + float(spy_dividend_cash_usd), 8)

    # ---- 2. huidige gewichten, 3. doelgewichten, 4. omzet, 5. kost
    huidig = {p["ticker"]: p["value_usd"] / totaal_usd for p in opening_posities}
    cash_gewicht = contant_usd / totaal_usd
    doel = {t: 1.0 / len(nieuwe_tickers) for t in nieuwe_tickers}

    omzet = bereken_omzet(huidig, doel, cash_gewicht, omzet_factor)
    tarief = float(vorige["cost_pct"]) if cost_pct is None else float(cost_pct)
    kost_usd = round(totaal_usd * omzet * tarief / 100.0, 8)
    belegd_usd = round(totaal_usd - kost_usd, 8)
    if belegd_usd <= 0:
        raise ValueError("Na de kosten blijft er niets over om te beleggen.")

    # ---- 6. opnieuw gelijk verdelen, tegen de slotkoers van die dag
    per_positie_usd = belegd_usd / len(nieuwe_tickers)
    posities = []
    for t in nieuwe_tickers:
        koers = round(float(beschikbaar[t]), 8)
        posities.append({
            "ticker": t,
            "buy_price_usd": koers,
            "shares": round(per_positie_usd / koers, 10),
            "invested_usd": round(per_positie_usd, 8),
            "invested_eur": round(per_positie_usd / float(fx_eurusd), 8),
            "target_weight": round(1.0 / len(nieuwe_tickers), 10),
        })

    payload = {
        "record_type": "rebalance",
        "schema_version": SCHEMA_VERSIE,
        "entry_hash": entry_hash,
        "prev_exec_hash": vorige["exec_hash"],
        "execution_date": str(nieuwe_datum.date()),
        "fx_pair": "EURUSD",
        "fx_rate": round(float(fx_eurusd), 10),
        "fx_source": fx_source,
        "fx_asof": fx_asof,
        "start_capital_eur": round(vorige["start_capital_eur"], 8),
        "cost_pct": round(tarief, 8),
        "opening": {
            "positions": opening_posities,
            "positions_usd": posities_usd,
            "cash_usd": contant_usd,
            "dividend_cash_usd": round(float(dividend_cash_usd), 8),
            "dividend_conventie": dividend_conventie or "geen dividend meegerekend",
            "total_usd": totaal_usd,
            "benchmark_close_usd": spy_koers,
            "benchmark_value_usd": round(
                float(bm_vorige["shares"]) * spy_koers + bm_contant, 8),
        },
        "turnover": round(omzet, 10),
        "turnover_convention": (
            "eenzijdig: 0,5 x de som van de gewichtsverschillen, zoals de "
            "bevroren simulatie in app.py"
        ),
        "cost_usd": kost_usd,
        "cost_eur": round(kost_usd / float(fx_eurusd), 8),
        "invested_usd": belegd_usd,
        "invested_eur": round(belegd_usd / float(fx_eurusd), 8),
        "positions": posities,
        "cash_usd": 0.0,
        "benchmark": {
            "ticker": bm_vorige["ticker"],
            "buy_price_usd": bm_vorige["buy_price_usd"],
            "shares": bm_vorige["shares"],
            "invested_eur": bm_vorige["invested_eur"],
            "invested_usd": bm_vorige["invested_usd"],
            "cash_usd": bm_contant,
        },
    }

    canoniek = canonical_json(payload)
    volledig = dict(payload)
    volledig["canonical_payload"] = canoniek
    volledig["exec_hash"] = sha256_text(canoniek)
    return volledig


# -------------------------------------------------------------------- verloop
def bouw_verloop_keten(
    uitvoeringen: List[dict],
    koersen: pd.DataFrame,
    fx: pd.Series,
    dividend_usd_per_dag: Optional[pd.Series] = None,
    spy_dividend_usd_per_dag: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Het dagelijkse verloop in euro over de hele keten, inclusief wissels.

    Vanaf de dag van een wissel gelden de nieuwe posities. Dat klopt met de
    rekenwijze: er wordt gewisseld tegen de slotkoers van die dag, dus de waarde
    van die dag is de waarde na de kost, en het nieuwe mandje begint pas de dag
    erna te bewegen.

    Dividend wordt in dollar meegegeven als bedrag per dag. Aan de kant van de
    portefeuille verdwijnt het contante geld bij elke wissel (het wordt dan
    meebelegd), aan de kant van SPY blijft het staan: die koopt niets meer bij.
    Zolang de fiscale conventie niet vastligt, hoort hier bij beide kanten niets
    meegegeven te worden, en meet de grafiek dus alleen koerswinst.
    """
    keten = sorteer_keten(uitvoeringen)
    if not keten:
        return pd.DataFrame()

    inleg = float(keten[0]["start_capital_eur"])
    bm_ticker = keten[0]["benchmark"]["ticker"]
    bm_aandelen = float(keten[0]["benchmark"]["shares"])

    start = pd.Timestamp(keten[0]["execution_date"])
    index = koersen.index[koersen.index >= start]
    if len(index) == 0:
        return pd.DataFrame()

    wisseldagen = {pd.Timestamp(u["execution_date"]) for u in keten[1:]}

    def actief_op(dag: pd.Timestamp) -> dict:
        geldig = keten[0]
        for u in keten:
            if pd.Timestamp(u["execution_date"]) <= dag:
                geldig = u
        return geldig

    def opgeteld(reeks, vanaf, tot, inclusief_vanaf: bool) -> float:
        if reeks is None or len(reeks) == 0:
            return 0.0
        vroeg = (reeks.index >= vanaf) if inclusief_vanaf else (reeks.index > vanaf)
        return float(reeks[vroeg & (reeks.index <= tot)].sum())

    rijen = []
    for dt in index:
        koers_dag = fx.reindex([dt]).ffill().iloc[0] if dt in fx.index else fx.asof(dt)
        if not koers_dag or koers_dag != koers_dag or koers_dag <= 0:
            continue

        geldig = actief_op(dt)
        aandelen = {p["ticker"]: float(p["shares"]) for p in geldig["positions"]}

        totaal_usd, compleet = 0.0, True
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

        spy_koers = koersen.at[dt, bm_ticker] if bm_ticker in koersen.columns else None
        if spy_koers is None or spy_koers != spy_koers or spy_koers <= 0:
            continue

        # Contant geld aan onze kant: alleen wat er sinds de laatste wissel is
        # bijgekomen. Wat er vóór die wissel stond, zit nu in de aandelen.
        contant_usd = float(geldig.get("cash_usd") or 0.0) + opgeteld(
            dividend_usd_per_dag, pd.Timestamp(geldig["execution_date"]), dt,
            inclusief_vanaf=False)
        spy_contant_usd = opgeteld(
            spy_dividend_usd_per_dag, start, dt, inclusief_vanaf=True)

        rijen.append({
            "datum": dt,
            "fx_eurusd": float(koers_dag),
            "portefeuille_eur": (totaal_usd + contant_usd) / float(koers_dag),
            "spy_eur": (bm_aandelen * float(spy_koers) + spy_contant_usd)
                       / float(koers_dag),
            "dividend_eur": contant_usd / float(koers_dag),
            "spy_dividend_eur": spy_contant_usd / float(koers_dag),
            "wissel": dt in wisseldagen,
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
