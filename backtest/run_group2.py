"""Orchestrator: read the per-setup result/cohort CSVs already produced by
setups/s*.py and build the final Group 2 comparison table + verdict.

Run the five setup scripts first; this script only aggregates - it does not
re-run any network fetch.

Group 2 uses a STRICTER bar than Group 1 (see handoff "Lekcja 2"): testing
five more hypotheses on the same market data raises the multiple-testing risk
of a false positive slipping through, so the bar is raised to compensate.
A setup that "almost passes" does not pass - the threshold is a threshold.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from core.cohorts import positive_cohort_count
from core.metrics import summarize_setup

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

SETUPS = [
    "s08_fda_regulatory",
    "s11_buyback_announcement",
    "s09_short_squeeze_candidate",
    "s20_uplisting",
    "s21_lockup_expiry",
]

# Setups capped at NOT ELIGIBLE regardless of metrics, due to a structural
# free-data limitation documented in their own setup script (not a metrics
# failure - a sourcing failure). s08: openFDA's bulk Drugs@FDA feed contains
# zero rejection/CRL records, so any measured edge is upward-biased by
# construction and cannot confirm or deny the regulatory-catalyst thesis.
DATA_CAPPED = {
    "s08_fda_regulatory": "openFDA Drugs@FDA has no rejection/CRL records - "
                           "approval-only sample, structurally biased upward, not a fair test",
}

MIN_N = 40
MIN_WIN_RATE = 0.57
MIN_EDGE_VS_SPY_T90 = 0.05
MIN_POSITIVE_COHORTS = 3
TOTAL_COHORT_YEARS = 5


def load_cohorts(setup):
    path = os.path.join(RESULTS_DIR, f"{setup}_yearly_cohorts.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def main():
    rows = []
    verdicts = []

    for setup in SETUPS:
        results_path = os.path.join(RESULTS_DIR, f"{setup}_results.csv")
        if not os.path.exists(results_path):
            print(f"WARNING: missing {results_path} - skipping {setup} (run its setup script first)")
            verdicts.append({"setup": setup, "verdict": "NO DATA"})
            continue

        df = pd.read_csv(results_path)
        summary = summarize_setup(df, setup)
        rows.append(summary)

        cohorts = load_cohorts(setup)
        n_positive_cohorts = (positive_cohort_count(cohorts, 90)
                              if not cohorts.empty else 0)
        n_total_cohorts = (cohorts[cohorts["horizon"] == 90]["year"].nunique()
                           if not cohorts.empty else 0)

        t90 = summary[summary["horizon"] == 90]
        if t90.empty or t90["n"].iloc[0] == 0:
            verdicts.append({"setup": setup, "verdict": "NO DATA AT T+90"})
            continue
        r = t90.iloc[0]

        n_ok = r["n"] >= MIN_N
        win_ok = (r["win_rate"] or 0) >= MIN_WIN_RATE
        edge_ok = (r["edge_vs_spy_median"] or -1) > MIN_EDGE_VS_SPY_T90
        cohort_ok = n_positive_cohorts >= MIN_POSITIVE_COHORTS

        data_capped = setup in DATA_CAPPED
        passed = n_ok and win_ok and edge_ok and cohort_ok and not data_capped

        if data_capped:
            verdict = f"NOT ELIGIBLE (data-capped: {DATA_CAPPED[setup]})"
        elif not n_ok:
            verdict = f"LOW CONFIDENCE (n={r['n']} < {MIN_N})"
        elif passed:
            verdict = "PASS -> validate like Setup 7"
        else:
            verdict = "FAIL"

        verdicts.append({
            "setup": setup,
            "n_t90": r["n"],
            "win_rate_t90": r["win_rate"],
            "median_edge_vs_spy_t90": r["edge_vs_spy_median"],
            "positive_cohorts_t90": f"{n_positive_cohorts}/{n_total_cohorts}",
            "n_ok": n_ok, "win_ok": win_ok, "edge_ok": edge_ok, "cohort_ok": cohort_ok,
            "verdict": verdict,
        })

    if not rows:
        print("No setup results found in results/ - nothing to aggregate.")
        return

    combined = pd.concat(rows, ignore_index=True)
    combined.to_csv(os.path.join(RESULTS_DIR, "group2_comparison.csv"), index=False)

    print("=" * 110)
    print("GROUP 2 COMPARISON - all setups, all horizons")
    print("=" * 110)
    print(combined.to_string(index=False))

    verdict_df = pd.DataFrame(verdicts)
    print("\n" + "=" * 110)
    print(f"VERDICT (stricter bar: n>={MIN_N}, win_rate>={MIN_WIN_RATE}, "
          f"median edge vs SPY T+90>{MIN_EDGE_VS_SPY_T90}, "
          f">={MIN_POSITIVE_COHORTS}/5 positive yearly cohorts at T+90)")
    print("=" * 110)
    print(verdict_df.to_string(index=False))
    verdict_df.to_csv(os.path.join(RESULTS_DIR, "group2_verdict.csv"), index=False)


if __name__ == "__main__":
    main()
