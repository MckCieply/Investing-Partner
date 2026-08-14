# Performance Digest — miesięczny audyt skuteczności

Deterministyczny (Python, bez LLM) skrypt, który **nie liczy nic samodzielnie
z rynku** — czyta trzy logi, które oba pipeline'y (`gem-inwestycyjny` i
`gem-position-auditor`) już piszą, i liczy z nich metryki, których żaden z
istniejących przepływów nie liczy dziś:

- `.claude/skills/gem-inwestycyjny/history/recommendations.csv` — lejek
  Scout→Quant→Alpha→Auditor→Director, win rate, kalibracja `timing_bucket`,
  i **czy filtr Alpha/Auditor dodaje wartość** (porównanie kupionych vs
  odrzuconych/wstrzymanych tickerów — Weekly Tracker aktualizuje cenę dla
  obu grup, więc to porównanie jest możliwe bez dodatkowych pull'i).
- `closed_positions.csv` — win rate i PnL zamkniętych pozycji Position
  Auditora, per powód (`STOP_HIT`/`TP_OR_MANUAL`) i per bucket.
- `.claude/skills/gem-inwestycyjny/history/scout_tickers.csv` — nowość i
  powtarzalność propozycji Scouta, konwersja Scout→Quant.

## Uruchomienie lokalne
```bash
python skills/performance-digest/performance_digest.py > report.md
```
Opcjonalne flagi `--recommendations` / `--closed` / `--scout` do zmiany ścieżek
źródłowych (domyślne jak wyżej).

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
