"""Setup 4: Sector out of favour -> rebound.

Thesis under test (Group 3 / handoff): a sector that is deeply out of favour
(>20% below its 52-week high) and then starts to turn (reclaims its SMA50) offers
a tradeable rebound edge.

Everything here is MECHANICAL and ex-ante observable on the trigger day - no
hand-picking of "sectors that recovered". The same state machine is applied to
every sector ETF over the whole scan window, and EVERY trigger is taken (the ones
that ran and the ones that fizzled).

Trigger (event date = day T):
  - regime: Close[T] <= 0.80 * (rolling 252-session high of Close)  ("out of favour")
  - turn:   Close[T] >= SMA50[T]  and  Close[T-1] < SMA50[T-1]      (reclaims SMA50)
Entry: T+1 (engine default), in the sector ETF itself.

PLACEBO / negative control (same turn signal, opposite regime):
  - Close[T] >= 0.95 * (rolling 252-session high)  ("near highs, NOT out of favour")
  - same SMA50 reclaim
If the placebo earns a similar return to the real sample, the edge is in the
SMA50-reclaim technicals, NOT in the "out of favour" narrative - which is the whole
point of this setup. The comparison is what makes the test honest.

NOTE on the "extended" version (top-momentum single stock inside the weak sector):
deliberately NOT implemented. Doing it correctly needs point-in-time sector
membership; using today's holdings to trade a historical signal is look-ahead /
survivorship bias (the basket's current members are partly selected by having
survived). Per the handoff's own rule, an extended version that can only be built
with hindsight is left out rather than done with bias. The ETF version is the
clean, unbiased test of the same thesis.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from data_layer import prices
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup
from core.cohorts import write_cohorts

# The 11 SPDR sector ETFs. (XLRE inception 2015-10, XLC inception 2018-06; the
# 252-session warmup for the 52wk high handles their short early history.)
SECTOR_ETFS = ["XLE", "XLF", "XLK", "XLV", "XLI", "XLP", "XLU", "XLB", "XLRE", "XLC", "XLY"]

SCAN_START = "2015-01-01"
SCAN_END = "2026-06-25"

HIGH_WINDOW = 252          # ~1 trading year for the 52-week high
SMA_PERIOD = 50
OUT_OF_FAVOUR = 0.80       # <= 80% of 52wk high  => >=20% below high
NEAR_HIGHS = 0.95          # >= 95% of 52wk high  => placebo regime
MIN_GAP_SESSIONS = 10      # dedup whipsaw: no two events on the same ETF within 10 sessions


def _indicators(df):
    out = df.copy()
    out["roll_high"] = out["Close"].rolling(HIGH_WINDOW, min_periods=HIGH_WINDOW).max()
    out["sma"] = out["Close"].rolling(SMA_PERIOD, min_periods=SMA_PERIOD).mean()
    out["pct_of_high"] = out["Close"] / out["roll_high"]
    # SMA50 reclaim: below yesterday, at/above today
    out["reclaim"] = (out["Close"] >= out["sma"]) & (out["Close"].shift(1) < out["sma"].shift(1))
    return out


def _scan_etf(ticker, regime_mask_fn, setup_type):
    """regime_mask_fn(row) -> bool decides whether the regime condition holds at T."""
    df = prices.get_history(ticker, SCAN_START, SCAN_END)
    if df.empty:
        return []
    ind = _indicators(df)
    ind = ind.dropna(subset=["roll_high", "sma"])

    events = []
    last_pos = -10**9
    positions = {d: i for i, d in enumerate(ind.index)}
    for d, row in ind.iterrows():
        if not row["reclaim"]:
            continue
        if not regime_mask_fn(row):
            continue
        pos = positions[d]
        if pos - last_pos < MIN_GAP_SESSIONS:
            continue
        last_pos = pos
        events.append({
            "ticker": ticker,
            "event_date": d.date().isoformat(),
            "setup_type": setup_type,
            "pct_of_52wk_high": round(float(row["pct_of_high"]), 4),
        })
    return events


def build_events():
    real, placebo = [], []
    for etf in SECTOR_ETFS:
        real.extend(_scan_etf(
            etf, lambda r: r["pct_of_high"] <= OUT_OF_FAVOUR, "s04_sector_rebound"))
        placebo.extend(_scan_etf(
            etf, lambda r: r["pct_of_high"] >= NEAR_HIGHS, "s04_sector_rebound_placebo"))
    return real, placebo


def _run_and_write(events, name, results_dir):
    pd.DataFrame(events).to_csv(os.path.join(results_dir, f"{name}_events.csv"), index=False)
    results = run_backtest(events)
    results.to_csv(os.path.join(results_dir, f"{name}_results.csv"), index=False)
    summary = summarize_setup(results, name)
    summary.to_csv(os.path.join(results_dir, f"{name}_summary.csv"), index=False)
    cohorts = write_cohorts(results, name, results_dir)
    return results, summary, cohorts


def main():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    real, placebo = build_events()
    print(f"Real (out of favour) events:  {len(real)}")
    print(f"Placebo (near highs) events:  {len(placebo)}")

    _, real_summary, _ = _run_and_write(real, "s04_sector_rebound", results_dir)
    print("\n== REAL (out of favour -> SMA50 reclaim) ==")
    print(real_summary.to_string(index=False))

    _, placebo_summary, _ = _run_and_write(placebo, "s04_sector_rebound_placebo", results_dir)
    print("\n== PLACEBO (near highs -> SMA50 reclaim) ==")
    print(placebo_summary.to_string(index=False))


if __name__ == "__main__":
    main()
