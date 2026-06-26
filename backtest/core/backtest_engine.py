"""Setup-agnostic backtest engine.

Every setup script produces a list of events:
    {"ticker": str, "event_date": "YYYY-MM-DD", "setup_type": str, ...extra fields}

run_backtest() turns that into one row per (event, horizon) with entry/exit prices,
returns net of costs, stop-loss outcomes, and the SPY benchmark over the same window.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from data_layer import prices

HORIZONS = (30, 60, 90)
SL_VARIANTS = {"pct10": ("pct", 0.10), "atr2": ("atr", 2.0)}

# XTB-ish round-trip cost assumption: ~0.10% commission per side + ~0.05% spread per side.
# Applied once on entry, once on exit -> ~0.30% total drag on the raw return.
ROUNDTRIP_COST = 0.0030

PRICE_LOOKBACK_DAYS = 60  # before event, for ATR context
PRICE_LOOKAHEAD_DAYS = 200  # after event, enough for T+90 sessions + buffer


def _sl_level(entry_price, atr_at_entry, variant):
    kind, mult = SL_VARIANTS[variant]
    if kind == "pct":
        return entry_price * (1 - mult)
    return entry_price - mult * atr_at_entry


def _sl_hit_before(df, entry_date, exit_date, sl_level):
    """True if Low <= sl_level on any session strictly after entry_date, up to exit_date."""
    window = df.loc[(df.index > entry_date) & (df.index <= exit_date)]
    if window.empty:
        return False
    return bool((window["Low"] <= sl_level).any())


def run_backtest(events, entry_offset_sessions=1, horizons=HORIZONS,
                  sl_variants=tuple(SL_VARIANTS.keys()), cost=ROUNDTRIP_COST):
    rows = []
    for ev in events:
        ticker = ev["ticker"]
        event_date = pd.Timestamp(ev["event_date"])
        start = (event_date - pd.Timedelta(days=PRICE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        end = (event_date + pd.Timedelta(days=PRICE_LOOKAHEAD_DAYS)).strftime("%Y-%m-%d")

        try:
            df = prices.get_history(ticker, start, end)
        except Exception as e:
            rows.append({**ev, "error": f"price_fetch_failed: {e}"})
            continue

        if df.empty or len(df) < 5:
            rows.append({**ev, "error": "no_price_data"})
            continue

        entry_date, entry_row = prices.session_offset(df, event_date, entry_offset_sessions)
        if entry_date is None:
            rows.append({**ev, "error": "entry_out_of_range"})
            continue
        entry_price = float(entry_row["Open"])

        atr_series = prices.atr(df)
        atr_at_entry = float(atr_series.loc[entry_date]) if entry_date in atr_series.index and pd.notna(atr_series.loc[entry_date]) else None

        spy_df = prices.get_spy(start, end)
        spy_entry_date, spy_entry_row = (None, None)
        if not spy_df.empty:
            spy_entry_date, spy_entry_row = prices.session_offset(spy_df, entry_date, 0)
        spy_entry_price = float(spy_entry_row["Open"]) if spy_entry_row is not None else None

        for horizon in horizons:
            exit_date, exit_row = prices.session_offset(df, entry_date, horizon)
            row = {**ev, "entry_date": entry_date.date().isoformat(),
                   "entry_price": entry_price, "horizon": horizon}

            if exit_date is None:
                row["error"] = "exit_out_of_range"
                rows.append(row)
                continue

            exit_price = float(exit_row["Close"])
            raw_return = exit_price / entry_price - 1
            net_return = raw_return - cost
            row["exit_date"] = exit_date.date().isoformat()
            row["exit_price"] = exit_price
            row["raw_return"] = raw_return
            row["net_return"] = net_return

            for variant in sl_variants:
                kind, _ = SL_VARIANTS[variant]
                if kind == "atr" and atr_at_entry is None:
                    row[f"sl_hit_{variant}"] = None
                    continue
                sl_level = _sl_level(entry_price, atr_at_entry, variant)
                hit = _sl_hit_before(df, entry_date, exit_date, sl_level)
                row[f"sl_hit_{variant}"] = hit
                if hit:
                    row[f"sl_return_{variant}"] = sl_level / entry_price - 1 - cost
                else:
                    row[f"sl_return_{variant}"] = net_return

            if spy_entry_price is not None:
                spy_exit_date, spy_exit_row = prices.session_offset(spy_df, exit_date, 0)
                if spy_exit_row is not None:
                    spy_exit_price = float(spy_exit_row["Close"])
                    row["spy_return"] = spy_exit_price / spy_entry_price - 1
                    row["edge_vs_spy"] = net_return - row["spy_return"]

            rows.append(row)

    return pd.DataFrame(rows)
