"""Setup: Quant Gate (validating the live pipeline's own screen, historically).

This is NOT a new candidate setup - it backtests the deterministic 3-gate rule
the live `gem-inwestycyjny` pipeline already runs every ticker through (Agent 02,
`.claude/skills/gem-inwestycyjny/shared/quant_scanner.py`):

    GREEN LIGHT = TRUE only if ALL THREE hold:
        Close > SMA50
        Close > SMA200
        RSI14 < 70
    StopLoss = Close - 2 * ATR14   (informational in quant_scanner; used here only
                                     as the engine's "atr2" stop-loss variant)

The SMA50/SMA200/RSI14 formulas here are copied verbatim from quant_scanner.py
(simple rolling mean SMA; RSI via `rolling(14).mean()` of gains/losses - NOT the
Wilder/ewm RSI in `data_layer/prices.py`, which is a different, smoother variant
used by other setups). Matching quant_scanner exactly is the point: this backtest
answers "does the rule Quant actually runs have a historical base rate", not "does
some adjacent version of RSI work". The stop-loss ATR, by contrast, comes from the
shared engine's `atr2` variant (Wilder-smoothed ATR via `data_layer/prices.atr`,
per house convention in `core/backtest_engine.py`) - ATR is not part of the green-
light gate itself, only of the informational stop level, so this mismatch does not
touch the signal being tested.

Signal (mechanical, ex-ante observable, whole universe, no cherry-picking):
  event date = the day the gate flips from NOT-green to green (false -> true).
  Only the flip is taken, never every day the gate stays green, so a single
  multi-month uptrend contributes one event, not one per session.
Entry: T+1 at Open (engine default) - no look-ahead.

Universe: S&P 500 (Wikipedia, full list) + a European large/mid-cap universe built
from five major national index constituent lists (Wikipedia): DAX 40, CAC 40,
FTSE 100, AEX 25, IBEX 35 (~238 unique names after de-dup). This is NOT the full
STOXX 600 - a clean, versioned STOXX 600 constituent list was not readily available
without a paid data source, so five liquid national blue-chip indices stand in as
a reasonable large/mid-cap European proxy. This under-represents European mid-caps
outside these five markets (e.g. Nordics, Poland/GPW, smaller Benelux/Swiss names)
relative to the live pipeline's full USA+Europe mandate. Documented limitation, not
faked coverage.

PLACEBO / decomposition (the gate is an AND of 3 conditions - isolate which one is
doing the work, same logic as Group 3's placebo in this project):
  placebo_sma50_only:    Close > SMA50 alone (flip false->true), ignoring SMA200 & RSI
  placebo_sma_both_norsi: Close > SMA50 AND Close > SMA200 (flip), ignoring RSI<70
Comparing real vs placebo_sma_both_norsi isolates RSI<70's marginal contribution;
comparing placebo_sma_both_norsi vs placebo_sma50_only isolates SMA200's marginal
contribution over a bare SMA50 breakout.

Compute-cost note: fetching ~740 tickers' full daily history via yfinance is the
actual bottleneck (network/rate limits), not indicator math (vectorized, cheap) -
`data_layer/prices.py`'s on-disk cache means this cost is paid once. The real
per-run cost is `run_backtest()`, which re-fetches a fresh (start,end) window per
EVENT (cache key includes the window, so it does not reuse the full-history
download). A bare SMA50 breakout flips often (crosses back and forth around a
choppy moving average), so the "SMA50-only" placebo generates a very large raw
event count across ~740 tickers x ~12 years. To keep runtime bounded, each event
pool (real, placebo A, placebo B) is capped at MAX_EVENTS_PER_POOL via a fixed-seed
uniform random sample when it exceeds the cap - a uniform sample (not "most recent
N") to avoid skewing the yearly-cohort mandate toward the last couple of years.
"""
import io
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import requests

from data_layer import prices
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup
from core.cohorts import write_cohorts

SCAN_START = "2013-06-01"
SCAN_END = "2026-08-14"

SMA_SHORT = 50
SMA_LONG = 200
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70

MAX_EVENTS_PER_POOL = 400
RANDOM_SEED = 42
MIN_GAP_SESSIONS = 20  # ~1 trading month; collapses RSI-whipsaw re-flickers of
                        # the same underlying trend into a single event (see
                        # _transitions() docstring)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

HEADERS = {"User-Agent": "Mozilla/5.0"}


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def get_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    symbols = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
    return sorted(set(symbols))


def get_europe_tickers():
    """~238 unique large/mid-cap European names from 5 national blue-chip indices.

    See module docstring for why this stands in for STOXX 600.
    """
    sources = [
        ("https://en.wikipedia.org/wiki/DAX", 4, "Ticker", ""),
        ("https://en.wikipedia.org/wiki/CAC_40", 4, "Ticker", ""),
        ("https://en.wikipedia.org/wiki/FTSE_100_Index", 6, "Ticker", ".L"),
        ("https://en.wikipedia.org/wiki/AEX_index", 3, "Ticker", ""),
        ("https://en.wikipedia.org/wiki/IBEX_35", 2, "Ticker", ""),
    ]
    tickers = set()
    for url, idx, col, suffix in sources:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        vals = tables[idx][col].astype(str).str.strip()
        vals = vals.apply(lambda x: re.sub(r"\[.*?\]", "", x))          # strip footnotes
        vals = vals.apply(lambda x: x.replace(".", "-") if suffix else x)  # BT.A -> BT-A (then +.L)
        vals = (vals + suffix).tolist()
        tickers.update(vals)
    return sorted(tickers)


def get_universe():
    us = [(t, "US") for t in get_sp500_tickers()]
    eu = [(t, "EU") for t in get_europe_tickers()]
    return us + eu


# ---------------------------------------------------------------------------
# Indicators - copied to match shared/quant_scanner.py exactly (rolling SMA,
# rolling-mean RSI - NOT data_layer.prices.rsi's Wilder/ewm variant).
# ---------------------------------------------------------------------------

def _rsi_quant(close, period=RSI_PERIOD):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _gate_series(df):
    """Returns a DataFrame with the 3 gate booleans + real/placebo green flags,
    aligned to df.index. NaN during warmup is always treated as NOT green.
    """
    close = df["Close"]
    sma50 = close.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean()
    sma200 = close.rolling(SMA_LONG, min_periods=SMA_LONG).mean()
    rsi14 = _rsi_quant(close)

    gt50 = (close > sma50) & sma50.notna()
    gt200 = (close > sma200) & sma200.notna()
    rsi_ok = (rsi14 < RSI_OVERBOUGHT) & rsi14.notna()

    out = pd.DataFrame(index=df.index)
    out["real"] = gt50 & gt200 & rsi_ok
    out["placebo_sma50_only"] = gt50
    out["placebo_sma_both_norsi"] = gt50 & gt200
    return out.fillna(False)


def _transitions(flag_series, min_gap=MIN_GAP_SESSIONS):
    """False->True flip dates, deduped with a minimum session gap.

    A pure state-flip (false->true) is NOT enough on its own: RSI in particular
    whipsaws back and forth across the 70 line during a single extended uptrend
    (SMA50/SMA200 stay green throughout), which would otherwise re-fire "new"
    real-gate events every few sessions for what is really one ongoing trend.
    Same fix as s04_sector_rebound's MIN_GAP_SESSIONS: once a flip is taken, any
    further flip within `min_gap` trading sessions on the SAME ticker/condition
    is treated as a re-flicker of the same signal, not a new one.
    """
    prev = flag_series.shift(1, fill_value=False)
    raw = flag_series.index[flag_series & (~prev)]
    if len(raw) == 0:
        return raw
    positions = {d: i for i, d in enumerate(flag_series.index)}
    kept = []
    last_pos = -10 ** 9
    for d in raw:
        pos = positions[d]
        if pos - last_pos < min_gap:
            continue
        kept.append(d)
        last_pos = pos
    return pd.DatetimeIndex(kept)


def _scan_ticker(ticker, region):
    df = prices.get_history(ticker, SCAN_START, SCAN_END)
    if df.empty or len(df) < SMA_LONG + 5:
        return {"real": [], "placebo_sma50_only": [], "placebo_sma_both_norsi": []}

    gates = _gate_series(df)
    out = {}
    for col in ("real", "placebo_sma50_only", "placebo_sma_both_norsi"):
        dates = _transitions(gates[col])
        out[col] = [
            {"ticker": ticker, "event_date": d.date().isoformat(),
             "setup_type": "s_quant_gate" if col == "real" else f"s_quant_gate_{col}",
             "region": region}
            for d in dates
        ]
    return out


def build_events(universe=None, verbose=True):
    universe = universe or get_universe()
    pools = {"real": [], "placebo_sma50_only": [], "placebo_sma_both_norsi": []}
    for i, (ticker, region) in enumerate(universe):
        if verbose and i % 100 == 0:
            print(f"  scanning {i}/{len(universe)}: {ticker} ({region})", flush=True)
        try:
            r = _scan_ticker(ticker, region)
        except Exception as e:
            print(f"  {ticker}: skipped ({e})", flush=True)
            continue
        for k in pools:
            pools[k].extend(r[k])
    return pools


def _cap_pool(events, max_n=MAX_EVENTS_PER_POOL, seed=RANDOM_SEED):
    """Fixed-seed UNIFORM sample (not 'most recent N') so yearly cohorts stay
    populated across the whole scan window rather than skewed to recent years.
    """
    if len(events) <= max_n:
        return events
    rng = random.Random(seed)
    return rng.sample(events, max_n)


# ---------------------------------------------------------------------------
# Backtest + write
# ---------------------------------------------------------------------------

def _run_and_write(events, name):
    pd.DataFrame(events).to_csv(os.path.join(RESULTS_DIR, f"{name}_events.csv"), index=False)
    if not events:
        print(f"{name}: 0 events, nothing to backtest.")
        return None, None, None
    results = run_backtest(events)
    results.to_csv(os.path.join(RESULTS_DIR, f"{name}_results.csv"), index=False)
    summary = summarize_setup(results, name)
    summary.to_csv(os.path.join(RESULTS_DIR, f"{name}_summary.csv"), index=False)
    cohorts = write_cohorts(results, name, RESULTS_DIR)
    return results, summary, cohorts


def main():
    print("Building universe (S&P 500 + 5 European blue-chip indices)...")
    universe = get_universe()
    n_us = sum(1 for _, r in universe if r == "US")
    n_eu = sum(1 for _, r in universe if r == "EU")
    print(f"  universe: {len(universe)} tickers ({n_us} US, {n_eu} EU)")

    print("Scanning for gate transitions (this fetches/caches full price history per ticker)...")
    pools = build_events(universe)
    for k, v in pools.items():
        print(f"  raw {k}: {len(v)} events")

    capped = {k: _cap_pool(v) for k, v in pools.items()}
    for k, v in capped.items():
        if len(v) < len(pools[k]):
            print(f"  {k}: capped {len(pools[k])} -> {len(v)} (fixed-seed uniform sample)")

    names = {
        "real": "s_quant_gate",
        "placebo_sma50_only": "s_quant_gate_placebo_sma50_only",
        "placebo_sma_both_norsi": "s_quant_gate_placebo_sma_both_norsi",
    }
    for key, name in names.items():
        print(f"\n== {name} ({len(capped[key])} events) ==")
        _, summary, _ = _run_and_write(capped[key], name)
        if summary is not None:
            print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
