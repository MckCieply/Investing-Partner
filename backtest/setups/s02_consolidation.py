"""Setup 2: Consolidation / Base.

Trigger: RSI(14) stays in the 40-55 band for >= N consecutive sessions while
price stays within +-5% of the window's mean close ("basing"). Event date =
the last session of the qualifying window (the point a trader would actually
notice the base and watch for a breakout).

Pure technical, no fundamental/news data needed - scans a sample of S&P 500
tickers (the Wikipedia constituent list, same source as Setup 6) over the
lookback window using yfinance only.
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import requests

from data_layer import prices
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
LOOKBACK_YEARS = 5
CONSOLIDATION_MIN_DAYS = 15
RSI_LOW, RSI_HIGH = 40, 55
RANGE_PCT = 0.05
SAMPLE_TICKERS = 80          # scanning all 500 over 5y is slow; sample for tractability
MAX_EVENTS = 60


def get_sp500_tickers(n=SAMPLE_TICKERS):
    r = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    symbols = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
    return symbols[:n]


def find_consolidations(ticker, start, end, min_days=CONSOLIDATION_MIN_DAYS):
    df = prices.get_history(ticker, start, end)
    if df.empty or len(df) < min_days + 20:
        return []

    rsi = prices.rsi(df, period=14)
    in_band = rsi.between(RSI_LOW, RSI_HIGH)

    events = []
    i = 0
    n = len(df)
    while i < n:
        if not in_band.iloc[i]:
            i += 1
            continue
        j = i
        while j < n and in_band.iloc[j]:
            j += 1
        window = df.iloc[i:j]
        if len(window) >= min_days:
            mean_close = window["Close"].mean()
            within_range = ((window["Close"] - mean_close).abs() / mean_close <= RANGE_PCT).all()
            if within_range:
                events.append({
                    "ticker": ticker,
                    "event_date": df.index[j - 1].date().isoformat(),
                    "setup_type": "s02_consolidation",
                    "consolidation_days": len(window),
                })
        i = j
    return events


def build_events():
    end = pd.Timestamp.now()
    start = (end - pd.Timedelta(days=365 * LOOKBACK_YEARS)).strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    tickers = get_sp500_tickers()
    print(f"Scanning {len(tickers)} tickers for consolidation bases...")

    events = []
    for t in tickers:
        try:
            events.extend(find_consolidations(t, start, end_str))
        except Exception as e:
            print(f"  {t}: skipped ({e})")

    if len(events) > MAX_EVENTS:
        print(f"  {len(events)} events found across the full sample; "
              f"capping to the {MAX_EVENTS} most recent (dropping {len(events) - MAX_EVENTS} older ones).")
        events = sorted(events, key=lambda e: e["event_date"], reverse=True)[:MAX_EVENTS]
    return events


def main():
    events = build_events()
    print(f"  {len(events)} consolidation events found")

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s02_consolidation_events.csv"), index=False)

    if not events:
        print("No events - nothing to backtest.")
        return

    results = run_backtest(events)
    results.to_csv(os.path.join(results_dir, "s02_consolidation_results.csv"), index=False)

    summary = summarize_setup(results, "s02_consolidation")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s02_consolidation_summary.csv"), index=False)


if __name__ == "__main__":
    main()
