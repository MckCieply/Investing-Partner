"""Setup 7: Insider Buying Cluster after Drawdown.

Trigger (per handoff): 3+ distinct insiders buying the same ticker within a
30-day rolling window, where the stock is already down >25% from its recent
high. Event date = the filing date of the 3rd (cluster-completing) insider
purchase, so the backtest never assumes knowledge before the cluster was
actually visible (no look-ahead).

Requires network access to openinsider.com - run with the sandbox network
restriction lifted (dangerouslyDisableSandbox) or this will time out.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from data_layer import openinsider, prices
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup

LOOKBACK_DAYS = 1095          # default ~3 years; override with --years on the CLI
CLUSTER_WINDOW_DAYS = 30
MIN_INSIDERS = 3
DRAWDOWN_LOOKBACK_DAYS = 90
MIN_DRAWDOWN = 0.25


def find_clusters(purchases_df, min_insiders=MIN_INSIDERS, window_days=CLUSTER_WINDOW_DAYS):
    """For each ticker, find the earliest date a rolling `window_days` window
    accumulates >= min_insiders distinct insiders. Returns one event per ticker
    (the first qualifying cluster only, to avoid double-counting overlapping windows).
    """
    clusters = []
    for ticker, g in purchases_df.groupby("ticker"):
        g = g.sort_values("trade_date")
        dates = g["trade_date"].tolist()
        insiders = g["insider_name"].tolist()

        for i in range(len(dates)):
            window_start = dates[i] - pd.Timedelta(days=window_days)
            in_window = [(d, ins) for d, ins in zip(dates, insiders) if window_start < d <= dates[i]]
            distinct_insiders = {ins for _, ins in in_window}
            if len(distinct_insiders) >= min_insiders:
                clusters.append({
                    "ticker": ticker,
                    "event_date": dates[i].date().isoformat(),
                    "n_insiders": len(distinct_insiders),
                })
                break  # first qualifying cluster for this ticker; stop to avoid overlap dupes
    return clusters


def filter_by_drawdown(clusters, lookback_days=DRAWDOWN_LOOKBACK_DAYS, min_drawdown=MIN_DRAWDOWN):
    """Keep only clusters where price was down >= min_drawdown from its
    trailing `lookback_days` high as of the cluster date.
    """
    kept = []
    for c in clusters:
        event_date = pd.Timestamp(c["event_date"])
        start = (event_date - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = (event_date + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        try:
            df = prices.get_history(c["ticker"], start, end)
        except Exception:
            continue
        if df.empty:
            continue
        prior = df[df.index <= event_date]
        if prior.empty:
            continue
        high = prior["Close"].max()
        last_close = prior["Close"].iloc[-1]
        drawdown = last_close / high - 1
        if drawdown <= -min_drawdown:
            c["drawdown_pct"] = round(drawdown, 4)
            c["setup_type"] = "s07_insider_buying"
            kept.append(c)
    return kept


def build_events(lookback_days, max_pages):
    print(f"Fetching OpenInsider purchase filings, last {lookback_days} days...")
    start = (pd.Timestamp.now() - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    purchases = openinsider.fetch_purchases(start, max_pages=max_pages, page_size=500)
    print(f"  {len(purchases)} purchase filings fetched")

    clusters = find_clusters(purchases)
    print(f"  {len(clusters)} tickers with a 3+-insider/30-day cluster")

    events = filter_by_drawdown(clusters)
    print(f"  {len(events)} clusters survive the >25% drawdown filter")
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=float, default=3.0,
                         help="lookback window in years (default 3, matching the original run)")
    parser.add_argument("--max-pages", type=int, default=80,
                         help="safety cap on OpenInsider screener pages to paginate through")
    parser.add_argument("--suffix", default=None,
                         help="output filename suffix, e.g. '_5y' (default: derived from --years)")
    args = parser.parse_args()

    lookback_days = round(args.years * 365)
    suffix = args.suffix if args.suffix is not None else (
        "" if args.years == 3.0 else f"_{args.years:g}y")

    events = build_events(lookback_days, args.max_pages)
    if not events:
        print("No qualifying events found - cannot backtest this setup with current data.")
        return

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    pd.DataFrame(events).to_csv(
        os.path.join(results_dir, f"s07_insider_buying_events{suffix}.csv"), index=False)

    results = run_backtest(events)
    results.to_csv(
        os.path.join(results_dir, f"s07_insider_buying_results{suffix}.csv"), index=False)

    summary = summarize_setup(results, "s07_insider_buying")
    print(summary.to_string())
    summary.to_csv(
        os.path.join(results_dir, f"s07_insider_buying_summary{suffix}.csv"), index=False)


if __name__ == "__main__":
    main()
