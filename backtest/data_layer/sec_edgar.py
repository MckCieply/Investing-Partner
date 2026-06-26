"""SEC EDGAR access: full-text search for 8-K events (spinoffs, mergers) and
CIK<->ticker resolution. www.sec.gov / data.sec.gov / efts.sec.gov are on the
default network allowlist, no sandbox override needed.

SEC's full text search only indexes filings from 2001 onward (fine for our
4-5 year backtest window) and returns ~10 results per page via the `from` offset.
"""
import os
import time

import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Investing-Partner backtest research contact@example.com"}
FTS_URL = "https://efts.sec.gov/LATEST/search-index"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def get_company_tickers():
    """CIK (int, no leading zeros) -> ticker map, cached to disk.

    SEC serves this as a dict-of-dicts keyed "0","1",... (not a JSON array),
    so it must be loaded with orient="index", not the default records orient.
    """
    path = os.path.join(CACHE_DIR, "company_tickers.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 86400 * 7:
        return pd.read_json(path, orient="records")
    r = requests.get(TICKERS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame.from_dict(data, orient="index")
    df.to_json(path, orient="records")
    return df


def cik_to_ticker(cik, tickers_df=None):
    tickers_df = tickers_df if tickers_df is not None else get_company_tickers()
    cik = int(cik)
    match = tickers_df[tickers_df["cik_str"] == cik]
    if match.empty:
        return None
    return match.iloc[0]["ticker"]


def full_text_search(query, forms="8-K", start_date=None, end_date=None, items=None,
                      max_results=200, page_size=10, sleep_between=0.3):
    """Raw EDGAR full-text-search hits for a query string within a form type/date range.

    Returns the list of `_source` dicts (ciks, file_date, adsh, display_names, items, ...).

    The `from` offset is into the API's own page size (100 per request, not
    configurable via a request param), so the loop must advance by the
    actual number of hits returned each call - NOT by `page_size`, which is
    a different, much smaller number of unrelated origin (kept only for the
    "fewer than a full page" stop condition). Advancing by `page_size`
    instead of the real page size caused massive overlapping re-fetches
    (10x+ duplicate hits) and eventually a 500 once `from` ran past the
    total hit count on a small result set.
    """
    params = {"q": query, "forms": forms}
    if start_date:
        params["startdt"] = pd.Timestamp(start_date).strftime("%Y-%m-%d")
    if end_date:
        params["enddt"] = pd.Timestamp(end_date).strftime("%Y-%m-%d")

    results = []
    offset = 0
    while offset < max_results:
        params["from"] = offset
        for attempt in range(4):
            r = requests.get(FTS_URL, params=params, headers=HEADERS, timeout=30)
            if r.status_code != 500:
                break
            time.sleep(2 * (attempt + 1))
        r.raise_for_status()
        data = r.json()
        total = data.get("hits", {}).get("total", {}).get("value", 0)
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h["_source"]
            if items and not any(i in src.get("items", []) for i in items):
                continue
            results.append(src)
        offset += len(hits)
        if offset >= total or len(hits) < page_size:
            break
        time.sleep(sleep_between)

    return results


def ticker_to_cik(ticker, tickers_df=None):
    tickers_df = tickers_df if tickers_df is not None else get_company_tickers()
    m = tickers_df[tickers_df["ticker"].str.upper() == ticker.upper()]
    if m.empty:
        return None
    return int(m.iloc[0]["cik_str"])


def get_earnings_dates(cik, start=None, end=None, sleep_between=0.15):
    """All earnings-announcement filing dates for one CIK, as a sorted DatetimeIndex.

    "Earnings announcement" = an 8-K carrying item 2.02 (Results of Operations and
    Financial Condition) OR a periodic report (10-Q / 10-K). The 8-K 2.02 filing
    date is the press-release date that actually moves the stock; the 10-Q/10-K is
    included as a backstop for issuers that report results inside the periodic
    filing itself.

    Pulls the `recent` block plus every older shard whose date range overlaps the
    requested window, so coverage is COMPLETE for the window (the OpenInsider
    completeness lesson: never trust a partial feed). data.sec.gov is on the
    default allowlist; results cached per CIK to disk.
    """
    cik_padded = str(int(cik)).zfill(10)
    cache_file = os.path.join(CACHE_DIR, f"earnings_{cik_padded}.parquet")
    if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < 86400 * 14:
        s = pd.read_parquet(cache_file)["date"]
        dates = pd.to_datetime(s)
    else:
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        time.sleep(sleep_between)  # SEC fair-access: stay well under 10 req/s
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()

        blocks = [data["filings"]["recent"]]
        for f in data["filings"].get("files", []):
            # older shard: fetch only if it could overlap the requested window
            if start and f.get("filingTo") and f["filingTo"] < pd.Timestamp(start).strftime("%Y-%m-%d"):
                continue
            time.sleep(sleep_between)
            rr = requests.get(f"https://data.sec.gov/submissions/{f['name']}", headers=HEADERS, timeout=30)
            if rr.status_code == 200:
                blocks.append(rr.json())

        rows = []
        for b in blocks:
            forms = b.get("form", [])
            fdates = b.get("filingDate", [])
            items = b.get("items", [""] * len(forms))
            for form, fdate, item in zip(forms, fdates, items):
                is_earn_8k = form == "8-K" and "2.02" in (item or "")
                is_periodic = form in ("10-Q", "10-K", "10-Q/A", "10-K/A")
                if is_earn_8k or is_periodic:
                    rows.append(fdate)
        dates = pd.to_datetime(pd.Series(sorted(set(rows))))
        pd.DataFrame({"date": dates}).to_parquet(cache_file)

    if start is not None:
        dates = dates[dates >= pd.Timestamp(start)]
    if end is not None:
        dates = dates[dates <= pd.Timestamp(end)]
    return pd.DatetimeIndex(sorted(dates))


def near_earnings(spike_date, earnings_index, window_days=3):
    """True if any earnings date falls within +-window_days of spike_date."""
    spike = pd.Timestamp(spike_date)
    if len(earnings_index) == 0:
        return False
    deltas = (earnings_index - spike).days
    return bool(((deltas >= -window_days) & (deltas <= window_days)).any())


def hits_to_events(hits, tickers_df=None, setup_type="unknown"):
    """Normalize raw full_text_search hits into {ticker, event_date, setup_type, adsh}."""
    tickers_df = tickers_df if tickers_df is not None else get_company_tickers()
    events = []
    for h in hits:
        ciks = h.get("ciks") or []
        if not ciks:
            continue
        ticker = cik_to_ticker(ciks[0], tickers_df)
        if not ticker:
            continue
        events.append({
            "ticker": ticker,
            "event_date": h.get("file_date"),
            "setup_type": setup_type,
            "adsh": h.get("adsh"),
            "company_name": (h.get("display_names") or [None])[0],
        })
    return events
