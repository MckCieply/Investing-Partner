"""
setups/pead_mwig40.py
=====================
PEAD na mWIG40 — frozen definicje + czysta logika obliczeniowa.

ZASADA: definicje zamrożone w FROZEN_PARAMS. Zero optymalizacji na danych.
Hash FROZEN_PARAMS trafia do RUN_META.json jako strażnik dryfu definicji.

Ten moduł NIE pobiera danych. Przyjmuje inputy wyprodukowane przez
data_layer/gpw_espi.py i zwraca metryki gotowe do persystencji.

Wszystkie funkcje są czyste i deterministyczne (poza jawnym seedem placebo).
Metryki (median edge / win rate / kohorty) zaimplementowane lokalnie dla
samowystarczalności — PRZED MERGEM podmień na core.metrics / core.cohorts.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────
# FROZEN PARAMS — zamrożone z góry. Każda zmiana = inny hash w RUN_META.json.
# ──────────────────────────────────────────────────────────────────────────
FROZEN_PARAMS: dict = {
    "universe": "mWIG40_point_in_time",
    "ticker_format": {"broker": "TICK.PL", "data": "TICK.WA"},

    # surprise: seasonal random walk (Foster / Bernard-Thomas), bez konsensusu
    "surprise_method": "seasonal_random_walk",
    "sue_lag_quarters": 4,            # YoY: EPS_q - EPS_{q-4}
    "sue_std_window_quarters": 8,     # σ po trailing 8 zmianach YoY
    "surprise_fallback_order": ["eps", "net_income", "revenue"],

    # podział na nogi
    "n_buckets": 5,                   # kwintyle (decyle gdy n urośnie)
    "long_bucket": "top",             # top kwintyl SUE = pozytywne zaskoczenie
    "short_signal_bucket": "bottom",  # defensywny sygnał (nietradeowalny na IKE)

    # filtr jakości (czysty size martwy → tylko jakościowe nazwy w LONG)
    "quality_require_positive_net_income": True,
    "quality_require_positive_ocf": True,
    "quality_max_net_debt_ebitda": 3.0,

    # timing
    "entry": "next_session_open_after_publication",  # T+1, anty-look-ahead
    "horizons_days": [30, 60, 90],
    "primary_horizon": 90,

    # benchmark
    "benchmark": "mWIG40_TR",         # NIE SPY. edge = ret - benchmark_ret
    "benchmark_alt": "WIG",

    # koszty (XTB IKE: prowizja 0; spread jest kosztem)
    "commission_bps": 0.0,
    "half_spread_bps": 35.0,          # 70 bps round-trip baza
    "cost_sensitivity_multipliers": [1.0, 2.0, 3.0],

    # progi PASS (LONG, net of costs)
    "pass_median_edge_t90_pct": 4.0,
    "pass_win_rate_pct": 55.0,
    "pass_min_cohort_share": 0.60,
    "pass_min_n": 40,
    "pass_require_beat_placebo": True,
    "pass_require_robust_2x_cost": True,

    # placebo
    "random_seed": 42,
}


def frozen_params_hash(params: dict = FROZEN_PARAMS) -> str:
    """SHA-256 kanonicznego JSON-a — strażnik dryfu definicji."""
    blob = json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# ──────────────────────────────────────────────────────────────────────────
# Kontener pojedynczego zdarzenia wynikowego
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class EarningsEvent:
    ticker_wa: str                    # format Yahoo/stooq, np. "ALE.WA"
    publication_dt: date              # timestamp publikacji ESPI (data sesji wejścia liczona dalej)
    eps_q: float | None               # EPS bieżącego kwartału
    eps_hist_yoy: list[float] = field(default_factory=list)  # [EPS_{q-4}, EPS_{q-8}, ...] do σ
    net_income: float | None = None
    ocf: float | None = None          # operating cash flow (trailing)
    net_debt_ebitda: float | None = None
    in_universe: bool = True          # point-in-time membership w dacie eventu


# ──────────────────────────────────────────────────────────────────────────
# Surprise: seasonal random walk
# ──────────────────────────────────────────────────────────────────────────
def compute_sue(ev: EarningsEvent, params: dict = FROZEN_PARAMS) -> float | None:
    """
    SUE = (EPS_q - EPS_{q-4}) / σ(ΔEPS przez trailing N kwartałów).
    eps_hist_yoy: lista historycznych ΔEPS (zmian YoY) długości >= N.
    """
    if ev.eps_q is None or len(ev.eps_hist_yoy) < params["sue_std_window_quarters"]:
        return None
    window = ev.eps_hist_yoy[: params["sue_std_window_quarters"]]
    sigma = float(np.std(window, ddof=1))
    if not math.isfinite(sigma) or sigma == 0:
        return None
    # ΔEPS bieżący = EPS_q - EPS_{q-4}; EPS_{q-4} = pierwszy element okna historii
    delta_now = ev.eps_q - ev.eps_hist_yoy[0]
    return delta_now / sigma


def passes_quality(ev: EarningsEvent, params: dict = FROZEN_PARAMS) -> bool:
    if params["quality_require_positive_net_income"] and (ev.net_income is None or ev.net_income <= 0):
        return False
    if params["quality_require_positive_ocf"] and (ev.ocf is None or ev.ocf <= 0):
        return False
    if ev.net_debt_ebitda is not None and ev.net_debt_ebitda > params["quality_max_net_debt_ebitda"]:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# Forward returns + edge vs benchmark, net of costs
# ──────────────────────────────────────────────────────────────────────────
def forward_return(
    prices: pd.Series,        # indeks = daty sesji, wartość = close (skorygowany)
    entry_dt: pd.Timestamp,   # sesja wejścia (T+1 po publikacji), wchodzimy na OPEN — tu approx close
    horizon_days: int,
) -> float | None:
    """Prosty buy&hold return od wejścia do T+H. Zwraca None gdy brak danych."""
    idx = prices.index
    pos = idx.searchsorted(entry_dt)
    if pos >= len(idx):
        return None
    entry_px = prices.iloc[pos]
    exit_pos = idx.searchsorted(entry_dt + pd.Timedelta(days=horizon_days))
    exit_pos = min(exit_pos, len(idx) - 1)
    if exit_pos <= pos:
        return None
    exit_px = prices.iloc[exit_pos]
    if entry_px <= 0:
        return None
    return float(exit_px / entry_px - 1.0)


def apply_costs(gross_ret: float, cost_mult: float, params: dict = FROZEN_PARAMS) -> float:
    """Odejmuje round-trip: 2× half_spread + 2× commission (commission=0 na IKE)."""
    rt_cost = 2 * (params["half_spread_bps"] + params["commission_bps"]) / 1e4 * cost_mult
    return gross_ret - rt_cost


def edge_vs_benchmark(stock_ret: float, bench_ret: float | None) -> float | None:
    if bench_ret is None:
        return None
    return stock_ret - bench_ret


# ──────────────────────────────────────────────────────────────────────────
# Metryki (LOKALNE — podmień na core.metrics przed mergem)
# ──────────────────────────────────────────────────────────────────────────
def _median(xs: list[float]) -> float | None:
    return float(np.median(xs)) if xs else None


def _mean(xs: list[float]) -> float | None:
    return float(np.mean(xs)) if xs else None


def _win_rate(xs: list[float]) -> float | None:
    return 100.0 * sum(1 for x in xs if x > 0) / len(xs) if xs else None


def cohort_table(edges_by_year: dict[int, list[float]]) -> pd.DataFrame:
    """Kohorty roczne: median edge, win rate, n per rok."""
    rows = []
    for yr in sorted(edges_by_year):
        e = edges_by_year[yr]
        rows.append({
            "year": yr,
            "n": len(e),
            "median_edge_pct": round(100 * _median(e), 2) if e else None,
            "mean_edge_pct": round(100 * _mean(e), 2) if e else None,
            "win_rate_pct": round(_win_rate(e), 1) if e else None,
            "positive": (_median(e) or 0) > 0,
        })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────
# Werdykt PASS/FAIL
# ──────────────────────────────────────────────────────────────────────────
def evaluate_pass(
    long_edges_t90: list[float],
    cohorts: pd.DataFrame,
    placebo_median_edge_t90: float | None,
    edge_at_2x_cost: float | None,
    params: dict = FROZEN_PARAMS,
) -> dict:
    median_edge = _median(long_edges_t90)
    win = _win_rate(long_edges_t90)
    n = len(long_edges_t90)
    cohort_share = (cohorts["positive"].mean() if len(cohorts) else 0.0)
    real_med = (median_edge or 0) * 100

    checks = {
        "median_edge_t90": (real_med, real_med > params["pass_median_edge_t90_pct"]),
        "win_rate": (win, (win or 0) > params["pass_win_rate_pct"]),
        "cohort_share": (round(cohort_share, 2), cohort_share >= params["pass_min_cohort_share"]),
        "n": (n, n >= params["pass_min_n"]),
        "beats_placebo": (
            None if placebo_median_edge_t90 is None else round(100 * placebo_median_edge_t90, 2),
            (
                (placebo_median_edge_t90 is not None and (median_edge or -1) > placebo_median_edge_t90)
                if params["pass_require_beat_placebo"]
                else True
            ),
        ),
        "robust_2x_cost": (
            None if edge_at_2x_cost is None else round(100 * edge_at_2x_cost, 2),
            (edge_at_2x_cost is not None and edge_at_2x_cost > 0) if params["pass_require_robust_2x_cost"] else True,
        ),
    }
    verdict = "PASS" if all(ok for _, ok in checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks}


if __name__ == "__main__":
    print("FROZEN_PARAMS hash:", frozen_params_hash())
