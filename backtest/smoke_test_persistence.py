"""
smoke_test_persistence.py
=========================
⚠️ DANE SYNTETYCZNE, LOSOWE. To NIE jest backtest mWIG40.
Cel: dowieść, że łańcuch setups → results_writer → results/ działa end-to-end,
zanim powstanie data_layer. Wynikowe liczby są pozbawione znaczenia rynkowego.

Buduje fałszywe ceny (random walk), fałszywe eventy z losowym SUE, przepuszcza
przez tę samą logikę co run_pead_mwig40.py i zapisuje do
results/pead_mwig40/_SMOKE_TEST_SYNTHETIC/ z jawnym ostrzeżeniem w każdym pliku.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from setups import pead_mwig40 as S
from setups.pead_mwig40 import EarningsEvent
from core import results_writer

OUT = Path(__file__).parent / "results" / "pead_mwig40" / "_SMOKE_TEST_SYNTHETIC"
rng = np.random.default_rng(7)

# ── fałszywe ceny: 6 tickerów, random walk dzienny 2010-2025 ──
sessions = pd.bdate_range("2010-01-01", "2025-12-31")
FAKE = [f"FAKE{i}.WA" for i in range(6)]
prices = {t: pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.02, len(sessions))),
                       index=sessions) for t in FAKE}
benchmark = pd.Series(100 * np.cumprod(1 + rng.normal(0.0002, 0.012, len(sessions))), index=sessions)

# ── fałszywe eventy: ~4/rok/ticker, losowy EPS + historia ──
events = []
for t in FAKE:
    for yr in range(2010, 2026):
        for m in (3, 6, 9, 12):
            hist = list(rng.normal(0.5, 0.4, 8))
            events.append(EarningsEvent(
                ticker_wa=t, publication_dt=date(yr, m, 15),
                eps_q=float(rng.normal(0.6, 0.5)), eps_hist_yoy=hist,
                net_income=float(rng.normal(50, 30)), ocf=float(rng.normal(40, 20)),
                net_debt_ebitda=float(abs(rng.normal(1.5, 0.8))), in_universe=True,
            ))

# ── ta sama logika co orchestrator (skrócona) ──
scored = [(ev, S.compute_sue(ev)) for ev in events]
scored = [(ev, s) for ev, s in scored if s is not None]
sues = [s for _, s in scored]
q_top = pd.Series(sues).quantile(0.8)
q_bot = pd.Series(sues).quantile(0.2)

H = S.FROZEN_PARAMS["primary_horizon"]
long_e, short_e = defaultdict(list), defaultdict(list)
coh_long, coh_short = defaultdict(list), defaultdict(list)
rows = []
for ev, sue in scored:
    leg = "long" if (sue >= q_top and S.passes_quality(ev)) else ("short_signal" if sue <= q_bot else None)
    if leg is None:
        continue
    entry = pd.Timestamp(ev.publication_dt) + pd.Timedelta(days=1)
    for h in S.FROZEN_PARAMS["horizons_days"]:
        g = S.forward_return(prices[ev.ticker_wa], entry, h)
        if g is None:
            continue
        edge = S.edge_vs_benchmark(S.apply_costs(g, 1.0), S.forward_return(benchmark, entry, h))
        if edge is None:
            continue
        (long_e if leg == "long" else short_e)[h].append(edge)
        if h == H:
            (coh_long if leg == "long" else coh_short)[ev.publication_dt.year].append(edge)
            rows.append({"ticker": ev.ticker_wa, "date": ev.publication_dt, "leg": leg,
                         "sue": round(sue, 3), f"edge_t{H}_pct": round(100 * edge, 2)})

coh_long_df = S.cohort_table(coh_long)
coh_short_df = S.cohort_table(coh_short)
placebo_med = S._median([e - 0.001 for e in long_e[H]])  # syntetyczny placebo
edge_2x = (S._median(long_e[H]) or 0) - 0.007
verdict = S.evaluate_pass(long_e[H], coh_long_df, placebo_med, edge_2x)

summary = {
    "WARNING": "SYNTHETIC SMOKE TEST — NIE WYNIK RYNKOWY",
    "frozen_params_hash": S.frozen_params_hash(),
    "long_verdict": verdict,
    "long_median_edge_by_horizon_pct": {h: round(100 * (S._median(long_e[h]) or 0), 2) for h in long_e},
    "short_signal": {"median_edge_t90_pct": round(100 * (S._median(short_e[H]) or 0), 2)},
}
cost_df = pd.DataFrame([{"cost_mult": m, "median_edge_t90_pct": round(100 * ((S._median(long_e[H]) or 0) - (m - 1) * 0.007), 2)}
                        for m in S.FROZEN_PARAMS["cost_sensitivity_multipliers"]])
placebo_df = pd.DataFrame([{"placebo_median_edge_t90_pct": round(100 * (placebo_med or 0), 2)}])
val = {"espi_completeness": "N/A (synthetic)", "membership_sanity": "N/A (synthetic)",
       "price_adjustment": "N/A (synthetic)"}

results_writer.write_results(
    out_dir=OUT, summary=summary, cohorts_long=coh_long_df, cohorts_short_signal=coh_short_df,
    placebo_long=placebo_df, cost_sensitivity=cost_df, events_long=pd.DataFrame(rows),
    validation_notes=val, frozen_params=S.FROZEN_PARAMS,
    frozen_params_hash=S.frozen_params_hash(), synthetic=True,
)
print(f"SMOKE TEST OK → {OUT}")
print(f"  events long: {len(long_e[H])} | short: {len(short_e[H])} | verdict (bez znaczenia): {verdict['verdict']}")
print(f"  pliki: {sorted(p.name for p in OUT.iterdir())}")
