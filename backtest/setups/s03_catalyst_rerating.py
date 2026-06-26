"""Setup 3: Catalyst Rerating (narrative / news catalyst proxy).

This is the closest mechanical test of the user's core thesis - "narrative moves
the market, and that is where the edge is". The proxy for "a narrative/news
catalyst just hit this stock" is a violent one-day move on abnormal volume that
is NOT an earnings release:

Trigger (event date = day T, the spike day):
  - Volume[T] > 3 * SMA50(Volume)        (abnormal participation)
  - Close[T] / Close[T-1] - 1 > +0.10    (>+10% one-session jump)
  - NO earnings within +-3 days of T      (strip out PEAD - that is a separate
    setup; here we want moves driven by something OTHER than the scheduled number)
Entry: T+1 (engine default). Question measured: after a non-earnings narrative
spike, does the move keep drifting (momentum/PEAD-like) or fade (mean-revert)?

Earnings exclusion uses SEC EDGAR submissions (8-K item 2.02 + 10-Q/10-K), which
is complete for the window - see data_layer/sec_edgar.get_earnings_dates and the
validation note. An INCOMPLETE earnings feed would silently let PEAD events
contaminate the "narrative" sample, so completeness is verified before trusting it.

PLACEBO / negative control: random NORMAL-volume, small-move days on the SAME
universe (also earnings-stripped). If random days earn a similar edge, the spike
carries no information and the "catalyst" is noise.

UNIVERSE NOTE: current S&P 500 constituents (Wikipedia). mWIG40 (Poland) from the
handoff is deliberately EXCLUDED here: there is no free, structured, verifiable
archive of Polish earnings-announcement dates, so the +-3d earnings strip cannot be
done completely for those names - including them would reintroduce exactly the PEAD
contamination this setup is designed to remove. Honest exclusion over a biased
sample (same principle as the Group 2 openFDA cap). Using *current* constituents
also imparts mild survivorship bias (names that crashed out of the index are
absent); flagged, not corrected (point-in-time membership is not freely available).
"""
import io
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import requests

from data_layer import prices, sec_edgar
from core.backtest_engine import run_backtest
from core.metrics import summarize_setup
from core.cohorts import write_cohorts

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SCAN_START = "2016-01-01"
SCAN_END = "2026-06-25"
HORIZONS = (10, 30, 60, 90)

VOL_MULT = 3.0
VOL_PERIOD = 50
PRICE_JUMP = 0.10
EARNINGS_WINDOW_DAYS = 3
DEDUP_SESSIONS = 20          # one spike per ticker per ~month (keep first of a cluster)
RANDOM_SEED = 42


def get_sp500_tickers():
    r = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    return tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()


def find_spikes(df):
    """Indices (Timestamps) of qualifying spike days in a price frame."""
    vol_sma = df["Volume"].rolling(VOL_PERIOD, min_periods=VOL_PERIOD).mean()
    ret = df["Close"] / df["Close"].shift(1) - 1
    mask = (df["Volume"] > VOL_MULT * vol_sma) & (ret > PRICE_JUMP)
    spikes = df.index[mask.fillna(False)]
    # dedup: drop spikes within DEDUP_SESSIONS of a kept one
    kept, last_pos = [], -10**9
    pos = {d: i for i, d in enumerate(df.index)}
    for d in spikes:
        if pos[d] - last_pos >= DEDUP_SESSIONS:
            kept.append((d, float(ret.loc[d]), float(df["Volume"].loc[d] / vol_sma.loc[d])))
            last_pos = pos[d]
    return kept


def normal_days(df, rng, n_sample):
    """Random earnings-free, normal-volume, small-move days for the placebo."""
    vol_sma = df["Volume"].rolling(VOL_PERIOD, min_periods=VOL_PERIOD).mean()
    ret = df["Close"] / df["Close"].shift(1) - 1
    normal = (df["Volume"].between(0.5 * vol_sma, 1.5 * vol_sma)) & (ret.abs() < 0.03)
    cand = list(df.index[normal.fillna(False)])
    if not cand:
        return []
    rng.shuffle(cand)
    return cand[:n_sample]


def build_events():
    rng = random.Random(RANDOM_SEED)
    tickers = get_sp500_tickers()
    print(f"Scanning {len(tickers)} S&P 500 tickers {SCAN_START}..{SCAN_END}")

    tickers_df = sec_edgar.get_company_tickers()
    real, placebo = [], []
    unresolved = 0

    for i, t in enumerate(tickers):
        try:
            df = prices.get_history(t, SCAN_START, SCAN_END)
        except Exception:
            continue
        if df.empty or len(df) < VOL_PERIOD + 5:
            continue

        spikes = find_spikes(df)
        if not spikes:
            continue

        cik = sec_edgar.ticker_to_cik(t, tickers_df)
        if cik is None:
            unresolved += 1
            continue
        try:
            earn = sec_edgar.get_earnings_dates(cik, start="2015-06-01", end=SCAN_END)
        except Exception:
            continue

        kept_spikes = []
        for d, r, vmult in spikes:
            if sec_edgar.near_earnings(d, earn, EARNINGS_WINDOW_DAYS):
                continue
            kept_spikes.append(d)
            real.append({
                "ticker": t,
                "event_date": d.date().isoformat(),
                "setup_type": "s03_catalyst_rerating",
                "spike_return": round(r, 4),
                "vol_x_sma50": round(vmult, 2),
            })

        # placebo: as many random normal days as this ticker contributed real spikes
        for d in normal_days(df, rng, len(kept_spikes)):
            if sec_edgar.near_earnings(d, earn, EARNINGS_WINDOW_DAYS):
                continue
            placebo.append({
                "ticker": t,
                "event_date": d.date().isoformat(),
                "setup_type": "s03_catalyst_rerating_placebo",
            })

        if (i + 1) % 50 == 0:
            print(f"  ..{i+1} tickers scanned; real spikes={len(real)} placebo={len(placebo)}")

    print(f"Unresolved CIKs (skipped): {unresolved}")
    return real, placebo


def _run_and_write(events, name, results_dir):
    pd.DataFrame(events).to_csv(os.path.join(results_dir, f"{name}_events.csv"), index=False)
    if not events:
        print(f"  {name}: no events")
        return None
    results = run_backtest(events, horizons=HORIZONS)
    results.to_csv(os.path.join(results_dir, f"{name}_results.csv"), index=False)
    summary = summarize_setup(results, name, horizons=HORIZONS)
    summary.to_csv(os.path.join(results_dir, f"{name}_summary.csv"), index=False)
    write_cohorts(results, name, results_dir, horizons=HORIZONS)
    return summary


def main():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    real, placebo = build_events()
    print(f"\nReal non-earnings spikes: {len(real)}")
    print(f"Placebo normal days:      {len(placebo)}")

    real_summary = _run_and_write(real, "s03_catalyst_rerating", results_dir)
    if real_summary is not None:
        print("\n== REAL (non-earnings +10% volume spike) ==")
        print(real_summary.to_string(index=False))

    placebo_summary = _run_and_write(placebo, "s03_catalyst_rerating_placebo", results_dir)
    if placebo_summary is not None:
        print("\n== PLACEBO (random normal days) ==")
        print(placebo_summary.to_string(index=False))


if __name__ == "__main__":
    main()
