"""Setup 21: Post Lock-up Expiry (contrarian).

Trigger: the IPO lock-up expiration date - the thesis (per handoff) is
contrarian: price often drifts down into the expiry on anticipated insider
selling, then the drop reverses once the (mostly unrealized) overhang clears.

Two free-data limitations, both documented rather than worked around:

1. No free source publishes actual insider-selling volume around lock-up
   expiry, so - exactly as the handoff anticipates - we can only measure
   price behavior around the date, not the real driver (how much insiders
   actually sold).

2. EDGAR full-text search has no clean field for "this is an IPO 424B4"
   vs. a follow-on/secondary 424B4 (same form, used for any registered
   offering), and prospectuses don't always state the lock-up length in a
   single consistently-findable sentence. We approximate: take 424B4 filings
   whose text contains "initial public offering" (filters out most secondary
   offerings) as the IPO event, and assume the standard 180-calendar-day
   lock-up (the market convention for the vast majority of US IPOs) from the
   424B4 filing date to compute the expiry date. This is a fixed assumption,
   not extracted per-filing, so any IPO using a non-standard lock-up (90-day,
   staggered, or extended) is silently mismeasured. This is the single
   biggest source of noise in this setup and is why it's flagged contrarian/
   exploratory rather than a clean trigger.

Entry: per the project's drawdown-anticipation framing, we enter T-5 sessions
before the computed expiry date (to capture the pre-expiry drift this setup
is contrarian against), consistent with the "around the date" measurement
the handoff calls for.
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
LOCKUP_DAYS = 180
ENTRY_OFFSET_SESSIONS = -5


def fetch_ipo_424b4(lookback_years):
    end = pd.Timestamp.now()
    # Lock-up expiry can be up to LOCKUP_DAYS after the IPO, so we need IPOs
    # filed up to LOCKUP_DAYS before our lookback start to still capture
    # their expiry inside the analysis window.
    start = end - pd.Timedelta(days=365 * lookback_years + LOCKUP_DAYS)
    # "initial public offering" inside a 424B4 returns >1000 hits per half-year
    # (EDGAR FTS truncates at a hard per-query cap), so we page year-by-year.
    all_hits = []
    for year_start in pd.date_range(start, end, freq="YS"):
        year_end = min(year_start + pd.DateOffset(years=1), end)
        hits = sec_edgar.full_text_search(
            '"initial public offering"', forms="424B4",
            start_date=year_start.strftime("%Y-%m-%d"),
            end_date=year_end.strftime("%Y-%m-%d"),
            max_results=500)
        print(f"  [{year_start.date()}..{year_end.date()}]: {len(hits)} hits")
        all_hits.extend(hits)
    return all_hits


def build_events(hits):
    tickers_df = sec_edgar.get_company_tickers()
    raw = sec_edgar.hits_to_events(hits, tickers_df, setup_type="s21_lockup_expiry")
    events = []
    seen_tickers = set()
    for ev in raw:
        if ev["ticker"] in seen_tickers:
            continue  # one IPO per ticker; 424B4 amendments would otherwise duplicate
        seen_tickers.add(ev["ticker"])
        ipo_date = pd.Timestamp(ev["event_date"])
        expiry = ipo_date + pd.Timedelta(days=LOCKUP_DAYS)
        events.append({
            "ticker": ev["ticker"],
            "event_date": expiry.date().isoformat(),
            "setup_type": "s21_lockup_expiry",
            "ipo_date": ipo_date.date().isoformat(),
        })
    return events


def main():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")

    print("Searching SEC EDGAR full-text search for 424B4 IPO prospectuses...")
    hits = fetch_ipo_424b4(LOOKBACK_YEARS)
    print(f"  {len(hits)} raw 424B4-with-IPO-language hits")

    events = build_events(hits)
    print(f"  {len(events)} IPOs resolved to a ticker, lock-up expiry computed at IPO+{LOCKUP_DAYS}d")

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * LOOKBACK_YEARS)
    events = [e for e in events if pd.Timestamp(e["event_date"]) >= cutoff]
    print(f"  {len(events)} with lock-up expiry inside the {LOOKBACK_YEARS}y analysis window")

    if not events:
        print("No events - cannot backtest.")
        return

    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s21_lockup_expiry_events.csv"), index=False)

    results = run_backtest(events, entry_offset_sessions=ENTRY_OFFSET_SESSIONS)
    results.to_csv(os.path.join(results_dir, "s21_lockup_expiry_results.csv"), index=False)

    summary = summarize_setup(results, "s21_lockup_expiry")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s21_lockup_expiry_summary.csv"), index=False)

    cohorts = write_cohorts(results, "s21_lockup_expiry", results_dir)
    print(cohorts.to_string())


if __name__ == "__main__":
    main()
