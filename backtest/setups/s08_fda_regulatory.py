"""Setup 8: Regulatory Catalyst - FDA decision (PDUFA-equivalent), approvals only.

Trigger (per Group 2 handoff): a scheduled FDA decision date for a biotech/
pharma ticker. Simplification: FDA only, ignore government-contract catalysts.

CRITICAL DATA LIMITATION - read before trusting any verdict here:
The only free, complete, machine-readable historical source we could find is
openFDA's bulk Drugs@FDA download (download.open.fda.gov). That dataset's
`submissions[].submission_status` field only ever takes the values AP
(approved) or TA (tentatively approved) - verified directly against all
~187k submission records in the bulk file. There are NO rejection / Complete
Response Letter records in it at all. This is a hard structural limit of
the source, not a filtering choice: a free dataset of FDA *rejections* with
per-ticker dates does not appear to exist (BioPharmaCatalyst/PDUFA.bio gate
historical CSV exports behind paid tiers).

Consequence: every event below is a *positive* FDA decision. The "binary
approval/rejection" reaction the handoff asks us to look at can only be
measured on the approval side. Any edge measured here is upward-biased by
construction (the rejection tail, which is presumably the larger downside
mover, is structurally absent) and CANNOT be used to confirm the regulatory-
catalyst thesis. We still run the full backtest on the approval-only sample
because it's real data and informative on its own terms, but the verdict
below is capped at LOW CONFIDENCE / NOT ELIGIBLE FOR PASS regardless of the
metrics, and that cap is documented, not silently applied.

A second, smaller limitation: Drugs@FDA has no ticker field, only a sponsor
company name (e.g. "PFIZER", "MODERNA, INC"). We resolve sponsor name ->
ticker via exact match against SEC's company_tickers.json after normalizing
both sides (uppercase, strip Inc/Corp/Ltd/LLC/Co suffixes). This only
matches sponsors that file with the SEC under (close to) the same legal name
as in Drugs@FDA, so it under-counts small biotechs that submit via a
differently-named subsidiary. That's a sample-size loss, not a bias in the
returns themselves, but it does mean low n is expected and is itself a
signal about this setup's tractability with free data.

A third limitation: Drugs@FDA's submission_status_date is the actual
decision date, not the originally-scheduled PDUFA target date (which the
market would have known about and priced in ahead of time, the whole reason
the mandate calls for entry T-7 "before the catalyst"). For the small
fraction of decisions delayed past their PDUFA date this introduces some
look-ahead-adjacent slack, but the *decision* date itself is never knowable
in advance from this source, only roughly inferable, so the T-7 entry here
is an approximation, not a guarantee of pre-event entry.
"""
import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import requests

from core.backtest_engine import run_backtest
from core.cohorts import write_cohorts
from core.metrics import summarize_setup
from data_layer import prices, sec_edgar

BULK_URL = "https://download.open.fda.gov/drug/drugsfda/drug-drugsfda-0001-of-0001.json.zip"
LOOKBACK_YEARS = 5
ENTRY_OFFSET_SESSIONS = -7  # "T-7" ahead of the decision date
SUFFIX_RE = re.compile(r"[,\.]|\b(INC|CORP|CORPORATION|LTD|LLC|CO|COMPANY|PLC|LP|HOLDINGS?)\b")


def _normalize_name(name):
    name = SUFFIX_RE.sub(" ", str(name).upper())
    return re.sub(r"\s+", " ", name).strip()


def fetch_bulk_drugsfda():
    print("Downloading openFDA Drugs@FDA bulk file...")
    r = requests.get(BULK_URL, timeout=180)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    import json
    data = json.loads(z.read(z.namelist()[0]))
    return data["results"]


def extract_approval_events(records, cutoff_date):
    """One event per (application_number) = its earliest ORIG NDA/BLA approval
    submission_status_date on/after cutoff_date. Only ORIG (not SUPPL, which is
    a label/manufacturing change, not a tradeable new-drug catalyst) and only
    NDA/BLA (ANDA = generic, no catalyst)."""
    events = []
    for rec in records:
        appnum = rec.get("application_number", "")
        if not (appnum.startswith("NDA") or appnum.startswith("BLA")):
            continue
        sponsor = rec.get("sponsor_name")
        if not sponsor:
            continue
        orig_approvals = [
            s for s in rec.get("submissions", [])
            if s.get("submission_type") == "ORIG" and s.get("submission_status") in ("AP", "TA")
            and s.get("submission_status_date")
        ]
        if not orig_approvals:
            continue
        dates = sorted(pd.Timestamp(s["submission_status_date"]) for s in orig_approvals)
        decision_date = dates[0]
        if decision_date < cutoff_date:
            continue
        events.append({
            "application_number": appnum,
            "sponsor_name": sponsor,
            "decision_date": decision_date.date().isoformat(),
        })
    return events


def resolve_tickers(events):
    tickers_df = sec_edgar.get_company_tickers()
    tickers_df["norm_title"] = tickers_df["title"].map(_normalize_name)
    name_to_ticker = dict(zip(tickers_df["norm_title"], tickers_df["ticker"]))

    resolved = []
    for ev in events:
        norm = _normalize_name(ev["sponsor_name"])
        ticker = name_to_ticker.get(norm)
        if not ticker:
            continue
        resolved.append({
            "ticker": ticker,
            "event_date": ev["decision_date"],
            "setup_type": "s08_fda_regulatory",
            "sponsor_name": ev["sponsor_name"],
            "application_number": ev["application_number"],
        })
    return resolved


def decision_day_reaction(events):
    """Binary single-day reaction: close(decision_date - 1 session) -> close(decision_date session)."""
    rows = []
    for ev in events:
        ticker = ev["ticker"]
        decision_date = pd.Timestamp(ev["event_date"])
        start = (decision_date - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
        end = (decision_date + pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        try:
            df = prices.get_history(ticker, start, end)
        except Exception:
            continue
        if df.empty:
            continue
        on_or_after = df.index[df.index >= decision_date]
        if len(on_or_after) == 0:
            continue
        decision_pos = df.index.get_loc(on_or_after[0])
        if decision_pos < 1:
            continue
        prior_close = float(df.iloc[decision_pos - 1]["Close"])
        decision_close = float(df.iloc[decision_pos]["Close"])
        rows.append({
            "ticker": ticker, "event_date": ev["event_date"],
            "decision_day_return": decision_close / prior_close - 1,
        })
    return pd.DataFrame(rows)


def main():
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * LOOKBACK_YEARS)

    records = fetch_bulk_drugsfda()
    print(f"  {len(records)} total Drugs@FDA application records")

    approval_events = extract_approval_events(records, cutoff)
    print(f"  {len(approval_events)} NDA/BLA original approvals in last {LOOKBACK_YEARS}y")

    events = resolve_tickers(approval_events)
    print(f"  {len(events)} resolved to a public ticker via SEC company_tickers")

    if not events:
        print("No resolvable events - cannot backtest.")
        return

    pd.DataFrame(events).to_csv(os.path.join(results_dir, "s08_fda_regulatory_events.csv"), index=False)

    results = run_backtest(events, entry_offset_sessions=ENTRY_OFFSET_SESSIONS)
    results.to_csv(os.path.join(results_dir, "s08_fda_regulatory_results.csv"), index=False)

    summary = summarize_setup(results, "s08_fda_regulatory")
    print(summary.to_string())
    summary.to_csv(os.path.join(results_dir, "s08_fda_regulatory_summary.csv"), index=False)

    cohorts = write_cohorts(results, "s08_fda_regulatory", results_dir)
    print(cohorts.to_string())

    reaction = decision_day_reaction(events)
    reaction.to_csv(os.path.join(results_dir, "s08_fda_regulatory_decision_day_reaction.csv"), index=False)
    if not reaction.empty:
        print("\nDecision-day reaction distribution (close-to-close, approvals only):")
        print(reaction["decision_day_return"].describe().to_string())


if __name__ == "__main__":
    main()
