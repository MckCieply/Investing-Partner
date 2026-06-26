"""Setup 5: Spinoff.

Trigger: 8-K filing confirming a completed spinoff/separation (item 9.01 exhibit
attached, keyword "spin-off" or "separation" in the filing text). Event date =
the 8-K filing date.

Simplification (documented, not silently dropped): SEC full-text search returns
whichever entity filed the 8-K - sometimes the parent, sometimes the new spinoff
itself (e.g. GE Vernova's own 8-Ks about its spinoff from GE). We do not attempt
to separate "parent post-spin" from "newco" tickers; both get backtested under
the same setup_type, which mixes two return profiles the real setup distinguishes.
Treat this setup's results as a noisier first pass, not a clean test of either leg.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from data_layer.sec_edgar import full_text_search, hits_to_events, get_company_tickers
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup

LOOKBACK_YEARS = 5
QUERIES = ['"spin-off"', '"the Separation"', '"Distribution Date"']


def fetch_spinoff_events():
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=365 * LOOKBACK_YEARS)
    tickers_df = get_company_tickers()

    all_events = []
    seen = set()
    for q in QUERIES:
        hits = full_text_search(q, forms="8-K", start_date=start, end_date=end,
                                 items=["9.01"], max_results=150)
        events = hits_to_events(hits, tickers_df, setup_type="s05_spinoff")
        for e in events:
            key = (e["ticker"], e["event_date"])
            if key not in seen:
                seen.add(key)
                all_events.append(e)
    return all_events


def main():
    print("Searching SEC EDGAR full-text for spinoff 8-Ks...")
    events = fetch_spinoff_events()
    print(f"  {len(events)} distinct (ticker, filing_date) spinoff events")

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s05_spinoff_events.csv"), index=False)

    results = run_backtest(events)
    results.to_csv(os.path.join(results_dir, "s05_spinoff_results.csv"), index=False)

    summary = summarize_setup(results, "s05_spinoff")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s05_spinoff_summary.csv"), index=False)


if __name__ == "__main__":
    main()
