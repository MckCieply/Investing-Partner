"""Setup 20: Uplisting (OTC/AIM -> NYSE/NASDAQ).

Trigger: a company's common stock moves from OTC (or, per the handoff, AIM)
to a major US exchange. We only cover the OTC -> NASDAQ/NYSE direction here -
AIM (London) listing-transfer announcements are not reliably findable in SEC
EDGAR (AIM is an LSE market; a dual-listed/redomiciled company would file with
the SEC under a different event entirely), so that half of the trigger is out
of scope for this free-data pass. Documented, not silently dropped.

Source: SEC EDGAR full-text search on 8-Ks for completed-uplisting language.
We deliberately use past-tense, event-specific phrases ("uplisted to ...")
rather than the generic "approved for listing on Nasdaq" (which also matches
ordinary new-IPO 8-Ks and returns 1000+ hits dominated by non-uplisting
events) or forward-looking phrases like "uplisting to the Nasdaq" (which
mostly matches companies stating an *intent* to pursue uplisting, not a
completed event - that phrasing alone returns >700 hits, almost all noise).

Known limitation flagged in the handoff up front: this is expected to be a
small sample. If n < 40 at T+60 we mark the setup LOW CONFIDENCE regardless
of the metrics - we do not force a PASS/FAIL verdict off an undersized
sample, and we do not spend further effort trying to inflate n with noisier
search phrases once that's established.

Entry: D+1 after the 8-K filing date (same convention as Setup 11).
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
    '"uplisted to the Nasdaq"',
    '"uplisted to Nasdaq"',
    '"uplisted its common stock"',
    '"completed its uplisting"',
    '"uplisted to the NYSE"',
]
DEDUPE_WINDOW_DAYS = 30
MIN_N_FOR_CONFIDENCE = 40


def fetch_uplisting_hits(lookback_years):
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=365 * lookback_years)
    all_hits = []
    for q in QUERIES:
        hits = sec_edgar.full_text_search(
            q, forms="8-K",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            max_results=500)
        print(f"  {q}: {len(hits)} hits")
        all_hits.extend(hits)
    return all_hits


def dedupe_events(events):
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

    print("Searching SEC EDGAR full-text search for completed-uplisting 8-Ks...")
    hits = fetch_uplisting_hits(LOOKBACK_YEARS)
    print(f"  {len(hits)} raw hits across all query phrases")

    tickers_df = sec_edgar.get_company_tickers()
    events = sec_edgar.hits_to_events(hits, tickers_df, setup_type="s20_uplisting")
    print(f"  {len(events)} resolved to a ticker")

    events = dedupe_events(events)
    print(f"  {len(events)} after de-duplication (same ticker within {DEDUPE_WINDOW_DAYS}d)")

    if not events:
        print("No events - cannot backtest.")
        return

    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s20_uplisting_events.csv"), index=False)

    results = run_backtest(events, entry_offset_sessions=1)
    results.to_csv(os.path.join(results_dir, "s20_uplisting_results.csv"), index=False)

    summary = summarize_setup(results, "s20_uplisting")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s20_uplisting_summary.csv"), index=False)

    cohorts = write_cohorts(results, "s20_uplisting", results_dir)
    print(cohorts.to_string())

    n_t60 = summary[summary["horizon"] == 60]["n"].iloc[0] if 60 in summary["horizon"].values else 0
    if n_t60 < MIN_N_FOR_CONFIDENCE:
        print(f"\nLOW CONFIDENCE: n={n_t60} at T+60 is below the {MIN_N_FOR_CONFIDENCE} floor - "
              f"not eligible for PASS regardless of edge/win-rate metrics.")


if __name__ == "__main__":
    main()
