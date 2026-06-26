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
