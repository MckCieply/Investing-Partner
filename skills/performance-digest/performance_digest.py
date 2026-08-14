#!/usr/bin/env python3
"""
performance_digest.py - miesieczny przeglad skutecznosci obu pipeline'ow.

Deterministyczny (bez LLM). Czyta trzy logi, ktore oba pipeline'y juz pisza,
i liczy z nich metryki, ktorych sam Weekly Tracker nie liczy (on tylko
aktualizuje status per wiersz, nic nie agreguje w czasie):

  - .claude/skills/gem-inwestycyjny/history/recommendations.csv
      lejek Scout->Quant->Alpha->Auditor->Director, win rate, kalibracja
      timingu, i najwazniejsze: czy odrzucone/wstrzymane tickery radza sobie
      GORZEJ niz kupione (filtr dodaje wartosc) czy LEPIEJ (filtr kosztuje
      edge) - Tracker sledzi cene dla WSZYSTKICH wierszy, nie tylko kupionych.
  - closed_positions.csv
      zamkniete pozycje Position Auditora: win rate, pnl per bucket/powod.
  - .claude/skills/gem-inwestycyjny/history/scout_tickers.csv
      nowosc/powtarzalnosc propozycji Scouta + konwersja Scout->recommendations.

Benchmark: SPY, ten sam mechanizm co backtest/ (edge = zwrot pozycji - zwrot
SPY w TYM SAMYM oknie czasowym run_date->last_checked_date), nie surowy zwrot
- zeby nie mylic bety rynku z alfa pipeline'u. Wymaga yfinance/pandas (juz w
requirements.txt); jesli niedostepne albo siec padnie, sekcje po prostu
pokazuja surowy zwrot z jawna adnotacja "brak benchmarku SPY".

Male n (kilkanascie wierszy przez pierwsze miesiace) -> raport explicite
oznacza kazda sekcje/werdykt jako orientacyjny, dopoki n nie urosnie. Nie
udaje statystycznej istotnosci, ktorej backtest/README.md wymaga przed
jakimkolwiek werdyktem PASS/FAIL - to nie jest test setupu, to log jednego
dzialajacego pipeline'u.

Uzycie:
  python3 skills/performance-digest/performance_digest.py > report.md
  python3 skills/performance-digest/performance_digest.py \
      --recommendations PATH --closed PATH --scout PATH
"""
import argparse
import csv
import os
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, date
from statistics import mean, median

try:
    import yfinance as yf
except ImportError:
    yf = None

MIN_N_NOTE = 20  # pod tym n sekcja dostaje etykiete "orientacyjne"
EDGE_MARGIN = 2.0  # pp - ponizej tego traktujemy edge jako "w okolicach benchmarku"

TIMING_DAYS = {"TERAZ": 28, "WKROTCE": 91, "ODLEGLY": 182}
BOUGHT_OUTCOMES = {"BOUGHT_FULL", "BOUGHT_HALF"}
# FILTERED_OUTCOMES = kazdy ticker, ktory NIE zostal kupiony - obejmuje zarowno
# odrzucenia PO bramce Quanta (REJECTED_ALPHA/AUDITOR_*/RESERVE_ALPHA, tickery
# ktore mialy ZIELONE_SWIATLO: TAK i odpadly u Alphy/Auditora/Directora) jak i
# QUANT_REJECTED_* (tickery odrzucone przez sama bramke techniczna Quanta -
# SMA50/SMA200/RSI - zanim Alpha je w ogole zobaczyla). Trzymane w jednej grupie
# (nie osobno per filtr) - sekcja "Filtr Alpha/Auditor" porownuje po prostu
# KUPIONE vs WSZYSTKO INNE.
FILTERED_OUTCOMES = {
    "REJECTED_ALPHA",
    "AUDITOR_VETO",
    "AUDITOR_HOLD",
    "RESERVE_ALPHA",
    "QUANT_REJECTED_SMA50",
    "QUANT_REJECTED_SMA200",
    "QUANT_REJECTED_RSI",
    "QUANT_REJECTED_ERROR",
}
RESOLVED_STATUSES = ("HIT_TARGET", "STOPPED")


# ---------------------------------------------------------------- helpers --

def normalize_pl(s):
    """Uppercase + strip polish diacritics, zeby ODLEGLY/ODLEGŁY/SREDNIA/ŚREDNIA byly tym samym kluczem."""
    if not s:
        return ""
    table = str.maketrans("óÓłŁęĘśŚżŻźŹćĆńŃąĄ", "oOlLeEsSzZzZcCnNaA")
    s = s.translate(table)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s.strip().upper()


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def to_date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def read_csv(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fmt_pct(x, digits=1):
    return f"{x:+.{digits}f}%" if x is not None else "brak danych"


def fmt_pp(x, digits=1):
    return f"{x:+.{digits}f} pp" if x is not None else "brak danych"


def n_flag(n):
    return " *(mała próbka, orientacyjne)*" if n < MIN_N_NOTE else ""


def verdict(value, small_n, thresholds, labels):
    """thresholds=(lo,hi), labels=(below,mid,above). value=None lub small_n -> nieznany."""
    if small_n:
        return "⚪ za wcześnie"
    if value is None:
        return "⚪ brak danych"
    lo, hi = thresholds
    if value < lo:
        return labels[0]
    if value > hi:
        return labels[2]
    return labels[1]


# ------------------------------------------------------------- SPY benchmark --

def fetch_spy_close():
    """Zwraca pandas.Series (Close, indeks=data) albo None jesli SPY niedostepne."""
    if yf is None:
        return None
    try:
        df = yf.Ticker("SPY").history(period="2y", auto_adjust=True)
        if df is None or df.empty:
            return None
        idx = df.index
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        df.index = idx.normalize()
        return df["Close"]
    except Exception:
        return None


def spy_price_on(spy_close, d):
    """Cena SPY na ostatniej sesji <= d (weekend/swieto -> ostatnia znana)."""
    if spy_close is None or d is None:
        return None
    try:
        import pandas as pd
        ts = pd.Timestamp(d)
        idx = spy_close.index[spy_close.index <= ts]
        if len(idx) == 0:
            return None
        return float(spy_close.loc[idx[-1]])
    except Exception:
        return None


def spy_return_pct(spy_close, start_date, end_date):
    p0 = spy_price_on(spy_close, start_date)
    p1 = spy_price_on(spy_close, end_date)
    if p0 is None or p1 is None or p0 == 0:
        return None
    return (p1 / p0 - 1) * 100


def enrich_recommendation_edges(rec_rows, spy_close):
    """Dopisuje do kazdego wiersza 'raw_pct' i 'edge_pct' (moga byc None)."""
    for r in rec_rows:
        raw = to_float(r.get("pct_change_since_entry"))
        run_date = to_date(r.get("run_date"))
        mark_date = to_date(r.get("last_checked_date"))
        spy_ret = spy_return_pct(spy_close, run_date, mark_date) if (run_date and mark_date) else None
        r["_raw_pct"] = raw
        r["_spy_pct"] = spy_ret
        r["_edge_pct"] = (raw - spy_ret) if (raw is not None and spy_ret is not None) else None
    return rec_rows


def group_edge_stats(rows):
    n = len(rows)
    raw = [r["_raw_pct"] for r in rows if r.get("_raw_pct") is not None]
    spy = [r["_spy_pct"] for r in rows if r.get("_spy_pct") is not None]
    edge = [r["_edge_pct"] for r in rows if r.get("_edge_pct") is not None]
    resolved = [r for r in rows if (r.get("status") or "").strip() in RESOLVED_STATUSES]
    wins = sum(1 for r in resolved if r.get("status", "").strip() == "HIT_TARGET")
    win_rate = (wins / len(resolved) * 100) if resolved else None
    return {
        "n": n,
        "avg_raw": mean(raw) if raw else None,
        "avg_spy": mean(spy) if spy else None,
        "avg_edge": mean(edge) if edge else None,
        "n_edge": len(edge),
        "win_rate": win_rate,
        "n_resolved": len(resolved),
    }


# ------------------------------------------------------------------ sections --

def section_summary(rec_rows, closed_rows, scout_rows, spy_available):
    lines = ["## Podsumowanie\n"]
    if not spy_available:
        lines.append(
            "⚠️ **Benchmark SPY niedostępny w tym runie** (brak yfinance/pandas albo "
            "sieci) — poniższe wiersze porównawcze pokazują surowy zwrot, nie edge.\n"
        )

    bought = [r for r in rec_rows if (r.get("outcome") or "").strip() in BOUGHT_OUTCOMES]
    filtered = [r for r in rec_rows if (r.get("outcome") or "").strip() in FILTERED_OUTCOMES]
    b_stats = group_edge_stats(bought)
    f_stats = group_edge_stats(filtered)

    filter_delta = None
    if b_stats["avg_edge"] is not None and f_stats["avg_edge"] is not None:
        filter_delta = b_stats["avg_edge"] - f_stats["avg_edge"]

    # kalibracja timingu - sredni relatywny blad wazony liczba probek
    buckets = defaultdict(list)
    for r in rec_rows:
        bucket = normalize_pl(r.get("timing_bucket"))
        rd, dd = to_date(r.get("run_date")), to_date(r.get("date_resolved"))
        if bucket in TIMING_DAYS and rd and dd:
            buckets[bucket].append((dd - rd).days)
    timing_n = sum(len(v) for v in buckets.values())
    rel_errs = []
    for bucket, days in buckets.items():
        est = TIMING_DAYS[bucket]
        rel_errs.extend(abs(d - est) / est for d in days)
    avg_rel_err = mean(rel_errs) if rel_errs else None

    # scout repeat rate
    tickers = [r.get("ticker_yahoo", "").strip() for r in scout_rows if r.get("ticker_yahoo")]
    repeat_rate = None
    if tickers:
        counts = Counter(tickers)
        repeated = sum(c for c in counts.values() if c > 1)
        repeat_rate = repeated / len(tickers) * 100

    # position auditor - surowy PnL, brak daty otwarcia w logu -> brak edge
    pa_pnl = [to_float(r.get("pnl_pct_est")) for r in closed_rows]
    pa_pnl = [x for x in pa_pnl if x is not None]
    pa_win = (sum(1 for x in pa_pnl if x > 0) / len(pa_pnl) * 100) if pa_pnl else None

    rows = [
        (
            "Kupione rekomendacje (FULL+HALF)",
            f"śr. edge vs SPY: {fmt_pp(b_stats['avg_edge'])}" if b_stats["avg_edge"] is not None
            else f"śr. zwrot: {fmt_pct(b_stats['avg_raw'])} (brak SPY)",
            "SPY, to samo okno run_date→last_checked_date",
            verdict(b_stats["avg_edge"], b_stats["n_edge"] < 5, (-EDGE_MARGIN, EDGE_MARGIN),
                    ("🔴 poniżej SPY", "🟡 w okolicach SPY", "🟢 bije SPY")),
        ),
        (
            "Filtr pipeline'u (Quant/Alpha/Auditor)",
            f"kupione − odrzucone: {fmt_pp(filter_delta)}" if filter_delta is not None
            else "brak danych do porównania",
            "dodatnia delta = filtr (na dowolnym etapie) trafnie odsiewa słabsze setupy",
            verdict(filter_delta, (b_stats["n_edge"] + f_stats["n_edge"]) < 8, (-EDGE_MARGIN, EDGE_MARGIN),
                    ("🔴 filtr kosztuje edge", "🟡 neutralny", "🟢 filtr dodaje wartość")),
        ),
        (
            "Kalibracja timingu (timing_bucket)",
            f"śr. błąd względny: {avg_rel_err * 100:.0f}%" if avg_rel_err is not None else "brak rozstrzygnięć",
            "0% = trafne oszacowanie daty rozstrzygnięcia",
            verdict(avg_rel_err, timing_n < 8, (0.25, 0.5),
                    ("🟢 dobrze skalibrowany", "🟡 częściowo rozkalibrowany", "🔴 mocno rozkalibrowany")),
        ),
        (
            "Position Auditor (zamknięte pozycje)",
            f"win rate: {pa_win:.0f}%, śr. PnL: {fmt_pct(mean(pa_pnl)) if pa_pnl else 'brak danych'}"
            if pa_pnl else "brak zamkniętych pozycji",
            "brak daty otwarcia w logu → brak edge-adjusted porównania",
            verdict(pa_win, len(pa_pnl) < 10, (45, 55),
                    ("🔴 poniżej 45% win rate", "🟡 w okolicach 50/50", "🟢 powyżej 55% win rate")),
        ),
        (
            "Scout — różnorodność propozycji",
            f"{repeat_rate:.0f}% propozycji to powtórki tickera" if repeat_rate is not None else "brak danych",
            "niski % = Scout znajduje nowe tezy, nie recykluje",
            verdict(repeat_rate, len(scout_rows) < 15, (15, 35),
                    ("🟢 dobra różnorodność", "🟡 umiarkowane powtórki", "🔴 dużo powtórek")),
        ),
    ]

    lines.append("| Obszar | Wynik | Benchmark / punkt odniesienia | Werdykt |")
    lines.append("|---|---|---|---|")
    for area, result, bench, v in rows:
        lines.append(f"| **{area}** | {result} | {bench} | {v} |")
    lines.append("")
    lines.append(
        "⚪ = za mało danych na werdykt (nie \"neutralny wynik\", tylko \"jeszcze nie wiadomo\"). "
        "Progi: edge vs SPY ±2pp, kalibracja timingu ±25%/±50% błędu względnego, "
        "Position Auditor 45–55% win rate, Scout 15–35% powtórek — dobrane orientacyjnie, "
        "nie wykalibrowane statystycznie (n na to jeszcze za małe)."
    )
    lines.append("")
    return "\n".join(lines)


def section_funnel(scout_rows, rec_rows):
    scout_dates = {r.get("date", "").strip() for r in scout_rows if r.get("date")}
    scout_tickers = {r.get("ticker_yahoo", "").strip() for r in scout_rows if r.get("ticker_yahoo")}
    rec_tickers = {r.get("ticker_yahoo", "").strip() for r in rec_rows if r.get("ticker_yahoo")}
    converted = scout_tickers & rec_tickers
    conv_rate = (len(converted) / len(scout_tickers) * 100) if scout_tickers else None

    outcome_counts = Counter((r.get("outcome") or "INNE/BRAK").strip() for r in rec_rows)

    lines = ["## 1. Lejek decyzyjny — Scout → Quant → Alpha/Auditor → Director\n"]
    lines.append(
        f"Scout zaproponował **{len(scout_rows)}** tickerów w {len(scout_dates)} runach "
        f"({len(scout_tickers)} unikalnych).{n_flag(len(scout_rows))}"
    )
    if conv_rate is not None:
        lines.append(
            f"\nZ tego **{len(rec_tickers)}** unikalnych ({conv_rate:.0f}%) zostało ocenionych "
            f"przez Quanta i trafiło do `recommendations.csv` — niezależnie od wyniku bramki "
            f"(`ZIELONE_SWIATLO: TAK` i `NIE` oba się logują):\n"
        )
    lines.append("| Outcome | n |")
    lines.append("|---|---|")
    for outcome, cnt in sorted(outcome_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {outcome} | {cnt} |")
    lines.append("")
    return "\n".join(lines)


def section_filter_value(rec_rows, spy_available):
    lines = ["## 2. Rekomendacje vs SPY — czy filtr pipeline'u dodaje wartość?\n"]
    lines.append(
        "Weekly Tracker aktualizuje cenę dla WSZYSTKICH tickerów w logu, nie tylko "
        "kupionych — więc można porównać zwrot (i edge vs SPY w tym samym oknie "
        "czasowym) tickerów faktycznie kupionych względem wszystkich odrzuconych na "
        "dowolnym etapie: technicznie przez Quanta (SMA50/SMA200/RSI, `QUANT_REJECTED_*`) "
        "albo później przez Alphę/Auditora (`REJECTED_ALPHA`/`AUDITOR_VETO`/"
        "`AUDITOR_HOLD`/`RESERVE_ALPHA`). Grupa ODRZUCONE/WSTRZYMANE poniżej łączy oba "
        "źródła — to jeden filtr pipeline'u widziany z zewnątrz, nie próba rozdzielenia "
        "wkładu każdego etapu z osobna.\n"
    )

    bought = [r for r in rec_rows if (r.get("outcome") or "").strip() in BOUGHT_OUTCOMES]
    filtered = [r for r in rec_rows if (r.get("outcome") or "").strip() in FILTERED_OUTCOMES]

    if spy_available:
        lines.append("| Grupa | n | śr. zwrot pozycji | śr. zwrot SPY (to samo okno) | śr. edge vs SPY | win rate |")
        lines.append("|---|---|---|---|---|---|")
        for label, rows in (("KUPIONE (FULL+HALF)", bought), ("ODRZUCONE/WSTRZYMANE", filtered)):
            s = group_edge_stats(rows)
            win_str = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "brak rozstrzygniętych"
            lines.append(
                f"| {label} | {s['n']} | {fmt_pct(s['avg_raw'])} | {fmt_pct(s['avg_spy'])} | "
                f"{fmt_pp(s['avg_edge'])} | {win_str} |"
            )
    else:
        lines.append("| Grupa | n | śr. zwrot pozycji | win rate |")
        lines.append("|---|---|---|---|")
        for label, rows in (("KUPIONE (FULL+HALF)", bought), ("ODRZUCONE/WSTRZYMANE", filtered)):
            s = group_edge_stats(rows)
            win_str = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "brak rozstrzygniętych"
            lines.append(f"| {label} | {s['n']} | {fmt_pct(s['avg_raw'])} | {win_str} |")
        lines.append("\n*(SPY niedostępne w tym runie — patrz Podsumowanie)*")

    lines.append("")
    n_total = len(bought) + len(filtered)
    lines.append(
        "**Interpretacja:** jeśli KUPIONE bije ODRZUCONE — filtr pipeline'u (Quant + "
        "Alpha/Auditor razem) łapie gorsze setupy zanim wejdziemy. Jeśli odwrotnie — "
        "filtr odcina zwycięzców (rola analogiczna do placebo w `backtest/`: to "
        "negative control, nie wyrok)."
        f"{n_flag(n_total)}"
    )
    lines.append("")
    return "\n".join(lines)


def section_timing(rec_rows):
    lines = ["## 3. Kalibracja timingu (timing_bucket vs rzeczywisty czas do rozstrzygnięcia)\n"]
    buckets = defaultdict(list)
    for r in rec_rows:
        bucket = normalize_pl(r.get("timing_bucket"))
        run_date = to_date(r.get("run_date"))
        resolved_date = to_date(r.get("date_resolved"))
        if bucket in TIMING_DAYS and run_date and resolved_date:
            buckets[bucket].append((resolved_date - run_date).days)

    if not buckets:
        lines.append("Brak jeszcze rozstrzygniętych rekomendacji z ustawionym timing_bucket.")
        lines.append("")
        return "\n".join(lines)

    total_n = sum(len(v) for v in buckets.values())
    lines.append(
        "„n rozstrzygniętych” liczy zarówno HIT_TARGET jak i STOPPED — mierzy czas do "
        "JAKIEGOKOLWIEK rozstrzygnięcia, nie tylko trafień w target.\n"
    )
    lines.append("| timing_bucket | n rozstrzygniętych | oszacowanie (dni) | rzeczywiste śr. (dni) | delta |")
    lines.append("|---|---|---|---|---|")
    for bucket, est_days in TIMING_DAYS.items():
        days = buckets.get(bucket, [])
        if not days:
            continue
        actual = mean(days)
        delta = actual - est_days
        lines.append(f"| {bucket} | {len(days)} | {est_days} | {actual:.0f} | {delta:+.0f} |")
    lines.append(f"\n{n_flag(total_n)}")
    lines.append("")
    return "\n".join(lines)


def section_conviction(rec_rows):
    lines = ["## 4. Konwikcja Alphy vs wynik\n"]
    groups = defaultdict(list)
    for r in rec_rows:
        conv = normalize_pl(r.get("conviction"))
        if conv:
            groups[conv].append(r)
    if not groups:
        lines.append("Brak danych o konwikcji.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Konwikcja | n | win rate (rozstrzygnięte) | śr. zwrot pozycji |")
    lines.append("|---|---|---|---|")
    for conv in ("WYSOKA", "SREDNIA", "NISKA"):
        rows = groups.get(conv, [])
        if not rows:
            continue
        s = group_edge_stats(rows)
        win_str = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "brak rozstrzygniętych"
        lines.append(f"| {conv} | {s['n']} | {win_str} | {fmt_pct(s['avg_raw'])} |")
    lines.append(f"\n{n_flag(len(rec_rows))}")
    lines.append("")
    return "\n".join(lines)


def section_position_auditor(closed_rows):
    lines = ["## 5. Position Auditor — zamknięte pozycje\n"]
    if not closed_rows:
        lines.append("Brak zamkniętych pozycji jeszcze (`closed_positions.csv` pusty/brak).")
        lines.append("")
        return "\n".join(lines)

    lines.append(
        "*Log nie zawiera daty otwarcia pozycji, więc poniżej jest surowy PnL, nie "
        "edge vs SPY jak w sekcji 2 — nie da się dopasować okna porównawczego.*\n"
    )

    n = len(closed_rows)
    pnl = [to_float(r.get("pnl_pct_est")) for r in closed_rows]
    pnl = [x for x in pnl if x is not None]
    wins = sum(1 for x in pnl if x > 0)
    lines.append(
        f"n={n}{n_flag(n)} | win rate: {(wins / len(pnl) * 100):.0f}% | "
        f"śr. PnL: {fmt_pct(mean(pnl)) if pnl else 'brak danych'} | "
        f"mediana PnL: {fmt_pct(median(pnl)) if pnl else 'brak danych'}"
    )
    lines.append("")

    by_reason = defaultdict(list)
    by_bucket = defaultdict(list)
    for r in closed_rows:
        p = to_float(r.get("pnl_pct_est"))
        if p is None:
            continue
        by_reason[(r.get("reason") or "BRAK").strip()].append(p)
        by_bucket[(r.get("bucket") or "BRAK").strip()].append(p)

    lines.append("| Powód zamknięcia | n | śr. PnL |")
    lines.append("|---|---|---|")
    for reason, vals in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"| {reason} | {len(vals)} | {fmt_pct(mean(vals))} |")
    lines.append("")

    lines.append("| Bucket | n | śr. PnL |")
    lines.append("|---|---|---|")
    for bucket, vals in sorted(by_bucket.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"| {bucket} | {len(vals)} | {fmt_pct(mean(vals))} |")
    lines.append("")
    return "\n".join(lines)


def section_scout(scout_rows):
    lines = ["## 6. Scout — nowość i powtarzalność\n"]
    if not scout_rows:
        lines.append("Brak danych Scouta.")
        lines.append("")
        return "\n".join(lines)

    tickers = [r.get("ticker_yahoo", "").strip() for r in scout_rows if r.get("ticker_yahoo")]
    unique = set(tickers)
    counts = Counter(tickers)
    repeats = sum(1 for t, c in counts.items() if c > 1)
    novelty = Counter((r.get("novelty") or "BRAK").strip() for r in scout_rows)

    lines.append(
        f"**{len(scout_rows)}** propozycji, **{len(unique)}** unikalnych tickerów, "
        f"**{repeats}** tickerów proponowanych więcej niż raz.\n"
    )
    lines.append("| Novelty | n |")
    lines.append("|---|---|")
    for label, cnt in sorted(novelty.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {label} | {cnt} |")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------- main --

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recommendations", default=".claude/skills/gem-inwestycyjny/history/recommendations.csv")
    ap.add_argument("--closed", default="closed_positions.csv")
    ap.add_argument("--scout", default=".claude/skills/gem-inwestycyjny/history/scout_tickers.csv")
    args = ap.parse_args()

    rec_rows = read_csv(args.recommendations)
    closed_rows = read_csv(args.closed)
    scout_rows = read_csv(args.scout)

    spy_close = fetch_spy_close()
    spy_available = spy_close is not None
    rec_rows = enrich_recommendation_edges(rec_rows, spy_close)

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"# Performance Digest — {today}\n")
    print(
        "Miesięczny przegląd skuteczności obu pipeline'ów, liczony deterministycznie "
        "(bez LLM) z logów, które pipeline'y już piszą. Część rekomendacji z outcome "
        "`BOUGHT_*` to pozycje **PAPER ONLY** (nieotwarte realnie przez użytkownika — "
        "patrz kolumna `notes` w `recommendations.csv`), więc liczby poniżej to skuteczność "
        "silnika rekomendacji, nie realny P&L portfela.\n"
    )
    if not rec_rows and not closed_rows and not scout_rows:
        print("Brak danych źródłowych — wszystkie trzy logi puste lub nie istnieją.")
        return

    print("---\n")
    print(section_summary(rec_rows, closed_rows, scout_rows, spy_available))
    print("---\n")
    print(section_funnel(scout_rows, rec_rows))
    print(section_filter_value(rec_rows, spy_available))
    print(section_timing(rec_rows))
    print(section_conviction(rec_rows))
    print(section_position_auditor(closed_rows))
    print(section_scout(scout_rows))
    print(
        "---\n\n*Metodologiczna uwaga: to log jednego pipeline'u, nie test setupu jak w "
        "`backtest/` (tam próg wymagał n≥50, placebo, ≥80% kohort rocznych dodatnich "
        "zanim padł werdykt PASS). Dopóki n w powyższych sekcjach jest małe, traktuj je "
        "jako kierunek, nie dowód.*"
    )


if __name__ == "__main__":
    main()
