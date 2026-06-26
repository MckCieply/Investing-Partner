"""Setup 9: Short Squeeze Candidate (high SI + drawdown proxy).

Trigger (per handoff): "short interest >20% float" - the handoff itself
flags this as needing a proxy, since the FINRA bi-weekly feed (the only
free source) has no float-shares field, only currentShortPositionQuantity
and averageDailyVolumeQuantity. We use daysToCoverQuantity (days-to-cover),
a standard practitioner short-squeeze-risk metric, as the substitute for
"% of float". See data_layer/finra.py for the full caveat.

Operational definition (frozen before any backtest run):
  - Listed equities only (marketClassCode in NNM/NYSE/SC/AMEX - excludes OTC
    pink sheets, which are largely untradeable/illiquid for this purpose,
    and ETF-only venues ARCA/BZX).
  - daysToCoverQuantity >= 20 on a bi-weekly settlement date.
  - Price down >= 25% from its trailing 90-day high as of that date (same
    drawdown filter/threshold as Setup 7, kept consistent across the project).
  - One event per ticker per 90-day window (first qualifying date only),
    since SI tends to persist for the same name across many consecutive
    bi-weekly snapshots and we don't want to count the same squeeze
    candidacy a dozen times.

Entry timing: FINRA does not publish the file on the settlement date itself
- there's a real-world dissemination lag. We don't have an exact published
lag calendar, so we approximate it as settlement_date + 8 calendar days
before entering, which is conservative based on FINRA's typical bi-weekly
publication cadence. This is documented as an approximation, not a verified
exact value.

Caveat from the handoff, repeated here: this is the highest-false-signal
setup in Group 2 (~55% expected) because high SI alone says nothing about
squeeze *timing* - we are testing "high SI + already fallen" as a proxy for
a forward squeeze, not detecting an actual squeeze trigger.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from core.backtest_engine import run_backtest
from core.cohorts import write_cohorts
from core.metrics import summarize_setup
from data_layer import finra, prices

LOOKBACK_YEARS = 5
LISTED_CLASSES = ("NNM", "NYSE", "SC", "AMEX")
MIN_DAYS_TO_COVER = 20
DRAWDOWN_LOOKBACK_DAYS = 90
MIN_DRAWDOWN = 0.25
DEDUPE_WINDOW_DAYS = 90
PUBLISH_LAG_DAYS = 8


def find_high_si_candidates(history):
    listed = history[history["marketClassCode"].isin(LISTED_CLASSES)]
    high_si = listed[listed["daysToCoverQuantity"] >= MIN_DAYS_TO_COVER].copy()
    high_si["settlementDate"] = pd.to_datetime(high_si["settlementDate"])
    high_si = high_si.sort_values(["symbolCode", "settlementDate"])

    kept = []
    last_seen = {}
    for _, row in high_si.iterrows():
        t = row["symbolCode"]
        d = row["settlementDate"]
        if t in last_seen and (d - last_seen[t]).days <= DEDUPE_WINDOW_DAYS:
            continue
        last_seen[t] = d
        kept.append({
            "ticker": t,
            "settlement_date": d,
            "days_to_cover": row["daysToCoverQuantity"],
        })
    return kept


def filter_by_drawdown(candidates):
    kept = []
    for c in candidates:
        ticker = c["ticker"]
        settlement_date = c["settlement_date"]
        start = (settlement_date - pd.Timedelta(days=DRAWDOWN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        end = (settlement_date + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        try:
            df = prices.get_history(ticker, start, end)
        except Exception:
            continue
        if df.empty:
            continue
        prior = df[df.index <= settlement_date]
        if prior.empty:
            continue
        high = prior["Close"].max()
        last_close = prior["Close"].iloc[-1]
        drawdown = last_close / high - 1
        if drawdown <= -MIN_DRAWDOWN:
            event_date = settlement_date + pd.Timedelta(days=PUBLISH_LAG_DAYS)
            kept.append({
                "ticker": ticker,
                "event_date": event_date.date().isoformat(),
                "setup_type": "s09_short_squeeze_candidate",
                "settlement_date": settlement_date.date().isoformat(),
                "days_to_cover": c["days_to_cover"],
                "drawdown_pct": round(drawdown, 4),
            })
    return kept


def main():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=365 * LOOKBACK_YEARS)

    print(f"Fetching FINRA bi-weekly short interest snapshots {start.date()}..{end.date()}...")
    history = finra.get_history(start, end)
    print(f"  {len(history)} total rows across all snapshots")
    if history.empty:
        print("No FINRA data fetched - cannot backtest.")
        return

    n_snapshots = history["actual_settlement_date"].nunique() if "actual_settlement_date" in history.columns else history["settlementDate"].nunique()
    print(f"  {n_snapshots} distinct bi-weekly snapshots covered")

    candidates = find_high_si_candidates(history)
    print(f"  {len(candidates)} ticker-events with days-to-cover >= {MIN_DAYS_TO_COVER} (post-dedupe)")

    events = filter_by_drawdown(candidates)
    print(f"  {len(events)} survive the >={int(MIN_DRAWDOWN*100)}% drawdown filter")

    if not events:
        print("No qualifying events - cannot backtest.")
        return

    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s09_short_squeeze_candidate_events.csv"), index=False)

    results = run_backtest(events, entry_offset_sessions=1)
    results.to_csv(os.path.join(results_dir, "s09_short_squeeze_candidate_results.csv"), index=False)

    summary = summarize_setup(results, "s09_short_squeeze_candidate")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s09_short_squeeze_candidate_summary.csv"), index=False)

    cohorts = write_cohorts(results, "s09_short_squeeze_candidate", results_dir)
    print(cohorts.to_string())


if __name__ == "__main__":
    main()
