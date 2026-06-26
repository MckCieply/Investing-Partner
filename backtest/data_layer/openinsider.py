"""OpenInsider scraper: raw Form-4 purchase filings, for cluster-buy detection.

openinsider.com is not on this environment's default network allowlist - calls
through this module need the sandbox network restriction lifted by the caller
(e.g. Bash/PowerShell `dangerouslyDisableSandbox: true`) or they will time out.

Cluster detection (3+ distinct insiders buying the same ticker within a rolling
window) and any drawdown pre-filter belong in the setup script, not here - this
module only fetches and normalizes raw per-filing purchase records.
"""
import hashlib
import io
import os
import time
from urllib.parse import quote

import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

PAGE_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "openinsider_pages")
os.makedirs(PAGE_CACHE_DIR, exist_ok=True)

BASE_URL = "http://openinsider.com/screener"
HEADERS = {"User-Agent": "Mozilla/5.0 (backtest research script)"}

# OpenInsider's screener silently caps total rows served per query at ~4500
# (9 pages x cnt=500): beyond that, requesting further pages just re-serves
# the last page's content instead of erroring or returning fewer rows. A
# relative "fd=<days>" filter does NOT avoid this - it still only surfaces
# the newest ~4500 matching rows. The only way to reach further back is an
# explicit fd=-1 + fdr=MM/DD/YYYY+-+MM/DD/YYYY date-range query, and even
# that range is subject to the same per-query cap, so wide ranges must be
# recursively bisected until each sub-range's row count is provably below it.
CAP_PAGES = 9

COLUMN_MAP = {
    "Filing\xa0Date": "filing_date",
    "Trade\xa0Date": "trade_date",
    "Ticker": "ticker",
    "Company\xa0Name": "company_name",
    "Insider\xa0Name": "insider_name",
    "Title": "title",
    "Trade\xa0Type": "trade_type",
    "Price": "price",
    "Qty": "qty",
    "Owned": "owned",
    "ΔOwn": "delta_own",
    "Value": "value",
}


def _parse_money(s):
    if pd.isna(s):
        return None
    return float(str(s).replace("$", "").replace(",", "").replace("+", ""))


def _page_cache_path(start_ts, end_ts, page, cnt, min_value_k):
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    key = f"{start_ts.date()}_{end_ts.date()}_{page}_{cnt}_{min_value_k}_{today}"
    h = hashlib.sha1(key.encode()).hexdigest()[:20]
    return os.path.join(PAGE_CACHE_DIR, f"{h}.html")


def _build_url(start_ts, end_ts, page, cnt, min_value_k):
    fdr = quote(start_ts.strftime("%m/%d/%Y")) + "+-+" + quote(end_ts.strftime("%m/%d/%Y"))
    query = (
        f"s=&o=&pl=&ph=&ll=&lh=&fd=-1&fdr={fdr}&td=0&tdr=&fdlyl=&fdlyh=&daysago="
        f"&xp=1&vl={min_value_k}&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0"
        f"&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt={cnt}&page={page}"
    )
    return f"{BASE_URL}?{query}"


def _fetch_page(start_ts, end_ts, page, cnt, min_value_k):
    cache_path = _page_cache_path(start_ts, end_ts, page, cnt, min_value_k)
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()

    url = _build_url(start_ts, end_ts, page, cnt, min_value_k)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            r.raise_for_status()
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(r.text)
            return r.text
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def _parse_table(html):
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return None
    data_tables = [t for t in tables if "Filing\xa0Date" in t.columns]
    if not data_tables:
        return None
    t = data_tables[0].rename(columns=COLUMN_MAP)
    if t.empty:
        return None
    t["filing_date"] = pd.to_datetime(t["filing_date"])
    t["trade_date"] = pd.to_datetime(t["trade_date"])
    return t


def _fetch_range(start_ts, end_ts, min_value_k, page_size, sleep_between):
    """Fetch every filing in [start_ts, end_ts] this single query can see.

    Returns (frames, truncated) - truncated=True means CAP_PAGES full pages
    were consumed without finding a short (end-of-data) page, i.e. this range
    likely holds more rows than the screener will ever serve for one query
    and must be bisected by the caller.
    """
    frames = []
    for page in range(1, CAP_PAGES + 1):
        html = _fetch_page(start_ts, end_ts, page, page_size, min_value_k)
        t = _parse_table(html)
        if t is None:
            return frames, False
        frames.append(t)
        if len(t) < page_size:
            return frames, False
        if page < CAP_PAGES:
            time.sleep(sleep_between)
    return frames, True


def _fetch_range_recursive(start_ts, end_ts, min_value_k, page_size, sleep_between, depth=0):
    frames, truncated = _fetch_range(start_ts, end_ts, min_value_k, page_size, sleep_between)
    if not truncated or (end_ts - start_ts).days < 2 or depth > 12:
        return frames
    mid = start_ts + (end_ts - start_ts) / 2
    left = _fetch_range_recursive(start_ts, mid, min_value_k, page_size, sleep_between, depth + 1)
    right = _fetch_range_recursive(mid + pd.Timedelta(seconds=1), end_ts, min_value_k, page_size, sleep_between, depth + 1)
    return left + right


def fetch_purchases(start_date, end_date=None, min_value_k=25, page_size=500, max_pages=80, sleep_between=1.0):
    """All individual purchase filings with filing_date in [start_date, end_date].

    Uses an explicit fd=-1/fdr=<range> query (see CAP_PAGES note above) and
    recursively bisects the date range whenever a sub-range looks like it hit
    the screener's per-query row cap, so the full window gets covered however
    many sub-queries that takes. `max_pages` is unused but kept for backward
    compatibility with existing callers.
    """
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) if end_date else pd.Timestamp.now()

    frames = _fetch_range_recursive(start_ts, end_ts, min_value_k, page_size, sleep_between)
    if not frames:
        return pd.DataFrame(columns=list(COLUMN_MAP.values()))

    df = pd.concat(frames, ignore_index=True)
    df = df[(df["filing_date"] >= start_ts) & (df["filing_date"] <= end_ts)]
    df = df[df["trade_type"].str.startswith("P - Purchase", na=False)]
    df["price"] = df["price"].map(_parse_money)
    df["value"] = df["value"].map(_parse_money)
    df = df.drop_duplicates(subset=["ticker", "insider_name", "trade_date", "qty"])
    return df[["filing_date", "trade_date", "ticker", "company_name", "insider_name",
               "title", "price", "qty", "value"]].reset_index(drop=True)
