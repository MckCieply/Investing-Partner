# Plan: Recommendation Tracking (zaimplementowane — krok 6 orchestratora)

## Cel

Po każdym pełnym przebiegu pipeline'u (Scout → Quant → Alpha → Auditor → Director) zapisujemy **każdy ticker, który Quant policzył** — nie tylko faktyczne rekomendacje BUY z Karty Zleceń Directora (`🟢 KUP`) — żeby móc cotygodniowo sprawdzić: czy cena dotarła do targetu, czy uderzył stop loss, czy nic się nie wydarzyło, i czy sama bramka Quanta trafnie odsiewa słabe setupy. Zakres finalny opisuje decyzja 3 niżej. Nie zapisujemy pełnych raportów (to już mamy w `history/scout_*.md` z poprzedniej zmiany) — to log skoncentrowany na metrykach do śledzenia statusu.

Zapis dzieje się raz, po Kroku 5 (Director), na podstawie danych już wyprodukowanych przez Alpha/Quant/Director — żaden agent nie dostaje nowej pracy.

## Gdzie to żyje

`${BASE_DIR}/history/recommendations.csv` — jeden wiersz = jedna rekomendacja BUY z jednego runu. Append-only (nowy run dopisuje nowe wiersze; **aktualizacja statusu istniejących wierszy** to osobna operacja, patrz "Weekly review" poniżej).

## Proponowany schemat (CSV)

| Kolumna | Opis | Źródło |
|---|---|---|
| `rec_id` | unikalny ID (np. `run_date` + `ticker`) | generowany |
| `run_date` | data runu / data rekomendacji | orchestrator (`${TODAY}`) |
| `ticker_xtb` | ticker w formacie brokera | Director (Karta Zleceń) |
| `ticker_yahoo` | ticker do pull'owania cen | Scout/nomenklatura |
| `nazwa` | nazwa spółki | Scout |
| `motyw` | motyw/teza | Scout |
| `entry_price` | cena w momencie rekomendacji | Quant (cena użyta do SMA/RSI) |
| `stop_loss` | SL | Quant → Director |
| `target_price` | cena docelowa (upside target) | Alpha (`UPSIDE_TARGET`) |
| `target_upside_pct` | % do targetu od entry | obliczone (Alpha podaje, albo liczymy) |
| `r_r_ratio` | risk:reward | Alpha |
| `timing_bucket` | TERAZ / WKRÓTCE / ODLEGŁY | Alpha |
| `target_date_est` | szacowana data dotarcia do targetu | obliczone z `run_date` + `timing_bucket` (np. TERAZ=+4 tyg, WKRÓTCE=+3 mies, ODLEGŁY=+6 mies) |
| `conviction` | WYSOKA/ŚREDNIA/NISKA | Alpha |
| `katalizator` | event + data | Scout |
| `position_size` | pełna / 50% | Director (korekta Auditora) |
| `status` | OPEN / HIT_TARGET / STOPPED / EXPIRED / CLOSED_MANUAL | aktualizowane w weekly review |
| `last_checked_date` | data ostatniej kontroli | weekly review |
| `last_checked_price` | ostatnia znana cena | weekly review |
| `pct_to_target` | dystans do targetu w % | obliczone w weekly review |
| `notes` | wolny tekst (np. "RSI przegrzanie, obniżona konwikcja") | opcjonalne |

To 19 kolumn — sporo, ale każda jest 1 polem, nie tekstem; plik zostaje w pełni skanowalny w Excelu/pandas.

## Cykl życia rekordu (`status`)

```
OPEN ──(cena ≥ target_price)──► HIT_TARGET
OPEN ──(cena ≤ stop_loss)──────► STOPPED
OPEN ──(dziś > target_date_est + bufor, brak ruchu)──► EXPIRED
OPEN ──(user manualnie zamknął pozycję)──► CLOSED_MANUAL
```

## Weekly review — co to właściwie robi

Osobny, lekki krok (nie pełny pipeline) odpalany np. raz w tygodniu:

1. Wczytaj `recommendations.csv`, weź wiersze ze `status == OPEN`.
2. Dla każdego tickera pobierz aktualną cenę (kandydaci: rozszerzenie `quant_scanner.py` o pojedyncze pull ceny, albo WebSearch jako fallback).
3. Zaktualizuj `last_checked_date`, `last_checked_price`, `pct_to_target`.
4. Przelicz `status` wg reguł powyżej.
5. Wypisz użytkownikowi krótkie podsumowanie: ile OPEN, ile HIT_TARGET od ostatniego review, ile STOPPED, ile EXPIRED — i ewentualnie flagnij te bliskie targetu/SL (np. <5% dystansu).

To by było naturalne miejsce na ewentualny nowy trigger typu "sprawdź status rekomendacji" / "co z naszymi pozycjami".

## Decyzje (finalne)

1. **Cena przy weekly review** — `quant_scanner.py` (yfinance), ten sam skrypt co Quant Core.
2. **Brak statusu EXPIRED** — to narzędzie do backtestu skuteczności pipeline'u, nie do zarządzania pozycją. Status śledzi cenę w nieskończoność, dopóki nie trafi target albo stop loss: `OPEN / HIT_TARGET / STOPPED`.
3. **Zakres trackingu: WSZYSTKIE tickery, które Quant policzył**, nie tylko te, co przeszły jego bramkę i nie tylko kupione. Każdy wiersz dostaje `outcome` — gdzie i czemu "spadł" z pipeline'u (Quant odrzucił na SMA50/SMA200/RSI / Alpha odrzuciła / Alpha rezerwa / Auditor VETO / Auditor WSTRZYMAJ / Director kupił). To pozwala z czasem ocenić nie tylko, czy Alpha/Auditor łapią dobre sygnały, ale też czy sama bramka techniczna Quanta (SMA50/SMA200/RSI<70) jest dobrze skalibrowana — bez tego nie ma forward-return danych o tym, co ona odrzuca.
4. **Trigger: scheduled, każdy piątek.**

## Finalny schemat CSV (`history/recommendations.csv`)

| Kolumna | Opis | Źródło |
|---|---|---|
| `rec_id` | `run_date` + `ticker_yahoo` | generowany |
| `run_date` | data runu pipeline'u | orchestrator |
| `ticker_xtb` / `ticker_yahoo` | tickery | Scout/nomenklatura |
| `nazwa` | nazwa spółki | Scout |
| `motyw` | motyw/teza | Scout |
| `entry_price` | cena w dniu runu | Quant |
| `stop_loss` | SL (2×ATR) | Quant |
| `target_price` | upside target | Alpha |
| `r_r_ratio` | risk:reward | Alpha |
| `timing_bucket` | TERAZ/WKRÓTCE/ODLEGŁY | Alpha |
| `target_date_est` | konkretna data, liczona z `run_date` + `timing_bucket` (TERAZ=+4tyg, WKRÓTCE=+3mc, ODLEGŁY=+6mc) | obliczone przy zapisie (Krok 6) |
| `conviction` | WYSOKA/ŚREDNIA/NISKA | Alpha |
| `outcome` | BOUGHT_FULL / BOUGHT_HALF / RESERVE_ALPHA / REJECTED_ALPHA / AUDITOR_VETO / AUDITOR_HOLD / QUANT_REJECTED_SMA50 / QUANT_REJECTED_SMA200 / QUANT_REJECTED_RSI / QUANT_REJECTED_ERROR | wyliczone z Quant+Alpha+Auditor+Director |
| `outcome_reason` | 1 zdanie — czemu spadł (lub czemu kupiony) | odpowiedni agent |
| `katalizator` | event + szacowana data | Scout |
| `status` | OPEN / HIT_TARGET / STOPPED | weekly review |
| `date_resolved` | data, w której `status` PIERWSZY RAZ przeszedł z OPEN na HIT_TARGET/STOPPED — zapisywana raz, nigdy nadpisywana | weekly review (Agent 06) |
| `last_checked_date` / `last_checked_price` | ostatni pull ceny | weekly review (quant_scanner.py) |
| `pct_change_since_entry` / `pct_to_target` | przeliczane | weekly review |
| `notes` | wolny tekst | opcjonalne |

`target_date_est` vs `date_resolved` to miara trafności szacowania horyzontu czasowego przez Alphę (np. "WKRÓTCE" miało oznaczać 3 miesiące, faktycznie zajęło 5) — niezależna od tego, czy kierunek (target/stop) był trafny.

## Co implementuję

1. **SKILL.md, Krok 6 (nowy, po Director):** orchestrator zbiera KAŻDY ticker z `QUANT_REPORT`, niezależnie od `ZIELONE_SWIATLO`.
   - Dla `TAK`: wyciąga `entry_price`/`stop_loss` (Quant), `target_price`/`r_r_ratio`/`timing_bucket`/`conviction` (Alpha), `outcome`/`outcome_reason` (Alpha odrzucenie / Auditor werdykt / obecność w Karcie Zleceń Directora).
   - Dla `NIE`: wyciąga `entry_price`/`stop_loss` (Quant), zostawia `target_price`/`r_r_ratio`/`timing_bucket`/`conviction` puste (Alpha nigdy tego tickera nie widziała), a `outcome`/`outcome_reason` wylicza z pierwszej niespełnionej bramki Quanta (SMA50 → SMA200 → RSI, w tej kolejności) lub `QUANT_REJECTED_ERROR` przy braku danych Yahoo.
   - Oba przypadki dostają `status = OPEN`, więc Weekly Tracker śledzi cenę identycznie dla obu grup, bez zmian w samym Trackerze.
   - Dopisuje wiersz do `history/recommendations.csv`.
2. **Nowy agent `agents/06-tracker.md` (Weekly Tracker, model haiku, effort none)** — odpalany osobno (nie część głównego pipeline'u): czyta `recommendations.csv`, filtruje `status == OPEN`, odpala `quant_scanner.py` na unikalnych tickerach, aktualizuje `last_checked_*`, przelicza `pct_to_target`, flipuje `status` na `HIT_TARGET`/`STOPPED` wg reguł cenowych, zwraca podsumowanie tygodnia.
3. **Scheduled task — każdy piątek**, odpala Krok 2 (tracker), bez dotykania głównego pipeline'u Scout→Director.
