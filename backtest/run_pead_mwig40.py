"""
run_pead_mwig40.py
==================
Orchestrator. Spina data_layer/gpw_espi.py → setups/pead_mwig40.py →
core/results_writer.py i persystuje do results/pead_mwig40/.

Użycie (po implementacji data_layer):
    python run_pead_mwig40.py --start 2010-01-01 --end 2025-12-31

Dopóki data_layer rzuca NotImplementedError, realny przebieg się nie odpali —
to celowe. Do dowodu persystencji służy smoke_test_persistence.py (dane syntetyczne).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from data_layer import gpw_espi
from setups import pead_mwig40 as S
from core import results_writer

RESULTS_DIR = Path(__file__).parent / "results" / "pead_mwig40"


def run(start: date, end: date, out_dir: Path = RESULTS_DIR) -> None:
    # 1. Inputy (jedyna pluggable granica)
    membership = gpw_espi.point_in_time_membership(start, end)
    tickers = sorted(membership["ticker_wa"].unique())
    prices = gpw_espi.load_prices(tickers, start, end)
    benchmark = gpw_espi.load_benchmark(start, end)
    events = gpw_espi.earnings_events(tickers, start, end)

    # 2. Walidacja kompletności PRZED backtestem (twarda reguła)
    val = gpw_espi.validate_completeness(events, prices, membership)
    if not all(val.get(k, False) for k in ("espi_completeness", "membership_sanity", "price_adjustment")):
        raise RuntimeError(f"Walidacja kompletności FAIL: {val}. Napraw źródło zanim policzysz cokolwiek.")

    # 3. Surprise + filtr jakości + nogi
    scored = []
    for ev in events:
        if not ev.in_universe:
            continue
        sue = S.compute_sue(ev)
        if sue is None:
            continue
        scored.append((ev, sue))

    sues = [s for _, s in scored]
    q_top = pd.Series(sues).quantile(1 - 1 / S.FROZEN_PARAMS["n_buckets"])
    q_bot = pd.Series(sues).quantile(1 / S.FROZEN_PARAMS["n_buckets"])

    long_edges = defaultdict(list)     # horizon -> [edge]
    short_edges = defaultdict(list)
    cohort_long = defaultdict(list)    # year -> [edge@primary]
    cohort_short = defaultdict(list)
    event_rows = []

    H = S.FROZEN_PARAMS["primary_horizon"]
    bench_series = benchmark
    for ev, sue in scored:
        leg = None
        if sue >= q_top and S.passes_quality(ev):
            leg = "long"
        elif sue <= q_bot:
            leg = "short_signal"
        if leg is None:
            continue
        px = prices.get(ev.ticker_wa)
        if px is None:
            continue
        entry = pd.Timestamp(ev.publication_dt) + pd.Timedelta(days=1)
        for h in S.FROZEN_PARAMS["horizons_days"]:
            gross = S.forward_return(px, entry, h)
            if gross is None:
                continue
            net = S.apply_costs(gross, cost_mult=1.0)
            bench_ret = S.forward_return(bench_series, entry, h)
            edge = S.edge_vs_benchmark(net, bench_ret)
            if edge is None:
                continue
            (long_edges if leg == "long" else short_edges)[h].append(edge)
            if h == H:
                yr = ev.publication_dt.year
                (cohort_long if leg == "long" else cohort_short)[yr].append(edge)
                event_rows.append({"ticker": ev.ticker_wa, "date": ev.publication_dt,
                                   "leg": leg, "sue": round(sue, 3),
                                   "edge_t%d_pct" % H: round(100 * edge, 2)})

    # 4. Placebo + sensitivity kosztu (long, primary horizon)
    placebo_med = _placebo(prices, bench_series, scored, H)  # zwraca median edge
    edge_2x = _cost_sensitivity_edge(long_edges[H], mult=2.0)

    cohorts_long_df = S.cohort_table(cohort_long)
    cohorts_short_df = S.cohort_table(cohort_short)
    verdict = S.evaluate_pass(long_edges[H], cohorts_long_df, placebo_med, edge_2x)

    summary = {
        "frozen_params_hash": S.frozen_params_hash(),
        "long_verdict": verdict,
        "long_median_edge_by_horizon_pct": {
            h: round(100 * (S._median(long_edges[h]) or 0), 2) for h in long_edges
        },
        "short_signal": {
            "median_edge_t90_pct": round(100 * (S._median(short_edges[H]) or 0), 2)
        },
    }
    cost_sens_df = pd.DataFrame([
        {"cost_mult": m, "median_edge_t90_pct": round(100 * _cost_sensitivity_edge(long_edges[H], m), 2)}
        for m in S.FROZEN_PARAMS["cost_sensitivity_multipliers"]
    ])
    placebo_df = pd.DataFrame([{"placebo_median_edge_t90_pct": round(100 * (placebo_med or 0), 2)}])

    results_writer.write_results(
        out_dir=out_dir, summary=summary,
        cohorts_long=cohorts_long_df, cohorts_short_signal=cohorts_short_df,
        placebo_long=placebo_df, cost_sensitivity=cost_sens_df,
        events_long=pd.DataFrame(event_rows),
        validation_notes=val, frozen_params=S.FROZEN_PARAMS,
        frozen_params_hash=S.frozen_params_hash(), synthetic=False,
    )
    print(f"Wyniki zapisane do {out_dir} | werdykt LONG: {verdict['verdict']}")


def _cost_sensitivity_edge(edges_1x: list[float], mult: float) -> float:
    """Re-aplikuje dodatkowy koszt względem 1x i zwraca median."""
    extra = (mult - 1.0) * 2 * (S.FROZEN_PARAMS["half_spread_bps"]) / 1e4
    adj = [e - extra for e in edges_1x]
    return S._median(adj) or 0.0


def _placebo(prices, bench, scored, horizon) -> float | None:
    """Losowe non-earnings wejścia, count-matched, seed z FROZEN_PARAMS."""
    import numpy as np
    rng = np.random.default_rng(S.FROZEN_PARAMS["random_seed"])
    edges = []
    per_ticker = defaultdict(int)
    for ev, _ in scored:
        per_ticker[ev.ticker_wa] += 1
    for tkr, cnt in per_ticker.items():
        px = prices.get(tkr)
        if px is None or len(px) < horizon + 5:
            continue
        for _ in range(cnt):
            i = int(rng.integers(0, len(px) - horizon - 1))
            entry = px.index[i]
            gross = S.forward_return(px, entry, horizon)
            if gross is None:
                continue
            net = S.apply_costs(gross, 1.0)
            bench_ret = S.forward_return(bench, entry, horizon)
            edge = S.edge_vs_benchmark(net, bench_ret)
            if edge is not None:
                edges.append(edge)
    return S._median(edges)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2025-12-31")
    a = ap.parse_args()
    run(date.fromisoformat(a.start), date.fromisoformat(a.end))
