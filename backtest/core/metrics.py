"""Summary statistics for one setup's backtest results, computed per horizon."""
import numpy as np
import pandas as pd


def summarize(df, horizon, sl_variant="pct10", return_col="net_return"):
    """One row of metrics for a given horizon, using results from run_backtest()."""
    if "horizon" not in df.columns or return_col not in df.columns:
        return {"horizon": horizon, "n": 0}
    sub = df[(df["horizon"] == horizon) & df[return_col].notna()]
    n = len(sub)
    if n == 0:
        return {"horizon": horizon, "n": 0}

    returns = sub[return_col]
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    win_rate = len(wins) / n

    sl_col = f"sl_hit_{sl_variant}"
    sl_hit_rate = sub[sl_col].mean() if sl_col in sub.columns and sub[sl_col].notna().any() else None

    expectancy = (win_rate * wins.mean() if len(wins) else 0) - \
                 ((1 - win_rate) * abs(losses.mean()) if len(losses) else 0)

    edge_vs_spy = sub["edge_vs_spy"].median() if "edge_vs_spy" in sub.columns and sub["edge_vs_spy"].notna().any() else None

    return {
        "horizon": horizon,
        "n": n,
        "win_rate": round(win_rate, 4),
        "median_return": round(returns.median(), 4),
        "mean_return": round(returns.mean(), 4),
        "max_drawdown": round(returns.min(), 4),
        "sl_hit_rate": round(sl_hit_rate, 4) if sl_hit_rate is not None else None,
        "expectancy": round(expectancy, 4),
        "edge_vs_spy_median": round(edge_vs_spy, 4) if edge_vs_spy is not None else None,
    }


def summarize_setup(df, setup_name, horizons=(30, 60, 90), sl_variant="pct10"):
    rows = []
    for h in horizons:
        m = summarize(df, h, sl_variant=sl_variant)
        m["setup"] = setup_name
        rows.append(m)
    return pd.DataFrame(rows)
