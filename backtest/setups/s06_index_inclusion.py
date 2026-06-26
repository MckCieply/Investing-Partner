"""Setup 6: S&P 500 Index Inclusion.

Trigger: binary - ticker added to the S&P 500. Event date = the announced
effective date from Wikipedia's "Selected changes" history table, which
mirrors S&P Dow Jones Indices' own change announcements. We only use the
"Added" side (the displaced/removed ticker is a different, unrelated setup).

This is the cleanest setup in Group 1 - no clustering, no judgment calls,
just a public historical record plus yfinance.
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import requests

from core.backtest_engine import run_backtest
from core.metrics import summarize_setup

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
LOOKBACK_YEARS = 5


def fetch_inclusion_events():
    r = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    changes = tables[1]
    changes.columns = ["effective_date", "added_ticker", "added_security",
                        "removed_ticker", "removed_security", "reason"]

    changes["effective_date"] = pd.to_datetime(changes["effective_date"], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * LOOKBACK_YEARS)
    changes = changes[changes["effective_date"] >= cutoff]
    changes = changes.dropna(subset=["added_ticker", "effective_date"])

    events = []
    for _, row in changes.iterrows():
        ticker = str(row["added_ticker"]).strip()
        if not ticker or ticker.lower() == "nan":
            continue
        events.append({
            "ticker": ticker,
            "event_date": row["effective_date"].date().isoformat(),
            "setup_type": "s06_index_inclusion",
            "reason": row["reason"],
        })
    return events


def main():
    print("Fetching S&P 500 inclusion history from Wikipedia...")
    events = fetch_inclusion_events()
    print(f"  {len(events)} inclusion events in the last {LOOKBACK_YEARS} years")

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s06_index_inclusion_events.csv"), index=False)

    results = run_backtest(events)
    results.to_csv(os.path.join(results_dir, "s06_index_inclusion_results.csv"), index=False)

    summary = summarize_setup(results, "s06_index_inclusion")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s06_index_inclusion_summary.csv"), index=False)


if __name__ == "__main__":
    main()
