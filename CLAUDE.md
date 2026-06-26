# CLAUDE.md — reguły pracy w tym repo

## Workflow / Git

- **Git = GitHub, zawsze.** Jedyny zdalny remote to `origin` → `MckCieply/Investing-Partner`. Nie ma innych developerów, innych branchy do koordynacji ani PR-ów do recenzji — commituj i pushuj bezpośrednio na `main`, bez pytania o potwierdzenie przy zwykłych zmianach w kodzie/skillach/configu.
- **Jestem jedynym programistą.** Nie trzeba ostrzegać przed "nadpisaniem czyjejś pracy" ani proponować PR-flow — to nie ma zastosowania w tym repo.
- Wyjątek: rzeczy nieodwracalne lub niosące realny koszt (force-push, reset --hard, usuwanie tagów/branchy, zmiany w sekretach/uprawnieniach repo) — o tych nadal pytaj.
- Commit messages: krótkie, po angielsku, konwencja `type(scope): opis` (np. `fix(gem-pipeline): ...`, `feat: ...`).

## Co to za projekt

Repo zawiera dwa niezależne, zautomatyzowane przez GitHub Actions narzędzia inwestycyjne dla osobistego portfela na XTB IKE:

### 1. Position Auditor (`skills/gem-position-auditor/`, `.github/workflows/audit.yml`)
- Deterministyczny (Python, bez LLM) silnik stop-loss/take-profit dla **aktualnie posiadanych** pozycji z `holdings.json`.
- Cron: niedziela 07:00 UTC + manualny `workflow_dispatch`.
- Liczy ATR/SMA/RSI, ratchetuje stopy tylko w górę (z tłumieniem szumu < 0.3% ceny), zapisuje stan w `stops_state.json`, wysyła HTML mailem (Gmail SMTP).
- Edycja pozycji = edytuj `holdings.json` (pola: `xtb`, `yahoo`, `avg_cost`).

### 2. Gem Inwestycyjny (`.claude/skills/gem-inwestycyjny/`, `.github/workflows/gem-pipeline.yml`)
- Pipeline 5 subagentów LLM (Scout → Quant → Alpha → Auditor → Director) szukający **nowych** kandydatów do wejścia (nie zarządza istniejącymi pozycjami — to robi Position Auditor).
- Mandat geograficzny: **wyłącznie USA i Europa** (Xetra, Euronext, LSE, GPW, Oslo, Sztokholm + NYSE/NASDAQ). Azja, Hong Kong, Chiny, Japonia — wykluczone.
- Cron: niedziela 18:00 UTC + manualny `workflow_dispatch` (input `quality`: optimal/lean/max).
- Auth: `CLAUDE_CODE_OAUTH_TOKEN` (token z planu Pro via `claude setup-token`) — **zużywa tygodniowy limit Claude Pro**, nie osobny budżet API. `--max-budget-usd 8.00` to wewnętrzny cap kosztu tokenów w ramach jednego runu, nie limit subskrypcji.
- Wymaga zainstalowanej GitHub App "Claude Code" na repo (https://github.com/apps/claude) — bez tego `claude-code-action@v1` failuje przy OIDC.
- Wynik: `reports/gem-<data>.md` (commitowany do repo) + mail HTML.
- Agent 06 (Weekly Tracker, w budowie) — osobny przepływ do logowania skuteczności rekomendacji w czasie (`.claude/skills/gem-inwestycyjny/history/`).

## Pułapki, na które już trafiliśmy (nie powtarzać)

- `dawidd6/action-send-mail@v3` **nie ma** inputu `content_type` — tylko `convert_markdown: true` + `html_body`. Próba dodania `content_type` wywala krok z "Unexpected input(s)".
- `anthropics/claude-code-action@v1` wymaga `permissions: id-token: write` w workflow (próbuje OIDC nawet z OAuth tokenem z planu Pro) — bez tego: "Could not fetch an OIDC token".
- Ten sam action podstawia własny git credential helper na runnerze — kolejny krok robiący `git push` zwykłym `actions/checkout` tokenem dostaje "Authentication failed". Fix: jawnie `git remote set-url origin https://x-access-token:${GH_TOKEN}@github.com/...` przed push w kroku commitującym.
- Skille dla `claude-code-action@v1` muszą leżeć w `.claude/skills/<nazwa>/` w repo, żeby były wykrywalne w CI (lokalna instalacja w Claude Desktop to nie to samo miejsce).
- Lokalny npm/Node na maszynie użytkownika był zepsuty (minizlib/Node 24 incompatibility) — Claude Code CLI instalujemy natywnym installerem (`irm https://claude.ai/install.ps1 | iex`), nie przez npm.
