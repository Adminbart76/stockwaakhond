"""De bevroren scorestrategie van StockWaakhond.

LET OP - LEES DIT VOOR JE IETS WIJZIGT
======================================
Alles in dit bestand is bevroren. De inhoud van STRATEGY_SPEC bepaalt de
strategiehash die in elk vastgelegd forward-signaal staat. Verander je hier
ook maar een komma, dan klopt die hash niet meer en is de forward-test waardeloos.

Dat is geen theorie: tests/test_bevroren_strategie.py faalt onmiddellijk bij
de kleinste wijziging, en die test loopt bij elke push naar GitHub.

Wil je een andere formule uitproberen? Maak dan een NIEUW bestand met een
eigen strategieversie en een eigen logboek. De lopende test blijft er
volledig los van staan. Dat is precies de bedoeling van een forward-test:
je mag de lat niet verleggen nadat je de sprong gezien hebt.

De code hieronder is letterlijk overgenomen uit app.py zoals die draaide bij
het eerste officiele signaal op 6 oktober 2026.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import List, Tuple

import numpy as np
import pandas as pd

TRADING_DAYS = 252

STRATEGY_VERSION = "SW_SCORE_V3_FROZEN_2026-10-06"

STRATEGY_SPEC = {
    "version": STRATEGY_VERSION,
    "weights": {
        "return_12m_percentile": 25,
        "return_6m_percentile": 20,
        "return_3m_percentile": 15,
        "relative_strength_6m_percentile": 15,
        "close_above_ma200": 10,
        "ma50_above_ma200": 5,
        "low_volatility_3m_percentile": 5,
        "low_drawdown_3m_percentile": 5,
    },
    "lookbacks_trading_days": {
        "3m": 63,
        "6m": 126,
        "12m": 252,
        "ma50": 50,
        "ma200": 200,
    },
    "benchmark": "SPY",
    "top_n_default": 5,
    "cost_pct_default": 0.15,
    "minimum_candidate_coverage_pct": 98.0,
    "signal_execution_rule": (
        "Signal uses latest completed daily close. Performance begins at the "
        "next available trading-day close after the signal market date."
    ),
}

STRATEGY_JSON = json.dumps(STRATEGY_SPEC, sort_keys=True, separators=(",", ":"))
STRATEGY_HASH = hashlib.sha256(STRATEGY_JSON.encode("utf-8")).hexdigest()

# De hash zoals die in het allereerste vastgelegde signaal staat. Blijft hier
# als vangnet staan: wijkt STRATEGY_HASH hiervan af, dan is de formule geraakt.
GENESIS_STRATEGY_HASH = "a399aecc207510c77450cd015f4f23e2b3639fc642eb9bcc29e95cbe2b84cc18"


def canonical_json(obj: dict) -> str:
    """Zet een dict om naar exact dezelfde tekst, ongeacht de volgorde van invoer.

    Dit moet byte-voor-byte stabiel blijven: het is de basis van elke hash in
    het logboek. Niet aanpassen.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spec_hash(formula_spec: dict) -> str:
    """Herberekent de strategiehash uit een formule-omschrijving.

    Wordt gebruikt om te controleren of de strategy_hash van een oud record
    werkelijk hoort bij de formule die in datzelfde record staat.
    """
    return sha256_text(json.dumps(formula_spec, sort_keys=True, separators=(",", ":")))


def percentile_rank(s: pd.Series, higher_better: bool = True) -> pd.Series:
    r = s.rank(pct=True, na_option="bottom")
    if not higher_better:
        r = 1 - r
    return r.fillna(0.0)


def build_score_table(
    prices: pd.DataFrame,
    universe: List[str],
    benchmark_ticker: str = "SPY",
) -> Tuple[pd.DataFrame, pd.Timestamp, float]:
    """Berekent de score van elk aandeel op de laatste voltooide koersdag.

    Geeft terug: de gesorteerde scoretabel, de signaaldatum en het
    dekkingspercentage. Letterlijk de berekening van het eerste signaal.
    """
    if benchmark_ticker not in prices.columns:
        raise ValueError("SPY ontbreekt in de koersdata.")

    benchmark = prices[benchmark_ticker].dropna()
    if len(benchmark) < 252:
        raise ValueError("Onvoldoende SPY-historiek.")

    signal_date = pd.Timestamp(benchmark.index[-1])
    b = benchmark.loc[:signal_date]
    b6 = b.iloc[-1] / b.iloc[-126] - 1

    rows = []
    for ticker in universe:
        if ticker not in prices.columns:
            continue

        s = prices[ticker].loc[:signal_date].dropna()
        if len(s) < 252:
            continue
        if (signal_date - pd.Timestamp(s.index[-1])).days > 7:
            continue

        last = float(s.iloc[-1])
        if not np.isfinite(last) or last <= 0:
            continue

        r3 = last / float(s.iloc[-63]) - 1
        r6 = last / float(s.iloc[-126]) - 1
        r12 = last / float(s.iloc[-252]) - 1
        ma50 = float(s.iloc[-50:].mean())
        ma200 = float(s.iloc[-200:].mean())
        peak63 = float(s.iloc[-63:].max())
        dd63 = last / peak63 - 1 if peak63 > 0 else np.nan

        daily = s.pct_change(fill_method=None).dropna()
        vol63 = (
            float(daily.iloc[-63:].std()) * math.sqrt(TRADING_DAYS)
            if len(daily) >= 63 else np.nan
        )

        vals = [r3, r6, r12, ma50, ma200, dd63, vol63]
        if not all(np.isfinite(x) for x in vals):
            continue

        rows.append({
            "Ticker": ticker,
            "Koers": last,
            "3m %": r3 * 100,
            "6m %": r6 * 100,
            "12m %": r12 * 100,
            "Rel. sterkte 6m %-punt": (r6 - b6) * 100,
            "Boven MA200": bool(last > ma200),
            "MA50 > MA200": bool(ma50 > ma200),
            "3m drawdown %": dd63 * 100,
            "3m volatiliteit %": vol63 * 100,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Geen aandelen met voldoende koershistoriek.")

    df["Score"] = (
        25 * percentile_rank(df["12m %"])
        + 20 * percentile_rank(df["6m %"])
        + 15 * percentile_rank(df["3m %"])
        + 15 * percentile_rank(df["Rel. sterkte 6m %-punt"])
        + 10 * df["Boven MA200"].astype(float)
        + 5 * df["MA50 > MA200"].astype(float)
        + 5 * percentile_rank(df["3m volatiliteit %"], higher_better=False)
        + 5 * percentile_rank(df["3m drawdown %"])
    )

    coverage = 100.0 * len(df) / len(universe)
    df = df.sort_values(["Score", "Ticker"], ascending=[False, True]).reset_index(drop=True)
    return df, signal_date, coverage
