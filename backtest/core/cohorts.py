"""Yearly cohort breakdown for one setup's backtest results.

Lesson from Setup 7 (Group 1): an aggregated edge can be entirely an artifact
of one anomalous year. Every Group 2 setup must run this alongside
summarize_setup() in the same pass - never report an aggregated edge without
also checking how it is distributed across calendar years.
"""
import os

import pandas as pd


def yearly_cohorts(df, horizons=(30, 60, 90), return_col="net_return",
                    edge_col="edge_vs_spy", date_col="event_date"):
    """One row per (horizon, year): n, win_rate, median/mean edge vs SPY.

    Year is taken from the event date (not entry/exit), so a setup's cohort
    membership doesn't shift if entry_offset changes.
    """
    if date_col not in df.columns:
        return pd.DataFrame()

    work = df.copy()
    work["year"] = pd.to_datetime(work[date_col], errors="coerce").dt.year

    rows = []
    for horizon in horizons:
        sub = work[(work["horizon"] == horizon) & work[return_col].notna()]
        for year, g in sub.groupby("year"):
            if pd.isna(year):
                continue
            n = len(g)
            wins = (g[return_col] > 0).sum()
            row = {
                "horizon": horizon,
                "year": int(year),
                "n": n,
                "win_rate": round(wins / n, 4) if n else None,
            }
            if edge_col in g.columns and g[edge_col].notna().any():
                row["median_edge_vs_spy"] = round(g[edge_col].median(), 4)
                row["mean_edge_vs_spy"] = round(g[edge_col].mean(), 4)
            else:
                row["median_edge_vs_spy"] = None
                row["mean_edge_vs_spy"] = None
            rows.append(row)

    return pd.DataFrame(rows).sort_values(["horizon", "year"]).reset_index(drop=True)


def positive_cohort_count(cohorts_df, horizon, edge_col="median_edge_vs_spy"):
    """How many distinct years at this horizon have a positive median edge."""
    sub = cohorts_df[cohorts_df["horizon"] == horizon]
    return int((sub[edge_col] > 0).sum())


def write_cohorts(df, setup_name, results_dir, horizons=(30, 60, 90)):
    cohorts = yearly_cohorts(df, horizons=horizons)
    path = os.path.join(results_dir, f"{setup_name}_yearly_cohorts.csv")
    cohorts.to_csv(path, index=False)
    return cohorts
