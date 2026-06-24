#!/usr/bin/env python3
"""
position_auditor.py — Silnik wyjsc Agenta 6 (Gem Inwestycyjny). v2

Co robi:
  - dobiera metode STOPA / TRANSZ per aktywo (rola + wiabilnosc ATR),
  - STANOWO: czyta stops_state.json z poprzedniego runu i pokazuje
    DOKLADNIE co zmienil w tym tygodniu (PODNIES X->Y, zmiana bucketa,
    przejscie na transze, WYJDZ),
  - ratchet stopa tylko w gore; TP-transze tylko w gore.

ZASADY (uzgodnione):
  CORE        -> SMA200 / -20% disaster (pasywny rdzen; akcji nie dotyczy)
  TREND <=5%  -> min[SMA50, high20-3xATR14], clamp do [-20%, -5%]
  TREND 5-10% -> min[SMA50, high20-4xATR14], clamp do [-20%, -5%]
  TREND >10%  -> JESLI w zysku: PLAN TRANSZ (Sell Limit, BEZ stopa)
                 JESLI pod kreska: szeroki stop jak 5-10%
  SPIKE       -> max[SMA20, high10-1.5xATR7, -18% od high]  (ciasno)
  MEANREVERT  -> dolek20 - 0.5xATR14, clamp; bez agresywnego ratchetu
  SPEC        -> -12% staly, bez trailingu

Histereza SPIKE/TREND: wejscie w SPIKE gdy ret20>45%, wyjscie gdy <35%.
SPIKE -> MEANREVERT gdy cena spada pod SMA50.

Stop broni DOLU (Sell Stop pod cena). Transze zdejmuja GORE (Sell Limit nad cena).
Stop >= cena => trend pekl => WYJDZ TERAZ.
"""
import sys, json, argparse, math, os
from datetime import datetime

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pip install yfinance pandas numpy --break-system-packages")
    sys.exit(1)

STATE_FILE = "stops_state.json"
CAP = 0.20          # max luz stopa od ceny (-20%)
FLOOR = 0.05        # min dystans stopa od ceny (-5%) dla akcji
HI_ATR = 0.10       # prog ATR% dla "parabola -> transze"
MIN_MOVE = 0.003    # min. ruch poziomu wzgledem ceny, by zglosic PODNIES (tlumi szum typu +0.0003)

def _ratchet(new_val, prior_val, price):
    """Stop/TP rusza sie tylko w gore, i tylko jesli ruch >= MIN_MOVE*price (inaczej szum)."""
    if new_val is None: return prior_val
    if prior_val is None: return new_val
    candidate = max(new_val, prior_val)
    if candidate - prior_val >= price * MIN_MOVE:
        return candidate
    return prior_val

def _atr(df, p):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(p, min_periods=p).mean()

def _sma(s, n): return s.rolling(n, min_periods=n).mean()

def _v(x):
    try:
        f = float(x); return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None

def fetch(y):
    try:
        d = yf.Ticker(y).history(period="1y", auto_adjust=True)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        return d if not d.empty else None
    except Exception:
        return None

def classify(df, is_etf, prev_bucket=None):
    if is_etf: return "CORE"
    c = df["Close"]; price = float(c.iloc[-1])
    s50 = _v(_sma(c, 50).iloc[-1]) if len(c) >= 50 else None
    s200 = _v(_sma(c, 200).iloc[-1]) if len(c) >= 200 else None
    ret20 = (price/float(c.iloc[-21]) - 1) if len(c) > 21 else 0.0
    # histereza SPIKE
    if prev_bucket == "SPIKE":
        if s50 and price < s50: return "MEANREVERT"   # spike pekl
        if ret20 >= 0.35: return "SPIKE"               # nadal goracy
        # ret20<35% -> dojrzal, schodzimy do TREND/MEANREVERT ponizej
    else:
        if ret20 >= 0.45: return "SPIKE"               # nowa parabola
    if s50 and price > s50 and (s200 is None or price > s200):
        return "TREND"
    return "MEANREVERT"

def clamp_stop(level, price):
    """Trzymaj stop w [-CAP, -FLOOR] od ceny; None gdy brak poziomu."""
    if level is None: return None
    lo, hi = price*(1-CAP), price*(1-FLOOR)
    return round(min(max(level, lo), hi), 4)

def plan(df, bucket, avg):
    c = df["Close"]; price = float(c.iloc[-1])
    a14 = _v(_atr(df, 14).iloc[-1]); a7 = _v(_atr(df, 7).iloc[-1])
    atrp = (a14/price) if (a14 and price) else None
    s20 = _v(_sma(c, 20).iloc[-1]) if len(c) >= 20 else None
    s50 = _v(_sma(c, 50).iloc[-1]) if len(c) >= 50 else None
    s200 = _v(_sma(c, 200).iloc[-1]) if len(c) >= 200 else None
    hi20 = float(c.tail(20).max()); hi10 = float(c.tail(10).max()); lo20 = float(c.tail(20).min())
    in_profit = (avg is not None and price > avg)
    notes = []
    def mn(vals):
        v = [x for x in vals if x is not None]; return min(v) if v else None
    def mx(vals):
        v = [x for x in vals if x is not None]; return max(v) if v else None

    # ---- PARABOLA: transze zamiast stopa, ale tylko w zysku ----
    if bucket == "TREND" and atrp and atrp > HI_ATR and in_profit and a14:
        tp1 = round(price + 2*a14, 4); tp2 = round(price + 4*a14, 4)
        return {"type": "TRANCHE", "price": round(price,4), "atr_pct": round(atrp*100,2),
                "tp1": tp1, "tp2": tp2,
                "note": "ATR%>10% + w zysku: stop wytrzasalby. 1/3 Sell Limit @tp1, 1/3 @tp2, 1/3 runner."}

    if bucket == "CORE":
        lvl = s200 if s200 else price*0.80
        return {"type":"STOP","stop":round(lvl,4),"price":round(price,4),"atr_pct":(round(atrp*100,2) if atrp else None),
                "method":"CORE: SMA200/-20% disaster","notes":["pasywny rdzen, nie trailuj"]}

    if bucket == "TREND":
        k = 4 if (atrp and atrp > 0.05) else 3
        cand = mn([s50, (hi20 - k*a14) if a14 else None])
        method = f"TREND: min[SMA50, high20-{k}xATR14], clamp [-20%,-5%]"
        if atrp and atrp > HI_ATR and not in_profit:
            notes.append("ATR%>10% ale pod kreska -> szeroki stop (nie transze)")
    elif bucket == "SPIKE":
        cand = mx([s20, (hi10 - 1.5*a7) if a7 else None, hi10*0.82])
        method = "SPIKE: max[SMA20, high10-1.5xATR7, -18% od high]"
    elif bucket == "MEANREVERT":
        cand = (lo20 - 0.5*a14) if a14 else lo20*0.97
        method = "MEANREVERT: dolek20 - 0.5xATR14"
        notes.append("bez agresywnego ratchetu")
    else:  # SPEC
        cand = price*0.88
        method = "SPEC: -12% staly"

    # spojnosc: jesli uczciwy stop schodzi PONIZEJ -20% od ceny
    if cand is not None and cand < price*(1-CAP) and bucket == "TREND":
        if atrp and atrp > HI_ATR:
            notes.append("uczciwy stop < -20% i ATR%>10% -> nie-trailowalna; transze gdy w zysku")
        else:
            notes.append("stop oparty o limit -20% (szeroki, OK do rideowania)")
    stop = clamp_stop(cand, price)
    return {"type":"STOP","stop":stop,"price":round(price,4),
            "atr_pct":(round(atrp*100,2) if atrp else None),"method":method,"notes":notes}

def audit(pos, prev):
    xtb = pos.get("xtb", pos["yahoo"]); avg = pos.get("avg_cost")
    df = fetch(pos["yahoo"])
    if df is None or len(df) < 25:
        return {"xtb": xtb, "error": "BRAK/za malo danych"}
    prev_bucket = prev.get(xtb, {}).get("bucket")
    bucket = pos.get("bucket") or classify(df, pos.get("is_etf", False), prev_bucket)
    p = plan(df, bucket, avg)
    price = p["price"]
    prior = prev.get(xtb, {})

    out = {"xtb": xtb, "bucket": bucket, "price": price, "atr_pct": p.get("atr_pct"), "type": p["type"]}

    if p["type"] == "TRANCHE":
        # ratchet TP w gore, z progiem MIN_MOVE (tlumi szum)
        ptp1 = prior.get("tp1"); ptp2 = prior.get("tp2")
        tp1 = _ratchet(p["tp1"], ptp1, price)
        tp2 = _ratchet(p["tp2"], ptp2, price)
        out.update({"tp1": tp1, "tp2": tp2, "note": p["note"]})
        if prior.get("type") != "TRANCHE":
            out["change"] = f"-> TRANSZE (z {prior.get('type','nowy')}): 1/3@{tp1} 1/3@{tp2} 1/3 runner"
        elif (tp1, tp2) != (ptp1, ptp2):
            out["change"] = f"PODNIES TP: tp1 {ptp1}->{tp1}, tp2 {ptp2}->{tp2}"
        else:
            out["change"] = "BEZ ZMIAN (transze)"
        return out

    stop = p["stop"]
    cur = prior.get("stop")
    # ratchet stopa w gore, z progiem MIN_MOVE (tlumi szum typu +0.0003)
    if cur is None:
        new = stop; act = "USTAW"
    else:
        new = _ratchet(stop, cur, price)
        act = "PODNIES" if (new is not None and new > cur) else "BEZ ZMIAN"
    exit_now = (new is not None and new >= price)
    if exit_now:
        act = "PRZEGLAD (pod SMA200)" if bucket == "CORE" else "WYJDZ TERAZ"
    out.update({"stop": new, "method": p["method"], "notes": p.get("notes", []),
                "dist_pct": round((price-new)/price*100, 1) if (new and price) else None,
                "action": act, "exit_now": exit_now,
                "locked": bool(avg is not None and not exit_now and new is not None and new > avg)})
    # opis zmiany tygodniowej
    if prior.get("type") == "TRANCHE":
        out["change"] = f"-> STOP (z transz): {act} @ {new}"
    elif cur is None:
        out["change"] = f"USTAW @ {new}"
    elif act == "PODNIES":
        out["change"] = f"PODNIES {cur} -> {new}  (+{(new/cur-1)*100:.1f}%)"
    elif exit_now:
        out["change"] = f"WYJDZ: stop {new} >= cena {price}"
    else:
        out["change"] = "BEZ ZMIAN"
    if prior.get("bucket") and prior["bucket"] != bucket:
        out["change"] = f"BUCKET {prior['bucket']}->{bucket} | " + out["change"]
    return out

def build_html(rows, last_run, n, today):
    def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    th = "padding:6px 10px;text-align:left;border-bottom:2px solid #ccc;"
    td = "padding:6px 10px;border-bottom:1px solid #eee;"
    changed = [r for r in rows if "error" not in r and not r.get("change", "").startswith("BEZ ZMIAN")]
    unchanged = [r for r in rows if "error" not in r and r.get("change", "").startswith("BEZ ZMIAN")]
    errors = [r for r in rows if "error" in r]

    html = [f"""<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1a1a1a;">
<h2 style="margin-bottom:4px;">Position Auditor &mdash; {esc(today)}</h2>
<p style="color:#666;margin-top:0;">Poprzedni run: {esc(last_run)} | Pozycji: {n}</p>"""]

    html.append(f'<h3 style="margin-bottom:6px;">Zmiany do przeklikania ({len(changed)})</h3>')
    if changed:
        html.append('<table style="border-collapse:collapse;width:100%;">')
        html.append(f'<tr><th style="{th}">Ticker</th><th style="{th}">Bucket</th><th style="{th}">Zmiana</th></tr>')
        for r in changed:
            flag = r.get("exit_now")
            row_style = "background:#fdecea;" if flag else ""
            html.append(f'<tr style="{row_style}"><td style="{td}"><b>{esc(r["xtb"])}</b></td>'
                        f'<td style="{td}">{esc(r["bucket"])}</td>'
                        f'<td style="{td}">{esc(r.get("change",""))}</td></tr>')
        html.append("</table>")
    else:
        html.append('<p style="color:#666;">Brak akcji do podjecia.</p>')

    if errors:
        html.append('<h3 style="margin-bottom:6px;">Błędy danych</h3><ul>')
        for r in errors:
            html.append(f'<li>{esc(r["xtb"])}: {esc(r["error"])}</li>')
        html.append("</ul>")

    if unchanged:
        names = ", ".join(esc(r["xtb"]) for r in unchanged)
        html.append(f'<p style="color:#666;"><b>Bez zmian ({len(unchanged)}):</b> {names}</p>')

    html.append('<h3 style="margin-bottom:6px;">Pełny stan</h3>')
    html.append('<table style="border-collapse:collapse;width:100%;">')
    html.append(f'<tr><th style="{th}">Ticker</th><th style="{th}">Typ</th><th style="{th}">Poziomy</th><th style="{th}">Metoda</th></tr>')
    for r in rows:
        if "error" in r: continue
        if r["type"] == "TRANCHE":
            lvl = f"cena {r['price']} | 1/3@{r['tp1']} 1/3@{r['tp2']} 1/3 runner"
        else:
            flag = " ⚠️WYJŚCIE" if r["exit_now"] else (" 🔒zysk zabezp." if r["locked"] else "")
            lvl = f"stop {r['stop']} ({r['dist_pct']}%){flag}"
        html.append(f'<tr><td style="{td}">{esc(r["xtb"])}</td><td style="{td}">{esc(r["type"])}</td>'
                    f'<td style="{td}">{esc(lvl)}</td><td style="{td}">{esc(r.get("method") or r.get("note",""))}</td></tr>')
    html.append("</table></body></html>")
    return "\n".join(html)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("holdings")
    ap.add_argument("--state", default=STATE_FILE)
    ap.add_argument("--html-out", default="audit_report.html")
    args = ap.parse_args()
    holdings = json.load(open(args.holdings, encoding="utf-8"))
    prev = {}
    if os.path.exists(args.state):
        try: prev = json.load(open(args.state, encoding="utf-8"))
        except Exception: prev = {}

    rows = [audit(p, prev) for p in holdings]
    print("="*74); print("POSITION_AUDITOR v2"); print(f"DATE: {datetime.now().strftime('%Y-%m-%d %a')}")
    last = prev.get("_meta", {}).get("date", "brak")
    print(f"POPRZEDNI RUN: {last} | POZYCJI: {len(holdings)}")
    print("-"*74)
    print("# ZMIANY OD OSTATNIEGO RUNU")
    for r in rows:
        if "error" in r: print(f"  {r['xtb']:10s} ERROR: {r['error']}"); continue
        print(f"  {r['xtb']:10s} [{r['bucket']:10s}] {r.get('change','')}")
    print("-"*74)
    print("# PELNY STAN")
    for r in rows:
        if "error" in r: continue
        if r["type"] == "TRANCHE":
            print(f"  {r['xtb']:10s} TRANSZE | cena {r['price']} | Sell Limit 1/3@{r['tp1']} 1/3@{r['tp2']} 1/3 runner")
            print(f"             {r['note']}")
        else:
            flag = " [!WYJSCIE]" if r["exit_now"] else (" [zysk zabezp.]" if r["locked"] else "")
            print(f"  {r['xtb']:10s} STOP {r['stop']} ({r['dist_pct']}%) | {r['action']}{flag} | {r['method']}")
            for n in r.get("notes", []): print(f"             - {n}")
    print("="*74)

    # zapis stanu
    state = {"_meta": {"date": datetime.now().strftime("%Y-%m-%d")}}
    for r in rows:
        if "error" in r: continue
        e = {"bucket": r["bucket"], "type": r["type"]}
        if r["type"] == "TRANCHE": e.update({"tp1": r["tp1"], "tp2": r["tp2"]})
        else: e["stop"] = r["stop"]
        state[r["xtb"]] = e
    json.dump(state, open(args.state, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Stan zapisany -> {args.state}")

    html = build_html(rows, last, len(holdings), datetime.now().strftime("%Y-%m-%d %a"))
    open(args.html_out, "w", encoding="utf-8").write(html)
    print(f"HTML report zapisany -> {args.html_out}")

if __name__ == "__main__":
    main()
