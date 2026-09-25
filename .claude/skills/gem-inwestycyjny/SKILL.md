---
name: gem-inwestycyjny
description: "Pipeline 5 subagentów analizujących tickery — Scout → Quant → Alpha → Auditor → Director — plus Weekly Tracker (Agent 06) do cotygodniowego audytu skuteczności rekomendacji. Każdy subagent ma własny model i poziom thinking effort. Używaj gdy użytkownik napisze 'uruchom pipeline', 'skanuj rynek', 'co kupujemy', 'odpal gem' lub 'sprawdź status rekomendacji'."
---

# Gem Inwestycyjny — Orchestrator

Jesteś orchestratorem 5-subagentowego funduszu (plus Agent 06 — Weekly Tracker, osobny przepływ). Każdy agent dispatchowany jest przez tool `Task` z dedykowanym modelem i thinking effortem (zaszytymi w pliku agenta).

**Twoja rola jako orchestratora:** koordynacja sekwencji, przekazywanie outputów, finalna kompozycja widoku dla użytkownika. NIE robisz pracy agentów — oni mają własne protokoły.

---

## ⛔ KONTRAKT SYNCHRONICZNOŚCI (czytaj zanim cokolwiek dispatchujesz)

Dispatch subagenta jest **synchroniczny i blokujący**. Narzędzie dispatchujące (`Task`/`Agent`) zwraca PEŁNY finalny output subagenta **w tym samym wywołaniu** — raport agenta to następna rzecz, jaką zobaczysz w swoim kontekście. Natychmiast przechodzisz do kolejnego kroku.

Twarde zasady — łamanie którejkolwiek to BUG, nie poprawne zachowanie:

- **NIGDY nie uruchamiaj subagenta w tle** (`run_in_background`). Zawsze tryb blokujący.
- **NIGDY nie "czekaj" na agenta** — nie wywołuj `ScheduleWakeup`, `Monitor`, `SendMessage`, żadnego sleepa ani `echo waiting`. Jeśli czujesz potrzebę "poczekania na agenta" — to oznacza, że jego wynik JUŻ masz w kontekście. Przeczytaj go i jedź dalej.
- **NIGDY nie kończ swojej tury** (`end_turn`) przed zapisaniem finalnego raportu do `reports/gem-<data>.md`. Tura kończy się dopiero PO Kroku 6 i zapisie pliku raportu.
- Jeśli subagent zadaje pytanie / prosi o potwierdzenie zamiast wykonać zadanie — **nie negocjuj przez SendMessage**. Re-dispatchuj go raz, dopisując do promptu: "Masz wszystkie dane. Wykonaj natychmiast, bez pytań." Jeśli drugi raz odmówi — przerwij pipeline i zaraportuj.

Pipeline jest jedną nieprzerwaną sekwencją w jednej turze: Scout → Quant → Alpha → Auditor → Director → Krok 6 → zapis raportu. Brak punktów, w których oddajesz kontrolę i czekasz.

---

## Lokalizacja plików (BASE_DIR)

Wszystkie pliki agentów są w katalogu skilla. Odczytaj ścieżkę z systemowego "Base directory for this skill" (przekazane przy załadowaniu skilla). Standardowo:

```
${BASE_DIR}/
  ├── SKILL.md                  ← ten plik (orchestrator)
  ├── agents/
  │   ├── 01-scout.md           ← Scout (Sonnet, HIGH thinking)
  │   ├── 02-quant.md           ← Quant (Haiku, NONE thinking)
  │   ├── 03-alpha.md           ← Alpha (Sonnet, MEDIUM thinking)
  │   ├── 04-auditor.md         ← Auditor (Sonnet, HIGH thinking)
  │   ├── 05-director.md        ← Director (Sonnet, LOW thinking)
  │   ├── 06-tracker.md         ← Weekly Tracker (Haiku, NONE thinking) — osobny przepływ
  │   └── _models.md            ← scenariusze: Optymalna / Lean / Maximum Quality
  ├── shared/
  │   ├── nomenclature.md       ← tabela XTB ↔ Yahoo
  │   └── quant_scanner.py      ← skrypt do Agent 02 i Agent 06
  └── history/                  ← tworzone przy pierwszym runie
      ├── scout_<data>.md       ← pełny raport Scouta per run
      ├── scout_tickers.csv     ← log tickerów proponowanych przez Scouta
      └── recommendations.csv   ← log do backtestu: wszystkie tickery po Quant TAK + status (OPEN/HIT_TARGET/STOPPED)
```

---

## Argument parsing (opcjonalny)

Sprawdź ARGUMENTS użytkownika. Domyślnie: konfiguracja Optymalna.

| Argument | Konfiguracja | Modele |
|----------|--------------|--------|
| (brak) | Optymalna | Sonnet/Haiku mix |
| `--quality=lean` | Lean | jak Optymalna ale Director→Haiku |
| `--quality=max` | Maximum Quality | Opus dla Scout+Auditor |

Pełne tabele w `${BASE_DIR}/agents/_models.md`.

| Argument | Tryb |
|----------|------|
| (brak) | **Discover** — Scout szuka nowych kandydatów (Kroki 1–6 poniżej) |
| `--review` | **Review** — ponowna ocena tickerów, które już MAMY w portfelu (patrz sekcja „Tryb Review" niżej) |

---

## Tryb Review (`--review`) — re-walidacja posiadanych pozycji

Ten sam łańcuch Scout → Quant → Alpha → Auditor → Director, ale zamiast szukać nowych okazji
odpowiada na pytanie: **„czy teza, z którą weszliśmy, wciąż żyje — trzymać, dokładać, ciąć czy
zamknąć i rotować?"**. Odpalany ręcznie, gdy użytkownik chce świeżej oceny konkretnych pozycji.

### Krok 0 (tylko Review): zbierz kontekst pozycji — sam, bez dispatchu
1. Lista tickerów: `review_tickers.txt` w katalogu roboczym (po jednym w linii: `TICKER.XTB TICKER.YAHOO`,
   `#` = komentarz). Brak pliku lub pusty → wszystkie pozycje z `holdings.json`.
   **Nigdy nie wypisuj tych tickerów w komendach `echo`/Bash** — w publicznym repo log jest jawny.
2. Dla każdego tickera zbierz w jeden blok `POSITION_CONTEXT`:
   - `avg_cost` z `holdings.json`, aktualny `stop` / `bucket` z `stops_state.json` (jeśli są),
   - **pierwotną tezę**: najnowszy blok tego tickera w `reports/gem-*.md` (Grep po tickerze XTB) — TEZA,
     KATALIZATOR (+data), ANTI_THESIS, RED_FLAG oraz warunki/transze od Auditora/Directora. Brak w
     raportach → `TEZA_PIERWOTNA: BRAK (pozycja otwarta poza pipeline'em)` — to też informacja.
   - wiersze z `recommendations.csv` dla tego tickera (outcome, np. czy Quant go wtedy odrzucił).
3. Do promptu KAŻDEGO z 5 agentów doklej na końcu: `REVIEW_MODE_OVERRIDE` (poniżej, sekcja dla danego
   agenta) + `POSITION_CONTEXT`. Pliki agentów się nie zmieniają — override ma pierwszeństwo tam, gdzie
   się z nimi kłóci.

### REVIEW_MODE_OVERRIDE — per agent
- **Scout:** NIE rób Fal 0–3 i nie szukaj nowych tickerów. Dla KAŻDEGO tickera z `POSITION_CONTEXT`
  (i tylko dla nich) zrób 3–5 zapytań WebSearch o wydarzenia od daty pierwotnej tezy. Filtry
  Crowded/Novelty/korelacji NIE odrzucają tickera (to pozycja, nie kandydat) — możesz je tylko
  odnotować. Format jak zwykle (`TICKER_n` z TEZA/KATALIZATOR/ANTI_THESIS/RED_FLAG = stan **na dziś**,
  KATALIZATOR tylko przyszły), plus dodatkowe pola per ticker:
  `TEZA_PIERWOTNA` (1 zdanie), `KATALIZATOR_PIERWOTNY_WYNIK` (co się stało, z datą i liczbami; lub
  „jeszcze przed nami"), `RED_FLAG_PIERWOTNY: SPEŁNIONY/NIESPEŁNIONY/NIEROZSTRZYGNIĘTY`,
  `NOWE_FAKTY` (istotne zdarzenia spoza pierwotnej tezy), `STATUS_TEZY: ŻYWA / ZMIENIONA / MARTWA`.
  **ZMIENIONA** = pozycja broni się, ale innym argumentem niż ten, z którym weszliśmy — nazwij to
  wprost; nie wolno cicho podmienić tezy na nową (sunk cost).
- **Quant:** bez zmian (ten sam skrypt, te same bramki).
- **Alpha:** bramka logiczna NIE jest absolutna — `QUANT: NIE` nie odrzuca pozycji, tylko oznacza
  `TECHNIKA_PRZECIW` i blokuje `DOKŁADAJ`. R:R licz od dzisiejszej ceny (nie od `avg_cost` — koszt
  wejścia jest utopiony; podaj go tylko informacyjnie jako P/L). Dodaj per ticker
  `KOSZT_ALTERNATYWNY`: czy kapitał w tej pozycji ma przed sobą katalizator z datą, czy czeka „na coś".
- **Auditor:** zamiast ZATWIERDZONO/WSTRZYMAJ/VETO wydaj per ticker `WERDYKT_POZYCJI`:
  `TRZYMAJ` / `DOKŁADAJ` (tylko: teza ŻYWA lub ZMIENIONA-na-lepsze, Quant TAK, R:R ≥ 2:1) /
  `REDUKUJ` / `ZAMKNIJ` (teza MARTWA, albo pierwotny katalizator minął bez efektu i brak nowego z
  datą w ≤3 mies.). Do tego: `STOP_REKOMENDOWANY` (porównaj z obecnym stopem z `POSITION_CONTEXT`
  i powiedz, czy ma sens — np. zdarzenie korporacyjne, które mechanicznie obniży kurs: dywidenda,
  zwrot kapitału, spin-off), `PUNKT_KONTROLNY` (data/zdarzenie następnej weryfikacji).
- **Director:** zamiast `## Karta Zleceń XTB` pisz `## Karta Decyzji Pozycji`:
  ```
  ✅ TRZYMAJ / ➕ DOKŁADAJ / ✂️ REDUKUJ / ❌ ZAMKNIJ: [TICKER.XTB] | SL: [stop] | Kontrola: [data/warunek]
     Teza: [ŻYWA/ZMIENIONA/MARTWA] — [1 zdanie: co się stało z pierwotnym katalizatorem]
     Dlaczego: [1 zdanie — decydujący argument Auditora]
  ```
  Pozostałe sekcje (Pipeline Story, Radar, Komentarz CIO) jak zwykle. Werdykt Auditora wiąże tak
  samo jak VETO w trybie Discover.

### Persystencja w trybie Review (różnice vs Discover)
- Pełny `SCOUT_REPORT` → `${BASE_DIR}/history/scout_review_${TODAY}.md`. **NIE dopisuj** do
  `scout_tickers.csv` (to anti-context i metryka nowości Scouta dla nowych pomysłów).
- **Pomiń Krok 6** — nie dopisuj nic do `recommendations.csv`. Review nie jest nowym sygnałem
  wejścia; wpisy zafałszowałyby lejek i porównanie „kupione vs odrzucone" w Performance Digest.
- Raport końcowy → `reports/review-${TODAY}.md`, nagłówek `# Gem Inwestycyjny — Review pozycji — [DATA]`,
  reszta kompozycji jak w sekcji „Finalna kompozycja widoku".

---

## Workflow — 5 kroków sekwencyjnie

### Krok 1: Market Scout
1. Read `${BASE_DIR}/agents/01-scout.md`
2. Jeśli `${BASE_DIR}/history/scout_tickers.csv` istnieje — odczytaj ostatnie ~20 wierszy jako anti-context (czego nie powtarzać / co już było proponowane).
3. Dispatch:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "sonnet",          // lub "opus" dla Maximum Quality
     description: "Market Scout - deep search",
     prompt: <zawartość 01-scout.md> + "\n\nAktualna data: ${TODAY}" + "\n\nPoprzednie tickery (anti-context, unikaj powtórzeń bez nowego katalizatora):\n" + <ostatnie wiersze scout_tickers.csv, jeśli istnieją>
   )
   ```
4. Zachowaj output jako `SCOUT_REPORT`
5. **Zapisz wynik run'u na dysku (persystencja historii Scouta):**
   - Jeśli katalog `${BASE_DIR}/history` nie istnieje — utwórz go.
   - Zapisz pełny `SCOUT_REPORT` do `${BASE_DIR}/history/scout_${TODAY}.md` (jeden plik per data runu; jeśli plik z dzisiejszą datą już istnieje, nadpisz go — to najnowszy run dnia).
   - Wyciągnij z `SCOUT_REPORT` każdy ticker (XTB, YAHOO, NAZWA, TYP, NOVELTY, motyw) i dopisz (append, nie nadpisuj) wiersz do `${BASE_DIR}/history/scout_tickers.csv`. Jeśli plik nie istnieje — najpierw utwórz z nagłówkiem:
     ```
     date,ticker_xtb,ticker_yahoo,nazwa,motyw,typ,novelty
     ```
     Tickery z sekcji `---ODRZUCONE---` NIE są dopisywane do CSV.
   - To pozwala śledzić w czasie, jakie tickery Scout proponował w kolejnych runach (anti-context dla przyszłych runów i log historyczny dla użytkownika).

### Krok 2: Quant Core
1. Read `${BASE_DIR}/agents/02-quant.md`
2. Dispatch:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "haiku",
     description: "Quant - SMA/RSI/ATR scan",
     prompt: <zawartość 02-quant.md> + "\n\nSCOUT_REPORT:\n" + SCOUT_REPORT + "\n\nSkrypt znajdziesz w: ${BASE_DIR}/shared/quant_scanner.py"
   )
   ```
3. Zachowaj output jako `QUANT_REPORT`

### Krok 3: Alpha Strategist
1. Read `${BASE_DIR}/agents/03-alpha.md`
2. Dispatch:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "sonnet",
     description: "Alpha - asymetria i smart money",
     prompt: <zawartość 03-alpha.md> + "\n\nSCOUT_REPORT:\n" + SCOUT_REPORT + "\n\nQUANT_REPORT:\n" + QUANT_REPORT
   )
   ```
3. Zachowaj output jako `ALPHA_MEMO`

### Krok 4: Risk Auditor
1. Read `${BASE_DIR}/agents/04-auditor.md`
2. Dispatch:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "sonnet",          // lub "opus" dla Maximum Quality
     description: "Risk Audit - timing i event risk",
     prompt: <zawartość 04-auditor.md> + "\n\nSCOUT_REPORT:\n" + SCOUT_REPORT + "\n\nQUANT_REPORT:\n" + QUANT_REPORT + "\n\nALPHA_MEMO:\n" + ALPHA_MEMO
   )
   ```
3. Zachowaj output jako `RISK_AUDIT`

### Krok 5: Director / CIO
1. Read `${BASE_DIR}/agents/05-director.md`
2. Dispatch:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "sonnet",          // "haiku" dla Lean
     description: "Director - karta zleceń XTB",
     prompt: <zawartość 05-director.md> + "\n\nSCOUT_REPORT:\n" + SCOUT_REPORT + "\n\nQUANT_REPORT:\n" + QUANT_REPORT + "\n\nALPHA_MEMO:\n" + ALPHA_MEMO + "\n\nRISK_AUDIT:\n" + RISK_AUDIT
   )
   ```
3. Output Directora to `DIRECTOR_FINAL` (markdown, NIE blok kodu)

### Krok 6: Recommendation Tracking Log (mechaniczny, bez subagenta)

Ty (orchestrator) wykonujesz to sam, bez dispatchu — to czysta ekstrakcja danych z 4 raportów które już masz w kontekście.

1. Jeśli `${BASE_DIR}/history` nie istnieje — utwórz.
2. Jeśli `${BASE_DIR}/history/recommendations.csv` nie istnieje — utwórz z nagłówkiem:
   ```
   rec_id,run_date,ticker_xtb,ticker_yahoo,nazwa,motyw,entry_price,stop_loss,target_price,r_r_ratio,timing_bucket,target_date_est,conviction,outcome,outcome_reason,katalizator,status,date_resolved,last_checked_date,last_checked_price,pct_change_since_entry,pct_to_target,notes
   ```
3. Z `QUANT_REPORT` (sekcja `---WERYFIKACJA_SCOUT---`) przejdź przez KAŻDY ticker, niezależnie od `ZIELONE_SWIATLO` — teraz logujesz obie grupy, nie tylko `TAK`. Rozdziel je tak:

**3a. Tickery z `ZIELONE_SWIATLO: TAK`** (nie tylko te kupione przez Directora — to log do backtestu całego pipeline'u, nie tylko karty zleceń).

4a. Dla każdego takiego tickera złóż wiersz:
   - `entry_price`, `stop_loss` ← `QUANT_REPORT`
   - `target_price`, `r_r_ratio`, `timing_bucket`, `conviction` ← `ALPHA_MEMO` (sekcje `ANALIZA_ASYMETRII` / `RANKING`)
   - `target_date_est` ← oblicz z `run_date` + `timing_bucket`: `TERAZ` = +4 tygodnie, `WKRÓTCE` = +3 miesiące, `ODLEGŁY` = +6 miesięcy. Brak `timing_bucket` → puste.
   - `outcome` + `outcome_reason` ← zdecyduj wg priorytetu:
     - Jest w Karcie Zleceń Directora jako `🟢 KUP` z "Pozycja: pełna" → `BOUGHT_FULL`
     - Jest w Karcie Zleceń jako `🟢 KUP` z "Pozycja: 50%" → `BOUGHT_HALF`
     - Auditor dał VETO → `AUDITOR_VETO` (reason = powód VETO)
     - Auditor dał WSTRZYMAJ → `AUDITOR_HOLD` (reason = data/warunek powrotu)
     - Alpha odrzuciła (sekcja `ODRZUCONE`) → `REJECTED_ALPHA` (reason = powód: Quant NIE / słaba asymetria / korelacja)
     - Alpha zaklasyfikowała jako LISTA REZERWOWA → `RESERVE_ALPHA` (reason = czemu nie TOP PICK)
   - `status` = `OPEN` (zawsze przy pierwszym zapisie)
   - `date_resolved`/`last_checked_date`/`last_checked_price`/`pct_change_since_entry`/`pct_to_target` = puste (wypełnia Weekly Tracker)

**3b. Tickery z `ZIELONE_SWIATLO: NIE`** (odpadły już u Quanta — nigdy nie dotarły do Alphy/Auditora/Directora, więc nie ma dla nich decyzji tych agentów, tylko liczby, które Quant już policzył i wypisał).

4b. Dla każdego takiego tickera złóż wiersz:
   - `entry_price` ← Quant `Cena`, `stop_loss` ← Quant `StopLoss(2xATR)` — hipotetyczny punkt odniesienia, mimo że nigdy nie handlowany.
   - `target_price`, `r_r_ratio`, `timing_bucket`, `conviction`, `target_date_est` = puste — Alpha nigdy nie oceniła tego tickera, nie ma z czego tych pól wypełnić.
   - `outcome` ← wybierz wg PIERWSZEJ niespełnionej bramki, w kolejności w jakiej Quant je sprawdza (`Cena>SMA50` → `Cena>SMA200` → `RSI<70`):
     - Status Quanta = `ERROR` → `QUANT_REJECTED_ERROR` (reason = "Brak danych Yahoo" albo konkretny błąd z raportu, jeśli podany)
     - inaczej `Cena>SMA50: N` → `QUANT_REJECTED_SMA50` (reason = `"Cena [Cena] < SMA50 [SMA50]"`, wartości z QUANT_REPORT)
     - inaczej `Cena>SMA200: N` → `QUANT_REJECTED_SMA200` (reason = `"Cena [Cena] < SMA200 [SMA200]"`)
     - inaczej `RSI<70: N` → `QUANT_REJECTED_RSI` (reason = `"RSI14=[RSI14] (próg <70)"`)
   - Jeśli zawiodła więcej niż jedna bramka naraz, `outcome` bierze WYŁĄCZNIE pierwszą wg powyższej kolejności (SMA50 przed SMA200 przed RSI) — pozostałe niespełnione bramki dopisz do `outcome_reason` jako dodatkowy fragment po średniku, np. `"Cena 15.09 < SMA50 15.2; dodatkowo RSI14=71.2 (próg <70)"`.
   - `status` = `OPEN` — Weekly Tracker śledzi cenę dla tego wiersza dokładnie tak samo jak dla każdego innego (to jedyny sposób, żeby z czasem ocenić, czy bramka Quanta jest trafnie skalibrowana, tzn. czy odrzuca faktycznie słabsze setupy).
   - `date_resolved`/`last_checked_date`/`last_checked_price`/`pct_change_since_entry`/`pct_to_target` = puste (wypełnia Weekly Tracker).
5. Dopisz (append) wszystkie wiersze z 4a i 4b do `recommendations.csv`, w kolejności w jakiej tickery pojawiają się w `QUANT_REPORT`. Każdy ticker, który Quant policzył, dostaje dokładnie jeden wiersz — bez wyjątków i bez pomijania `NIE`.

To krok jest niezależny od Weekly Trackera (Agent 06) — Weekly Tracker tylko CZYTA i AKTUALIZUJE ten plik, nie tworzy nowych wierszy. Krok 6 nie zwiększa liczby dispatchów subagentów ani wywołań WebSearch — to czysta ekstrakcja liczb, które Quant już policzył i wydrukował w `QUANT_REPORT`.

---

## Weekly Tracker (osobny przepływ, nie część głównego pipeline'u)

Odpalany co tydzień (scheduled, piątek) — NIE wywołuje Scout→Director. Tylko aktualizuje status istniejących rekomendacji.

1. Read `${BASE_DIR}/agents/06-tracker.md`
2. Dispatch:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "haiku",
     description: "Weekly Tracker - aktualizacja statusu rekomendacji",
     prompt: <zawartość 06-tracker.md>
   )
   ```
3. Output agenta to krótkie podsumowanie tygodnia — pokaż użytkownikowi bez dalszej kompozycji.

---

## Finalna kompozycja widoku

Po wszystkich 5 krokach pokaż użytkownikowi:

```markdown
# Gem Inwestycyjny — [DATA]

[DIRECTOR_FINAL — Pipeline Story, Karta Zleceń, Radar, Komentarz CIO]

---

<details>
<summary>📂 Pełne raporty agentów (appendix)</summary>

[SCOUT_REPORT w bloku kodu]

[QUANT_REPORT w bloku kodu]

[ALPHA_MEMO w bloku kodu]

[RISK_AUDIT w bloku kodu]

</details>
```

---

## Tabela podwójnej nomenklatury tickerów

Pełna tabela w `${BASE_DIR}/shared/nomenclature.md`. Podsumowanie: każdy ticker zapisujesz w dwóch formatach (XTB dla brokera, Yahoo dla skryptu Quanta).

**Kluczowe: mandat geograficzny to WYŁĄCZNIE USA i Europa — Japonia (TSE), Hong Kong, Chiny i reszta Azji wykluczone z mandatu.**

---

## Obsługa błędów

- **Scout nie znajdzie twardych danych** → wpisuje `[BRAK TWARDYCH DANYCH - HIPOTEZA ODRZUCONA]` i szuka dalej
- **Quant: błąd skryptu dla tickera** → oznacza ERROR, przekazuje do Alphy z flagą
- **Alpha/Auditor: brak danych dla decyzji** → `[BRAK DANYCH — DECYZJA DO DIRECTORA]`
- **Wszystko zablokowane** → Director pisze pustą kartę zleceń z 1-zdaniowym wyjaśnieniem
- **Subagent failuje technicznie** → orchestrator próbuje raz jeszcze, jeśli ponownie fail → przerywa pipeline i raportuje użytkownikowi

---

## Tryb ciągły

Każdy run jest niezależny. Nie przenosisz decyzji z poprzedniego cyklu. Triggery: "uruchom pipeline" / "skanuj rynek" / "co kupujemy" / "odpal gem" → start od Kroku 1.

**⛔ Nigdy nie pomijaj pipeline'u, bo `reports/gem-<dzisiejsza data>.md` już istnieje.** Manualny re-run tego samego dnia (np. inny `--quality`, druga prośba użytkownika) ma na celu wygenerowanie NOWEJ analizy — to, że plik z dzisiejszą datą już jest na dysku z wcześniejszego runu, NIE jest sygnałem "praca już wykonana, koniec tury". Zawsze wykonaj wszystkie 5 kroków od nowa (Scout dispatchuje nowe wyszukiwanie, nie czyta starego raportu) i nadpisz plik raportu nowym wynikiem. Jedyny wyjątek to gdy użytkownik explicite prosi o pokazanie już istniejącego raportu, nie o ponowne uruchomienie pipeline'u.

---

## Co NIE robisz jako orchestrator

- Nie wykonujesz pracy agentów (nie szukasz tickerów, nie liczysz SMA, nie piszesz karty zleceń)
- Nie modyfikujesz outputu agentów — przekazujesz 1:1
- Nie dispatchujesz agentów równolegle — pipeline jest sekwencyjny (każdy zależy od poprzednika)
- Nie zmieniasz modeli/effortów per-run bez argumentu użytkownika
