#!/usr/bin/env python3
"""
performance_digest.py - miesieczny przeglad skutecznosci obu pipeline'ow.

Deterministyczny, tylko stdlib (csv/statistics/datetime) - zero LLM, zero
sieci. Czyta trzy logi, ktore juz istnieja, i liczy z nich metryki, ktorych
sam Weekly Tracker nie liczy (on tylko aktualizuje status per wiersz):

  - .claude/skills/gem-inwestycyjny/history/recommendations.csv
      lejek Scout->Quant->Alpha->Auditor->Director, win rate, kalibracja
      timingu, i najwazniejsze: czy odrzucone/wstrzymane tickery radza sobie
      GORZEJ niz kupione (filtr dodaje wartosc) czy LEPIEJ (filtr kosztuje
      edge) - Tracker sledzi cene dla WSZYSTKICH wierszy, nie tylko kupionych.
  - closed_positions.csv
      zamkniete pozycje Position Auditora: win rate, pnl per bucket/powod.
  - .claude/skills/gem-inwestycyjny/history/scout_tickers.csv
      nowosc/powtarzalnosc propozycji Scouta + konwersja Scout->recommendations.

Male n (kilkanascie wierszy przez pierwsze miesiace) -> raport explicite
oznacza kazda sekcje jako orientacyjna, dopoki n nie urosnie. Nie udaje
statystycznej istotnosci, ktorej backtest/README.md wymaga przed jakimkolwiek
werdyktem PASS/FAIL - to nie jest test setupu, to log jednego pipeline'u.

Uzycie:
  python3 skills/performance-digest/performance_digest.py > report.md
  python3 skills/performance-digest/performance_digest.py \
      --recommendations PATH --closed PATH --scout PATH
"""
import argparse
import csv
import os
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median

MIN_N_NOTE = 20  # pod tym n sekcja dostaje etykiete "orientacyjne"

TIMING_DAYS = {"TERAZ": 28, "WKROTCE": 91, "ODLEGLY": 182}
BOUGHT_OUTCOMES = {"BOUGHT_FULL", "BOUGHT_HALF"}
FILTERED_OUTCOMES = {"REJECTED_ALPHA", "AUDITOR_VETO", "AUDITOR_HOLD", "RESERVE_ALPHA"}


def normalize_pl(s):
    """Uppercase + strip polish diacritics, zeby ODLEGLY/ODLEGŁY/SREDNIA/ŚREDNIA byly tym samym kluczem."""
    if not s:
        return ""
    table = str.maketrans(
        "óÓłŁęĘśŚżŻźŹćĆńŃąĄ",
        "oOlLeEsSzZzZcCnNaA",
    )
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


def n_flag(n):
    return " *(mała próbka, orientacyjne)*" if n < MIN_N_NOTE else ""


def section_funnel(scout_rows, rec_rows):
    scout_dates = {r.get("date", "").strip() for r in scout_rows if r.get("date")}
    scout_tickers = {r.get("ticker_yahoo", "").strip() for r in scout_rows if r.get("ticker_yahoo")}
    rec_tickers = {r.get("ticker_yahoo", "").strip() for r in rec_rows if r.get("ticker_yahoo")}
    converted = scout_tickers & rec_tickers
    conv_rate = (len(converted) / len(scout_tickers) * 100) if scout_tickers else None

    outcome_counts = Counter((r.get("outcome") or "INNE/BRAK").strip() for r in rec_rows)

    lines = ["## 1. Lejek decyzyjny — Scout → Quant → Alpha/Auditor → Director\n"]
    lines.append(
        f"Scout: {len(scout_rows)} propozycji w {len(scout_dates)} runach "
        f"({len(scout_tickers)} unikalnych tickerów).{n_flag(len(scout_rows))}"
    )
    if conv_rate is not None:
        lines.append(
            f"→ przeszło bramkę Quanta (zalogowane w recommendations.csv): "
            f"{len(rec_tickers)} unikalnych ({conv_rate:.0f}% konwersji Scout→Quant)."
        )
    lines.append("")
    lines.append("| Outcome | n |")
    lines.append("|---|---|")
    for outcome, cnt in sorted(outcome_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {outcome} | {cnt} |")
    lines.append("")
    return "\n".join(lines)


def section_filter_value(rec_rows):
    lines = ["## 2. Czy filtr Alpha/Auditor dodaje wartość, czy kosztuje edge?\n"]
    lines.append(
        "Weekly Tracker aktualizuje cenę dla WSZYSTKICH tickerów po bramce Quanta, "
        "nie tylko kupionych — więc można porównać, jak radzą sobie tickery, które "
        "faktycznie kupiliśmy (pełna/50% pozycja), względem tych odrzuconych/wstrzymanych "
        "przez Alphę/Auditora, na tej samej osi czasu.\n"
    )

    def group_stats(rows):
        n = len(rows)
        pct = [to_float(r.get("pct_change_since_entry")) for r in rows]
        pct = [x for x in pct if x is not None]
        resolved = [r for r in rows if (r.get("status") or "").strip() in ("HIT_TARGET", "STOPPED")]
        wins = sum(1 for r in resolved if r.get("status", "").strip() == "HIT_TARGET")
        win_rate = (wins / len(resolved) * 100) if resolved else None
        return n, (mean(pct) if pct else None), win_rate, len(resolved)

    bought = [r for r in rec_rows if (r.get("outcome") or "").strip() in BOUGHT_OUTCOMES]
    filtered = [r for r in rec_rows if (r.get("outcome") or "").strip() in FILTERED_OUTCOMES]

    lines.append("| Grupa | n | śr. zmiana ceny od entry | win rate (rozstrzygnięte) | n rozstrzygniętych |")
    lines.append("|---|---|---|---|---|")
    for label, rows in (("KUPIONE (FULL+HALF)", bought), ("ODRZUCONE/WSTRZYMANE", filtered)):
        n, avg_pct, win_rate, n_res = group_stats(rows)
        win_str = f"{win_rate:.0f}%" if win_rate is not None else "brak rozstrzygniętych"
        lines.append(f"| {label} | {n} | {fmt_pct(avg_pct)} | {win_str} | {n_res} |")
    lines.append("")
    n_total = len(bought) + len(filtered)
    lines.append(
        f"Interpretacja: jeśli KUPIONE > ODRZUCONE — filtr Alpha/Auditor łapie gorsze "
        f"setupy zanim wejdziemy. Jeśli odwrotnie — filtr odcina zwycięzców "
        f"(analogicznie do roli placebo w backtest/: to negative control, nie wyrok)."
        f"{n_flag(n_total)}"
    )
    lines.append("")
    return "\n".join(lines)


def section_timing(rec_rows):
    lines = ["## 3. Kalibracja timingu (timing_bucket vs rzeczywisty czas do rozstrzygnięcia)\n"]
    buckets = defaultdict(list)
    for r in rec_rows:
        bucket_raw = (r.get("timing_bucket") or "").strip()
        bucket = normalize_pl(bucket_raw)
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
        "„n rozstrzygniętych\" liczy zarówno HIT_TARGET jak i STOPPED — mierzy czas "
        "do JAKIEGOKOLWIEK rozstrzygnięcia, nie tylko trafień w target."
    )
    lines.append("")
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

    lines.append("| Konwikcja | n | win rate (rozstrzygnięte) | śr. zmiana ceny |")
    lines.append("|---|---|---|---|")
    for conv in ("WYSOKA", "SREDNIA", "NISKA"):
        rows = groups.get(conv, [])
        if not rows:
            continue
        resolved = [r for r in rows if (r.get("status") or "").strip() in ("HIT_TARGET", "STOPPED")]
        wins = sum(1 for r in resolved if r.get("status", "").strip() == "HIT_TARGET")
        win_rate = f"{(wins / len(resolved) * 100):.0f}%" if resolved else "brak rozstrzygniętych"
        pct = [to_float(r.get("pct_change_since_entry")) for r in rows]
        pct = [x for x in pct if x is not None]
        lines.append(f"| {conv} | {len(rows)} | {win_rate} | {fmt_pct(mean(pct)) if pct else 'brak danych'} |")
    lines.append(f"\n{n_flag(len(rec_rows))}")
    lines.append("")
    return "\n".join(lines)


def section_position_auditor(closed_rows):
    lines = ["## 5. Position Auditor — zamknięte pozycje\n"]
    if not closed_rows:
        lines.append("Brak zamkniętych pozycji jeszcze (closed_positions.csv pusty/brak).")
        lines.append("")
        return "\n".join(lines)

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
        f"{len(scout_rows)} propozycji, {len(unique)} unikalnych tickerów, "
        f"{repeats} tickerów proponowanych więcej niż raz."
    )
    lines.append("")
    lines.append("| Novelty | n |")
    lines.append("|---|---|")
    for label, cnt in sorted(novelty.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {label} | {cnt} |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recommendations", default=".claude/skills/gem-inwestycyjny/history/recommendations.csv")
    ap.add_argument("--closed", default="closed_positions.csv")
    ap.add_argument("--scout", default=".claude/skills/gem-inwestycyjny/history/scout_tickers.csv")
    args = ap.parse_args()

    rec_rows = read_csv(args.recommendations)
    closed_rows = read_csv(args.closed)
    scout_rows = read_csv(args.scout)

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"# Performance Digest — {today}\n")
    print(
        "Miesięczny przegląd skuteczności obu pipeline'ów, liczony deterministycznie "
        "(bez LLM) z logów, które pipeline'y już piszą. Część rekomendacji z outcome "
        "`BOUGHT_*` to pozycje **PAPER ONLY** (nieotwarte realnie przez użytkownika — "
        "patrz kolumna `notes` w recommendations.csv), więc liczby poniżej to skuteczność "
        "silnika rekomendacji, nie realny P&L portfela.\n"
    )
    if not rec_rows and not closed_rows and not scout_rows:
        print("Brak danych źródłowych — wszystkie trzy logi puste lub nie istnieją.")
        return

    print(section_funnel(scout_rows, rec_rows))
    print(section_filter_value(rec_rows))
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
