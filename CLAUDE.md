# CLAUDE.md — reguły pracy w tym repo

## Workflow / Git

- **Git = GitHub, zawsze.** Jedyny zdalny remote to `origin` → `MckCieply/Investing-Partner`. Nie ma innych developerów, innych branchy do koordynacji ani PR-ów do recenzji — commituj i pushuj bezpośrednio na `main`, bez pytania o potwierdzenie przy zwykłych zmianach w kodzie/skillach/configu.
- **Jestem jedynym programistą.** Nie trzeba ostrzegać przed "nadpisaniem czyjejś pracy" ani proponować PR-flow — to nie ma zastosowania w tym repo.
- Wyjątek: rzeczy nieodwracalne lub niosące realny koszt (force-push, reset --hard, usuwanie tagów/branchy, zmiany w sekretach/uprawnieniach repo) — o tych nadal pytaj.
- Commit messages: krótkie, po angielsku, konwencja `type(scope): opis` (np. `fix(gem-pipeline): ...`, `feat: ...`).
- **Pipeline first.** Jeśli dane zadanie może być wykonane przez GitHub Actions (cron, workflow_dispatch, Python skrypt w CI) — powinno być tam zrobione, nie lokalnie ani ręcznie w sesji. Ręczna praca lokalna to prototyp lub jednorazowy fix; docelowo każde powtarzalne działanie trafia do pipeline'u.
- **Persistuj dane przedstawione przez użytkownika.** Gdy użytkownik podaje dane (pozycje portfela, ceny wejścia, decyzje o kupnie/sprzedaży, wyniki transakcji) — zanim zakończę pracę z tymi danymi, zweryfikuj czy powinny być zapisane do repo (np. `holdings.json`, `history/recommendations.csv`, `stops_state.json`). Dane prezentowane jako zdjęcie/screenshot traktuj jak dane do wprowadzenia, a nie tylko do przeczytania.

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
- Krok 6 (mechaniczny, bez subagenta) loguje każdy ticker z `ZIELONE_SWIATLO: TAK` do `history/recommendations.csv` (entry/stop/target, `timing_bucket`, `target_date_est`, `outcome`) — backtest skuteczności całego pipeline'u, nie tylko karty zleceń.

### 3. Gem Tracker (Agent 06, `.github/workflows/gem-tracker.yml`)
- Osobny, lekki przepływ (Haiku, zero "myślenia") — NIE odpala Scout→Director, tylko aktualizuje status istniejących rekomendacji z `history/recommendations.csv`.
- Cron: piątek 08:00 UTC + manualny `workflow_dispatch`.
- Pobiera aktualne ceny (`quant_scanner.py`), flipuje `status` na `HIT_TARGET`/`STOPPED` (ustawia `date_resolved` raz, przy pierwszym rozstrzygnięciu), liczy `pct_to_target`.
- Wynik: `reports/tracker-<data>.md` + mail, commit zaktualizowanego CSV do repo. Te same fixy (OIDC `id-token: write`, `git remote set-url` przed push) co w `gem-pipeline.yml`.

## Dokumentacja — pełne dokumenty referencyjne

Ten plik (CLAUDE.md) jest zawsze ładowany do kontekstu — ma zostać krótki. Poniżej katalog dokumentów-dzieci: każdy odpowiada za jeden temat, otwieraj tylko ten, którego aktualnie potrzebujesz.

- [`README.md`](README.md) — szybki start Position Auditora (instalacja, lokalny run, edycja `holdings.json`).
- [`skills/gem-position-auditor/SKILL.md`](skills/gem-position-auditor/SKILL.md) — pełna logika Agenta 6: dobór metody stopa per bucket (ATR% vs SMA/RSI), transze, histereza, format diffu tygodniowego.
- [`.claude/skills/gem-inwestycyjny/SKILL.md`](.claude/skills/gem-inwestycyjny/SKILL.md) — orchestrator pipeline'u 5 subagentów (Scout→Director) + kontrakt synchroniczności dispatchu.
- [`.claude/skills/gem-inwestycyjny/PLAN_recommendation_tracking.md`](.claude/skills/gem-inwestycyjny/PLAN_recommendation_tracking.md) — schemat CSV i zasady logowania rekomendacji BUY do `history/recommendations.csv` (krok 6, zaimplementowany — patrz sekcja 2 wyżej).
- [`backtest/README.md`](backtest/README.md) — projekt badawczy "czy setup wejściowy daje edge nad SPY": metodologia, wynik (Grupy 1–3: FAIL), i stamtąd dalsze linki do `HANDOFF_pead_mwig40.md` (nowy, wciąż otwarty wątek PEAD/mWIG40) i notatek walidacyjnych grup 2–3.

Nieobjęte katalogiem (logi, nie dokumentacja referencyjna): `reports/*.md` (wygenerowane raporty pipeline'u/trackera per data) i `session-handoffs/*.md` (zapiski z sesji). Przeglądaj je bezpośrednio, gdy potrzebujesz historii konkretnego dnia.

## Pułapki, na które już trafiliśmy (nie powtarzać)

- `dawidd6/action-send-mail@v3` **nie ma** inputu `content_type` — tylko `convert_markdown: true` + `html_body`. Próba dodania `content_type` wywala krok z "Unexpected input(s)".
- `anthropics/claude-code-action@v1` wymaga `permissions: id-token: write` w workflow (próbuje OIDC nawet z OAuth tokenem z planu Pro) — bez tego: "Could not fetch an OIDC token".
- Ten sam action podstawia własny git credential helper na runnerze — kolejny krok robiący `git push` zwykłym `actions/checkout` tokenem dostaje "Authentication failed". Fix: jawnie `git remote set-url origin https://x-access-token:${GH_TOKEN}@github.com/...` przed push w kroku commitującym.
- Skille dla `claude-code-action@v1` muszą leżeć w `.claude/skills/<nazwa>/` w repo, żeby były wykrywalne w CI (lokalna instalacja w Claude Desktop to nie to samo miejsce).
- Lokalny npm/Node na maszynie użytkownika był zepsuty (minizlib/Node 24 incompatibility) — Claude Code CLI instalujemy natywnym installerem (`irm https://claude.ai/install.ps1 | iex`), nie przez npm.
- Manualny re-run `gem-pipeline.yml` tego samego dnia (np. inny `--quality`) może się "udać" bez wykonania żadnej pracy: orchestrator widzi, że `reports/gem-<data>.md` już istnieje z wcześniejszego runu i kończy turę w ~5 turns/20s bez dispatchu Scout→Director, zostawiając stary plik nietknięty — `verify report produced` przechodził, bo sprawdzał tylko obecność/keywords w pliku, nie to, czy ten konkretny run go zmienił. Fix: SKILL.md ma teraz explicit zakaz pomijania pipeline'u z tego powodu + workflow dodatkowo wymaga `git status --porcelain` na pliku raportu (musi się różnić od HEAD).
