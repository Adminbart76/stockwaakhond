from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="StockWaakhond V7", layout="wide")

TRADING_DAYS = 252
APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "forward_log"
LEDGER_FILE = LOG_DIR / "ledger.jsonl"
UNIVERSE_CACHE = LOG_DIR / "latest_universe.json"

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

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def yahoo_symbol(symbol: str) -> str:
    # Wikipedia uses BRK.B / BF.B; Yahoo uses BRK-B / BF-B.
    return symbol.strip().upper().replace(".", "-")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_current_sp500_universe() -> Tuple[List[str], str]:
    headers = {"User-Agent": "Mozilla/5.0 StockWaakhond/1.0"}
    response = requests.get(WIKI_URL, headers=headers, timeout=30)
    response.raise_for_status()

    tables = pd.read_html(io.StringIO(response.text))
    table = None
    for candidate in tables:
        if "Symbol" in candidate.columns and "Security" in candidate.columns:
            table = candidate
            break

    if table is None:
        raise ValueError("S&P 500-tabel niet gevonden op Wikipedia.")

    symbols = sorted({yahoo_symbol(x) for x in table["Symbol"].astype(str)})
    if len(symbols) < 450:
        raise ValueError(f"Onverwacht klein S&P 500-universum: {len(symbols)} symbolen.")

    content_hash = sha256_text(",".join(symbols))
    return symbols, content_hash


@st.cache_data(ttl=1800, show_spinner=False)
def download_adjusted_close(tickers: Tuple[str, ...], period: str = "18mo") -> pd.DataFrame:
    raw = yf.download(
        list(tickers),
        period=period,
        auto_adjust=True,
        progress=False,
        actions=False,
        group_by="column",
        threads=True,
    )

    if raw.empty:
        raise ValueError("Geen koersdata ontvangen.")

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise ValueError("Geen slotkoersen ontvangen.")
        close = raw["Close"].copy()
    else:
        close = raw[["Close"]].copy()
        close.columns = [tickers[0]]

    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])

    close = close.sort_index()
    close = close.replace([np.inf, -np.inf], np.nan)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


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


def read_ledger() -> List[dict]:
    ensure_dirs()
    if not LEDGER_FILE.exists():
        return []

    rows = []
    with LEDGER_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def verify_ledger(entries: List[dict]) -> Tuple[bool, str]:
    prev_hash = "GENESIS"
    for i, entry in enumerate(entries, start=1):
        stored_hash = entry.get("entry_hash")
        payload = dict(entry)
        payload.pop("entry_hash", None)

        if payload.get("previous_hash") != prev_hash:
            return False, f"Ketenbreuk bij regel {i}: previous_hash klopt niet."

        calculated = sha256_text(canonical_json(payload))
        if calculated != stored_hash:
            return False, f"Hashfout bij regel {i}: inhoud is gewijzigd."

        if payload.get("strategy_hash") != STRATEGY_HASH:
            return False, f"Strategiehash wijkt af bij regel {i}."

        prev_hash = stored_hash

    return True, "Ledger intact."


def append_signal_entry(entry_payload: dict) -> dict:
    ensure_dirs()
    entries = read_ledger()
    ok, message = verify_ledger(entries)
    if not ok:
        raise ValueError(
            "Bestaand forward-logboek faalt de integriteitscontrole. "
            "Er wordt niets toegevoegd. " + message
        )

    previous_hash = entries[-1]["entry_hash"] if entries else "GENESIS"
    payload = dict(entry_payload)
    payload["previous_hash"] = previous_hash
    payload["strategy_hash"] = STRATEGY_HASH
    payload["strategy_version"] = STRATEGY_VERSION

    entry_hash = sha256_text(canonical_json(payload))
    final = dict(payload)
    final["entry_hash"] = entry_hash

    with LEDGER_FILE.open("a", encoding="utf-8", newline="\n") as f:
        f.write(canonical_json(final) + "\n")

    return final


def days_since_last_signal(entries: List[dict], signal_date: pd.Timestamp) -> int | None:
    signals = [e for e in entries if e.get("record_type") == "signal"]
    if not signals:
        return None
    last = max(pd.Timestamp(e["signal_market_date"]) for e in signals)
    return int((signal_date.normalize() - last.normalize()).days)


def can_lock_new_signal(entries: List[dict], signal_date: pd.Timestamp) -> Tuple[bool, str]:
    signals = [e for e in entries if e.get("record_type") == "signal"]
    if not signals:
        return True, "Eerste forward-signaal."

    last = max(pd.Timestamp(e["signal_market_date"]) for e in signals)
    delta = int((signal_date.normalize() - last.normalize()).days)

    if delta < 28:
        return False, f"Vorige signaal was {delta} dagen geleden. Nieuwe selectie pas vanaf 28 dagen."
    return True, f"{delta} dagen sinds het vorige signaal."


def next_trading_day_after(index: pd.DatetimeIndex, dt: pd.Timestamp) -> pd.Timestamp | None:
    later = index[index > dt]
    return pd.Timestamp(later[0]) if len(later) else None


@st.cache_data(ttl=1800, show_spinner=False)
def download_forward_history(tickers: Tuple[str, ...], start_date: str) -> pd.DataFrame:
    start = pd.Timestamp(start_date) - pd.Timedelta(days=10)
    end = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)

    raw = yf.download(
        list(tickers),
        start=start.date(),
        end=end.date(),
        auto_adjust=True,
        progress=False,
        actions=False,
        group_by="column",
        threads=True,
    )

    if raw.empty:
        raise ValueError("Geen forward-koersdata ontvangen.")

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:
        close = raw[["Close"]].copy()
        close.columns = [tickers[0]]

    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])

    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def simulate_forward(entries: List[dict], cost_pct: float) -> Tuple[pd.Series, pd.Series, pd.DataFrame]:
    signals = [e for e in entries if e.get("record_type") == "signal"]
    if not signals:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.DataFrame()

    signals = sorted(signals, key=lambda x: x["signal_market_date"])
    first_signal = pd.Timestamp(signals[0]["signal_market_date"])

    tickers = {"SPY"}
    for e in signals:
        tickers.update(x["ticker"] for x in e["selected"])

    prices = download_forward_history(tuple(sorted(tickers)), str(first_signal.date()))
    if "SPY" not in prices.columns:
        raise ValueError("SPY ontbreekt in de forward-koersdata.")

    # Map elk signaal naar de eerste beschikbare handelsdag erna.
    exec_map = {}
    for e in signals:
        signal_date = pd.Timestamp(e["signal_market_date"])
        exec_date = next_trading_day_after(prices.index, signal_date)
        if exec_date is not None:
            exec_map[exec_date] = e

    if not exec_map:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.DataFrame()

    start = min(exec_map.keys())
    idx = prices.index[prices.index >= start]

    asset_returns = prices.pct_change(fill_method=None)

    wealth = 1.0
    spy_wealth = 1.0
    weights: Dict[str, float] = {}
    cash_weight = 1.0
    strategy_eq = pd.Series(index=idx, dtype=float)
    spy_eq = pd.Series(index=idx, dtype=float)

    execution_rows = []

    spy_start_price = None

    for dt in idx:
        # Existing portfolio earns today's return.
        if weights:
            gross_factor = cash_weight
            new_values = {}
            for ticker, w in weights.items():
                r = asset_returns.at[dt, ticker] if ticker in asset_returns.columns else np.nan
                if not np.isfinite(r):
                    r = 0.0
                factor = max(0.0, 1.0 + float(r))
                new_values[ticker] = w * factor
                gross_factor += w * factor

            if gross_factor <= 0:
                gross_factor = 1e-12

            wealth *= gross_factor
            weights = {t: v / gross_factor for t, v in new_values.items()}
            cash_weight = cash_weight / gross_factor

        if spy_start_price is None and np.isfinite(prices.at[dt, "SPY"]):
            spy_start_price = float(prices.at[dt, "SPY"])

        if spy_start_price:
            current_spy = prices.at[dt, "SPY"]
            if np.isfinite(current_spy):
                spy_wealth = float(current_spy) / spy_start_price

        # Rebalance at end of execution date. New holdings earn from next session.
        if dt in exec_map:
            entry = exec_map[dt]
            chosen = [x["ticker"] for x in entry["selected"]]
            chosen = [t for t in chosen if t in prices.columns]

            if chosen:
                target = {t: 1.0 / len(chosen) for t in chosen}
                names = set(weights) | set(target)
                stock_turnover = sum(
                    abs(target.get(t, 0.0) - weights.get(t, 0.0))
                    for t in names
                )
                cash_turnover = abs(cash_weight)
                turnover = 0.5 * (stock_turnover + cash_turnover)
                fee = turnover * (cost_pct / 100.0)
                wealth *= max(0.0, 1.0 - fee)

                weights = target
                cash_weight = 0.0

                execution_rows.append({
                    "Signaaldatum": entry["signal_market_date"],
                    "Uitvoeringsdatum": str(pd.Timestamp(dt).date()),
                    "Top": ", ".join(chosen),
                    "Omzet %": turnover * 100,
                    "Kost % portefeuille": fee * 100,
                })

        strategy_eq.at[dt] = wealth
        spy_eq.at[dt] = spy_wealth

    return strategy_eq.dropna(), spy_eq.dropna(), pd.DataFrame(execution_rows)


def drawdown(eq: pd.Series) -> float:
    if eq.empty:
        return np.nan
    return float((eq / eq.cummax() - 1).min() * 100)


ensure_dirs()

st.title("StockWaakhond V7 — bevroren forward-test")
st.caption(
    "Geen historische optimalisatie meer. Nieuwe Top-5-selecties worden vooraf vastgelegd in een controleerbaar append-only logboek."
)

with st.sidebar:
    st.header("Bevroren instellingen")
    top_n = st.number_input(
        "Top-N",
        min_value=5,
        max_value=5,
        value=5,
        disabled=True,
    )
    cost_pct = st.number_input(
        "Transactiekost (%)",
        min_value=0.15,
        max_value=0.15,
        value=0.15,
        disabled=True,
    )

    st.code(STRATEGY_VERSION)
    st.caption("Strategiehash")
    st.code(STRATEGY_HASH[:20] + "…")

entries = read_ledger()
ledger_ok, ledger_message = verify_ledger(entries)

if ledger_ok:
    st.success(f"Logboek-integriteit: OK — {len(entries)} record(s).")
else:
    st.error("LOGBOEK NIET INTACT: " + ledger_message)
    st.stop()

st.subheader("1. Huidige markt scannen")

try:
    universe, universe_hash = fetch_current_sp500_universe()
except Exception as exc:
    st.error(f"Actueel S&P 500-universum kon niet worden geladen: {exc}")
    st.stop()

try:
    with st.spinner(f"Koersdata ophalen voor {len(universe)} S&P 500-symbolen..."):
        tickers = tuple(sorted(set(universe + ["SPY"])))
        prices = download_adjusted_close(tickers)
        scan, signal_date, coverage = build_score_table(prices, universe)
except Exception as exc:
    st.error(f"Marktscan mislukt: {exc}")
    st.stop()

st.write(
    f"Laatste voltooide koersdag: **{signal_date.date()}** · "
    f"kandidatendekking: **{coverage:.1f}%** · universum: **{len(universe)}** aandelen."
)

st.dataframe(
    scan.head(20)[
        [
            "Ticker", "Score", "Koers", "3m %", "6m %", "12m %",
            "Rel. sterkte 6m %-punt", "Boven MA200", "MA50 > MA200",
            "3m drawdown %", "3m volatiliteit %"
        ]
    ].style.format(
        {
            "Score": "{:.1f}",
            "Koers": "{:.2f}",
            "3m %": "{:+.1f}",
            "6m %": "{:+.1f}",
            "12m %": "{:+.1f}",
            "Rel. sterkte 6m %-punt": "{:+.1f}",
            "3m drawdown %": "{:.1f}",
            "3m volatiliteit %": "{:.1f}",
        }
    ),
    hide_index=True,
    width="stretch",
)

top = scan.head(5).copy()
st.info("Huidige Top-5: " + ", ".join(top["Ticker"].tolist()))

allowed, reason = can_lock_new_signal(entries, signal_date)

if coverage < STRATEGY_SPEC["minimum_candidate_coverage_pct"]:
    allowed = False
    reason = (
        f"Dekking {coverage:.1f}% is lager dan de bevroren minimumgrens "
        f"van {STRATEGY_SPEC['minimum_candidate_coverage_pct']:.1f}%."
    )

if allowed:
    st.warning(
        "Klikken op de knop hieronder schrijft deze selectie definitief in het forward-logboek. "
        "De app biedt geen functie om oude signalen te wijzigen of te verwijderen."
    )
else:
    st.info("Nieuwe selectie kan nu niet worden vastgelegd: " + reason)

if st.button(
    "Leg deze Top-5 definitief vast",
    type="primary",
    width="stretch",
    disabled=not allowed,
):
    payload = {
        "record_type": "signal",
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "signal_market_date": str(signal_date.date()),
        "universe_source": WIKI_URL,
        "universe_hash": universe_hash,
        "universe_count": len(universe),
        "eligible_count": int(len(scan)),
        "coverage_pct": round(float(coverage), 6),
        "selected": [
            {
                "rank": int(i + 1),
                "ticker": str(row["Ticker"]),
                "score": round(float(row["Score"]), 8),
                "signal_close": round(float(row["Koers"]), 8),
            }
            for i, (_, row) in enumerate(top.iterrows())
        ],
        "spy_signal_close": round(float(prices["SPY"].dropna().iloc[-1]), 8),
        "formula_spec": STRATEGY_SPEC,
    }

    entry = append_signal_entry(payload)
    st.success(
        "Top-5 is vastgelegd. Entry hash: "
        + entry["entry_hash"][:24]
        + "…"
    )
    st.rerun()

st.subheader("2. Vastgelegde forward-signalen")

signals = [e for e in entries if e.get("record_type") == "signal"]
if not signals:
    st.info("Nog geen forward-signaal vastgelegd.")
else:
    log_rows = []
    for e in signals:
        log_rows.append({
            "Signaaldatum": e["signal_market_date"],
            "Vastgelegd UTC": e["created_at_utc"],
            "Top-5": ", ".join(x["ticker"] for x in e["selected"]),
            "Dekking %": e["coverage_pct"],
            "Entry hash": e["entry_hash"][:16] + "…",
        })

    st.dataframe(
        pd.DataFrame(log_rows).style.format({"Dekking %": "{:.1f}"}),
        hide_index=True,
        width="stretch",
    )

st.subheader("3. Echte forward-prestatie")

if signals:
    try:
        strategy_eq, spy_eq, executions = simulate_forward(signals, float(cost_pct))

        if strategy_eq.empty or spy_eq.empty:
            st.info(
                "Het eerste signaal is vastgelegd, maar er is nog geen volgende handelsdag beschikbaar "
                "om een eerlijke uitvoeringskoers te bepalen."
            )
        else:
            common = strategy_eq.index.intersection(spy_eq.index)
            curve = pd.DataFrame({
                "StockWaakhond": 10000 * strategy_eq.reindex(common),
                "SPY": 10000 * spy_eq.reindex(common),
            }).dropna()

            st.line_chart(curve)

            sw_return = (strategy_eq.iloc[-1] - 1) * 100
            spy_return = (spy_eq.iloc[-1] - 1) * 100
            edge = sw_return - spy_return

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("StockWaakhond", f"{sw_return:+.2f}%")
            c2.metric("SPY", f"{spy_return:+.2f}%")
            c3.metric("Verschil", f"{edge:+.2f} %-punt")
            c4.metric("SW max drawdown", f"{drawdown(strategy_eq):.2f}%")

            if not executions.empty:
                st.markdown("#### Uitvoeringen")
                st.dataframe(
                    executions.style.format(
                        {
                            "Omzet %": "{:.1f}",
                            "Kost % portefeuille": "{:.3f}",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                )
    except Exception as exc:
        st.warning(
            "Forward-prestatie kon nog niet volledig worden berekend: " + str(exc)
        )

st.subheader("4. Integriteitsbewijs")

st.write(
    "Strategieversie: **" + STRATEGY_VERSION + "**"
)
st.code(STRATEGY_HASH)

if signals:
    st.write("Laatste ledger-hash:")
    st.code(signals[-1]["entry_hash"])

st.caption(
    "De hash-keten maakt onopgemerkte wijzigingen aan eerdere regels detecteerbaar. "
    "Dit is geen externe cryptografische timestamp: iemand met volledige toegang tot de bestanden "
    "kan theoretisch een volledig nieuw logboek genereren. Voor onze eigen blinde test voorkomt dit "
    "wel achteraf stilletjes aanpassen van oude selecties."
)

st.subheader("5. Ruwe logboekdata")

if LEDGER_FILE.exists():
    st.download_button(
        "Download ledger.jsonl",
        data=LEDGER_FILE.read_bytes(),
        file_name="stockwaakhond_forward_ledger.jsonl",
        mime="application/jsonl",
    )
