# Backtest — weryfikacja setupów wejściowych pod kątem realnego edge'u

Projekt badawczy: sprawdzić, czy którykolwiek z kandydujących **setupów wejściowych**
(sygnałów „kup teraz") daje **systematyczny, ex-ante, dostępny retailowi po kosztach
edge nad SPY**. Setupy, które przejdą, miały zasilić przepisanie Scouta (Agent 01)
w pipelinie `gem-inwestycyjny`. Setupy, które nie przejdą, zostają poza pipelinem.

> **Wynik końcowy (2026-06-26): żaden setup nie przeszedł.** ~12–16 setupów w 3 grupach,
> zero z potwierdzonym przez placebo edge'em. Szczegóły i interpretacja niżej oraz w
> `results/group3_data_validation_notes.md`.

---

## 1. Hipoteza i pytanie badawcze

Hipoteza użytkownika: największy edge leży w **narracji** (komunikacja polityczna/medialna
porusza ceny). Projekt rozdziela dwie rzeczy, które łatwo pomylić:

1. **„Narracja porusza rynek"** — PRAWDA, bezdyskusyjna.
2. **„Narracja (lub dowolny setup) daje backtestowalny edge dostępny tobie"** — to jest
   tezą testowaną tutaj. Rynkiem może ruszać narracja, a mimo to nie da się z tego
   systematycznie zarabiać, bo nie wiesz *z góry* która narracja chwyci, a gdy widać,
   że chwyciła — ruch już się dokonał.

Pytanie operacyjne: **czy wejście wg mechanicznego, ex-ante obserwowalnego triggera
bije SPY w horyzoncie T+30/60/90, po kosztach, stabilnie w czasie?**

---

## 2. Początkowe założenia (wspólne dla wszystkich setupów)

Zaimplementowane w `core/backtest_engine.py` i celowo NIEZMIENIANE między grupami,
żeby porównania były uczciwe:

| Założenie | Wartość | Uzasadnienie |
|---|---|---|
| Horyzonty pomiaru | **T+30, T+60, T+90** sesje | średnioterminowy holding, zgodny z profilem pipeline'u |
| Wejście | **T+1 po zdarzeniu, po cenie Open** | brak look-ahead — wchodzisz dzień po tym, jak sygnał był widoczny |
| Benchmark | **SPY** nad tym samym oknem | edge = zwrot netto − zwrot SPY. Liczy się **tylko** edge, nie zwrot bezwzględny |
| Koszty | **0,30% round-trip** (~0,10% prowizja + ~0,05% spread na stronę) | założenie XTB-podobne, nakładane raz na wejściu, raz na wyjściu |
| Stop-loss (warianty) | pct −10% oraz ATR ×2 | raportowane jako wariant; bazowy zwrot bez SL |
| Statystyka centralna | **mediana > średnia** | mediana odporna na pojedyncze grube ogony (które zawyżają średnią) |
| Kohorty roczne | **OBOWIĄZKOWE** | zagregowany edge może być artefaktem jednego anomalnego roku (lekcja z Setup 7) |
| Źródło cen | yfinance, `auto_adjust=True`, cache na dysku | jedno źródło prawdy: `data_layer/prices.py` |

**Reguła doboru próbki (anty-bias, obowiązkowa):** próbka definiowana PROSPEKTYWNIE
przez mechaniczny, ex-ante obserwowalny trigger zastosowany do całego uniwersum —
bierzemy WSZYSTKIE trafienia (te, które zadziałały, i te, które zgasły). Żadnego
doboru „setupów/spółek, które pamiętamy" — to gwarantowany survivorship bias.

---

## 3. Próg PASS — zaostrzany z każdą grupą (multiple testing)

Każda kolejna grupa testuje nowe hipotezy na **tych samych danych**, więc ryzyko
fałszywego pozytywu przez przypadek rośnie. Próg rośnie, by to skompensować:

| Kryterium | Grupa 1 | Grupa 2 | **Grupa 3** |
|---|---|---|---|
| mediana edge vs SPY @ T+90 | > +3% | > +5% | **> +7%** |
| win rate | — | > 57% | **> 58%** |
| dodatnie kohorty roczne | — | ≥ 3/5 | **≥ 80% (≙ 4/5)** |
| n zdarzeń | — | ≥ 40 | **≥ 50** |
| **placebo / negative control** | — | — | **wymagane, wyraźnie słabsze** |
| przeżywa koszty transakcyjne | tak | tak | tak |

Setup musi spełnić **WSZYSTKIE** kryteria swojej grupy. „Prawie" = FAIL.

**Placebo (Grupa 3):** dla każdego setupu druga próbka z tym samym triggerem
technicznym, ale bez warunku narracyjnego. Jeśli placebo daje podobny edge —
edge nie pochodzi z narracji, tylko z techniki. To placebo jest tym, co czyni
test uczciwym.

---

## 4. Struktura repo

```
backtest/
├── core/
│   ├── backtest_engine.py   # run_backtest(): zdarzenia -> wiersze (entry/exit/zwrot/SPY/SL)
│   ├── metrics.py           # summarize_setup(): n, win_rate, mediana, edge vs SPY per horyzont
│   └── cohorts.py           # yearly_cohorts(): rozbicie edge'u na lata kalendarzowe
├── data_layer/
│   ├── prices.py            # yfinance + cache; ATR, RSI, session_offset, get_spy
│   ├── sec_edgar.py         # full-text search 8-K; CIK<->ticker; get_earnings_dates (8-K 2.02 + 10-Q/K)
│   ├── openinsider.py       # Form-4 (insider buys) — wymaga wyłączonego sandboxa sieci
│   ├── finra.py             # bi-weekly short interest
│   └── fred.py              # kalendarz FOMC (statyczny)
├── setups/                  # jeden plik na setup, każdy: build_events() -> run_backtest()
├── results/                 # *_results.csv, *_summary.csv, *_yearly_cohorts.csv, *_placebo*, group*_*.csv
├── run_group1.py / run_group2.py / run_group3.py   # agregacja + werdykt per grupa
└── .cache/                  # ~450MB pobrań (gitignored, regenerowalne)
```

Każdy setup produkuje listę zdarzeń `{"ticker", "event_date", "setup_type", ...}`,
którą silnik zamienia na wiersze (zdarzenie × horyzont) z ceną wejścia/wyjścia,
zwrotem netto, wynikiem stop-loss i benchmarkiem SPY.

---

## 5. Testowane setupy i źródła danych

| # | Setup | Trigger (mechaniczny) | Źródło |
|---|---|---|---|
| **Grupa 1** ||||
| s02 | Konsolidacja/baza | RSI 40–55 przez ≥15 sesji, cena ±5% od średniej | yfinance (S&P 500) |
| s05 | Spinoff | 8-K spinoff | SEC EDGAR |
| s06 | Wejście do S&P 500 | data efektywna dodania | Wikipedia |
| s07 | Insider buying cluster | 3+ insiderów/30 dni + drawdown >25% | OpenInsider |
| s12 | Merger arbitrage | 8-K merger | SEC EDGAR |
| s14 | Rate sensitivity | data decyzji FOMC × ETF wrażliwe na stopy | FRED/FOMC |
| **Grupa 2** ||||
| s08 | FDA/regulatory | zatwierdzenie NDA/BLA | openFDA |
| s09 | Short squeeze candidate | days-to-cover ≥20 | FINRA |
| s11 | Buyback announcement | 8-K „authorized new repurchase program" | SEC EDGAR |
| s20 | Uplisting | 8-K „uplisted to Nasdaq/NYSE" | SEC EDGAR |
| s21 | Lockup expiry | IPO (424B4) + 180 dni | SEC EDGAR |
| **Grupa 3 (narracyjne)** ||||
| s04 | Sektor w niełasce → odbicie | ETF >20% pod 52-tyg szczytem, potem przebicie SMA50 | yfinance (11 ETF SPDR) |
| s03 | Catalyst rerating | wolumen >3× SMA50 + zwrot >+10% w 1 sesji, BEZ earnings ±3 dni | yfinance + SEC EDGAR (earnings) |
| s10 | Geopolityczny arbitraż | **UNTESTABLE WITHOUT BIAS** (patrz niżej) | Federal Register / EUR-Lex |

---

## 6. Wyniki

### Grupa 1
- **s07 insider buying** — wstępnie PASS (+1,4% edge), ale w walidacji robustności
  3y vs 5y edge okazał się niestabilny (patrz `results/s07_robustness_3y_vs_5y.csv`).
- s02, s05, s06, s12, s14 — **FAIL** (edge ujemny vs SPY).

### Grupa 2 (`results/group2_verdict.csv`)
- s08 FDA — **NOT ELIGIBLE (data-capped):** feed openFDA Drugs@FDA nie zawiera ŻADNYCH
  rekordów odrzuceń/CRL → próbka tylko-zatwierdzenia, strukturalnie zawyżona, nie da
  się uczciwie przetestować tezy o katalizatorze regulacyjnym.
- s11, s09, s20, s21 — **FAIL** (edge ujemny, win rate poniżej progu, kohorty 0/5–1/6).

### Grupa 3 (`results/group3_verdict.csv`) — T+90, netto kosztów

| setup | n | win rate | mediana zwrotu | **edge vs SPY** | placebo edge | kohorty + | werdykt |
|---|---|---|---|---|---|---|---|
| s04 sektor w niełasce | 34 | 67,6% | +7,7% | **−2,8%** | −1,1% | 3/5 | **FAIL** |
| s03 catalyst rerating | 254 | 63,4% | +8,5% | **−0,1%** | +1,2% | 5/11 | **FAIL** |
| s10 geopolityczny | — | — | — | — | — | — | **UNTESTABLE** |

**Pułapka, którą wyłapało placebo:** oba setupy w izolacji wyglądają atrakcyjnie
(wysoki win rate, dodatni *surowy* zwrot). Względem SPY edge znika do ~zera/ujemu —
zwroty bezwzględne to beta rynku plus (dla s03) garść grubych ogonów (średnia +16,5%
vs mediana +8,5%, pojedyncze obsunięcia −58% do −84%). Placebo dobija:
- s04: kupowanie pobitego sektora (−2,8%) jest *gorsze* niż to samo przebicie SMA50
  blisko szczytów (−1,1%) — narracja „w niełasce" odejmuje wartość.
- s03: wejście po realnym spike'u narracyjnym (−0,1%) nie bije wejścia w losowy
  normalny dzień (+1,2%) — do T+1 ruch jest już w cenie.

**s10 — dlaczego UNTESTABLE WITHOUT BIAS:** daty legislacji są dostępne (Federal
Register API potwierdzony), ale (1) listy sektorów-beneficjentów nie da się zamrozić
*naprawdę* na ślepo — konstruktor zna już wyniki historyczne; (2) wybór „które ustawy
się liczą" jest uznaniowy → survivorship; (3) „data wejścia w życie" to maksymalnie
nieświeża data wejścia (legislacja wyceniana przy prawdopodobieństwie, nie przy
efektywności). Oznaczono UNTESTABLE zamiast produkować zafałszowany wynik.

---

## 7. Wnioski

Przez 3 grupy: ~12–16 setupów wejściowych, **zero** przeżyło próg z potwierdzonym
przez placebo edge'em. Silny sygnał strukturalny: **generowanie nowych wejść nie jest
źródłem edge'u dostępnego retailowi po kosztach.**

Krytyczne rozróżnienie: to **nie** znaczy „narracja nie porusza rynku" (porusza).
Znaczy „nie da się tego ex-ante, po kosztach, zamienić w backtestowalny sygnał
wejścia tymi narzędziami". To najsilniej uzasadnia pivot na **Agent 6 / zarządzanie
pozycjami** — spójne z wcześniejszą analizą 84 transakcji (zyski w pozycjach
nietkniętych, aktywny trading ujemny).

---

## 8. Lekcje metodologiczne (do reużycia w każdym przyszłym backteście)

1. **Liczy się edge nad benchmarkiem, nie zwrot bezwzględny.** Wysoki win rate i
   dodatni zwrot przy ujemnym edge vs SPY = kupujesz betę, nie alfę.
2. **Placebo / negative control** rozstrzyga, czy edge pochodzi z hipotezy, czy z
   mechaniki technicznej. Bez niego nie wiesz nic.
3. **Kohorty roczne obowiązkowe** — zagregowany edge bywa artefaktem jednego roku
   (np. odbicie po COVID 2020).
4. **Kompletność źródła weryfikuj PRZED backtestem** (openFDA bez odrzuceń; mWIG40
   bez weryfikowalnych dat earnings → wykluczone z s03, by nie skazić próbki PEAD-em).
5. **Survivorship/selection bias** — próbka zawsze z mechanicznego triggera na całym
   uniwersum, nigdy z pamięci. Gdy bias nieusuwalny → oznacz UNTESTABLE, nie kombinuj.
6. **Zaostrzaj próg z liczbą hipotez** (multiple testing).

---

## 9. Uruchomienie

```bash
pip install -r requirements.txt
# pojedynczy setup (buduje zdarzenia + backtest + zapis CSV):
python setups/s03_catalyst_rerating.py
python setups/s04_sector_rebound.py
# agregacja + werdykt grupy:
python run_group3.py
```

Setupy używające OpenInsider (s07) wymagają wyłączonego sandboxa sieci. SEC EDGAR,
yfinance, FINRA i Federal Register działają na domyślnym allowliście. Pierwszy
przebieg pobiera dane do `.cache/` (~450MB); kolejne czytają z cache.
