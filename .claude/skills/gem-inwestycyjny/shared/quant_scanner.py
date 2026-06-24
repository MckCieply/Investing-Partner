#!/usr/bin/env python3
"""Quant Scanner - SMA50, SMA200, RSI(14), ATR(14), Stop Loss + makro DXY/US10Y.
Pobiera dane z Yahoo Finance. Używany przez Agent 02 (Quant Core).

Usage: python3 quant_scanner.py TICKER1 TICKER2 ...
"""
import sys
import argparse
from datetime import datetime

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pip install yfinance pandas numpy --break-system-packages")
    sys.exit(1)


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(val, 2) if not np.isnan(val) else None


def compute_atr(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    val = atr.iloc[-1]
    return round(val, 2) if not np.isnan(val) else None


def scan_ticker(yahoo_ticker):
    result = {"ticker": yahoo_ticker, "error": None, "price": None,
              "sma50": None, "sma200": None, "rsi14": None, "atr14": None,
              "stop_loss": None, "price_gt_sma50": None, "price_gt_sma200": None,
              "rsi_lt_70": None, "green_light": None}
    try:
        tk = yf.Ticker(yahoo_ticker)
        df = tk.history(period="1y")
        if df.empty:
            result["error"] = "BRAK DANYCH Z YAHOO FINANCE"
            return result
        close = df["Close"]
        price = round(float(close.iloc[-1]), 2)
        sma50 = round(float(close.rolling(50).mean().iloc[-1]), 2) if len(close) >= 50 else None
        sma200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None
        rsi = compute_rsi(close)
        atr = compute_atr(df)
        stop_loss = round(price - 2 * atr, 2) if atr else None
        result.update({"price": price, "sma50": sma50, "sma200": sma200,
                       "rsi14": rsi, "atr14": atr, "stop_loss": stop_loss})
        # Force pure Python bool to avoid numpy.bool_ display issues
        result["price_gt_sma50"] = bool(price > sma50) if sma50 else None
        result["price_gt_sma200"] = bool(price > sma200) if sma200 else None
        result["rsi_lt_70"] = bool(rsi < 70) if rsi else None
        conditions = [result["price_gt_sma50"], result["price_gt_sma200"], result["rsi_lt_70"]]
        result["green_light"] = bool(all(conditions)) if all(c is not None for c in conditions) else None
    except Exception as e:
        result["error"] = str(e)
    return result


def scan_macro():
    macro = {"dxy": None, "us10y": None}
    try:
        df = yf.Ticker("DX-Y.NYB").history(period="5d")
        if not df.empty:
            macro["dxy"] = round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        pass
    try:
        df = yf.Ticker("^TNX").history(period="5d")
        if not df.empty:
            macro["us10y"] = round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return macro


def b(val):
    return "T" if val is True else ("N" if val is False else "?")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    args = parser.parse_args()
    macro = scan_macro()
    print(f"\n{'='*70}")
    print("QUANT_SCANNER_RAW_OUTPUT")
    print(f"DATE: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"\n---MAKRO---")
    print(f"DXY: {macro['dxy'] or 'BRAK'} | US10Y: {macro['us10y'] or 'BRAK'}%")
    print(f"\n---SKANER_NOWYCH_TICKEROW---")
    for t in args.tickers:
        r = scan_ticker(t)
        if r["error"]:
            print(f"TICKER: {t} | ERROR: {r['error']}")
            continue
        status = "PRZEGRZANIE" if (r["rsi14"] and r["rsi14"] >= 70) else "OK"
        print(f"TICKER: {t} | Cena: {r['price']} | SMA50: {r['sma50']} | "
              f"SMA200: {r['sma200']} | RSI14: {r['rsi14']} | ATR14: {r['atr14']} | "
              f"StopLoss(2xATR): {r['stop_loss']} | Cena>SMA50: {b(r['price_gt_sma50'])} | "
              f"Cena>SMA200: {b(r['price_gt_sma200'])} | RSI<70: {b(r['rsi_lt_70'])} | "
              f"ZIELONE_SWIATLO: {b(r['green_light'])} | Status: {status}")
    print(f"{'='*70}\nEND_QUANT_SCANNER")


if __name__ == "__main__":
    main()
