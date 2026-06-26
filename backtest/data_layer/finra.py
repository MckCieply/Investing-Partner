"""FINRA equity short interest (bi-weekly, free, no auth).

Files are published at https://cdn.finra.org/equity/otcmarket/biweekly/shrt<YYYYMMDD>.csv
for each SEC Rule 4560 settlement date (the 15th and the last calendar day of
each month, shifted backward to the nearest day FINRA actually published on -
weekends/holidays shift the file date back, never forward). We don't have an
authoritative settlement-date calendar, so we probe backward from the 15th/
month-end by up to a few days and take the first file that exists.

Coverage caveat (FINRA's own documentation): before June 2021 this feed only
covers OTC-reported names, not exchange-listed equities. Anything before that
date is OTC-only and should not be treated as a full-market short-interest
snapshot.

There is no float-shares field in this file - only currentShortPositionQuantity,
averageDailyVolumeQuantity and the derived daysToCoverQuantity. We do not have
a free, point-in-time historical float dataset, so "short interest >20% float"
from the handoff is approximated via daysToCoverQuantity (days-to-cover), a
standard practitioner proxy for short-squeeze risk that doesn't require float
data. This substitution is documented in the setup script, not hidden here.
"""
import os
import time

import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "finra")
os.makedirs(CACHE_DIR, exist_ok=True)

BASE_URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{}.csv"
HEADERS = {"User-Agent": "Investing-Partner backtest research contact@example.com"}


def _try_fetch(date, max_back=5):
    for back in range(max_back + 1):
        d = date - pd.Timedelta(days=back)
        url = BASE_URL.format(d.strftime("%Y%m%d"))
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and len(r.content) > 1000:
            return d, r.content
    return None, None


def settlement_dates(start, end):
    """Candidate settlement dates: 15th and month-end of every month in range."""
    dates = []
    for month_start in pd.date_range(pd.Timestamp(start).to_period("M").start_time,
                                      pd.Timestamp(end), freq="MS"):
        mid = month_start.replace(day=15)
        month_end = month_start + pd.offsets.MonthEnd(0)
        for d in (mid, month_end):
            if pd.Timestamp(start) <= d <= pd.Timestamp(end):
                dates.append(d)
    return sorted(set(dates))


def get_snapshot(date):
    """One bi-weekly short-interest CSV as a DataFrame, cached to disk by actual file date used."""
    date = pd.Timestamp(date)
    cache_key = date.strftime("%Y%m%d")
    cache_path = os.path.join(CACHE_DIR, f"shrt_{cache_key}.parquet")
    miss_marker = os.path.join(CACHE_DIR, f"shrt_{cache_key}.missing")
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path)
    if os.path.exists(miss_marker):
        return pd.DataFrame()

    actual_date, content = _try_fetch(date)
    if content is None:
        open(miss_marker, "w").close()
        return pd.DataFrame()

    import io
    df = pd.read_csv(io.BytesIO(content), sep="|")
    df["actual_settlement_date"] = actual_date
    df.to_parquet(cache_path)
    return df


def get_history(start, end, sleep_between=0.2):
    """Concat all bi-weekly snapshots in [start, end]. Each row keeps its own settlementDate."""
    frames = []
    for d in settlement_dates(start, end):
        snap = get_snapshot(d)
        if not snap.empty:
            frames.append(snap)
        time.sleep(sleep_between)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
