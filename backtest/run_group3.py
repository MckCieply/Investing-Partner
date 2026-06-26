"""Orchestrator: aggregate Group 3 (narrative) setup results into the final
comparison table + verdict, applying the STRICTEST bar of the project plus a
mandatory placebo/negative-control comparison.

Run the setup scripts first (setups/s04_sector_rebound.py,
setups/s03_catalyst_rerating.py); this script only reads their CSV output.

Strictest bar (handoff): testing the 12th-16th hypothesis on the same data, so the
multiple-testing false-positive risk is highest here.
  - median edge vs SPY at T+90 > +0.07
  - win rate > 0.58
  - positive median edge in >= 4 of 5 yearly cohorts at T+90
  - n >= 50
  - placebo edge at T+90 clearly weaker than the real edge
  - (edge is already net of round-trip costs in the engine)
A setup must clear ALL of them. "Almost" does not pass.
"""
import os

import pandas as pd

from core.cohorts import positive_cohort_count

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# (real_setup, placebo_setup)
PAIRS = [
    ("s04_sector_rebound", "s04_sector_rebound_placebo"),
    ("s03_catalyst_rerating", "s03_catalyst_rerating_placebo"),
]

# Setups not run because no bias-free mechanical test could be constructed.
# See results/group3_data_validation_notes.md (Setup 10).
UNTESTABLE = {
    "s10_geopolitical_arb": "no bias-free mechanical test constructible - beneficiary "
                            "mapping can't be frozen blind to outcomes; effective-date "
                            "entry is maximally stale (see validation notes)",
}

VERDICT_HORIZON = 90
MIN_N = 50
MIN_WIN_RATE = 0.58
MIN_EDGE_VS_SPY = 0.07
# Handoff bar is ">=4 of 5" yearly cohorts = 80% must be positive. Express as a
# ratio so it stays just as strict when more than 5 cohort-years are available
# (e.g. a 10-year scan): a count of "4 positive" out of 11 is NOT a pass.
MIN_POSITIVE_COHORT_RATIO = 0.80
PLACEBO_MARGIN = 0.02  # real edge must beat placebo edge by at least this much


def _summary_row(setup, horizon):
    path = os.path.join(RESULTS_DIR, f"{setup}_summary.csv")
    if not os.path.exists(path):
        return None
    s = pd.read_csv(path)
    r = s[s["horizon"] == horizon]
    return r.iloc[0] if not r.empty else None


def _cohorts(setup):
    path = os.path.join(RESULTS_DIR, f"{setup}_yearly_cohorts.csv")
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def main():
    comparison_rows = []
    verdicts = []

    for real, placebo in PAIRS:
        rr = _summary_row(real, VERDICT_HORIZON)
        pr = _summary_row(placebo, VERDICT_HORIZON)
        if rr is None:
            verdicts.append({"setup": real, "verdict": "NO DATA (run setup script first)"})
            continue

        coh = _cohorts(real)
        n_pos = positive_cohort_count(coh, VERDICT_HORIZON) if not coh.empty else 0
        n_years = (coh[coh["horizon"] == VERDICT_HORIZON]["year"].nunique()
                   if not coh.empty else 0)

        real_edge = rr.get("edge_vs_spy_median")
        placebo_edge = pr.get("edge_vs_spy_median") if pr is not None else None

        comparison_rows.append({
            "setup": real,
            "n_t90": int(rr["n"]),
            "win_rate_t90": rr["win_rate"],
            "median_return_t90": rr["median_return"],
            "real_edge_vs_spy_t90": real_edge,
            "placebo_edge_vs_spy_t90": placebo_edge,
            "real_minus_placebo": (round(real_edge - placebo_edge, 4)
                                   if real_edge is not None and placebo_edge is not None else None),
            "positive_cohorts_t90": f"{n_pos}/{n_years}",
        })

        n_ok = rr["n"] >= MIN_N
        win_ok = (rr["win_rate"] or 0) >= MIN_WIN_RATE
        edge_ok = (real_edge or -1) > MIN_EDGE_VS_SPY
        cohort_ok = n_years >= 5 and (n_pos / n_years) >= MIN_POSITIVE_COHORT_RATIO
        placebo_ok = (real_edge is not None and placebo_edge is not None
                      and real_edge - placebo_edge >= PLACEBO_MARGIN)
        passed = all([n_ok, win_ok, edge_ok, cohort_ok, placebo_ok])

        if passed:
            verdict = "PASS -> validate robustness like Setup 7, then Test B (Wayback)"
        elif not n_ok and edge_ok:
            verdict = f"LOW CONFIDENCE (n={int(rr['n'])} < {MIN_N})"
        else:
            fails = []
            if not n_ok: fails.append(f"n={int(rr['n'])}<{MIN_N}")
            if not win_ok: fails.append(f"win={rr['win_rate']}<{MIN_WIN_RATE}")
            if not edge_ok: fails.append(f"edge={real_edge}<={MIN_EDGE_VS_SPY}")
            if not cohort_ok: fails.append(f"cohorts={n_pos}/{n_years}<80%")
            if not placebo_ok: fails.append("placebo not clearly weaker")
            verdict = "FAIL (" + "; ".join(fails) + ")"

        verdicts.append({
            "setup": real, "n_t90": int(rr["n"]), "win_rate_t90": rr["win_rate"],
            "real_edge_t90": real_edge, "placebo_edge_t90": placebo_edge,
            "positive_cohorts_t90": f"{n_pos}/{n_years}",
            "n_ok": n_ok, "win_ok": win_ok, "edge_ok": edge_ok,
            "cohort_ok": cohort_ok, "placebo_ok": placebo_ok, "verdict": verdict,
        })

    for setup, reason in UNTESTABLE.items():
        verdicts.append({"setup": setup, "verdict": f"UNTESTABLE WITHOUT BIAS ({reason})"})

    if comparison_rows:
        comp = pd.DataFrame(comparison_rows)
        comp.to_csv(os.path.join(RESULTS_DIR, "group3_comparison.csv"), index=False)
        print("=" * 120)
        print("GROUP 3 COMPARISON (T+90, real vs placebo)")
        print("=" * 120)
        print(comp.to_string(index=False))

    vdf = pd.DataFrame(verdicts)
    vdf.to_csv(os.path.join(RESULTS_DIR, "group3_verdict.csv"), index=False)
    print("\n" + "=" * 120)
    print(f"VERDICT (strictest bar: n>={MIN_N}, win>{MIN_WIN_RATE}, "
          f"edge vs SPY T+90>{MIN_EDGE_VS_SPY}, >={MIN_POSITIVE_COHORT_RATIO:.0%} cohorts positive, "
          f"placebo weaker by >={PLACEBO_MARGIN})")
    print("=" * 120)
    print(vdf.to_string(index=False))


if __name__ == "__main__":
    main()
