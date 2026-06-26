"""
core/results_writer.py
======================
Persystencja wyników do results/pead_mwig40/ wg konwencji projektu.
W pełni działający (zapisuje pliki). Wywoływany na końcu run_pead_mwig40.py.

Strażnik dryfu: RUN_META.json zawiera SHA-256 FROZEN_PARAMS + git commit.
Wyniki wersjonowane razem z definicją, która je wygenerowała.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "NO_GIT"


def write_results(
    out_dir: Path,
    summary: dict,
    cohorts_long: pd.DataFrame,
    cohorts_short_signal: pd.DataFrame,
    placebo_long: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    events_long: pd.DataFrame,
    validation_notes: dict,
    frozen_params: dict,
    frozen_params_hash: str,
    synthetic: bool = False,
) -> None:
    """Zapisuje pełen komplet artefaktów. synthetic=True dorzuca ostrzeżenie."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. JSON headline
    (out_dir / "pead_mwig40_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    # 2. CSV-e
    cohorts_long.to_csv(out_dir / "cohorts_long.csv", index=False)
    cohorts_short_signal.to_csv(out_dir / "cohorts_short_signal.csv", index=False)
    placebo_long.to_csv(out_dir / "placebo_long.csv", index=False)
    cost_sensitivity.to_csv(out_dir / "cost_sensitivity.csv", index=False)

    # 3. Event-level (parquet jeśli pyarrow, inaczej csv)
    try:
        events_long.to_parquet(out_dir / "events_long.parquet", index=False)
    except Exception:
        events_long.to_csv(out_dir / "events_long.csv", index=False)

    # 4. Notatki walidacyjne
    _write_validation_md(out_dir / "data_validation_notes.md", validation_notes, synthetic)

    # 5. Markdown werdykt (styl results projektu)
    _write_summary_md(out_dir / "pead_mwig40_summary.md", summary, cohorts_long,
                      placebo_long, cost_sensitivity, synthetic)

    # 6. RUN_META — strażnik dryfu
    (out_dir / "RUN_META.json").write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "frozen_params_hash": frozen_params_hash,
        "frozen_params": frozen_params,
        "synthetic_smoke_test": synthetic,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_validation_md(path: Path, notes: dict, synthetic: bool) -> None:
    lines = ["# Data validation notes — PEAD mWIG40\n"]
    if synthetic:
        lines.append("> ⚠️ **SMOKE TEST — DANE SYNTETYCZNE. NIE SĄ WYNIKIEM BACKTESTU.**\n")
    lines.append("Checki kompletności PRZED werdyktem (twarda reguła — lekcja Setup 7).\n")
    for k, v in notes.items():
        lines.append(f"- **{k}:** {v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_md(path, summary, cohorts_long, placebo, cost_sens, synthetic) -> None:
    v = summary.get("long_verdict", {})
    lines = ["# PEAD mWIG40 — wyniki\n"]
    if synthetic:
        lines += ["> ⚠️ **SMOKE TEST — DANE SYNTETYCZNE, LOSOWE. To dowód, że pipeline",
                  "> persystencji działa, NIE wynik rynkowy. Nie interpretować liczb.**\n"]
    lines.append(f"**Werdykt LONG: {v.get('verdict', '?')}**\n")
    lines.append("## Bramki PASS (LONG, net of costs)\n")
    lines.append("| check | wartość | spełniony |")
    lines.append("|---|---|---|")
    for name, (val, ok) in v.get("checks", {}).items():
        lines.append(f"| {name} | {val} | {'✅' if ok else '❌'} |")
    lines.append("\n## Kohorty roczne (LONG)\n")
    lines.append(cohorts_long.to_markdown(index=False))
    lines.append("\n## Placebo (negative control)\n")
    lines.append(placebo.to_markdown(index=False))
    lines.append("\n## Sensitivity kosztu\n")
    lines.append(cost_sens.to_markdown(index=False))
    short = summary.get("short_signal", {})
    if short:
        lines.append("\n## Sygnał defensywny SHORT (nietradeowalny na IKE)\n")
        lines.append(f"median edge T+90: {short.get('median_edge_t90_pct')}% "
                     f"(wg Szyszki najczystszy dryf; filtr wyjścia dla Agenta 6)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
