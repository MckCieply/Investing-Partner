#!/usr/bin/env python3
"""
reentry_scanner.py — Agent 6b: skaner powrotu do zamknietych pozycji.

Czyta closed_positions.csv (ledger wybitych/zamknietych pozycji, zasilany
auto-logiem position_auditor.py) i dla kazdej pozycji sprawdza, czy setup
techniczny, ktory kazal nam wyjsc, sie ODWROCIL — czyli czy warto rozwazyc
powrot. To skan ILOSCIOWY (trend/momentum), NIE sygnal kupna: decyzje o
wejsciu podejmuje uzytkownik (ew. po weryfikacji narracji przez gem-pipeline).

Logika (per pozycja, na danych 1y dziennych):
  - odzyskany trend:   cena > SMA50 i cena > SMA200
  - odzyskany poziom:  cena > exit_stop (poziom, ktory nas wybil)
  - momentum:          ret20 > 0
  - nie przegrzane:    RSI14 < 75 i cena <= ~1.05*high20 (blisko wybicia, nie w euforii)

Klasyfikacja:
  RE-ENTER  — trend + poziom + momentum odzyskane, nie przegrzane  -> kandydat do powrotu
  WATCH     — czesc warunkow spelniona (odbudowa w toku)           -> obserwuj
  SKIP      — cena < SMA50 (trend nadal zlamany)                   -> odpuszczamy

Pomija tickery ktore sa juz z powrotem w holdings.json (wrocilismy) oraz
pozycje zamkniete dawniej niz --max-age-days (domyslnie 365).

Uzycie:
  python skills/gem-position-auditor/reentry_scanner.py closed_positions.csv \
      --holdings holdings.json --html-out reentry_report.html
"""
import sys, os, csv, argparse, math
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import pandas as pd
    from position_auditor import fetch, _atr, _sma, _v   # DRY: te same helpery co auditor
except ImportError as e:
    print(f"ERROR: {e}. pip install yfinance pandas numpy --break-system-packages")
    sys.exit(1)


def _rsi(close, period=14):
    """RSI Wildera."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = ag / al.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


def _num(x):
    try:
        f = float(x)
        return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def _age_days(date_closed, today):
    try:
        d0 = datetime.strptime(date_closed, "%Y-%m-%d")
        return (today - d0).days
    except (ValueError, TypeError):
        return None


def analyze(row, today):
    xtb = row.get("xtb", "")
    yahoo = row.get("yahoo") or xtb.split(".")[0]
    avg = _num(row.get("avg_cost"))
    exit_stop = _num(row.get("exit_stop"))
    df = fetch(yahoo)
    if df is None or len(df) < 60:
        return {"xtb": xtb, "error": "BRAK/za malo danych"}
    c = df["Close"]
    price = float(c.iloc[-1])
    s50 = _v(_sma(c, 50).iloc[-1]) if len(c) >= 50 else None
    s200 = _v(_sma(c, 200).iloc[-1]) if len(c) >= 200 else None
    hi20 = float(c.tail(20).max())
    ret20 = (price / float(c.iloc[-21]) - 1) * 100 if len(c) > 21 else None
    rsi = _v(_rsi(c).iloc[-1])

    trend_back = bool(s50 and price > s50 and (s200 is None or price > s200))
    above_s50 = bool(s50 and price > s50)
    level_back = bool(exit_stop is not None and price > exit_stop)
    momentum = bool(ret20 is not None and ret20 > 0)
    overheated = bool((rsi is not None and rsi >= 75) or price > hi20 * 1.05)

    if trend_back and level_back and momentum and not overheated:
        verdict = "RE-ENTER"
    elif above_s50 and not overheated:
        verdict = "WATCH"
    else:
        verdict = "SKIP"

    reasons = []
    reasons.append(("trend" if trend_back else ("nad SMA50" if above_s50 else "pod SMA50")))
    if exit_stop is not None:
        reasons.append("nad starym stopem" if level_back else "pod starym stopem")
    if momentum:
        reasons.append(f"ret20 {ret20:+.0f}%")
    if overheated:
        reasons.append("przegrzane")

    return {
        "xtb": xtb, "verdict": verdict, "price": round(price, 2),
        "avg_cost": avg, "exit_stop": exit_stop,
        "orig_reason": row.get("reason", ""),
        "date_closed": row.get("date_closed", ""),
        "sma50": round(s50, 2) if s50 else None,
        "sma200": round(s200, 2) if s200 else None,
        "ret20": round(ret20, 1) if ret20 is not None else None,
        "rsi": round(rsi, 0) if rsi is not None else None,
        # ruch ceny od naszego wyjscia (szacowanego z exit_stop)
        "since_exit_pct": round((price / exit_stop - 1) * 100, 1) if exit_stop else None,
        "note": ", ".join(reasons),
    }


ORDER = {"RE-ENTER": 0, "WATCH": 1, "SKIP": 2}


def build_html(rows, today_display, n_total):
    def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    th = "padding:6px 10px;text-align:left;border-bottom:2px solid #ccc;"
    td = "padding:6px 10px;border-bottom:1px solid #eee;"
    ok = [r for r in rows if "error" not in r]
    errs = [r for r in rows if "error" in r]
    ok.sort(key=lambda r: (ORDER.get(r["verdict"], 9), -(r.get("since_exit_pct") or -999)))
    cand = [r for r in ok if r["verdict"] == "RE-ENTER"]

    html = [f"""<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1a1a1a;">
<h2 style="margin-bottom:4px;">Re-entry Scanner &mdash; {esc(today_display)}</h2>
<p style="color:#666;margin-top:0;">Zamknietych pozycji w analizie: {n_total} | Kandydaci do powrotu: {len(cand)}</p>
<p style="color:#888;font-size:12px;">Skan ILOSCIOWY (trend/momentum), nie sygnal kupna. Ceny wyjscia szacowane z exit_stop.</p>"""]

    color = {"RE-ENTER": "#e7f6e7", "WATCH": "#fff8e1", "SKIP": ""}
    html.append('<table style="border-collapse:collapse;width:100%;">')
    html.append(f'<tr><th style="{th}">Ticker</th><th style="{th}">Werdykt</th><th style="{th}">Cena</th>'
                f'<th style="{th}">Od wyjscia</th><th style="{th}">SMA50/200</th><th style="{th}">ret20</th>'
                f'<th style="{th}">RSI</th><th style="{th}">Zamkn.</th><th style="{th}">Powod exitu</th>'
                f'<th style="{th}">Uwagi</th></tr>')
    for r in ok:
        bg = color.get(r["verdict"], "")
        since = f'{r["since_exit_pct"]:+.1f}%' if r.get("since_exit_pct") is not None else "—"
        html.append(
            f'<tr style="background:{bg};"><td style="{td}"><b>{esc(r["xtb"])}</b></td>'
            f'<td style="{td}"><b>{esc(r["verdict"])}</b></td>'
            f'<td style="{td}">{esc(r["price"])}</td>'
            f'<td style="{td}">{esc(since)}</td>'
            f'<td style="{td}">{esc(r["sma50"])} / {esc(r["sma200"])}</td>'
            f'<td style="{td}">{esc(r["ret20"])}%</td>'
            f'<td style="{td}">{esc(r["rsi"])}</td>'
            f'<td style="{td}">{esc(r["date_closed"])}</td>'
            f'<td style="{td}">{esc(r["orig_reason"])}</td>'
            f'<td style="{td}">{esc(r["note"])}</td></tr>')
    html.append("</table>")

    if errs:
        html.append('<h3>Bledy danych</h3><ul>')
        for r in errs:
            html.append(f'<li>{esc(r["xtb"])}: {esc(r["error"])}</li>')
        html.append("</ul>")
    html.append('<p style="color:#999;font-size:12px;">RE-ENTER = trend (>SMA50 i >SMA200) + cena nad starym stopem '
                '+ dodatni ret20 + nie przegrzane. WATCH = nad SMA50, odbudowa w toku. SKIP = pod SMA50.</p>')
    html.append("</body></html>")
    return "\n".join(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("closed", nargs="?", default="closed_positions.csv")
    ap.add_argument("--holdings", default="holdings.json")
    ap.add_argument("--html-out", default="reentry_report.html")
    ap.add_argument("--max-age-days", type=int, default=365)
    args = ap.parse_args()

    if not os.path.exists(args.closed):
        print(f"Brak {args.closed} — nic do analizy."); return
    with open(args.closed, newline="", encoding="utf-8") as f:
        closed_rows = list(csv.DictReader(f))

    held = set()
    if os.path.exists(args.holdings):
        import json
        try:
            for p in json.load(open(args.holdings, encoding="utf-8")):
                held.add(p.get("xtb", p.get("yahoo")))
        except Exception:
            pass

    today = datetime.now()
    today_display = today.strftime("%d.%m.%Y")

    # najnowszy wpis per ticker, pomin te ktore juz mamy z powrotem lub zbyt stare
    latest = {}
    for row in closed_rows:
        xtb = row.get("xtb")
        if not xtb or xtb in held:
            continue
        age = _age_days(row.get("date_closed", ""), today)
        if age is not None and age > args.max_age_days:
            continue
        prev = latest.get(xtb)
        if prev is None or (row.get("date_closed", "") > prev.get("date_closed", "")):
            latest[xtb] = row

    candidates = list(latest.values())
    print("=" * 74)
    print("REENTRY_SCANNER"); print(f"DATE: {today_display} | pozycji do analizy: {len(candidates)}")
    print("-" * 74)
    rows = [analyze(r, today) for r in candidates]
    for r in sorted([x for x in rows if "error" not in x], key=lambda r: ORDER.get(r["verdict"], 9)):
        since = f'{r["since_exit_pct"]:+.1f}%' if r.get("since_exit_pct") is not None else "—"
        print(f"  {r['xtb']:10s} {r['verdict']:9s} cena {r['price']:>8} | od wyjscia {since:>7} | {r['note']}")
    for r in [x for x in rows if "error" in x]:
        print(f"  {r['xtb']:10s} ERROR: {r['error']}")
    print("=" * 74)

    html = build_html(rows, today_display, len(candidates))
    open(args.html_out, "w", encoding="utf-8").write(html)
    print(f"HTML report zapisany -> {args.html_out}")


if __name__ == "__main__":
    main()
