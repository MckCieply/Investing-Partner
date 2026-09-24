#!/usr/bin/env python3
"""
public_summary.py — the only thing scheduled workflows are allowed to say in public.

This repo's Actions logs are world-readable, the data they process is not. Every
subcommand here reads private files from data/ and emits ONLY aggregate counts
(no tickers, prices, stops, PnL, model output) to stdout and $GITHUB_STEP_SUMMARY,
so a visitor can see that the pipeline ran and roughly what it did.

Subcommands:
  claude-run  RUN_JSON SUMMARY_JSONL --run-id ID --date YYYY-MM-DD [--title T]
      Parse claude-code-action's execution log. Appends the FULL summary
      (incl. error text) to SUMMARY_JSONL in the private repo; publishes only
      turns / cost / duration / per-stage timing with canonical stage names.
  funnel      RECOMMENDATIONS_CSV SCOUT_CSV --date YYYY-MM-DD
      Scout -> Quant -> Alpha -> Auditor -> Director counts for one run date.
  tracker     RECOMMENDATIONS_CSV
      OPEN / HIT_TARGET / STOPPED counts across all tracked recommendations.
  audit       STOPS_STATE_JSON
      Number of positions, stop vs tranche plans, exit signals.
  reentry     CANDIDATES_JSON
      Number of RE-ENTER candidates.

Stdlib only — runs on the bare runner python3 without pip.
"""
import argparse, csv, json, os, sys
from collections import Counter

# Task descriptions in the execution log come from SKILL.md, but the orchestrator
# may enrich them (e.g. append tickers). Publish the canonical stage name only.
STAGES = [
    ("scout", "Scout"), ("quant", "Quant"), ("alpha", "Alpha"),
    ("risk audit", "Auditor"), ("auditor", "Auditor"), ("director", "Director"),
    ("tracker", "Tracker"),
]


def canonical_stage(desc):
    d = (desc or "").lower()
    for key, name in STAGES:
        if key in d:
            return name
    return "sub-task"


def publish(lines):
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_claude_run(a):
    try:
        with open(a.run_json, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        # the exception text is ours (path/JSON position), not portfolio data
        private = {"run_id": a.run_id, "date": a.date, "error": f"failed to parse log: {e}"}
        _append_jsonl(a.summary_jsonl, private)
        publish([f"### {a.title}", "", "Execution log missing or unreadable — no run metadata."])
        return

    events = data if isinstance(data, list) else [data]
    result = next((e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result"), {})
    denials = result.get("permission_denials") or []

    # per-stage timing from Task dispatch/completion events (Scout, Quant, ...,
    # plus Scout's own search-wave sub-tasks), in chronological order
    descriptions, completions, seen = {}, [], set()
    for e in events:
        if not isinstance(e, dict) or e.get("type") != "system":
            continue
        if e.get("subtype") == "task_started" and e.get("task_id"):
            descriptions.setdefault(e["task_id"], e.get("description", e["task_id"]))
        elif e.get("subtype") == "task_updated":
            patch = e.get("patch") or {}
            tid = e.get("task_id")
            if patch.get("status") == "completed" and patch.get("end_time") and tid not in seen:
                seen.add(tid)
                completions.append((tid, patch["end_time"]))
    completions.sort(key=lambda x: x[1])

    duration_ms = result.get("duration_ms")
    prev_end = (completions[-1][1] - duration_ms) if (completions and duration_ms) else None
    timeline = []
    for tid, end_ms in completions:
        elapsed = round((end_ms - prev_end) / 1000, 1) if prev_end is not None else None
        timeline.append({"stage": descriptions.get(tid, tid)[:80], "elapsed_sec": elapsed})
        prev_end = end_ms

    private = {
        "run_id": a.run_id,
        "date": a.date,
        "subtype": result.get("subtype"),
        "is_error": result.get("is_error"),
        "num_turns": result.get("num_turns"),
        "total_cost_usd": result.get("total_cost_usd"),
        "permission_denials_count": result.get("permission_denials_count", len(denials)),
        "error": result.get("result") if result.get("is_error") else None,
        "stage_timeline": timeline,
    }
    _append_jsonl(a.summary_jsonl, private)

    cost = result.get("total_cost_usd")
    lines = [
        f"### {a.title}", "",
        "| | |", "|---|---|",
        f"| wynik | {'❌ błąd' if result.get('is_error') else '✅ ' + str(result.get('subtype') or 'n/d')} |",
        f"| tury | {result.get('num_turns', 'n/d')} |",
        f"| czas | {round(duration_ms / 60000, 1) if duration_ms else 'n/d'} min |",
        f"| koszt tokenów | {f'${cost:.2f}' if isinstance(cost, (int, float)) else 'n/d'} |",
        f"| odmowy uprawnień | {private['permission_denials_count']} |",
    ]
    if timeline:
        lines += ["", "| etap | czas |", "|---|---|"]
        for t in timeline:
            secs = f"{t['elapsed_sec']:.0f} s" if t["elapsed_sec"] is not None else "?"
            lines.append(f"| {canonical_stage(t['stage'])} | {secs} |")
    publish(lines)


def _append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def cmd_funnel(a):
    scout = [r for r in read_csv(a.scout) if r.get("date") == a.date]
    recs = [r for r in read_csv(a.recommendations) if r.get("run_date") == a.date]
    outcome = lambda r: (r.get("outcome") or "").upper()
    quant_pass = [r for r in recs if not outcome(r).startswith("QUANT_REJECTED")]
    alpha_pass = [r for r in quant_pass if outcome(r) not in ("REJECTED_ALPHA", "RESERVE_ALPHA")]
    auditor_pass = [r for r in alpha_pass if not outcome(r).startswith("AUDITOR_")]
    bought = [r for r in auditor_pass if outcome(r).startswith("BOUGHT")]
    publish([
        f"### Lejek pipeline'u ({a.date})", "",
        "| Scout | Quant (policzone) | Quant ✓ | Alpha ✓ | Auditor ✓ | Director: kupno |",
        "|---|---|---|---|---|---|",
        f"| {len(scout)} | {len(recs)} | {len(quant_pass)} | {len(alpha_pass)} | {len(auditor_pass)} | {len(bought)} |",
    ])


def cmd_tracker(a):
    counts = Counter((r.get("status") or "?").upper() for r in read_csv(a.recommendations))
    publish([
        "### Śledzone rekomendacje", "",
        "| OPEN | HIT_TARGET | STOPPED | razem |", "|---|---|---|---|",
        f"| {counts.get('OPEN', 0)} | {counts.get('HIT_TARGET', 0)} | {counts.get('STOPPED', 0)} | {sum(counts.values())} |",
    ])


def cmd_audit(a):
    try:
        with open(a.state, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        publish(["### Position audit", "", "Brak stanu stopów po runie."])
        return
    pos = [v for k, v in state.items() if not k.startswith("_") and isinstance(v, dict)]
    publish([
        "### Position audit", "",
        "| pozycje | plan: stop | plan: transze | sygnał WYJDŹ |", "|---|---|---|---|",
        f"| {len(pos)} | {sum(p.get('type') != 'TRANCHE' for p in pos)} | "
        f"{sum(p.get('type') == 'TRANCHE' for p in pos)} | {sum(bool(p.get('exit_now')) for p in pos)} |",
    ])


def cmd_reentry(a):
    try:
        with open(a.candidates, encoding="utf-8") as f:
            n = len(json.load(f))
    except Exception:
        n = 0
    publish(["### Re-entry review", "", f"Kandydaci RE-ENTER po bramce technicznej: **{n}**"
             + (" → warstwa narracyjna (LLM) uruchomiona." if n else " → warstwa LLM pominięta.")])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("claude-run")
    p.add_argument("run_json"); p.add_argument("summary_jsonl")
    p.add_argument("--run-id", required=True); p.add_argument("--date", required=True)
    p.add_argument("--title", default="Claude run")
    p = sub.add_parser("funnel")
    p.add_argument("recommendations"); p.add_argument("scout"); p.add_argument("--date", required=True)
    p = sub.add_parser("tracker"); p.add_argument("recommendations")
    p = sub.add_parser("audit"); p.add_argument("state")
    p = sub.add_parser("reentry"); p.add_argument("candidates")
    a = ap.parse_args()
    {"claude-run": cmd_claude_run, "funnel": cmd_funnel, "tracker": cmd_tracker,
     "audit": cmd_audit, "reentry": cmd_reentry}[a.cmd](a)


if __name__ == "__main__":
    main()
