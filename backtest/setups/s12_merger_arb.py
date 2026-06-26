"""Setup 12: Merger Arbitrage.

Trigger: 8-K announcing a definitive merger agreement (item 1.01, "Agreement
and Plan of Merger"). We want the TARGET side (buy the target post-announcement
to capture the remaining spread to deal close), not the acquirer.

SEC full-text search returns whichever entity filed - both signing parties
often file their own 8-K. We can't reliably separate target from acquirer from
search metadata alone, so we use a mechanical proxy: keep only events where the
ticker's price jumped >3% on the filing date (the textbook target reaction;
acquirers are typically flat-to-down on deal announcement). This is a heuristic,
not a guarantee - documented here rather than silently assumed correct.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from data_layer import prices
from data_layer.sec_edgar import full_text_search, hits_to_events, get_company_tickers
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup

LOOKBACK_YEARS = 5
TARGET_JUMP_THRESHOLD = 0.03


def is_target_reaction(ticker, event_date):
    event_date = pd.Timestamp(event_date)
    start = (event_date - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    end = (event_date + pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    try:
        df = prices.get_history(ticker, start, end)
    except Exception:
        return False
    if df.empty:
        return False
    before = df[df.index < event_date]
    on_or_after = df[df.index >= event_date]
    if before.empty or on_or_after.empty:
        return False
    pre_close = before["Close"].iloc[-1]
    post_close = on_or_after["Close"].iloc[0]
    return (post_close / pre_close - 1) >= TARGET_JUMP_THRESHOLD


def fetch_merger_events():
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=365 * LOOKBACK_YEARS)
    tickers_df = get_company_tickers()

    hits = full_text_search('"Agreement and Plan of Merger"', forms="8-K",
                             start_date=start, end_date=end, items=["1.01"], max_results=300)
    candidates = hits_to_events(hits, tickers_df, setup_type="s12_merger_arb")

    seen = set()
    events = []
    for c in candidates:
        key = (c["ticker"], c["event_date"])
        if key in seen:
            continue
        seen.add(key)
        if is_target_reaction(c["ticker"], c["event_date"]):
            events.append(c)
    return events


def main():
    print("Searching SEC EDGAR full-text for merger agreement 8-Ks...")
    events = fetch_merger_events()
    print(f"  {len(events)} events pass the target-reaction filter")

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s12_merger_arb_events.csv"), index=False)

    results = run_backtest(events)
    results.to_csv(os.path.join(results_dir, "s12_merger_arb_results.csv"), index=False)

    summary = summarize_setup(results, "s12_merger_arb")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s12_merger_arb_summary.csv"), index=False)


if __name__ == "__main__":
    main()
