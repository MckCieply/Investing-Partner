"""Setup 14: Rate Sensitivity Play.

Trigger: FOMC decision date (hike/cut/hold), tested against rate-sensitive
sector ETFs (utilities, REITs, regional banks, homebuilders). This measures
CORRELATION between Fed decisions and sector reaction, not causation - the
handoff flags this explicitly. Treat results as directional context, not a
standalone tradeable edge.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from data_layer.fred import FOMC_MEETINGS, RATE_SENSITIVE_ETFS
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup


def build_events():
    events = []
    for m in FOMC_MEETINGS:
        for etf in RATE_SENSITIVE_ETFS:
            events.append({
                "ticker": etf,
                "event_date": m["date"],
                "setup_type": "s14_rate_sensitivity",
                "fomc_direction": m["direction"],
            })
    return events


def main():
    events = build_events()
    print(f"{len(events)} FOMC-meeting x rate-sensitive-ETF events")

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s14_rate_sensitivity_events.csv"), index=False)

    results = run_backtest(events, horizons=(10, 20, 30))
    results.to_csv(os.path.join(results_dir, "s14_rate_sensitivity_results.csv"), index=False)

    summary = summarize_setup(results, "s14_rate_sensitivity", horizons=(10, 20, 30))
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s14_rate_sensitivity_summary.csv"), index=False)

    if "fomc_direction" in results.columns:
        for direction in ["hike", "cut", "hold"]:
            sub = results[results["fomc_direction"] == direction]
            dir_summary = summarize_setup(sub, f"s14_rate_sensitivity_{direction}", horizons=(10, 20, 30))
            print(f"\n-- direction={direction} --")
            print(dir_summary.to_string())


if __name__ == "__main__":
    main()
