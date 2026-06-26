"""Setup 11: Buyback Announcement.

Trigger: an 8-K filing announcing a NEW share/stock repurchase authorization
(SEC EDGAR full-text search). We measure the market's reaction to the
announcement itself - whether the buyback is later executed is not in scope
and not visible in this data (a known, documented gap: announcement !=
execution, and some of this may already be priced in by the time the 8-K
hits EDGAR if it follows an earnings call same-day).

Query design: EDGAR full-text search for the bare phrase "stock repurchase
program" inside 8-Ks returns ~450 hits/month, mostly incidental mentions
inside quarterly-earnings press releases (Item 2.02) that reference an
*existing* program, not a new authorization. To isolate genuine new-
authorization events we instead search a small set of specific phrases that
only appear when a board newly authorizes/approves a program. This trades
recall for precision (we will miss authorizations using different wording)
deliberately, since duplicate/incidental hits would otherwise swamp the
sample with non-events.

Entry: D+1 after the 8-K filing date, per the handoff.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from core.backtest_engine import run_backtest
from core.cohorts import write_cohorts
from core.metrics import summarize_setup
from data_layer import sec_edgar

LOOKBACK_YEARS = 5
QUERIES = [
    '"authorized a new share repurchase program"',
    '"authorized a new stock repurchase program"',
    '"approved a new share repurchase program"',
    '"approved a new stock repurchase program"',
]
DEDUPE_WINDOW_DAYS = 5  # same company, same/adjacent filing date -> one event


def fetch_buyback_hits(lookback_years):
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=365 * lookback_years)
    all_hits = []
    # SEC FTS caps results per query; walk year-by-year windows to stay under that cap.
    for year_start in pd.date_range(start, end, freq="YS"):
        year_end = min(year_start + pd.DateOffset(years=1), end)
        for q in QUERIES:
            hits = sec_edgar.full_text_search(
                q, forms="8-K",
                start_date=year_start.strftime("%Y-%m-%d"),
                end_date=year_end.strftime("%Y-%m-%d"),
                max_results=300)
            print(f"  {q} [{year_start.date()}..{year_end.date()}]: {len(hits)} hits")
            all_hits.extend(hits)
    return all_hits


def dedupe_events(events):
    """One event per ticker per DEDUPE_WINDOW_DAYS-day window (keep earliest)."""
    df = pd.DataFrame(events)
    if df.empty:
        return []
    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.sort_values(["ticker", "event_date"])
    kept = []
    last_seen = {}
    for _, row in df.iterrows():
        t = row["ticker"]
        if t in last_seen and (row["event_date"] - last_seen[t]).days <= DEDUPE_WINDOW_DAYS:
            continue
        last_seen[t] = row["event_date"]
        kept.append({**row.to_dict(), "event_date": row["event_date"].date().isoformat()})
    return kept


def main():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")

    print("Searching SEC EDGAR full-text search for buyback-authorization 8-Ks...")
    hits = fetch_buyback_hits(LOOKBACK_YEARS)
    print(f"  {len(hits)} raw hits across all query phrases/years")

    tickers_df = sec_edgar.get_company_tickers()
    events = sec_edgar.hits_to_events(hits, tickers_df, setup_type="s11_buyback_announcement")
    print(f"  {len(events)} resolved to a ticker")

    events = dedupe_events(events)
    print(f"  {len(events)} after de-duplication (same ticker within {DEDUPE_WINDOW_DAYS}d)")

    if not events:
        print("No events - cannot backtest.")
        return

    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s11_buyback_announcement_events.csv"), index=False)

    results = run_backtest(events, entry_offset_sessions=1)
    results.to_csv(os.path.join(results_dir, "s11_buyback_announcement_results.csv"), index=False)

    summary = summarize_setup(results, "s11_buyback_announcement")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s11_buyback_announcement_summary.csv"), index=False)

    cohorts = write_cohorts(results, "s11_buyback_announcement", results_dir)
    print(cohorts.to_string())


if __name__ == "__main__":
    main()
