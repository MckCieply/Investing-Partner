"""yfinance wrapper: single source of truth for OHLCV access used by every setup.

All functions cache raw downloads on disk (backtest/.cache) keyed by ticker+range,
since the same ticker/window gets hit repeatedly across setups and engine runs.
"""
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd
import yfinance as yf

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

SPY = "SPY"


def _cache_path(ticker, start, end):
    key = f"{ticker}_{start}_{end}"
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    # CSV, not parquet: avoids a hard pyarrow/fastparquet dependency for what are
    # small per-ticker OHLCV frames where parquet's performance edge doesn't matter.
    return os.path.join(CACHE_DIR, f"{h}.csv")


def get_history(ticker, start, end, retries=3):
    """Daily OHLCV for one ticker between start/end (inclusive-ish, yfinance semantics).

    Returns a flat-column DataFrame (Open/High/Low/Close/Volume) indexed by Date,
    or an empty DataFrame if the ticker has no data in range (delisted, bad symbol, etc).
    """
    path = _cache_path(ticker, start, end)
    if os.path.exists(path):
        cached = pd.read_csv(path, index_col=0, parse_dates=True)
        cached.index.name = "Date"
        return cached

    last_err = None
    for attempt in range(retries):
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"yfinance failed for {ticker} after {retries} attempts: {last_err}")

    if df is None or df.empty:
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df.index.name = "Date"
        df.to_csv(path)
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "Date"
    df.to_csv(path)
    return df


def price_on_or_after(df, date, field="Open"):
    """First trading-day value at/after `date`. Returns (date_used, value) or (None, None)."""
    date = pd.Timestamp(date)
    idx = df.index[df.index >= date]
    if len(idx) == 0:
        return None, None
    d = idx[0]
    return d, float(df.loc[d, field])


def session_offset(df, anchor_date, n_sessions):
    """Trading session N bars after the first session at/after anchor_date.

    n_sessions can be negative to look back. Returns (date, row) or (None, None)
    if out of range.
    """
    anchor_date = pd.Timestamp(anchor_date)
    pos_idx = df.index[df.index >= anchor_date]
    if len(pos_idx) == 0:
        return None, None
    anchor_pos = df.index.get_loc(pos_idx[0])
    target_pos = anchor_pos + n_sessions
    if target_pos < 0 or target_pos >= len(df.index):
        return None, None
    d = df.index[target_pos]
    return d, df.loc[d]


def atr(df, period=14):
    """Average True Range, Wilder smoothing, as a Series aligned to df.index."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def get_spy(start, end):
    return get_history(SPY, start, end)
