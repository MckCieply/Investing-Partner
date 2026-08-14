# Performance Digest — miesięczny audyt skuteczności

Deterministyczny (Python, bez LLM) skrypt, który czyta trzy logi, które oba
pipeline'y (`gem-inwestycyjny` i `gem-position-auditor`) już piszą, i liczy
z nich metryki, których żaden z istniejących przepływów nie liczy dziś:

- `.claude/skills/gem-inwestycyjny/history/recommendations.csv` — lejek
  Scout→Quant→Alpha→Auditor→Director, win rate, kalibracja `timing_bucket`,
  i **czy filtr pipeline'u dodaje wartość** (porównanie kupionych vs
  odrzuconych/wstrzymanych tickerów — Weekly Tracker aktualizuje cenę dla
  wszystkich grup, więc to porównanie jest możliwe bez dodatkowych pull'i).
  Od rozszerzenia Kroku 6 orchestratora (log obejmuje też tickery odrzucone
  przez samego Quanta na SMA50/SMA200/RSI, `outcome` = `QUANT_REJECTED_*`)
  grupa "odrzucone/wstrzymane" łączy oba filtry — techniczną bramkę Quanta
  i późniejszy filtr Alpha/Auditora — w jedno porównanie: kupione vs
  wszystko, co pipeline odsiał na dowolnym etapie. To świadoma decyzja, nie
  przeoczenie: nie rozdzielamy wkładu każdego etapu z osobna.
- `closed_positions.csv` — win rate i PnL zamkniętych pozycji Position
  Auditora, per powód (`STOP_HIT`/`TP_OR_MANUAL`) i per bucket.
- `.claude/skills/gem-inwestycyjny/history/scout_tickers.csv` — nowość i
  powtarzalność propozycji Scouta, konwersja Scout→Quant.

Raport otwiera się sekcją **Podsumowanie** — jedna tabela, jeden wiersz per
obszar (rekomendacje, filtr pipeline'u, timing, Position Auditor, Scout),
z werdyktem 🟢/🟡/🔴/⚪ dla każdego. ⚪ oznacza wprost "za mało danych", nigdy
nie udaje pewności, której n nie uzasadnia. Reszta raportu (sekcje 1–6) to
rozwinięcie każdego wiersza podsumowania w tabelę źródłową.

## Benchmark: SPY, nie surowy zwrot
Sekcja 2 (i wiersz "Kupione rekomendacje" w Podsumowaniu) liczy **edge vs
SPY**, nie sam zwrot pozycji — ten sam mechanizm co `backtest/`: zwrot SPY w
DOKŁADNIE tym samym oknie (`run_date` → `last_checked_date`), więc liczy się
tylko to, co pipeline dodał ponad rynek, nie ogólną hossę/bessę. Wymaga
`yfinance`/`pandas` (już w `requirements.txt`) i sieci; jeśli którekolwiek
niedostępne, skrypt **nie failuje** — łapie wyjątek, drukuje ostrzeżenie na
górze raportu i pokazuje surowy zwrot zamiast edge.

`closed_positions.csv` (Position Auditor) **nie ma** kolumny z datą otwarcia
pozycji, więc dla tej sekcji nie da się dopasować okna do SPY — sekcja 5
pokazuje surowy PnL z jawną adnotacją, dlaczego nie ma tam edge.

## Uruchomienie lokalne
```bash
pip install yfinance pandas  # jesli jeszcze nie zainstalowane
python skills/performance-digest/performance_digest.py > report.md
```
Opcjonalne flagi `--recommendations` / `--closed` / `--scout` do zmiany ścieżek
źródłowych (domyślne jak wyżej). Bez `yfinance`/sieci skrypt nadal działa —
patrz sekcja Benchmark wyżej.

## Harmonogram
`.github/workflows/performance-digest.yml` — cron 1. dzień miesiąca, 08:00 UTC,
+ `workflow_dispatch`. Zapisuje `reports/performance-digest-<data>.md`
(commitowany do repo), wysyła mailem (HTML, `convert_markdown: true`, jak
`gem-tracker.yml`). Brak `claude-code-action`, więc brak OIDC/`id-token` —
prosty `actions/checkout` + `actions/setup-python`, żaden krok nie zużywa
limitu Claude Pro.

## Dlaczego miesięcznie, nie co tydzień
Recommendations.csv rośnie o ~1-3 wiersze na run pipeline'u (2×/tydzień) —
tygodniowy digest powtarzałby niemal ten sam obraz. Miesięczna częstotliwość
daje realny przyrost danych między raportami, przy nadal niskim n (raport
sam oznacza sekcje z n < 20 jako orientacyjne).

## Dlaczego to nie jest "drugi backtest/"
`backtest/` testuje, czy dany setup wejściowy ma edge nad SPY w ogóle (n≥50,
placebo, kohorty roczne, próg PASS/FAIL) — patrz `backtest/README.md`. Ten
skrypt audytuje **skuteczność już działającego pipeline'u** (czy filtr
Alpha/Auditor coś daje, czy timing jest skalibrowany) na jego własnym, na
razie małym logu. Nie wydaje werdyktów PASS/FAIL — tylko liczby i flagę
"mała próbka" tam, gdzie n na to zasługuje.

## Rozszerzanie
Nowa sekcja = nowa funkcja `section_*(rows) -> str` w `performance_digest.py`
+ wywołanie w `main()`. Każda sekcja powinna działać na pustych/brakujących
danych źródłowych (repo świeżo sklonowane, logi jeszcze puste) bez wyjątku.
