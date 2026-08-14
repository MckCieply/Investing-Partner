# Tabela podwójnej nomenklatury tickerów (XTB ↔ Yahoo Finance)

Każdy ticker zapisujesz w dwóch formatach: XTB (dla brokera) i Yahoo (dla skryptów).

| Rynek     | Format XTB  | Format Yahoo | Przykład XTB → Yahoo  |
|-----------|-------------|--------------|------------------------|
| USA       | TICK.US     | TICK         | NVDA.US → NVDA         |
| Polska    | TICK.PL     | TICK.WA      | PKN.PL → PKN.WA        |
| Niemcy    | TICK.DE     | TICK.DE      | SAP.DE → SAP.DE        |
| UK        | TICK.UK     | TICK.L       | SHEL.UK → SHEL.L       |
| Francja   | TICK.FR     | TICK.PA      | AIR.FR → AIR.PA        |
| Holandia  | TICK.NL     | TICK.AS      | ASML.NL → ASML.AS      |
| Norwegia  | TICK.NO     | TICK.OL      | KOG.NO → KOG.OL        |
| Szwecja   | TICK.SE     | TICK.ST      | VOLV-B.SE → VOLV-B.ST  |

**WAŻNE: Mandat geograficzny pipeline'u to WYŁĄCZNIE USA i Europa.** Pomijaj Japonię (TSE), Hong Kong, Chiny i resztę Azji — nie są w mandacie, niezależnie od dostępności na XTB.

## Kraje faktycznie dostępne na XTB (akcje rzeczywiste, nie CFD)

Powyższa tabela to tylko konwencja nazewnicza — **nie gwarantuje, że dany ticker jest faktycznie kupowalny na XTB**. Zweryfikowano 15.08.2026 przez filtr krajów na `xtb.com/pl/specyfikacja-instrumentow` (zakładka "Akcje", 7448 instrumentów, real stocks/STC — czyli dokładnie to, co jest dostępne na koncie IKE). XTB oferuje akcje rzeczywiste **wyłącznie z tych 16-17 krajów**:

Belgia, Czechy, Dania, Finlandia, Francja, Hiszpania, Holandia, Niemcy, Norwegia, Polska, Portugalia, Stany Zjednoczone, Szwajcaria, Szwecja, Wielka Brytania, Wielka Brytania (IOB USD), Włochy.

To jest krótsza/łatwiejsza do zapamiętania lista niż "co jest wykluczone" — każdy ticker spoza tych krajów NIE jest kupowalny na XTB jako real stock, niezależnie od tego, czy heurystyczny format `TICK.KRAJ` z tabeli wyżej "wygląda" poprawnie.

**Pułapka AIM (potwierdzona 14.08.2026, przypadek TUN.L / Tungsten West Plc):**
Filtr krajów XTB ma tylko jedną pozycję "Wielka Brytania" — to główny rynek LSE (Main Market/SETS). **AIM (Alternative Investment Market, londyński rynek dla small-caps) to osobny, znacznie płycej pokryty segment i NIE jest tam objęty jako oddzielna kategoria.** Scout wygenerował `TUN.UK` dla Tungsten West (AIM small-cap, ~£440 mln) zgodnie z konwencją `TICK.UK` z tabeli wyżej — ticker "wyglądał" poprawnie, ale wyszukiwarka na xtb.com zwróciła zero wyników zarówno dla "TUN", jak i "Tungsten West" (test kontrolny: "Almonty" → natychmiast znaleziono `ALM.US`, więc wyszukiwarka działa poprawnie, po prostu instrumentu nie ma w ofercie).

**Praktyczna zasada dla Scouta:** dla każdego kandydata z UK ustal, czy spółka jest notowana na LSE Main Market czy na AIM (widoczne w profilu spółki / Yahoo Finance jako ".L" z adnotacją "AIM" lub w opisie giełdy). Jeśli AIM — traktuj jak NYSE American: wymagaj jawnej weryfikacji dostępności (np. próba wyszukania na `xtb.com/pl/specyfikacja-instrumentow`) zanim ticker trafi do rekomendacji, albo oznacz w karcie ryzyko niedostępności.

Analogiczna, już wcześniej znana pułapka: **NYSE American (dawny AMEX)** też nie jest w pełni pokryte przez XTB mimo że formalnie mieści się w "Stany Zjednoczone" — małe spółki z tej giełdy bywają niedostępne. Ten sam mechanizm ryzyka (drugorzędny/junior segment danej giełdy głównej) dotyczy więc obu rynków.
