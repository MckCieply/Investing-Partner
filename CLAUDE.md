# CLAUDE.md — reguły pracy w tym repo

## To repo jest publiczne — dwurepowa architektura

**`Investing-Partner` (to repo) jest publiczne. Nigdy nie commituj tu prawdziwych danych
pozycji.** Prawdziwe `holdings.json`, `stops_state.json`, `closed_positions.csv`,
`audit_report.html/txt`, `.claude/skills/gem-inwestycyjny/history/` (w tym
`recommendations.csv`) i `reports/` żyją w osobnym **prywatnym** repo
`MckCieply/investing-partner-data`. Ten kod (skille, agenci, workflowy) jest identyczny w obu —
publiczny status dotyczy wyłącznie logiki, nie danych.

Mechanizm: każdy workflow w `.github/workflows/` checkoutuje `investing-partner-data` do
podkatalogu `data/` (token z GitHub App, mintowany per-run przez
`actions/create-github-app-token` — zobacz [`GITHUB_APP_SETUP.md`](GITHUB_APP_SETUP.md)), po
czym symlinkuje realne pliki/katalogi (`holdings.json`, `stops_state.json`, `closed_positions.csv`,
`.claude/skills/gem-inwestycyjny/history/`, `skills/gem-position-auditor/history/`, `reports/`) z
`data/...` na ich zwykłe względne ścieżki w root repo. **Dzięki temu SKILL.md, pliki agentów i
skrypty Pythona nie wiedzą o istnieniu drugiego repo** — czytają/piszą dokładnie te same względne
ścieżki co wcześniej w jednorepowej wersji; symlink robi tłumaczenie. Kroki `commit`/`push` w
workflowach commitują **do `data/`**, nie do tego repo — ten publiczny checkout nigdy nie ma nic
do zacommitowania z automatyzacji.

Historia commitów w tym repo jest **wyekstrahowana** z prywatnego repo deweloperskiego (ten sam
`Investing-Partner`, teraz przemianowany na `investing-partner-data`) przez `git filter-repo`,
zachowując prawdziwe daty i wiadomości commitów, ale tylko dla ścieżek kodu — pliki danych nigdy
nie weszły do tej historii. Dwa commit messages i jeden przykład w dokumentacji, które
przypadkiem cytowały prawdziwe liczby (ceny wejścia/wyjścia), zostały zredagowane
(`--replace-text`/`--replace-message`) — reszta historii jest dosłowna.

## Workflow / Git

- **Git = GitHub, zawsze.** Dwa repo, jeden zdalny remote każde: to repo → `origin` →
  `MckCieply/Investing-Partner` (publiczne, kod); `MckCieply/investing-partner-data` (prywatne,
  dane — osobny checkout w CI, nie remote tego repo). Nie ma innych developerów, innych branchy
  do koordynacji ani PR-ów do recenzji — commituj i pushuj bezpośrednio na `main`, bez pytania o
  potwierdzenie przy zwykłych zmianach w kodzie/skillach/configu.
- **Jestem jedynym programistą.** Nie trzeba ostrzegać przed "nadpisaniem czyjejś pracy" ani proponować PR-flow — to nie ma zastosowania w tym repo.
- Wyjątek: rzeczy nieodwracalne lub niosące realny koszt (force-push, reset --hard, usuwanie tagów/branchy, zmiany w sekretach/uprawnieniach repo) — o tych nadal pytaj.
- Commit messages: krótkie, po angielsku, konwencja `type(scope): opis` (np. `fix(gem-pipeline): ...`, `feat: ...`).
- **Zanim scommitujesz cokolwiek do TEGO repo, sprawdź czy to nie jest dana pozycji/PnL/exit.**
  Jeśli tak — cel to `investing-partner-data`, nie tutaj. W razie wątpliwości: jeśli plik zawiera
  prawdziwy ticker + prawdziwą cenę/PnL, należy do prywatnego repo.
- **Pipeline first.** Jeśli dane zadanie może być wykonane przez GitHub Actions (cron, workflow_dispatch, Python skrypt w CI) — powinno być tam zrobione, nie lokalnie ani ręcznie w sesji. Ręczna praca lokalna to prototyp lub jednorazowy fix; docelowo każde powtarzalne działanie trafia do pipeline'u.
- **Persistuj dane przedstawione przez użytkownika — ale do `investing-partner-data`, nie tutaj.** Gdy użytkownik podaje dane (pozycje portfela, ceny wejścia, decyzje o kupnie/sprzedaży, wyniki transakcji), zapisuj je w prywatnym repo. Dane prezentowane jako zdjęcie/screenshot traktuj jak dane do wprowadzenia, a nie tylko do przeczytania.

## Co to za projekt

Repo zawiera dwa niezależne, zautomatyzowane przez GitHub Actions narzędzia inwestycyjne dla osobistego portfela na XTB IKE:

### 1. Position Auditor (`skills/gem-position-auditor/`, `.github/workflows/audit.yml`)
- Deterministyczny (Python, bez LLM) silnik stop-loss/take-profit dla **aktualnie posiadanych** pozycji z `holdings.json`.
- Cron: niedziela 07:00 UTC + manualny `workflow_dispatch`.
- Liczy ATR/SMA/RSI, ratchetuje stopy tylko w górę (z tłumieniem szumu < 0.3% ceny), zapisuje stan w `stops_state.json`, wysyła HTML mailem (Gmail SMTP).
- Edycja pozycji = edytuj `holdings.json` (pola: `xtb`, `yahoo`, `avg_cost`).
- **Auto-log zamknięć.** Gdy ticker znika z `holdings.json`, a był w `stops_state.json` (= pozycja zamknięta między runami), auditor dopisuje go do `closed_positions.csv` z powodem (`STOP_HIT` / `TP_OR_MANUAL` / `CLOSED`) i szacowanym PnL (z ostatniego stopa/tp — realny fill z XTB potwierdzaj ręcznie). `stops_state.json` trzyma teraz też `avg_cost`/`yahoo`/`last_price`/`exit_now` per ticker, żeby było z czego to policzyć.

### 1b. Re-entry Review (Agent 6b, `skills/gem-position-auditor/reentry_scanner.py`, `.github/workflows/reentry-review.yml`)
Dwuwarstwowy przepływ, cron czwartek 08:00 UTC + `workflow_dispatch`:
- **Bramka techniczna (job `reentry`, zawsze, bez LLM — nie zużywa limitu Pro).** Skaner czyta `closed_positions.csv` i ocenia, czy setup techniczny, który nas wybił, się odwrócił (cena vs stary stop, SMA50/200, ret20, RSI) → werdykt `RE-ENTER` / `WATCH` / `SKIP`. Pomija tickery już z powrotem w `holdings.json` oraz zamknięte dawniej niż `--max-age-days` (365). Zapisuje `reentry_candidates.json` (tickery z `RE-ENTER`) i wysyła HTML mailem (bez commitu — raport efemeryczny).
- **Warstwa narracyjna (job `narrative`, LLM, tylko gdy `has_candidates == true`).** Odpala się **wyłącznie** gdy bramka techniczna wypuściła ≥1 `RE-ENTER` (gate przez output joba + `if:`), więc w tygodnie bez kandydatów limit Pro się nie rusza. Dla każdego kandydata robi WebSearch newsów od daty wyjścia i wydaje werdykt `THESIS_BACK` / `MIXED` / `THESIS_DEAD` (raport `reentry_narrative.md` mailem). Auth i pułapki jak w `gem-pipeline.yml` (OIDC `id-token: write`, GitHub App). Lista kandydatów wędruje między jobami przez `upload/download-artifact`.
- To skan/analiza, **nie sygnał kupna** — decyzję o wejściu podejmuje użytkownik.
- **Pamięć międzysystemowa (`reentry_context.py`).** Auditor (wyjścia) i Pipeline (wejścia) nie mają wspólnego stanu, więc pipeline potrafi zarekomendować powrót do tickera wybitego dzień wcześniej. Ten deterministyczny, idempotentny krok (tylko stdlib) dopisuje do `recommendations.csv` w kolumnie `notes` tag `[RE-ENTRY: wyjście DD.MM @ EXIT (powód, Nd temu); wejście @ ENTRY = ±X% vs wyjście]` dla każdej rekomendacji, której ticker jest w `closed_positions.csv` (data zamknięcia ≤ run_date). Ujemna delta = „kup taniej niż sprzedałeś", dodatnia = „chase, uwaga". Wpięty jako krok w `gem-pipeline.yml` (po logowaniu rekomendacji) i `gem-tracker.yml` (co piątek).

### 2. Gem Inwestycyjny (`.claude/skills/gem-inwestycyjny/`, `.github/workflows/gem-pipeline.yml`)
- Pipeline 5 subagentów LLM (Scout → Quant → Alpha → Auditor → Director) szukający **nowych** kandydatów do wejścia (nie zarządza istniejącymi pozycjami — to robi Position Auditor).
- Mandat geograficzny: **wyłącznie USA i Europa** (Xetra, Euronext, LSE, GPW, Oslo, Sztokholm + NYSE/NASDAQ). Azja, Hong Kong, Chiny, Japonia — wykluczone.
- Cron: **niedziela 18:00 UTC oraz środa 14:00 UTC** (2× w tygodniu) + manualny `workflow_dispatch` (input `quality`: optimal/lean/max). Uwaga: każdy run zużywa tygodniowy limit Pro, więc dwa runy = podwojone zużycie.
- Auth: `CLAUDE_CODE_OAUTH_TOKEN` (token z planu Pro via `claude setup-token`) — **zużywa tygodniowy limit Claude Pro**, nie osobny budżet API. `--max-budget-usd 8.00` to wewnętrzny cap kosztu tokenów w ramach jednego runu, nie limit subskrypcji.
- Wymaga zainstalowanej GitHub App "Claude Code" na repo (https://github.com/apps/claude) — bez tego `claude-code-action@v1` failuje przy OIDC.
- Wynik: `reports/gem-<data>.md` (commitowany do repo) + mail HTML.
- Krok 6 (mechaniczny, bez subagenta) loguje KAŻDY ticker, który Quant policzył, do `history/recommendations.csv` — nie tylko `ZIELONE_SWIATLO: TAK`. Tickery `NIE` dostają `outcome` = `QUANT_REJECTED_SMA50`/`_SMA200`/`_RSI`/`_ERROR` (wg pierwszej niespełnionej bramki), `entry_price`/`stop_loss` z Quanta, resztę pól (target/timing/conviction) pustą, i `status = OPEN`, więc Weekly Tracker śledzi ich cenę tak samo jak każdą inną rekomendację — pozwala z czasem ocenić, czy bramka SMA50/SMA200/RSI<70 jest trafnie skalibrowana. Backtest skuteczności całego pipeline'u, nie tylko karty zleceń.

### 3. Gem Tracker (Agent 06, `.github/workflows/gem-tracker.yml`)
- Osobny, lekki przepływ (Haiku, zero "myślenia") — NIE odpala Scout→Director, tylko aktualizuje status istniejących rekomendacji z `history/recommendations.csv`.
- Cron: piątek 08:00 UTC + manualny `workflow_dispatch`.
- Pobiera aktualne ceny (`quant_scanner.py`), flipuje `status` na `HIT_TARGET`/`STOPPED` (ustawia `date_resolved` raz, przy pierwszym rozstrzygnięciu), liczy `pct_to_target`.
- Wynik: `reports/tracker-<data>.md` + mail, commit zaktualizowanego CSV do repo. Te same fixy (OIDC `id-token: write`, `git remote set-url` przed push) co w `gem-pipeline.yml`.

### 4. Performance Digest (`skills/performance-digest/`, `.github/workflows/performance-digest.yml`)
- Deterministyczny (Python, bez LLM) miesięczny audyt skuteczności — Weekly Tracker aktualizuje status per wiersz, ale nic nie agreguje w czasie; to robi ten skrypt.
- Cron: 1. dzień miesiąca 08:00 UTC + manualny `workflow_dispatch`. Bez `claude-code-action` → bez OIDC, nie zużywa limitu Pro.
- Liczy z `recommendations.csv` / `closed_positions.csv` / `scout_tickers.csv`: lejek Scout→Quant→Alpha→Auditor→Director, **czy filtr pipeline'u dodaje wartość** (kupione vs odrzucone/wstrzymane tickery, liczone jako edge vs SPY w tym samym oknie run_date→last_checked_date — Tracker śledzi cenę dla wszystkich grup), kalibrację `timing_bucket`, win rate Position Auditora per bucket/powód zamknięcia, nowość/powtarzalność Scouta. Grupa "odrzucone/wstrzymane" łączy `QUANT_REJECTED_*` (bramka SMA50/SMA200/RSI) razem z `REJECTED_ALPHA`/`AUDITOR_VETO`/`AUDITOR_HOLD`/`RESERVE_ALPHA` (późniejszy filtr Alpha/Auditora) w jedno porównanie vs kupione — świadomie nierozdzielone na etapy.
- Raport otwiera sekcja Podsumowanie: jedna tabela z werdyktem 🟢/🟡/🔴/⚪ per obszar (⚪ = za mało danych, nie "neutralnie"). Sekcje/wiersze z n < 20 są explicite oznaczane jako orientacyjne — to nie test setupu jak `backtest/` (tam próg PASS wymagał n≥50 + placebo), tylko log jednego działającego pipeline'u.
- Wynik: `reports/performance-digest-<data>.md` (commitowany) + mail.

## Dokumentacja — pełne dokumenty referencyjne

Ten plik (CLAUDE.md) jest zawsze ładowany do kontekstu — ma zostać krótki. Poniżej katalog dokumentów-dzieci: każdy odpowiada za jeden temat, otwieraj tylko ten, którego aktualnie potrzebujesz.

- [`README.md`](README.md) — szybki start Position Auditora (instalacja, lokalny run, edycja `holdings.json`).
- [`GITHUB_APP_SETUP.md`](GITHUB_APP_SETUP.md) — jak skonfigurować GitHub App łączący to repo z `investing-partner-data` (jednorazowy setup, ręczne kroki w UI GitHuba).
- [`skills/gem-position-auditor/SKILL.md`](skills/gem-position-auditor/SKILL.md) — pełna logika Agenta 6: dobór metody stopa per bucket (ATR% vs SMA/RSI), transze, histereza, format diffu tygodniowego.
- [`.claude/skills/gem-inwestycyjny/SKILL.md`](.claude/skills/gem-inwestycyjny/SKILL.md) — orchestrator pipeline'u 5 subagentów (Scout→Director) + kontrakt synchroniczności dispatchu.
- [`.claude/skills/gem-inwestycyjny/PLAN_recommendation_tracking.md`](.claude/skills/gem-inwestycyjny/PLAN_recommendation_tracking.md) — schemat CSV i zasady logowania rekomendacji BUY do `history/recommendations.csv` (krok 6, zaimplementowany — patrz sekcja 2 wyżej).
- [`backtest/README.md`](backtest/README.md) — projekt badawczy "czy setup wejściowy daje edge nad SPY": metodologia, wynik (Grupy 1–3: FAIL), i stamtąd dalsze linki do `HANDOFF_pead_mwig40.md` (nowy, wciąż otwarty wątek PEAD/mWIG40) i notatek walidacyjnych grup 2–3.
- [`skills/performance-digest/SKILL.md`](skills/performance-digest/SKILL.md) — co dokładnie liczy miesięczny audyt skuteczności (sekcja 4 wyżej), dlaczego miesięcznie nie tygodniowo, i czym różni się od `backtest/`.

Nieobjęte katalogiem (logi, nie dokumentacja referencyjna): `reports/*.md` (wygenerowane raporty pipeline'u/trackera per data) i `session-handoffs/*.md` (zapiski z sesji). Przeglądaj je bezpośrednio, gdy potrzebujesz historii konkretnego dnia.

## Pułapki, na które już trafiliśmy (nie powtarzać)

- `dawidd6/action-send-mail@v3` **nie ma** inputu `content_type` — tylko `convert_markdown: true` + `html_body`. Próba dodania `content_type` wywala krok z "Unexpected input(s)".
- `anthropics/claude-code-action@v1` wymaga `permissions: id-token: write` w workflow (próbuje OIDC nawet z OAuth tokenem z planu Pro) — bez tego: "Could not fetch an OIDC token".
- Ten sam action podstawia własny git credential helper na runnerze — kolejny krok robiący `git push` zwykłym `actions/checkout` tokenem dostaje "Authentication failed". Fix: jawnie `git remote set-url origin https://x-access-token:${GH_TOKEN}@github.com/...` przed push w kroku commitującym.
- Skille dla `claude-code-action@v1` muszą leżeć w `.claude/skills/<nazwa>/` w repo, żeby były wykrywalne w CI (lokalna instalacja w Claude Desktop to nie to samo miejsce).
- Lokalny npm/Node na maszynie użytkownika był zepsuty (minizlib/Node 24 incompatibility) — Claude Code CLI instalujemy natywnym installerem (`irm https://claude.ai/install.ps1 | iex`), nie przez npm.
- **NYSE American (dawny AMEX) nie jest w pełni pokryte przez XTB** — małe spółki z tej giełdy (np. MPTI) często są niedostępne mimo że formalnie to regulowana giełda USA. Scout powinien preferować NYSE i NASDAQ dla tickerów US; dla NYSE American wymagać weryfikacji dostępności zanim ticker trafi do rekomendacji.
- **XTB oferuje akcje rzeczywiste (real stocks, nie CFD) tylko z 16-17 krajów** — zweryfikowano 15.08.2026 przez filtr krajów na `xtb.com/pl/specyfikacja-instrumentow` (zakładka "Akcje"): Belgia, Czechy, Dania, Finlandia, Francja, Hiszpania, Holandia, Niemcy, Norwegia, Polska, Portugalia, Stany Zjednoczone, Szwajcaria, Szwecja, Wielka Brytania, Wielka Brytania (IOB USD), Włochy. Pełny kontekst i mechanizm weryfikacji: [nomenclature.md](.claude/skills/gem-inwestycyjny/shared/nomenclature.md). **AIM (londyński junior market) NIE jest osobno pokryty** — filtr ma tylko jedną pozycję "Wielka Brytania" (LSE Main Market). Przypadek testowy: Scout zarekomendował `TUN.UK` (Tungsten West Plc, AIM) 14.08.2026 — ticker wyglądał poprawnie wg konwencji `TICK.UK`, ale wyszukiwarka na xtb.com zwróciła zero wyników. Ten sam mechanizm ryzyka co NYSE American powyżej (junior segment głównej giełdy) — Scout ma teraz w `01-scout.md` wymóg weryfikacji dla obu przypadków.
- Manualny re-run `gem-pipeline.yml` tego samego dnia (np. inny `--quality`) może się "udać" bez wykonania żadnej pracy: orchestrator widzi, że `reports/gem-<data>.md` już istnieje z wcześniejszego runu i kończy turę w ~5 turns/20s bez dispatchu Scout→Director, zostawiając stary plik nietknięty — `verify report produced` przechodził, bo sprawdzał tylko obecność/keywords w pliku, nie to, czy ten konkretny run go zmienił. Fix: SKILL.md ma teraz explicit zakaz pomijania pipeline'u z tego powodu + workflow dodatkowo wymaga `git status --porcelain` na pliku raportu (musi się różnić od HEAD) — **uwaga: to sprawdzenie musi teraz biec wewnątrz `data/` (`cd data && git status --porcelain -- "$REPORT_FILE"`), nie w tym repo, bo raport fizycznie żyje w `investing-partner-data`.**
- **Dwa repo w jednym jobie = dwa oddzielne `git remote set-url` przed push.** `claude-code-action@v1` podstawia własny credential helper na runnerze (patrz punkt wyżej) — dotyczy to całego runnera, nie tylko checkoutu, w którym action się wykonał. Fix jest identyczny jak dla `origin`: embedded token w URL (`https://x-access-token:$TOKEN@github.com/...`) bije każdy credential helper, więc krok commitujący do `data/` robi swój własny `git remote set-url` z tokenem z GitHub App, osobno od tego, co dzieje się w root repo.
- `actions/checkout@v4` z `repository:`/`token:`/`path:` na drugie, prywatne repo działa bez konfliktu z pierwszym (domyślnym) checkoutem — muszą tylko mieć różne `path:`. Domyślny `fetch-depth: 1` (shallow) wystarcza — nie potrzeba pełnej historii, żeby czytać/nadpisywać stan i pushować nowy commit na czubek.
- GitHub App installation token (`actions/create-github-app-token`) wygasa po godzinie i jest mintowany od nowa przy każdym runie — nie ma czego "rotować" ręcznie poza samym kluczem prywatnym Appki (patrz `GITHUB_APP_SETUP.md`). To świadomy wybór nad fine-grained PAT: PAT wiąże się z kontem osobistym i wygasa max po 366 dniach, co przy czterech niezależnych cronach oznacza ciche, niezauważone padanie pusha, dopóki ktoś nie zauważy braku maila.
