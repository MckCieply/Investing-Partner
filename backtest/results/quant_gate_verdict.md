# Quant Gate — walidacja historyczna bramki technicznej (2026-08-14)

Nie jest to nowy kandydujący setup konkurujący z Grupami 1–3 na tym samym
wyfishowanym zbiorze danych — to walidacja reguły, którą pipeline `gem-inwestycyjny`
**już stosuje na żywo** do każdego tickera Scouta (Agent 02 Quant Core,
`.claude/skills/gem-inwestycyjny/shared/quant_scanner.py`):

```
ZIELONE_ŚWIATŁO = TRUE tylko jeśli WSZYSTKIE TRZY:
    Cena > SMA50
    Cena > SMA200
    RSI14 < 70
StopLoss = Cena − 2×ATR14
```

## Metodologia

- **Uniwersum:** S&P 500 (503 tickery) + ~238 unikalnych dużych/średnich spółek
  z 5 europejskich indeksów blue-chip (DAX, CAC 40, FTSE 100, AEX, IBEX 35) —
  **nie** pełny STOXX 600 (niedostępny bez płatnego źródła danych); świadome
  niedoreprezentowanie europejskich midcapów spoza tych 5 rynków (Skandynawia,
  GPW, mniejsze Beneluksy/Szwajcaria) względem pełnego mandatu USA+Europa
  pipeline'u na żywo. 741 tickerów łącznie.
- **Okres:** 2013-06-01 → 2026-08-14 (~13 lat).
- **Sygnał:** dzień, w którym bramka przechodzi z FALSE na TRUE (flip), nie każdy
  dzień, w którym bramka jest zielona — inaczej jeden wielomiesięczny trend
  liczyłby się jako dziesiątki zdarzeń. Cooldown 20 sesji między flipami tego
  samego tickera (RSI oscyluje wokół progu 70 podczas trendu i bez tego
  wielokrotnie "odpalałby" ten sam ruch jako nowe zdarzenie).
- **Wejście:** T+1 po flipie, cena Open (bez look-ahead) — standardowa konwencja
  silnika (`core/backtest_engine.py`).
- **Wzorce RSI/SMA:** skopiowane 1:1 z `quant_scanner.py` (prosta SMA, RSI liczone
  jako `rolling(14).mean()` przyrostów/spadków), **nie** wariant Wilder/ewm z
  `data_layer/prices.py` używany w innych setupach Grup 1–3 — celowo, żeby testować
  dokładnie tę regułę, którą Quant faktycznie stosuje.
- **Próbka:** 50 426 surowych zdarzeń (flipów) dla pełnej bramki 3-warunkowej w
  całym uniwersum/okresie — capped do 400 przez fixed-seed **uniform** sample
  (nie "najnowsze N"), żeby kohorty roczne zostały zapełnione w całym oknie, nie
  tylko w ostatnich latach.
- **Placebo / dekompozycja** (bramka to AND trzech warunków — trzeba wiedzieć,
  który robi robotę):
  - **Placebo A** — sama `Cena > SMA50` (bez SMA200, bez RSI).
  - **Placebo B** — `Cena > SMA50 AND Cena > SMA200` (bez RSI<70).
  - Realna bramka vs Placebo B izoluje wkład RSI<70. Placebo B vs Placebo A
    izoluje wkład potwierdzenia SMA200.
- **Próg PASS** (bar Grupy 2 — pojedyncza pre-rejestrowana hipoteza — plus
  wymóg placebo z Grupy 3, bo zadanie explicite wymagało dekompozycji):
  n≥50, win rate >55%, mediana edge vs SPY @ T+90 >+5%, ≥60% kohort rocznych
  dodatnich, realna bramka bije najsilniejsze placebo o ≥2pp.

## Wynik @ T+90 (horyzont werdyktu)

| | n | win rate | mediana zwrotu | **mediana edge vs SPY** | dodatnie kohorty |
|---|---|---|---|---|---|
| **Realna bramka (3 warunki)** | 386 | 59.8% | +3.26% | **−2.09%** | 4/13 (31%) |
| Placebo B (SMA50+SMA200, bez RSI) | 383 | 60.6% | +4.08% | −0.63% | 4/13 (31%) |
| Placebo A (sama SMA50) | 389 | 65.3% | +4.88% | **+0.81%** | 6/14 (43%) |

**WERDYKT: FAIL.** Realna bramka nie spełnia 3 z 5 kryteriów:
- edge vs SPY: −2,09% (próg: >+5%)
- kohorty dodatnie: 4/13 = 31% (próg: ≥60%)
- placebo: realna bramka jest **słabsza**, nie silniejsza, od najsłabszego
  testowanego wariantu (Placebo A, sama SMA50) — różnica −2,9pp na niekorzyść
  pełnej bramki.

n≥50 i win rate >55% — jedyne dwa kryteria, które bramka spełnia — **nie
wystarczają same w sobie**: wysoki win rate przy ujemnym edge vs SPY oznacza,
że kupujesz betę rynku (SPY samo w sobie miało w tym okresie dobrą hossę), nie
alfę specyficzną dla tickera. To dokładnie ta sama pułapka, którą Grupa 3
złapała przez placebo (`group3_data_validation_notes.md`).

## Interpretacja — im więcej warunków, tym gorzej

Uszeregowanie edge vs SPY @ T+90: Placebo A (+0,81%) > Placebo B (−0,63%) >
Realna bramka (−2,09%). Dodawanie potwierdzenia SMA200, a potem RSI<70,
**pogarsza** wynik względem SPY, nie poprawia go, na tym historycznym teście.
Możliwe wyjaśnienia (nierozstrzygnięte tym testem):
1. SMA200-potwierdzenie i RSI<70 systematycznie łapią tickery **później** w
   trendzie (bliżej wyczerpania ruchu) niż sama SMA50 — dokładnie ten sam
   mechanizm co "alfa skonsumowana" z reguł Auditora (RAR).
2. Kohorty roczne pokazują, że to nie artefakt jednego roku — 2018, 2019, 2022,
   2023, 2025 wszystkie ujemne dla realnej bramki na T+90, w tym niektóre lata
   z dwucyfrowym ujemnym edge (2018: −7,1%; 2023: −5,6%).

## Co to znaczy dla pipeline'u na żywo

Ten wynik **nie** dowodzi, że Quant powinien zniknąć — bramka wciąż odsiewa
tickery pod SMA50/SMA200 lub z RSI>70 zanim Scout/Alpha/Auditor zainwestują
czas w analizę jakościową, co ma wartość operacyjną niezależnie od czystego
edge'u technicznego. Dowodzi natomiast, że **sama bramka techniczna, w
oderwaniu od research Scouta i osądu Alpha/Auditora, nie jest źródłem edge'u
nad SPY** — spójne z wnioskiem Grup 1–3 dla setupów wejściowych w ogóle
(`## 7. Wnioski` w głównym README). Wartość pipeline'u — jeśli jest — leży w
warstwie narracyjnej/jakościowej nad bramką, nie w samej bramce.

Nie zmieniamy reguł Quanta na podstawie tego jednego testu — to dokument
referencyjny do przyszłej rewizji `02-quant.md`, nie automatyczny trigger zmiany.

## Pliki

`results/s_quant_gate_*` (real), `results/s_quant_gate_placebo_sma50_only_*`,
`results/s_quant_gate_placebo_sma_both_norsi_*` — events/results/summary/yearly_cohorts
per pula. `results/quant_gate_comparison.csv` — pełna tabela wszystkich
horyzontów. `results/quant_gate_verdict.csv` — werdykt maszynowo czytelny.

Uruchomienie: `python setups/s_quant_gate.py` (skanuje uniwersum, ~10-15 min,
network-bound) → `python run_quant_gate.py` (agregacja + werdykt, sekundy).
