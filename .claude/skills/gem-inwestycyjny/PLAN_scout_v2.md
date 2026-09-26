# PLAN — Scout v2: od googlowania motywów do wykrywania zdarzeń

> Status: **plan, nic nie zaimplementowane.** Dokument roboczy z sesji analizy wyników
> pipeline'u (wrzesień 2026). Liczby per ticker/PnL, na których oparto diagnozę, żyją w
> prywatnym `investing-partner-data` (`recommendations.csv`, `scout_tickers.csv`) — tutaj tylko
> wnioski i projekt.

## 1. Diagnoza — dlaczego obecny Scout nie może działać

Scout (Agent 01) jest dziś jedynym źródłem kandydatów dla Quanta, a robi to przez **WebSearch
fraz tematycznych** (`sector rotation … winners`, `gold mining stocks record prices`,
`stocks breaking out …`) i wyciąganie nazw spółek z artykułów. Wady mechanizmu:

1. **Pula kandydatów = to, co zwróci wyszukiwarka.** Artykuły opisują spółki, które już się
   ruszyły i o których już się pisze. Brak ścieżki do spółki, o której nikt nie pisze.
2. **Niepowtarzalne i nietestowalne.** Dwa runy tego samego dnia dają dwie różne listy; nie da
   się odtworzyć, co Google zwróciłoby rok temu → **Scouta nie da się zbacktestować**.
3. **Motyw przed spółką** — prawie każdy run to nowa historia z ostatnich nagłówków, bez
   ciągłości tez między runami.
4. **Opóźnienie** — reakcja dni/tygodnie po newsie, gdy rynek już wycenił informację.
5. **Scout nie widzi danych przed wyborem** — większość propozycji odpada na bramce Quanta
   (spółki w spadku, bo „okazja po spadku" to popularny temat w artykułach).
6. **Wysiłek idzie w weryfikację zamiast w szukanie** — kapitalizacja, insiderzy, data wyników,
   segment giełdy (AIM/NYSE American) czytane z artykułów zamiast z API → złe tickery,
   pomyłki GBP/GBp, spółki niekupowalne na XTB.
7. **Samoocena `NOVELTY` nie niesie informacji** (w danych działa raczej odwrotnie), a powtórki
   tickerów wypadają gorzej niż pierwsze propozycje — anti-context 20 wierszy to za mało.

Na wynikach: kupione rekomendacje wypadły gorzej niż odrzucone na dowolnym etapie; zero
trafionych targetów wśród kupionych. Szczegóły liczbowe — prywatne repo.

## 2. Zasada odwrócenia

| | Dziś | Scout v2 |
|---|---|---|
| Kto generuje kandydatów | LLM przez WebSearch | **deterministyczne skrypty na danych** |
| Kandydat to | spółka, o której się pisze | spółka, w której **w danych coś się wydarzyło** |
| Rola LLM | zgaduje, co będzie modne | **czyta źródło pierwotne i ocenia zdarzenie** |
| Zasięg | kilka nazw z artykułów | całe uniwersum, codziennie/tygodniowo |
| Backtest | niemożliwy | każdy detektor testowalny w `backtest/` przed wdrożeniem |

Kluczowe: **nie oceniamy każdej z ~3000 spółek każdą metodą.** Pytanie brzmi „kto miał
zdarzenie w tym tygodniu?", a każde źródło zwraca listę zdarzeń dla całego rynku naraz —
łączymy ją z uniwersum. Najtańsze dane (cena/wolumen) liczymy na wszystkim, najdroższą pracę
(LLM czytający dokumenty) tylko dla kilkunastu finalistów.

## 3. Warstwa 0 — uniwersum

- Stała lista spółek z mandatu (USA NYSE/NASDAQ + Europa z listy krajów XTB real stocks, patrz
  `shared/nomenclature.md`), **bez AIM i NYSE American**.
- Filtr płynności/kapitalizacji; każdy wiersz ze zweryfikowaną parą `ticker_xtb` ↔ `ticker_yahoo`
  i walutą notowania (GBP vs GBp).
- Odświeżanie raz w miesiącu, deterministycznie, w CI. Plik publiczny (to lista giełdowa, nie dane
  portfela) — np. `shared/universe.csv`.
- Efekt uboczny: zła symbolika i niekupowalne spółki przestają istnieć dla pipeline'u.

## 4. Warstwa 1 — detektory zdarzeń

Każdy detektor = osobna hipoteza, dlaczego cena miałaby dalej rosnąć. Każdy zapisuje
**wszystkie trafienia** (nie tylko przekazane dalej) → darmowa grupa kontrolna i własny track
record per detektor. Detektor, który w pomiarze nie dodaje wartości, wyłączamy.

### a) Raporty okresowe (kwartalne/półroczne/roczne)

- **Pomysł:** post-earnings drift (PEAD) — po zaskoczeniu wynikami cena dryfuje w kierunku
  zaskoczenia przez kolejne tygodnie. Najlepiej udokumentowany w małych/mniej śledzonych
  spółkach i rynkach (stąd otwarty wątek `backtest/HANDOFF_pead_mwig40.md`).
- **Detekcja bez danych o EPS:** dzień raportu widać w notowaniach — luka cenowa przy wolumenie
  3–5× średniej. Kalendarz wyników (Yahoo) tylko potwierdza, że to raport, a nie inny news.
- **Kiedy wchodzimy:** po pierwszym skoku (większość reakcji w dniu raportu), licząc na dryf.
  Nie „przed ruchem".
- **Dane:** kalendarz Yahoo — przyzwoity dla dużych spółek, dziurawy dla europejskich SMID;
  wynik vs konsensus — sensowny dla USA, często brak dla Europy. Treść raportu czyta dopiero LLM.
- **Ryzyko:** PEAD w dużych spółkach USA mocno osłabł — test w `backtest/` obowiązkowy.

### b) Wolumen / technika cenowa

- **Pomysł:** wybicie do szczytu 52 tygodni przy ponadprzeciętnym wolumenie (momentum,
  literatura: George & Hwang 2004); anomalie wolumenu bez newsa jako wczesny ślad akumulacji.
- **Detekcja:** jedno zbiorcze pobranie dziennych OHLCV dla całego uniwersum, cache na dysku
  (pełna historia raz, potem tylko nowe sesje), obliczenia w pandas. Minuty w CI.
- **Kiedy wchodzimy:** na początku / w środku trendu — z definicji po starcie ruchu, licząc na
  kontynuację.
- **Dane:** Yahoo działa, ale niestabilnie — w dotychczasowych runach CI ~11% tickerów bez danych
  w danym runie, z czego większość przejściowo (całe giełdy bez ostatniej sesji). Wymagane:
  ponowienia, uzupełnianie braków w kolejnym runie, kontrola jakości (NaN ostatniej sesji, skoki
  ×100). Zapasowe źródło do sprawdzenia: Stooq. Rate limiting przy ~3000 tickerach — niezbadany.
- **Synergia:** te same dane obsługują bramki Quanta — Quant nie pobiera już niczego osobno.

### c) Transakcje insiderów

- **Pomysł:** zakupy (nie sprzedaże) przez członków zarządu, najsilniejsze gdy kupuje kilku
  insiderów w krótkim oknie (cluster buying). **Jedyny sygnał, który może wyprzedzić ruch ceny**,
  ale słaby i powolny (horyzont miesięcy).
- **Detekcja:** źródła zwracają listę wszystkich zgłoszeń za okres → join z uniwersum. Setki
  wierszy tygodniowo, nie tysiące zapytań.
- **Opóźnienie:** zgłoszenie do 2 dni roboczych po transakcji (US Form 4), do 3 (EU MAR art. 19).
- **Dane (do weryfikacji w CI):**

  | Rynek | Źródło | Ocena |
  |---|---|---|
  | USA | SEC EDGAR Form 4 (dzienny indeks) | dobre — darmowe, oficjalne; wymagany User-Agent z kontaktem, limit 10 req/s |
  | Szwecja | Finansinspektionen, rejestr insiderów | dobre — eksport za zakres dat |
  | Norwegia | Oslo NewsWeb (mandatory notification of trade) | średnie — parsowanie |
  | Niemcy / Francja | BaFin / AMF BDIF | średnie — przeglądarki bez API |
  | UK / Polska | RNS / ESPI | słabe — tekst komunikatów, brak darmowego API |

- **Start:** USA + Szwecja, potem Norwegia. Reszta Europy = osobny projekt per kraj.

### d) Newsy / komunikaty

- **Pomysł:** nie „śledzimy newsów" dla 3000 spółek. Komunikat regulacyjny (kontrakt, buyback,
  podniesienie prognoz) jest zdarzeniem, ale rynek reaguje na niego w minutach, a my działamy raz
  dziennie → sam news jako trigger jest **po fakcie**.
- **Rola:** news to **kontekst dla finalistów**, nie osobny detektor. Czyta go LLM (warstwa 3) dla
  spółek, które już wyłapały detektory a–c — żeby odpowiedzieć, *co* się wydarzyło i czy jest
  istotne.
- **Dane:** kanały per giełda (ESPI, RNS, Oslo NewsWeb, EQS) — największy koszt budowy; na start
  wystarczy WebSearch/WebFetch LLM-a zawężony do jednej spółki i jednego zdarzenia.

### (odłożone) Rewizje prognoz analityków

Darmowe dane słabe (szczególnie Europa), sygnał zwykle *po* ruchu ceny. Nie w pierwszej wersji.

## 5. Co dalej po detekcji — kiedy wchodzi LLM

Kolejność ustawiona tak, żeby **wszystko, co tanie i deterministyczne, odbyło się przed LLM**:

```
Warstwa 0  uniwersum (~3000)                               Python, raz w miesiącu
   │
Warstwa 1  detektory a/b/c                                 Python, CI
   │       → ~100–200 spółek ze zdarzeniem w tygodniu
   │
Warstwa 2  bramki Quanta (względem zdarzenia) + ranking     Python, CI
   │       → ~15–25 spółek
   │
Warstwa 3  LLM — analityk zdarzenia (nowy Scout)            ← TU WCHODZI LLM
   │       → ~3–5 spółek z tezą
   │
Warstwa 4  Auditor (twarde dyskwalifikacje) → Director      LLM
```

### Warstwa 2 — bramki i ranking (Python, bez LLM)

- **Quant przesuwa się przed LLM** — to czysty skrypt, nie ma powodu, żeby LLM oceniał spółki,
  które i tak odpadną na bramce.
- Bramki powinny być liczone **względem zdarzenia**, nie na długich średnich: SMA50/SMA200 z
  definicji spóźniają się o tygodnie/miesiące i spółka po świeżej luce z dołka ich nie przejdzie.
  Przykłady: cena utrzymuje się nad zamknięciem sprzed raportu, luka niezamknięta w N dni,
  wolumen nadal podwyższony. (Konkretne bramki — z trwającego researchu Quanta.)
- Ranking: nakładanie się sygnałów (np. luka po raporcie + zakupy insiderów) > pojedynczy sygnał;
  deduplikacja; pełna historia tickera (kiedy proponowany, z jakiego detektora, jak się skończyło).

### Warstwa 3 — LLM jako analityk zdarzenia

LLM dostaje **konkretną spółkę + konkretne zdarzenie + liczby z warstw 1–2** (reakcja ceny,
wolumen, transakcje insiderów — podane, nie wyszukiwane). Czyta źródło pierwotne (komunikat,
raport, zgłoszenie insidera) i odpowiada na zamknięte pytania:

1. **Co się wydarzyło** — klasyfikacja: wyniki / kontrakt / guidance / M&A / buyback /
   regulacja / insider / brak identyfikowalnej przyczyny.
2. **Czy jest istotne** — np. wartość kontraktu vs roczne przychody, skala zaskoczenia.
3. **Czy jest powtarzalne** — zysk jednorazowy (sprzedaż aktywa, księgowość) vs trwała zmiana.
4. **Ile rynek już wycenił** — na podstawie podanej reakcji ceny od zdarzenia.
5. **Teza + konkretny scenariusz upadku + poziom inwalidacji.**

Wynik strukturalny (pola do CSV: `event_type`, `event_date`, `detector`, `materiality`,
`one_off`, `verdict`, `confidence`), żeby dało się mierzyć, co działa.

**LLM nie robi:** nie wybiera tickerów, nie pobiera cen, nie liczy wskaźników, nie ustala stopów,
nie szuka „motywów". WebSearch tylko w kontekście tej jednej spółki i tego jednego zdarzenia.

Alpha (Agent 03) w obecnej formie przestaje być potrzebny — R:R liczony z targetów z artykułów
i przepuszczający prawie wszystko; jego sensowne części (klasyfikacja timingu, konwikcja)
wchodzą do warstwy 3.

### Warstwa 4 — Auditor i Director

- **Auditor** zawężony do twardych dyskwalifikacji: ryzyko egzystencjalne (upadłość, utrata
  licencji), niekupowalność na XTB, wynik kwartalny < N dni. Bez rutynowego tnięcia do 50% za
  CPI/FOMC (w praktyce prowadziło do zera pełnych pozycji).
- **Director** — tani szablon / Haiku, bez zmian merytorycznych.

## 6. Pomiar (warunek konieczny każdej zmiany)

- Każda propozycja (i każde trafienie detektora, także nieprzekazane dalej) oceniana po
  **stałym horyzoncie T+30/60/90 vs benchmark** (SPY dla USA, STOXX 600 dla Europy), bez
  stopów i targetów — tak jak w `backtest/`.
- Placebo: losowe spółki z tego samego uniwersum, giełdy i dnia.
- Wynik per detektor i per werdykt LLM → wiadomo, która warstwa dodaje wartość.

## 7. Kolejność wdrożenia

1. **Probe workflow w CI** (`workflow_dispatch`, tylko dane publiczne): zbiorcze pobranie ~3000
   tickerów z Yahoo (czas, % braków, rate limit), Stooq jako zapas, jeden dzień SEC EDGAR, tydzień
   z rejestru FI, pokrycie kalendarza wyników Yahoo dla próbki europejskich spółek.
2. **Warstwa 0** — `shared/universe.csv` + skrypt odświeżający.
3. **Detektor b (wolumen/52w high) i a (luka po raporcie)** — oba z tych samych danych cenowych;
   najpierw backtest w `backtest/` z placebo.
4. **Warstwa 2** z bramkami z researchu Quanta.
5. **Warstwa 3** — nowy prompt Scouta jako analityka zdarzenia.
6. **Shadow run 4–8 tygodni** — stary i nowy Scout równolegle, nowy tylko loguje; porównanie wg
   sekcji 6.
7. Detektor c (insiderzy USA + SE), wyłączenie starego Scouta, jeśli nowy wypada lepiej.

## 8. Czego ten plan nie obiecuje

- **Wejścia przed ruchem** — przy danych dziennych z CI wejście jest najwcześniej na otwarciu
  następnej sesji; cel to wejście na początku *drugiej fazy* ruchu (dryf/kontynuacja), nie łapanie
  dołka. Jedyny sygnał potencjalnie wyprzedzający to insiderzy.
- **Edge'u** — to znane anomalie, które przez lata osłabły; wcześniejsze grupy w `backtest/` dały
  FAIL. Architektura gwarantuje tylko, że edge (albo jego brak) będzie **mierzalny przed
  wdrożeniem**, a nie po stracie.
