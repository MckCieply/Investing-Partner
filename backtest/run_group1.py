"""Orchestrator: read the per-setup result CSVs already produced by setups/s*.py
and build the final Group 1 comparison table + a pass/fail verdict for Step 2.

Run the six setup scripts first (each writes results/<setup>_results.csv);
this script only aggregates - it does not re-run any network fetch.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from core.metrics import summarize_setup

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

SETUPS = [
    "s07_insider_buying",
    "s06_index_inclusion",
    "s12_merger_arb",
    "s05_spinoff",
    "s02_consolidation",
    "s14_rate_sensitivity",
]

# Verdict thresholds: a setup "passes" to Step 2 (Scout rewrite) if it clears
# all three at the T+60 horizon. Documented here so the bar is set up front,
# not picked after seeing results.
MIN_N = 25
MIN_WIN_RATE = 0.50
MIN_EDGE_VS_SPY = 0.0


def main():
    rows = []
    for setup in SETUPS:
        path = os.path.join(RESULTS_DIR, f"{setup}_results.csv")
        if not os.path.exists(path):
            print(f"WARNING: missing {path} - skipping {setup} (run its setup script first)")
            continue
        df = pd.read_csv(path)
        summary = summarize_setup(df, setup, horizons=(30, 60, 90) if setup != "s14_rate_sensitivity" else (10, 20, 30))
        rows.append(summary)

    if not rows:
        print("No setup results found in results/ - nothing to aggregate.")
        return

    combined = pd.concat(rows, ignore_index=True)
    combined.to_csv(os.path.join(RESULTS_DIR, "group1_comparison.csv"), index=False)

    print("=" * 100)
    print("GROUP 1 COMPARISON - all setups, all horizons")
    print("=" * 100)
    print(combined.to_string(index=False))

    mid_horizon = combined[combined["horizon"].isin([60, 20])]
    verdicts = []
    for setup in SETUPS:
        sub = mid_horizon[mid_horizon["setup"] == setup]
        if sub.empty:
            verdicts.append({"setup": setup, "verdict": "NO DATA"})
            continue
        r = sub.iloc[0]
        passed = (r["n"] >= MIN_N and r["win_rate"] >= MIN_WIN_RATE
                  and (r["edge_vs_spy_median"] or 0) > MIN_EDGE_VS_SPY)
        verdicts.append({
            "setup": setup, "n": r["n"], "win_rate": r["win_rate"],
            "edge_vs_spy_median": r["edge_vs_spy_median"],
            "verdict": "PASS -> Step 2" if passed else "FAIL (stays out of Scout rewrite)",
        })

    verdict_df = pd.DataFrame(verdicts)
    print("\n" + "=" * 100)
    print(f"VERDICT (bar: n>={MIN_N}, win_rate>={MIN_WIN_RATE}, median edge vs SPY>{MIN_EDGE_VS_SPY}, mid-horizon)")
    print("=" * 100)
    print(verdict_df.to_string(index=False))
    verdict_df.to_csv(os.path.join(RESULTS_DIR, "group1_verdict.csv"), index=False)


if __name__ == "__main__":
    main()
