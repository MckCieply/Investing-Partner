#!/usr/bin/env python3
"""
reentry_context.py — pamiec miedzysystemowa (Position Auditor <-> Gem Pipeline).

Problem: Auditor (wyjscia) i Pipeline (wejscia) nie maja wspolnej pamieci, wiec
pipeline potrafi zarekomendowac powrot do tickera, ktory Auditor wybil dzien
wczesniej — bez zadnego sladu "wlasnie z tego wyszedles po X".

Ten skrypt to domyka: dla kazdej rekomendacji z recommendations.csv, ktorej
ticker wystepuje w closed_positions.csv z data zamkniecia <= run_date rekomendacji,
dopisuje do kolumny `notes` idempotentny tag kontekstu wyjscia:

  [RE-ENTRY: wyjscie DD.MM.YYYY @ EXIT (POWOD, Nd temu); wejscie @ ENTRY = ±X% vs wyjscie]

Dzieki temu od razu widac, czy to 'kup taniej niz sprzedales' (delta ujemna, OK)
czy 'chase' (delta dodatnia, uwaga). Idempotentnie — nie dubluje istniejacego tagu,
nie rusza zadnej innej kolumny. Tylko stdlib (csv), bez zaleznosci.

Uzycie:
  python3 skills/gem-position-auditor/reentry_context.py \
      .claude/skills/gem-inwestycyjny/history/recommendations.csv closed_positions.csv
"""
import sys, os, csv, argparse
from datetime import datetime

TAG_MARK = "[RE-ENTRY:"
REASON_PL = {"STOP_HIT": "stop", "TP_OR_MANUAL": "TP/ręcznie", "CLOSED": "zamknięte"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _fmt(d):
    return d.strftime("%d.%m.%Y") if d else "?"


def load_closures(path):
    """xtb -> lista (date_obj, exit_stop_float, reason) posortowana rosnaco po dacie."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            xtb = (row.get("xtb") or "").strip()
            d = _date(row.get("date_closed"))
            if not xtb or d is None:
                continue
            out.setdefault(xtb, []).append((d, _f(row.get("exit_stop")), row.get("reason", "")))
    for xtb in out:
        out[xtb].sort(key=lambda t: t[0])
    return out


def build_tag(closure, entry, run_date):
    d, exit_ref, reason = closure
    days = (run_date - d).days if run_date else None
    days_s = f"{days}d temu" if days is not None else "?"
    reason_s = REASON_PL.get(reason, reason or "?")
    if exit_ref and entry:
        delta = (entry / exit_ref - 1) * 100
        return (f"{TAG_MARK} wyjście {_fmt(d)} @ {exit_ref:g} ({reason_s}, {days_s}); "
                f"wejście @ {entry:g} = {delta:+.1f}% vs wyjście]")
    return f"{TAG_MARK} wyjście {_fmt(d)} ({reason_s}, {days_s}); brak porównywalnej ceny]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recommendations")
    ap.add_argument("closed", nargs="?", default="closed_positions.csv")
    args = ap.parse_args()

    if not os.path.exists(args.recommendations):
        print(f"Brak {args.recommendations} — nic do anotowania."); return
    closures = load_closures(args.closed)
    if not closures:
        print(f"Brak zamknięć w {args.closed} — nic do anotowania."); return

    with open(args.recommendations, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    if "notes" not in (fields or []):
        print("recommendations.csv nie ma kolumny `notes` — pomijam."); return

    annotated = []
    for r in rows:
        notes = r.get("notes") or ""
        if TAG_MARK in notes:
            continue  # juz otagowane — idempotencja
        xtb = (r.get("ticker_xtb") or "").strip()
        run_date = _date(r.get("run_date"))
        cands = closures.get(xtb)
        if not cands or run_date is None:
            continue
        # najnowsze wyjscie NIE pozniejsze niz data rekomendacji
        prior = [c for c in cands if c[0] <= run_date]
        if not prior:
            continue
        tag = build_tag(prior[-1], _f(r.get("entry_price")), run_date)
        r["notes"] = (notes + " | " + tag) if notes.strip() else tag
        annotated.append((xtb, tag))

    if not annotated:
        print("Brak rekomendacji do otagowania (żaden ticker nie pasuje do zamknięć lub już otagowane).")
        return

    with open(args.recommendations, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Otagowano {len(annotated)} rekomendacji kontekstem re-entry:")
    for xtb, tag in annotated:
        print(f"  {xtb:10s} {tag}")


if __name__ == "__main__":
    main()
