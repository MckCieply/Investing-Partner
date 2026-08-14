"""Orchestrator: aggregate the Quant Gate backtest into a comparison table +
verdict, with the mandatory placebo/decomposition comparison.

Run setups/s_quant_gate.py first; this script only reads its CSV output.

This is a validation of an ALREADY-LIVE rule (Agent 02's 3-gate screen), not a
proposal for a new setup competing with Groups 1-3 on the same fished dataset -
so the bar here is not identical to Group 3's multiple-testing-inflated bar.
It mirrors Group 2's bar (single pre-registered hypothesis) but keeps the
placebo requirement from Group 3, since the task explicitly calls for isolating
which of the 3 gate conditions is doing the work:
  - n >= 50
  - win rate > 0.55
  - median edge vs SPY @ T+90 > +0.05
  - positive median edge in >= 60% of yearly cohorts @ T+90
  - real edge must beat the stronger placebo by >= 0.02 (2pp)
A setup must clear ALL of them for a clean PASS; "almost" is reported as such,
not rounded up.
"""
import os

import pandas as pd

from core.cohorts import positive_cohort_count

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

REAL = "s_quant_gate"
PLACEBO_SMA50_ONLY = "s_quant_gate_placebo_sma50_only"
PLACEBO_SMA_BOTH_NORSI = "s_quant_gate_placebo_sma_both_norsi"

VERDICT_HORIZON = 90
MIN_N = 50
MIN_WIN_RATE = 0.55
MIN_EDGE_VS_SPY = 0.05
MIN_POSITIVE_COHORT_RATIO = 0.60
PLACEBO_MARGIN = 0.02


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


def _row_for(setup, horizon):
    r = _summary_row(setup, horizon)
    if r is None:
        return None
    coh = _cohorts(setup)
    n_pos = positive_cohort_count(coh, horizon) if not coh.empty else 0
    n_years = coh[coh["horizon"] == horizon]["year"].nunique() if not coh.empty else 0
    return {
        "n": int(r["n"]),
        "win_rate": r["win_rate"],
        "median_return": r["median_return"],
        "edge_vs_spy_median": r.get("edge_vs_spy_median"),
        "positive_cohorts": f"{n_pos}/{n_years}",
        "n_pos_cohorts": n_pos,
        "n_years_cohorts": n_years,
    }


def main():
    horizons = (30, 60, 90)
    comparison_rows = []
    for setup, label in [
        (REAL, "real (3-gate: SMA50 & SMA200 & RSI<70)"),
        (PLACEBO_SMA_BOTH_NORSI, "placebo B (SMA50 & SMA200, no RSI)"),
        (PLACEBO_SMA50_ONLY, "placebo A (SMA50 only)"),
    ]:
        for h in horizons:
            row = _row_for(setup, h)
            if row is None:
                continue
            row.update({"setup": setup, "label": label, "horizon": h})
            comparison_rows.append(row)

    if not comparison_rows:
        print("No summary CSVs found - run setups/s_quant_gate.py first.")
        return

    comp = pd.DataFrame(comparison_rows)
    cols = ["setup", "label", "horizon", "n", "win_rate", "median_return",
            "edge_vs_spy_median", "positive_cohorts"]
    comp = comp[cols]
    comp.to_csv(os.path.join(RESULTS_DIR, "quant_gate_comparison.csv"), index=False)

    print("=" * 130)
    print("QUANT GATE - REAL vs PLACEBO DECOMPOSITION (all horizons)")
    print("=" * 130)
    print(comp.to_string(index=False))

    # ---- verdict at T+90 -------------------------------------------------
    real90 = _row_for(REAL, VERDICT_HORIZON)
    placebo_b90 = _row_for(PLACEBO_SMA_BOTH_NORSI, VERDICT_HORIZON)
    placebo_a90 = _row_for(PLACEBO_SMA50_ONLY, VERDICT_HORIZON)

    if real90 is None:
        print("\nNo real-gate data at T+90 - cannot render a verdict.")
        return

    real_edge = real90["edge_vs_spy_median"]
    placebo_edges = [p["edge_vs_spy_median"] for p in (placebo_b90, placebo_a90)
                      if p is not None and p["edge_vs_spy_median"] is not None]
    strongest_placebo_edge = max(placebo_edges) if placebo_edges else None

    n_ok = real90["n"] >= MIN_N
    win_ok = (real90["win_rate"] or 0) >= MIN_WIN_RATE
    edge_ok = (real_edge or -1) > MIN_EDGE_VS_SPY
    n_years = real90["n_years_cohorts"]
    n_pos = real90["n_pos_cohorts"]
    cohort_ok = n_years > 0 and (n_pos / n_years) >= MIN_POSITIVE_COHORT_RATIO
    placebo_ok = (real_edge is not None and strongest_placebo_edge is not None
                  and real_edge - strongest_placebo_edge >= PLACEBO_MARGIN)

    passed = all([n_ok, win_ok, edge_ok, cohort_ok, placebo_ok])

    if passed:
        verdict = ("PASS - historical base rate supports the live 3-gate rule; "
                   "all 3 conditions together outperform either partial gate")
    else:
        fails = []
        if not n_ok: fails.append(f"n={real90['n']}<{MIN_N}")
        if not win_ok: fails.append(f"win={real90['win_rate']}<{MIN_WIN_RATE}")
        if not edge_ok: fails.append(f"edge={real_edge}<={MIN_EDGE_VS_SPY}")
        if not cohort_ok: fails.append(f"cohorts={n_pos}/{n_years}<{MIN_POSITIVE_COHORT_RATIO:.0%}")
        if not placebo_ok: fails.append("placebo not clearly weaker (gate adds no measurable edge over partial conditions)")
        verdict = "FAIL (" + "; ".join(fails) + ")"

    verdict_row = {
        "rule": "quant_gate_3condition", "horizon": VERDICT_HORIZON,
        "n": real90["n"], "win_rate": real90["win_rate"],
        "edge_vs_spy_median": real_edge,
        "strongest_placebo_edge": strongest_placebo_edge,
        "real_minus_strongest_placebo": (round(real_edge - strongest_placebo_edge, 4)
                                          if real_edge is not None and strongest_placebo_edge is not None else None),
        "positive_cohorts": f"{n_pos}/{n_years}",
        "n_ok": n_ok, "win_ok": win_ok, "edge_ok": edge_ok,
        "cohort_ok": cohort_ok, "placebo_ok": placebo_ok, "verdict": verdict,
    }
    vdf = pd.DataFrame([verdict_row])
    vdf.to_csv(os.path.join(RESULTS_DIR, "quant_gate_verdict.csv"), index=False)

    print("\n" + "=" * 130)
    print(f"VERDICT @ T+{VERDICT_HORIZON} (n>={MIN_N}, win>{MIN_WIN_RATE}, edge vs SPY>{MIN_EDGE_VS_SPY}, "
          f">={MIN_POSITIVE_COHORT_RATIO:.0%} cohorts positive, real edge beats strongest placebo by >={PLACEBO_MARGIN})")
    print("=" * 130)
    print(vdf.to_string(index=False))


if __name__ == "__main__":
    main()
