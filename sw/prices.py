"""Koersen en wisselkoersen ophalen bij Yahoo Finance.

Twee soorten koersen, met een belangrijk verschil:

  echte koers (raw)       - wat er die dag op het scherm stond
  herrekende koers (adj)  - diezelfde koers, achteraf verlaagd voor dividend
                            en splitsingen

De herrekende koersen veranderen met terugwerkende kracht: zodra een bedrijf
dividend uitkeert, worden alle oudere koersen van dat aandeel verlaagd. Handig
om totaalrendement te meten, onbruikbaar om te tonen wat je portefeuille waard
is. Daarom halen we ze allebei op en leggen we ze allebei vast.

Wanneer een koers definitief is, staat niet hier maar in sw/beurskalender.py.
Dat is pure klokrekenkunde zonder internet, en daardoor te testen zonder dat
er ook maar iets opgehaald wordt. De namen blijven hieronder beschikbaar, zodat
de scripts gewoon `pr.beurs_is_gesloten_voor(...)` kunnen blijven gebruiken.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from .beurskalender import (  # noqa: F401  (hier beschikbaar voor de scripts)
    BEURS,
    beurs_is_gesloten_voor,
    laatste_voltooide_handelsdag,
    slotmoment,
    wisselkoers_is_definitief,
)

FX_SYMBOOL = "EURUSD=X"
FX_BRON = "Yahoo Finance EURUSD=X dagslotkoers"


def _sluitkoersen(ruw: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    if ruw is None or ruw.empty:
        raise ValueError("Geen koersdata ontvangen.")

    if isinstance(ruw.columns, pd.MultiIndex):
        if "Close" not in ruw.columns.get_level_values(0):
            raise ValueError("Geen slotkoersen ontvangen.")
        close = ruw["Close"].copy()
    else:
        close = ruw[["Close"]].copy()
        close.columns = [tickers[0]]

    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])

    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def haal_koersen(
    tickers: List[str],
    start: str,
    eind: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Haalt echte en herrekende slotkoersen op. Geeft (echt, herrekend) terug."""
    tickers = sorted(set(tickers))
    eind_dt = pd.Timestamp(eind) if eind else pd.Timestamp.today().normalize()
    eind_dt = eind_dt + pd.Timedelta(days=1)

    gemeen = dict(start=pd.Timestamp(start).date(), end=eind_dt.date(),
                  progress=False, actions=False, group_by="column", threads=True)

    echt = _sluitkoersen(yf.download(tickers, auto_adjust=False, **gemeen), tickers)
    herrekend = _sluitkoersen(yf.download(tickers, auto_adjust=True, **gemeen), tickers)
    return echt, herrekend


def haal_wisselkoers(start: str, eind: Optional[str] = None) -> pd.Series:
    """Dagelijkse slotkoers euro-dollar: het aantal dollar voor een euro."""
    eind_dt = (pd.Timestamp(eind) if eind else pd.Timestamp.today().normalize()) + pd.Timedelta(days=1)
    ruw = yf.download(FX_SYMBOOL, start=pd.Timestamp(start).date(), end=eind_dt.date(),
                      auto_adjust=True, progress=False, actions=False, threads=False)
    if ruw is None or ruw.empty:
        raise ValueError("Geen wisselkoersen ontvangen.")

    koers = ruw["Close"]
    if isinstance(koers, pd.DataFrame):
        koers = koers.iloc[:, 0]
    koers.index = pd.to_datetime(koers.index).tz_localize(None)
    return koers.sort_index().dropna()


def eerste_handelsdag_na(index: pd.DatetimeIndex, datum: str) -> Optional[pd.Timestamp]:
    later = index[index > pd.Timestamp(datum)]
    return pd.Timestamp(later[0]) if len(later) else None


def koersen_op(frame: pd.DataFrame, datum: pd.Timestamp) -> Dict[str, float]:
    """De koersen van een bepaalde dag als eenvoudige tabel."""
    if datum not in frame.index:
        raise ValueError(f"Geen koersen voor {datum.date()}.")
    rij = frame.loc[datum]
    return {t: float(v) for t, v in rij.items() if pd.notna(v) and float(v) > 0}


def laatste_koersen(tickers: List[str]) -> Tuple[Dict[str, float], str]:
    """De meest recente koers per aandeel, voor het dashboard.

    Dit is vertraagde data, geen realtime. Het tijdstip komt mee terug zodat
    het scherm eerlijk kan tonen hoe oud de cijfers zijn.
    """
    tickers = sorted(set(tickers))
    ruw = yf.download(tickers, period="5d", interval="1m", auto_adjust=False,
                      progress=False, actions=False, group_by="column", threads=True)
    if ruw is None or ruw.empty:
        ruw = yf.download(tickers, period="5d", auto_adjust=False,
                          progress=False, actions=False, group_by="column", threads=True)

    if isinstance(ruw.columns, pd.MultiIndex):
        close = ruw["Close"]
    else:
        close = ruw[["Close"]]
        close.columns = [tickers[0]]

    laatste = {}
    for t in close.columns:
        reeks = close[t].dropna()
        if len(reeks):
            laatste[str(t)] = float(reeks.iloc[-1])

    tijdstip = pd.Timestamp(close.index[-1])
    if tijdstip.tzinfo is None:
        tijdstip = tijdstip.tz_localize("UTC")
    return laatste, tijdstip.isoformat()
