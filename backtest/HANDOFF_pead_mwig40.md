# SESSION HANDOFF → PEAD / Momentum na mWIG40 (plan wykonawczy + teoria)

**Data:** 2026-06-26
**Typ:** handoff WYKONAWCZY (state + frozen definicje + kod). Następca po
`HANDOFF_grupa3.md`. Wynik Grup 1–3: ~12–16 setupów wejściowych FAIL, zero
przeżywa bramkę z placebo. Ten dokument otwiera nowy wątek na nowym uniwersum.

---

## DLACZEGO TO NIE JEST POWTÓRKA 11/11 FAIL

Setupy z Grup 1–3 padły, bo testowane były na **rynku US**, gdzie publiczny
trigger jest natychmiast w cenie (Martineau: rynki coraz efektywniej przetwarzają
zaskoczenia wynikowe dzięki dystrybucji informacji + algo). Underreaction
została wyarbitrażowana.

Teza tego planu NIE brzmi „znajdźmy inny trigger". Brzmi: **ten sam publiczny
trigger (wynik kwartalny) NIEDOREAGUJE na mWIG40, bo nie ma kapitału arbitrażowego,
który zabija niedoreakcję.** Ten sam mechanizm, inny reżim efektywności.

**Zasada nadrzędna:** edge przeżywa wyłącznie tam, gdzie strukturalna bariera
blokuje arbitraż. Bariery mWIG40:
- **Pojemność** — instytucja nie wrzuci sensownego kapitału w cienką spółkę bez
  ruszenia ceny; smart money spłaszczające anomalie w WIG20/US tu fizycznie nie operuje.
- **Pokrycie/uwaga** — mało/zero analityków, wolna dyfuzja. PEAD silniejszy w
  zaniedbanych nazwach.
- **Język + struktura uczestników** — ESPI po polsku, rynek zdominowany przez
  krajowy retail → błędy behawioralne mniej korygowane.

---

## DOWODY SPECYFICZNE DLA GPW (nie tylko literatura US)

To jedyny setup w całym projekcie z **podwójnym dowodem** — globalna literatura
PEAD (Ball-Brown, Bernard-Thomas) PLUS lokalna walidacja na GPW:

1. **Szyszka (2002), "Quarterly Financial Reports and the Stock Price Reaction at
   the WSE" (SSRN 295299):** udokumentowany istotny post-announcement drift na
   GPW. Najczystszy był po **negatywnej** stronie zaskoczenia (spółki z mocno
   rozczarowującymi wynikami kontynuowały spadek).
   → KONSEKWENCJA: na IKE (long-only, brak shorta) negatywny dryf jest sygnałem
     DEFENSYWNYM (nie kupuj / wyjdź), nie pozycją. Strona long (dryf po pozytywnym
     zaskoczeniu) jest tradeowalna, ale wg Szyszki mniej wyraźna — to realne
     ograniczenie, mierzymy obie strony osobno.

2. **Wójtowicz (2011), "Efekt momentum na GPW w Warszawie 2003–2010":**
   udokumentowany efekt momentum na warszawskim parkiecie. To „darmowy" towarzysz
   PEAD — potrzebuje tylko cen, żadnych fundamentów. Setup secondary.

3. **Ostrzeżenie — czysty size jest martwy (Asness/AQR; Robeco 2025):** „czysty"
   efekt rozmiaru znika po uwzględnieniu bety; premia tylko w absolutnie
   najmniejszych, niehandlowalnych firmach. Rozmiar to NIE teza — to **wzmacniacz**
   momentum/value w spółkach o **wysokiej jakości**. Stąd obowiązkowy filtr jakości.

---

## CENTRALNE NAPIĘCIE: edge i koszt z tego samego źródła

Im bardziej spółka niezarbitrażowana (więcej dryfu), tym cieńsza (większy spread).
Handlowalny pas = przecięcie: na tyle płynne by tanio wejść, na tyle zaniedbane
by zachować niedoreakcję. **To jest definicja mWIG40** — płynniejsze niż
sWIG80/NewConnect (gdzie koszt zjada wszystko), mniej zarbitrażowane niż WIG20.
Wybór mWIG40 jest uzasadniony teoretycznie, nie arbitralnie.

→ Dlatego model kosztu nie jest dodatkiem na koniec. JEST warunkiem istnienia tezy.
  Jeśli edge nie przebija spreadu, cała reszta jest martwa (jak raw return s03).

---

## FROZEN DEFINICJE SETUPU (zamrożone z góry — ZERO optymalizacji na danych)

Pełna implementacja: `setups/pead_mwig40.py` (stała `FROZEN_PARAMS`, hashowana do
`RUN_META.json` jako strażnik dryfu definicji).

### Uniwersum
- **Point-in-time** skład mWIG40 (rekonstrukcja z komunikatów rewizyjnych GPW:
  rewizja roczna = 3. piątek marca; korekty kwartalne = 3. piątek VI/IX/XII).
- Survivorship trap: użycie DZISIEJSZEGO składu mWIG40 = look-ahead. To ten sam
  grzech, który już wykluczasz w s03/s04. NIE wolno.
- Nomenklatura podwójna: `TICK.PL` (XTB) / `TICK.WA` (Yahoo/stooq).

### Zdarzenie (event)
- Publikacja raportu okresowego ESPI (skonsolidowany raport kwartalny/półroczny/roczny).
- ESPI jest timestampowane. Jeśli publikacja PO zamknięciu sesji → wejście na
  otwarciu następnej sesji. Anty-look-ahead (analogia do item 2.02 8-K w s03).

### Surprise — SEASONAL RANDOM WALK (bez konsensusu analityków)
```
ΔEPS_q  = EPS_q − EPS_{q−4}                         (zmiana rok-do-roku)
SUE_q   = ΔEPS_q / σ(ΔEPS przez trailing 8 kwartałów)
```
- To definicja Foster / Bernard-Thomas. Livnat & Mendenhall (2006) potwierdzili,
  że surprise z szeregu czasowego jest legalną alternatywą dla konsensusu.
- **Eliminuje potrzebę płatnych danych o konsensusie** (I/B/E/S, Zacks).
- Fallback gdy EPS niedostępny/parsowalny słabo: net income YoY → revenue YoY,
  oznaczone jako surprise niższej jakości (NIE wchodzi do primary PASS).

### Nogi (legs)
- Ranking eventów po SUE na kwintyle (decyle jeśli n pozwoli).
- **LONG (tradeowalna):** top kwintyl SUE → kup, trzymaj T+1 do T+H.
- **SHORT-as-SIGNAL (defensywna, nietradeowalna na IKE):** bottom kwintyl SUE →
  nie trzymaj / wyjdź. Mierzona dla kompletności (najczystszy dryf wg Szyszki),
  ale NIE jako pozycja long.

### Filtr jakości (bo czysty size martwy)
Zamrożony, prosty: spółka kwalifikuje się do LONG tylko gdy spełnia łącznie:
- dodatni trailing net income (rentowna),
- dodatni operacyjny cash flow,
- dźwignia w ryzach (net debt / EBITDA < próg, domyślnie 3.0).
Junk wykluczony — PEAD-long tylko wśród nazw jakościowych (zgodnie z Asness).

### Timing wejścia/wyjścia
- Wejście: otwarcie sesji NASTĘPUJĄCEJ po publikacji ESPI (T+1). Pomija bar
  ogłoszenia (mikrostruktura), zgodnie z literaturą mierzącą dryf od dnia +2.
- Wyjście: zamknięcie T+H.

### Horyzonty i benchmark
- Horyzonty: **T+30 / T+60 / T+90** (standard projektu). Primary = T+90.
- **Benchmark = mWIG40 Total Return** (NIE SPY — to Polska). Edge = return − mWIG40_TR
  w tym samym oknie. Alt do raportowania: WIG.

### Model kosztu (THE killer — explicit, obowiązkowy)
- **Prowizja: XTB IKE = 0** (realna przewaga strukturalna — to spread, nie
  prowizja, jest kosztem).
- **Spread:** half-spread płacony na wejściu i wyjściu. Baza zamrożona:
  **35 bps half-spread = 70 bps round-trip** dla mWIG40. Sensitivity OBOWIĄZKOWA:
  przebieg przy 1x / 2x / 3x. Jeśli da się podpiąć realny bid-ask (stooq intraday /
  IBKR L2) — użyj per-name zamiast stałej.
- **Impact:** dla retail size pomijalny względem spreadu; bindującą barierą jest
  POJEMNOŚĆ (ile kapitału w ogóle przejdzie), nie impact na trade. Udokumentować,
  nie modelować per-trade.

---

## PROGI PASS (zamrożone)

Argument o multiple testing (który windował bar Grup 2→3) tu **nie przenosi się
1:1** — to nowy rynek i hipoteza z podwójną literaturą + pre-rejestracją, nie 17.
test na tych samych danych US. Bar ustawiony rygorystycznie, ale bez sztucznej
inflacji:

**LONG leg (primary), net of costs:**
- median edge vs mWIG40 @ T+90 **> +4%**
- win rate **> 55%**
- edge dodatni w **≥ 60% kohort rocznych** (np. ≥9/15)
- **n ≥ 40** eventów long (łatwo spełnione: ~40 spółek × 4 raporty × top kwintyl × 15 lat)
- **placebo-confirmed:** edge realnych top-kwintyl-SUE wejść MUSI wyraźnie przebić
  placebo (losowe non-earnings wejścia, count-matched, seed=42)
- **robust na koszt:** edge przeżywa sensitivity 2x

**SHORT-as-SIGNAL (defensywny, niższa stawka):** wystarczy stabilnie ujemny edge
(wg Szyszki najczystszy), żeby uzasadnić go jako filtr wyjścia/unikania. Nie
podlega progowi long.

**Placebo (dyscyplina Grupy 3, obowiązkowa):** losowe normalno-wolumenowe
non-earnings dni na tym samym jakościowym uniwersum mid-cap, count-matched
per ticker, `RANDOM_SEED=42` (jak s03). Bez placebo „edge" to tylko beta mid-capa.

---

## ŹRÓDŁA DANYCH (free-first; koszt = czas, nie pieniądze)

| Komponent | Źródło | Status |
|---|---|---|
| Ceny .WA + indeks mWIG40_TR | **stooq** (primary, lepsza jakość PL niż yfinance), yfinance (cross-check) | wymaga walidacji adjustacji (dyw/split) |
| Daty publikacji wyników | **ESPI raporty okresowe**, gpw.pl (CSV/XLS, darmowe) | brak czystego archiwum hist. → scrape/build |
| Historia EPS (do SUE) | raporty okresowe / biznesradar / stockwatch / Notoria (jeśli uczelnia) | najtrudniejszy darmowy element; fallback NI/revenue |
| Point-in-time skład mWIG40 | komunikaty rewizyjne GPW (3. piątek III/VI/IX/XII) | buildable z darmowych komunikatów (labor) |

**Trop uczelniany:** sprawdź czy WSB Merito daje dostęp do **EMIS** albo **Notoria**
przez bibliotekę — to darmowy konsensus + fundamenty PL, inaczej nierozsądnie drogie.

### WALIDACJA KOMPLETNOŚCI PRZED BACKTESTEM (twarda reguła — lekcja Setup 7)
Zanim policzysz cokolwiek, do `data_validation_notes.md`:
1. Archiwum ESPI: spot-check kilku nazw — czy 4 raporty/rok każdego roku, bez luk?
2. Timeline członkostwa: weryfikacja vs znane historyczne zmiany w mWIG40.
3. Adjustacja cen: czy seria .WA poprawnie skorygowana o dywidendy/splity?
Bez tego = ryzyko fałszywego PASS jak pozorny Setup 7 (8 mies. zamiast 5 lat).

---

## PERSYSTENCJA WYNIKÓW (wymóg „persist na repo" — konkretnie)

Automatyczna, przez `core/results_writer.py` wywoływany na końcu
`run_pead_mwig40.py`. Zapis do `results/pead_mwig40/`:

```
results/pead_mwig40/
  pead_mwig40_summary.json     # headline metryki per leg/horyzont
  pead_mwig40_summary.md       # werdykt PASS/FAIL w stylu results projektu
  cohorts_long.csv             # per-rok: edge, win rate, n (long)
  cohorts_short_signal.csv     # kohorty sygnału defensywnego
  placebo_long.csv             # edge placebo do porównania
  cost_sensitivity.csv         # edge @ 1x/2x/3x kosztu
  events_long.parquet          # pełna tabela event-level (frozen, reprodukowalna)
  data_validation_notes.md     # checki kompletności PRZED werdyktem
  RUN_META.json                # git commit, hash FROZEN_PARAMS, seed, snapshot date, timestamp
```

**Strażnik dryfu:** `RUN_META.json` zawiera SHA-256 `FROZEN_PARAMS`. Jeśli ktoś
po cichu zmieni definicję (overfitting), hash się zmieni → widać w diffie repo.

**Git (konwencja projektu):** branch `feat/pead-mwig40`, squash commit. Commituj
RAZEM kod + `results/pead_mwig40/` (wyniki wersjonowane z definicją, która je
wygenerowała).

---

## TEST A / TEST B (framework projektu — bez zmian)
- **Test A** (ten plan): czy mWIG40 PEAD ma edge? Mechaniczny, free data, bez Scouta.
- **Test B** (deferred): czy Scout znajdzie to na żywo (Wayback). Po przejściu Testu A.

---

## STAN TECHNICZNY / PLIKI W TYM HANDOFFIE

Architektura — jedna pluggable granica (data_layer), reszta to działający kod:

```
data_layer/gpw_espi.py   → produkuje inputy (STUB: jedyny element do implementacji)
        ↓ (ceny, eventy, membership, benchmark)
setups/pead_mwig40.py    → czysta logika: SUE, forward returns, edge, kohorty, placebo (RUNNABLE)
        ↓
core/results_writer.py   → persystencja do results/ (RUNNABLE)
run_pead_mwig40.py       → orchestrator spinający całość
```

- `setups/pead_mwig40.py` i `core/results_writer.py` są **samowystarczalne i
  uruchamialne** (smoke-test je przeszedł na danych syntetycznych).
- Metryki (median edge, win rate, kohorty) zaimplementowane minimalnie lokalnie
  dla samowystarczalności. **Przed mergem:** podmień na importy z istniejących
  `core/metrics.py` i `core/cohorts.py`, żeby zachować jedno źródło prawdy
  (dyscyplina shared-code, którą już stosujesz).
- `data_layer/gpw_espi.py` rzuca `NotImplementedError` z dokładnym kontraktem
  każdej funkcji — to jedyna rzecz do dopisania.

---

## MAPA DALSZA (kolejność)
1. Zbuduj `data_layer/gpw_espi.py` wg kontraktu (membership → ceny stooq → ESPI
   scrape → EPS hist). Walidacja kompletności do `data_validation_notes.md`.
2. Podmień lokalne metryki w `setups/` na `core/metrics`+`core/cohorts`.
3. Odpal `run_pead_mwig40.py` → realne wyniki lądują w `results/pead_mwig40/`.
4. Werdykt wg progów PASS. Jeśli LONG PASS + placebo-confirmed → Test B (Wayback).
   Jeśli FAIL → SHORT-signal nadal może żyć jako filtr Agenta 6 (wyjścia).
5. Dług techniczny niski: decyl zamiast kwintyla gdy n urośnie; per-name spread z L2.

## ZAWSZE OTWARTA OPCJA
Jeśli LONG FAIL: wynik nie jest stracony. Defensywny SHORT-signal (dryf po
negatywnym zaskoczeniu, najczystszy wg Szyszki) wpina się wprost w Agenta 6 jako
reguła wyjścia — spójne z analizą 84 transakcji (zyski w pozycjach nietkniętych,
aktywny trading ujemny). Czyli nawet negatywny wynik LONG zasila właściwą dźwignię.
