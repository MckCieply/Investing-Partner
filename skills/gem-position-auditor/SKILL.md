# AGENT 6: POSITION AUDITOR — moduł wyjść (Gem Inwestycyjny) — v2

> Dołącz do `gem-inwestycyjny/SKILL.md`. Agenci 1–5 to silnik WEJŚĆ
> (bezstanowy, w przód). Position Auditor to silnik WYJŚĆ: **stanowy, patrzy
> wstecz na to, co trzymasz.** Uruchamiany osobno: `audytuj pozycje` / `odpal stopy`.
> v2: progi ATR%, transze dla parabol, histereza bucketów, **diff tygodniowy ze stanu**.

---

## ZASADA NACZELNA

Nie ma jednego stopa dla całego portfela. Metoda jest wybierana per aktywo na
podstawie ROLI (bucket) i WIABILNOŚCI ATR (`ATR% = ATR14/cena`). Dwa odrębne
mechanizmy, z dwóch stron pozycji:

- **STOP LOSS broni DOŁU** — sprzedaje, gdy cena spada. Sell Stop PONIŻEJ ceny.
- **TRANSZE zdejmują GÓRĘ** — sprzedajesz kawałek, gdy cena rośnie. Sell Limit POWYŻEJ ceny.

To nie są warianty tej samej rzeczy. Parabola dostaje transze ZAMIAST stopa,
bo każdy stop dość ciasny, by ją chronić, jest dość ciasny, by ją whipsawnąć.

---

## REGUŁY STOPÓW (uzgodnione, empirycznie skalibrowane)

- **CORE** (pasywne ETF) — bez trailingu. SMA200 lub −20% disaster. Akcji nie dotyczy.
- **TREND, ATR% ≤ 5%** (spokojny grind) — `min[SMA50, high20 − 3×ATR14]`, clamp do [−20%, −5%].
- **TREND, ATR% 5–10%** (zmienny grind: AMD, MOD, ONTO) — `min[SMA50, high20 − 4×ATR14]`, clamp do [−20%, −5%].
- **TREND, ATR% > 10%** (parabola: MRVL):
  - **w zysku → PLAN TRANSZ**, bez stopa: 1/3 Sell Limit @ `cena+2×ATR`, 1/3 @ `cena+4×ATR`, 1/3 runner.
  - **pod kreską → szeroki stop** jak w tierze 5–10% (nie transze — nie ma czego odkładać w górę).
- **SPIKE** — `max[SMA20, high10 − 1,5×ATR7, −18% od high]`. Ciasno (spike wraca gwałtownie).
- **MEANREVERT** (Nokia, szarpane small-capy) — `dolek20 − 0,5×ATR14`, clamp. Bez agresywnego ratchetu.
- **SPEC** (teza binarna) — `−12%` stały, bez trailingu.

**Globalnie:**
- `min[...]` zamiast `max[...]` w TREND → bierzemy SZERSZY (niższy) poziom.
  Powód empiryczny: ze spod SMA50 w żywym trendzie wraca się często (Twoje
  nazwy: ONTO 85%, MOD 73%, MRVL 67% wrotów ≤10 sesji), więc stop na/tuż-pod
  SMA50 whipsawuje. Stop musi siedzieć GŁĘBIEJ, z buforem.
- **Clamp [−20%, −5%]:** stop nigdy nie ciaśniej niż −5% (szum) ani luźniej niż
  −20% (katastrofa). Jeśli uczciwy stop schodzi pod −20% przy ATR%>10% → nazwa
  nie-trailowalna → transze.
- **Ratchet tylko w górę.** Stop nigdy nie schodzi. TP-transze też tylko w górę.
- **Stop ≥ cena → `WYJDŹ TERAZ`** (trend pękł).

## HISTEREZA BUCKETÓW (zapobiega miganiu co tydzień)

- Wejście w **SPIKE**: `ret20 > 45%`. Wyjście ze SPIKE: `ret20 < 35%` (pas martwy 35–45%).
- **SPIKE → TREND**: impet wygasł (`ret20 < 35%`), cena nadal nad SMA50 → luzujesz stop z ciasnego na szeroki.
- **SPIKE → MEANREVERT**: cena spadła POD SMA50 → to już nie momentum, tylko spadająca nazwa.
- **TREND → SPIKE**: spokojna nazwa znów `ret20 > 45%` → zaciskasz.

---

## MECHANIKA XTB IKE (wbudowane ograniczenia)

- **Brak auto-trailingu na akcjach/ETF.** Trailing = ręczny: Sell Stop, który
  **podnosisz raz w tygodniu** (ratchet w górę).
- **Stop = osobne zlecenie Sell Stop** PONIŻEJ ceny. Sell **Limit** = take profit POWYŻEJ. Nie myl.
- **Stop wykonuje się po cenie rynkowej** → poślizg na gapie. Stąd clamp i bufor ATR.
- **FIFO:** częściowy Sell Stop/Limit zamyka NAJSTARSZY lot, nie wybrany.
- **SL i TP dzielą tę samą pulę wolumenu** — przy transzach rozdziel sztuki świadomie.
- Wygaśnięcie zlecenia: **wyłączone** (GTC), żeby stop nie znikał.

---

## DIFF TYGODNIOWY (stan między uruchomieniami)

Skrypt czyta `stops_state.json` z poprzedniego runu i na górze outputu drukuje
sekcję **# ZMIANY OD OSTATNIEGO RUNU** — dokładnie co się zmieniło:
`USTAW @ X`, `PODNIEŚ X → Y (+Z%)`, `BEZ ZMIAN`, `WYJDŹ`, zmiana bucketa
(`BUCKET SPIKE→TREND`), przejście na transze. Po runie zapisuje nowy stan.
Dzięki temu co weekend widzisz tylko delty do przeklikania, nie cały book od zera.

---

## HARMONOGRAM — jak ustawić „co weekend"

Trzy poziomy automatyzacji, od najprostszego:

1. **Przypomnienie (półautomat):** cotygodniowy budzik/reminder (niedziela 18:00).
   Dostajesz ping → otwierasz czat → `audytuj pozycje` → Claude odpala skrypt →
   przeklikujesz delty w XTB. Claude w czacie **nie odpali się sam** — musi być
   Twój trigger.
2. **Pełna automatyzacja skryptu (zalecane — masz infra):** `position_auditor.py`
   jest samodzielny, więc zaplanuj SAM SKRYPT, bez Claude'a w pętli:
   - **Windows Task Scheduler** (Twój self-hosted runner): zadanie co niedzielę
     `python position_auditor.py holdings.json` → output do pliku/maila.
   - **GitHub Actions** (masz doświadczenie): `on: schedule: - cron: '0 17 * * 0'`
     (niedziela 17:00 UTC), commituje `stops_state.json` i wypluwa kartę w logu/artefakcie.
   - **cron** (Linux/WSL): `0 18 * * 0 cd ~/gem && python position_auditor.py holdings.json`
   Wtedy w niedzielę masz gotową kartę stopów; Ty tylko przeklikujesz XTB.
3. **Claude Code na schedule** — jeśli odpalasz przez Claude Code, ten sam cron
   wywołuje pipeline w trybie agentowym.

Realnie: obliczenia nie potrzebują Claude'a — to czysty Python. Claude jest
potrzebny tylko gdy chcesz, żeby Director ubrał surowy output w narrację. Do
samego liczenia stopów wystarczy cron/Task Scheduler + przeklik w appce.

---

## WORKFLOW

1. **`holdings.json`** (eksport otwartych pozycji z XTB albo ręcznie):
```json
[
  {"xtb":"AMD.US",  "yahoo":"AMD",      "avg_cost":100.00},
  {"xtb":"NOKIA.FI","yahoo":"NOKIA.HE", "avg_cost":50.00},
  {"xtb":"MRVL.US", "yahoo":"MRVL", "bucket":"TREND", "avg_cost":150.00}
]
```
Pola: `xtb`, `yahoo`, `avg_cost`; opcjonalnie `is_etf`, `bucket` (ręczne nadpisanie).

2. **Odpal:**
```bash
pip install yfinance pandas numpy --break-system-packages 2>/dev/null
python position_auditor.py holdings.json          # stan w stops_state.json
```

3. **Przeklik:** sekcja ZMIANY mówi co ruszyć. `USTAW`/`PODNIEŚ` → edytuj Sell Stop
   w XTB. `TRANSZE` → ustaw Sell Limity na częściach wolumenu. `WYJDŹ TERAZ` → zamknij ręcznie.

---

## SKRYPT (position_auditor.py)

```python
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
        # ratchet TP w gore
        ptp1 = prior.get("tp1"); ptp2 = prior.get("tp2")
        tp1 = max(p["tp1"], ptp1) if ptp1 else p["tp1"]
        tp2 = max(p["tp2"], ptp2) if ptp2 else p["tp2"]
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
    # ratchet stopa w gore
    if cur is None:
        new = stop; act = "USTAW"
    elif stop is not None and stop > cur:
        new = stop; act = "PODNIES"
    else:
        new = cur; act = "BEZ ZMIAN"
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("holdings")
    ap.add_argument("--state", default=STATE_FILE)
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

if __name__ == "__main__":
    main()
```

---

## OBSŁUGA BŁĘDÓW
- Brak/za mało danych z Yahoo (<25 sesji) → `BRAK danych`, pomiń (GPW small-capy bywają dziurawe).
- Stop ≥ cena → `WYJDŹ TERAZ`, nigdy „zysk zabezpieczony".
- Ratchet: `nowy = max(policzony, poprzedni)`. Stop NIGDY w dół.
- Pierwszy run bez stanu → wszystko `USTAW`; od drugiego runu pełny diff.
