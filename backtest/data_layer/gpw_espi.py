"""
data_layer/gpw_espi.py
======================
JEDYNA pluggable granica całego planu. Reszta pipeline'u to działający kod.
Każda funkcja rzuca NotImplementedError z dokładnym kontraktem outputu.

Kolejność budowy (wg HANDOFF_pead_mwig40.md):
  1. point_in_time_membership  — rekonstrukcja z komunikatów rewizyjnych GPW
  2. load_prices               — stooq (primary), yfinance (cross-check)
  3. load_benchmark            — mWIG40 Total Return (stooq)
  4. earnings_events           — scrape ESPI raporty okresowe + EPS history
  5. validate_completeness     — checki PRZED backtestem (lekcja Setup 7)

Po implementacji: outputy wpinają się 1:1 do setups/pead_mwig40.py.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from setups.pead_mwig40 import EarningsEvent


def point_in_time_membership(start: date, end: date) -> pd.DataFrame:
    """
    Zwraca timeline członkostwa mWIG40.
    KONTRAKT outputu — DataFrame z kolumnami:
        ticker_wa : str          ("ALE.WA")
        from_date : date         (wejście do indeksu)
        to_date   : date | NaT   (wyjście; NaT = nadal w indeksie)
    Źródło: komunikaty rewizyjne GPW (rewizja roczna = 3. piątek III;
            korekty kwartalne = 3. piątek VI/IX/XII).
    UWAGA survivorship: NIE używać dzisiejszego składu jako proxy historii.
    """
    raise NotImplementedError("Zbuduj z komunikatów rewizyjnych GPW. Patrz HANDOFF sekcja Uniwersum.")


def load_prices(tickers_wa: list[str], start: date, end: date) -> dict[str, pd.Series]:
    """
    KONTRAKT: {ticker_wa: pd.Series(index=daty sesji, values=close SKORYGOWANY o
    dywidendy/splity)}. Primary: stooq. Cross-check: yfinance.
    Walidacja adjustacji obowiązkowa (validate_completeness).
    """
    raise NotImplementedError("stooq primary. Zweryfikuj adjustację przed użyciem.")


def load_benchmark(start: date, end: date) -> pd.Series:
    """KONTRAKT: pd.Series(index=daty sesji, values=mWIG40 Total Return level). Źródło: stooq."""
    raise NotImplementedError("mWIG40_TR ze stooq. NIE SPY.")


def earnings_events(tickers_wa: list[str], start: date, end: date) -> list[EarningsEvent]:
    """
    KONTRAKT: lista EarningsEvent z wypełnionym:
      - publication_dt (timestamp ESPI; po zamknięciu → wejście liczone na T+1)
      - eps_q + eps_hist_yoy (>= 8 historycznych ΔEPS do σ)
      - net_income, ocf, net_debt_ebitda (filtr jakości)
      - in_universe (z point_in_time_membership w dacie eventu)
    Źródło dat: ESPI raporty okresowe (gpw.pl CSV/XLS). Źródło EPS: raporty /
    biznesradar / Notoria (jeśli uczelnia). Fallback EPS→NI→revenue (flagowany).
    """
    raise NotImplementedError("Scrape ESPI raporty okresowe + historia EPS. Patrz HANDOFF Źródła danych.")


def validate_completeness(
    events: list[EarningsEvent],
    prices: dict[str, pd.Series],
    membership: pd.DataFrame,
) -> dict:
    """
    Checki PRZED backtestem (twarda reguła — lekcja Setup 7: pozorny PASS z
    uciętej próbki). Zwraca dict zapisywany do data_validation_notes.md:
      - espi_completeness: czy ~4 raporty/rok/spółka bez luk (spot-check)?
      - membership_sanity: czy timeline zgadza się ze znanymi zmianami mWIG40?
      - price_adjustment: czy serie skorygowane (test na znanej dywidendzie)?
    Jeśli którykolwiek FAIL → NIE uruchamiaj backtestu, napraw źródło.
    """
    raise NotImplementedError("Zaimplementuj 3 checki kompletności. Bez nich ryzyko fałszywego PASS.")
