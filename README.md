# Investing-Partner

A set of independently scheduled automation and research tools for a personal equity portfolio (XTB IKE, US/Europe mandate). This is **not** an investment product, a trading signal service, or a broker integration — every system here either watches a portfolio the owner already holds, or researches whether an idea is worth acting on. Trade decisions are made by the owner, by hand, outside this repo.

**Personal tooling, not investment advice.** No audited track record, no forward-looking performance claims. `backtest/` and `skills/performance-digest/` exist specifically to check the tools' own numbers against reality, including the possibility that they add no value — see [Backtest](#backtest--does-any-entry-setup-beat-spy) below for a case where that's exactly what happened.

**About this repo's history.** This is the public half of a two-repo split: the code here (skills,
agents, workflows) is real and runs on a live schedule, but it reads and writes actual portfolio
state — holdings, stops, closed positions, recommendation outcomes — from a private sibling repo,
`investing-partner-data`, that isn't published. This repo's commit history is an *extracted* copy
of the original single-repo development history (via `git filter-repo`, keeping only code paths),
with the real commit dates and messages preserved — it's not a fresh dump, but it's also not the
literal, unedited original history; two commit messages that happened to quote real position
numbers were redacted in the process. See [`CLAUDE.md`](CLAUDE.md) for exactly how the split
works.

## Architecture: deterministic first, LLM only where judgment is needed

Three of the five systems below run on plain Python — no model call, no token cost, no variance between runs. Only the two research/discovery flows that require reading news, weighing catalysts, or drafting an investment thesis reach for an LLM, and one of those (Re-entry Review's narrative layer) only fires when a cheap deterministic gate has already found something worth looking at. This split is deliberate: it's what keeps a project with five scheduled jobs cheap enough to run against a personal Claude Pro subscription instead of a metered API budget, and it keeps the parts that must be exactly reproducible (stop-loss math, ledger updates) out of the parts that are allowed to vary.

| System | Trigger | LLM? | State |
|---|---|---|---|
| [Position Auditor](#1-position-auditor) | weekly (Sun) | No | `stops_state.json`, `closed_positions.csv` |
| [Re-entry Review](#2-re-entry-review) | weekly (Thu) | Gated — only when the deterministic scan finds a candidate | `reentry_candidates.json` (ephemeral) |
| [Gem Pipeline](#3-gem-pipeline) | 3×/week (Sun, Wed, Fri) | Yes — 5-agent pipeline | `history/recommendations.csv`, `history/scout_tickers.csv` |
| [Gem Tracker](#4-gem-tracker) | weekly (Fri) | Yes (smallest/cheapest model, no reasoning) | updates `history/recommendations.csv` |
| [Performance Digest](#5-performance-digest) | monthly | No | reads the above, writes a report |

## The five systems

### 1. Position Auditor
`skills/gem-position-auditor/`, [`.github/workflows/audit.yml`](.github/workflows/audit.yml)

Deterministic stop-loss/take-profit engine over the positions currently held (`holdings.json`). Computes ATR/SMA/RSI per ticker, ratchets stop levels only upward (with damping below 0.3% of price to suppress noise), and emails an HTML report. State — including a per-ticker `avg_cost`/`last_price`/`exit_now` snapshot — lives in `stops_state.json`. When a ticker disappears from `holdings.json` between runs, the auditor infers it was closed and logs it to `closed_positions.csv` with an estimated reason (`STOP_HIT` / `TP_OR_MANUAL` / `CLOSED`) and an estimated PnL from the last known stop/target — the real fill price from the broker is confirmed by hand, not by this tool.

Editing a position means editing `holdings.json` — no UI, no database.

### 2. Re-entry Review
`skills/gem-position-auditor/reentry_scanner.py`, [`.github/workflows/reentry-review.yml`](.github/workflows/reentry-review.yml)

A two-layer flow that asks whether a position the Auditor stopped out of is worth watching again. The deterministic gate runs every week regardless: it reads `closed_positions.csv` and checks whether the setup that triggered the exit has reversed (price vs. the old stop, SMA50/200, 20-day return, RSI), producing a `RE-ENTER` / `WATCH` / `SKIP` verdict per closed ticker. Only when that gate produces at least one `RE-ENTER` does a second, LLM-driven job run — it searches recent news for each candidate and classifies whether the original thesis is `THESIS_BACK`, `MIXED`, or `THESIS_DEAD`. In a week with no candidates, the LLM layer never runs, so it costs nothing.

This is a scan, not a buy signal — the entry decision stays with the owner. A related script, `reentry_context.py`, is the only piece of shared state between this system and the Gem Pipeline below: it annotates new pipeline recommendations with a note when the same ticker was recently stopped out, so a "new" recommendation the next day doesn't look unrelated to a position closed the day before.

### 3. Gem Pipeline
`.claude/skills/gem-inwestycyjny/`, [`.github/workflows/gem-pipeline.yml`](.github/workflows/gem-pipeline.yml)

Five sequential LLM subagents — Scout → Quant → Alpha → Auditor → Director — searching for **new** entry candidates across the US and European markets (Xetra, Euronext, LSE, GPW, Oslo, Stockholm, NYSE/NASDAQ; Asia is explicitly out of mandate). This is discovery only — it does not manage positions already held, which is the Position Auditor's job.

Each stage runs on a different model and thinking budget, sized to how much judgment that stage actually needs — the same cost-consciousness as the deterministic/LLM split above, one level deeper: **Scout** (Sonnet, high effort) proposes candidates with a thesis and a specific invalidation scenario; **Quant** (Haiku, no reasoning) is a purely mechanical technical gate — price above SMA50/SMA200, RSI14 < 70; **Alpha** (Sonnet, medium effort) ranks survivors into a top pick vs. reserve list; **Auditor** (Sonnet, or Opus on the "max" quality preset) is the risk check — APPROVE / HOLD / VETO, including cutting position size in half when event risk (earnings, pending litigation) is elevated rather than a flat yes/no; **Director** (Sonnet, or Haiku to save cost) only writes up the decisions already made, adding no analysis of its own. Every ticker the Quant stage scores gets logged to `history/recommendations.csv`, including the ones any stage rejects or holds back (with the reason), so the pipeline's own hit rate is auditable later, not just its buy calls.

### 4. Gem Tracker
[`.github/workflows/gem-tracker.yml`](.github/workflows/gem-tracker.yml)

A lightweight weekly job on the smallest available model, doing no reasoning of its own — it re-prices every open recommendation from `history/recommendations.csv`, flips `status` to `HIT_TARGET`/`STOPPED` when a level is crossed, and updates `pct_to_target`. It doesn't run Scout→Director and doesn't originate ideas.

### 5. Performance Digest
`skills/performance-digest/`, [`.github/workflows/performance-digest.yml`](.github/workflows/performance-digest.yml)

A deterministic monthly rollup — none of the systems above aggregate their own history over time; the Tracker only flips per-row status. This script reads `recommendations.csv`, `closed_positions.csv`, and `scout_tickers.csv` and asks the question none of the weekly jobs do: **does the pipeline's own filtering actually add value**, by comparing bought tickers against everything the pipeline rejected or held back, each measured as edge over SPY across the same window. It also checks `timing_bucket` calibration and the Auditor's win rate per stop-loss method. Sections built on fewer than 20 data points are explicitly flagged as too small to trust rather than left looking confident.

This is *not* a second backtest — it audits the live pipeline's own small, growing sample with no pass/fail bar, where [Backtest](#backtest--does-any-entry-setup-beat-spy) below tests a hypothesis against a much larger, stricter one (n≥50, placebo-controlled) before anything reaches production.

## Backtest — does any entry setup beat SPY?

`backtest/` is a separate, standalone research project, and the most rigorous work in this repo — it does not feed live signals into any of the five systems above; it exists to test whether it should.

**Question:** does any mechanical, ex-ante-observable entry trigger beat SPY over T+30/60/90 sessions, after realistic transaction costs, consistently across years — not just "does a narrative move the market" (true, and not what's being tested), but "can that be turned into a backtestable trading signal" (the actual claim under test).

**Method:** ~12–16 candidate setups across 3 groups (index-consolidation and corporate-event triggers, then regulatory/technical triggers, then narrative-driven triggers), evaluated against a fixed protocol: entry at T+1 open (no look-ahead), edge measured against SPY over the identical window (not raw return), median rather than mean (resistant to fat-tail distortion), mandatory yearly-cohort breakdowns (an aggregate edge can be one anomalous year), and — starting with the narrative group — a required placebo/negative-control comparison, since a setup that looks good in isolation but performs the same as its placebo has no real edge. The pass bar tightens with each group to correct for testing multiple hypotheses on the same data.

**Result: zero of the tested setups passed with a placebo-confirmed edge.** A separate, later validation (`backtest/results/quant_gate_verdict.md`) backtested the exact technical gate the live Gem Pipeline's Quant stage already uses (price above SMA50 and SMA200, RSI14 < 70) over ~13 years and ~741 tickers — also FAIL, and the placebo comparison showed that adding SMA200 and the RSI filter on top of plain SMA50 makes the edge *worse*, not better.

This negative result is the point, not a footnote: it's the reason system #3 above logs rejected tickers as carefully as accepted ones, and it's why "does this actually work" is treated as an ongoing question (see Performance Digest) rather than something settled once at launch. Full methodology, per-group thresholds, and the individual setup results are in [`backtest/README.md`](backtest/README.md); the still-open follow-up thread (a different market regime — mWIG40 — not yet tested to the same standard) is in [`backtest/HANDOFF_pead_mwig40.md`](backtest/HANDOFF_pead_mwig40.md).

## Running things locally

Position Auditor is the simplest entry point. This repo doesn't ship a real `holdings.json` (that
lives in the private data repo) — copy the example to get a working local run against real market
data for made-up positions:

```bash
pip install -r requirements.txt
cp holdings.json.example holdings.json
python skills/gem-position-auditor/position_auditor.py holdings.json
```

`holdings.json` is a flat array of `{"xtb": "<XTB ticker>", "yahoo": "<Yahoo Finance ticker>", "avg_cost": <number>}` objects. State is written to `stops_state.json` in the same directory — in production that's a symlink into the private data repo (see [`CLAUDE.md`](CLAUDE.md)); locally it's just a plain file, and `holdings.json`/`stops_state.json` are gitignored so a local run never accidentally gets committed here.

The other systems (`skills/performance-digest/performance_digest.py`, `skills/gem-position-auditor/reentry_scanner.py`) are also plain Python scripts and can be run the same way; see each system's own doc below for flags and output paths. The Gem Pipeline's LLM agents are designed to run inside the GitHub Actions workflow, not ad hoc locally.

## Full documentation

This README is deliberately an overview. Deeper reference docs, one per topic:

- [`skills/gem-position-auditor/SKILL.md`](skills/gem-position-auditor/SKILL.md) — full Position Auditor logic: stop method per bucket, tranches, hysteresis.
- [`.claude/skills/gem-inwestycyjny/SKILL.md`](.claude/skills/gem-inwestycyjny/SKILL.md) — Gem Pipeline orchestrator.
- [`.claude/skills/gem-inwestycyjny/PLAN_recommendation_tracking.md`](.claude/skills/gem-inwestycyjny/PLAN_recommendation_tracking.md) — `recommendations.csv` schema.
- [`skills/performance-digest/SKILL.md`](skills/performance-digest/SKILL.md) — what the monthly digest computes and why monthly, not weekly.
- [`backtest/README.md`](backtest/README.md) — the backtest project in full.
- [`CLAUDE.md`](CLAUDE.md) — includes a running **pitfalls log** of GitHub Actions/CI issues already hit and fixed (OIDC auth, email action quirks, exchange-coverage gaps). Kept there rather than duplicated here.

## License

[MIT](LICENSE).
