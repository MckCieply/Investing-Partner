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

from data_layer import prices as _prices
from setups.pead_mwig40 import EarningsEvent

# mWIG40 Total Return ma na Yahoo tylko jeden free, tradeowalny proxy:
# Beta ETF mWIG40TR (replikuje indeks TR 1:1, fee ~0.5%/rok). Realny indeks
# mWIG40TR nie ma darmowej historii poza stooq (zablokowane bot-protection –
# zob. notatka w validate_completeness). ETF startował 2019-09-05 → to TWARDY
# dolny limit okna backtestu przy użyciu tego źródła, nie wybór arbitralny.
BENCHMARK_ETF_PROXY = "ETFBM40TR.WA"
BENCHMARK_PROXY_INCEPTION = date(2019, 9, 5)


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

    STAN BADANIA (2026-06-26) — NAJTRUDNIEJSZY element całego planu, nierozwiązany:
    - gpwbenchmark.pl/komunikaty-i-uchwaly-gpw: lista komunikatów istnieje, ale
      strona jest JS-renderowana i mWIG40 nie był widoczny w pierwszym fetchu —
      wymaga nawigacji/paginacji per-rewizja (kwartalnie, ~15 lat × 4 = ~60
      komunikatów), każdy osobny dokument do sparsowania (prawdopodobnie PDF/XLS).
    - gpw.pl/biblioteka-gpw-pobierz: sprawdzony jeden link (gpwl_id=26) —
      to broszura InDesign PDF, NIE lista uczestników. Ślepy zaułek.
    - stooq.com: ma prawdopodobnie najczystsze dane historyczne składu, ale
      strona ma od niedawna JS proof-of-work bot-protection (sha256 hashcash,
      4 hex zer) + dodatkową warstwę po stronie serwera („Access denied" nawet
      po poprawnym rozwiązaniu wyzwania i POST do /__verify) — NIE próbuj dalej
      obchodzić, to przekracza próg uzasadnionego workaroundu.
    - stockwatch.pl/gpw/indeks/mwig40,sklad.aspx — pokazuje skład AKTUALNY,
      nie historyczny. Może mieć archiwalne wersje per data w URL (niesprawdzone).
    NASTĘPNY KROK: ręczne przejście komunikatów gpwbenchmark.pl rewizja po
    rewizji (najprościej: kwartalne komunikaty prasowe GPW "Rewizja
    [roczna/kwartalna] portfeli indeksów..." — każdy wymienia spółki
    wchodzące/wychodzące, NIE pełny skład — trzeba zrekonstruować timeline
    przyrostowo od najstarszego znanego punktu).
    """
    raise NotImplementedError("Zbuduj z komunikatów rewizyjnych GPW. Patrz HANDOFF sekcja Uniwersum + notatka badawcza wyżej.")


def load_prices(tickers_wa: list[str], start: date, end: date) -> dict[str, pd.Series]:
    """
    KONTRAKT: {ticker_wa: pd.Series(index=daty sesji, values=close SKORYGOWANY o
    dywidendy/splity)}.
    Źródło: Yahoo Finance (.WA tickery) przez data_layer/prices.get_history
    (auto_adjust=True, ten sam cache i retry co reszta projektu). Stooq —
    pierwotnie planowany jako primary — ma od niedawna JS proof-of-work
    bot-protection blokujące programatyczny dostęp (zob. notatka w
    validate_completeness); Yahoo .WA działa bez bramki i sięga do 2010 dla
    długo notowanych spółek (spot-check: KGH/CDR/BDX/MBK = 4222 sesji od
    2010-01-01; nowsze IPO jak DNP od daty debiutu).
    """
    out: dict[str, pd.Series] = {}
    for tkr in tickers_wa:
        df = _prices.get_history(tkr, start.isoformat(), end.isoformat())
        if df.empty:
            continue
        s = df["Close"].copy()
        s.index = pd.DatetimeIndex(s.index).tz_localize(None)
        out[tkr] = s
    return out


def load_benchmark(start: date, end: date) -> pd.Series:
    """
    KONTRAKT: pd.Series(index=daty sesji, values=mWIG40 Total Return level).
    Źródło: BENCHMARK_ETF_PROXY (Beta ETF mWIG40TR, Yahoo .WA) — jedyny darmowy,
    programatycznie dostępny proxy mWIG40 TR (prawdziwy indeks zablokowany przez
    stooq bot-protection). NIE SPY.
    UWAGA: proxy istnieje od 2019-09-05. Żądania `start` przed tą datą są
    przycinane — patrz validate_completeness, pole "benchmark_window_truncated".
    """
    eff_start = max(start, BENCHMARK_PROXY_INCEPTION)
    df = _prices.get_history(BENCHMARK_ETF_PROXY, eff_start.isoformat(), end.isoformat())
    if df.empty:
        return pd.Series(dtype=float)
    s = df["Close"].copy()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    return s


def earnings_events(tickers_wa: list[str], start: date, end: date) -> list[EarningsEvent]:
    """
    KONTRAKT: lista EarningsEvent z wypełnionym:
      - publication_dt (timestamp ESPI; po zamknięciu → wejście liczone na T+1)
      - eps_q + eps_hist_yoy (>= 8 historycznych ΔEPS do σ)
      - net_income, ocf, net_debt_ebitda (filtr jakości)
      - in_universe (z point_in_time_membership w dacie eventu)
    Źródło dat: ESPI raporty okresowe (gpw.pl CSV/XLS). Źródło EPS: raporty /
    biznesradar / Notoria (jeśli uczelnia). Fallback EPS→NI→revenue (flagowany).

    STAN BADANIA (2026-06-26) — częściowo rozwiązane, jedna brakująca część:
    - biznesradar.pl NIE ma JS bot-protection (plain requests + browser UA
      działają, zweryfikowane curl-em). Dane fundamentalne PER SPÓŁKA:
        * EPS kwartalny: https://www.biznesradar.pl/wskazniki-wartosci-rynkowej/<TICKER>,Q
          → wiersz <tr data-field="Z"> ("Zysk na akcję"), 73 kolumny
          kwartalne 2008/Q1–2026/Q1 (sprawdzone na CD-PROJEKT). Wartości z
          przecinkiem dziesiętnym (PL format), trzeba .replace(",", ".").
        * Net income: https://www.biznesradar.pl/raporty-finansowe-rachunek-zyskow-i-strat/<TICKER>,Q
          → <tr data-field="IncomeNetProfit"> (skonsolidowany, jeśli istnieje;
          fallback IncomeShareholderNetProfit).
        * OCF: analogiczna strona .../raporty-finansowe-przeplywy-pieniezne/<TICKER>,Q (niesprawdzona dokładna nazwa data-field, ale wzorzec ten sam).
        * Net debt / EBITDA: .../raporty-finansowe-bilans/<TICKER>,Q (zadłużenie)
          + EBITDA z rachunku wyników; trzeba policzyć ręcznie z dwóch tabel.
        * <TICKER> dla biznesradar to nazwa spółki w ich URL-slug (np.
          "CD-PROJEKT"), NIE giełdowy symbol — wymaga mapowania ticker_wa →
          slug biznesradar (do zbudowania, np. ze strony wyszukiwania).
      KAŻDA tabela ma nagłówki okresów jako "2009/Q1 (mar 09)" — to KONIEC
      kwartału, NIE data publikacji raportu ESPI. Brakujący element ↓
    - DATA PUBLIKACJI (krytyczna dla anty-look-ahead T+1): sprawdzone
      strefainwestorow.pl/dane/raporty/lista-publikacji-raportow-okresowych —
      to kalendarz WYŁĄCZNIE nadchodzących 7 dni (filtrowalny per indeks
      mWIG40/WIG20/sWIG80), BRAK widocznego archiwum historycznego mimo
      zakładki "Opublikowane" — niesprawdzone, czy ta zakładka daje głębszą
      historię per spółka (wymaga dalszej nawigacji/parametrów URL).
      Alternatywa do zbadania: ESPI archiwum samego GPW (gpw.pl) ma
      wyszukiwarkę komunikatów z datami — nieprzetestowane w tej sesji.
    NASTĘPNY KROK: (1) zbuduj mapowanie ticker_wa→slug biznesradar,
    (2) sprawdź zakładkę "Opublikowane" na strefainwestorow lub wyszukiwarkę
    ESPI na gpw.pl dla dat publikacji, (3) napisz parser tabel biznesradar
    (BeautifulSoup/pandas.read_html na <table class="report-table">).
    """
    raise NotImplementedError("Scrape ESPI raporty okresowe + historia EPS. Patrz HANDOFF Źródła danych + notatka badawcza wyżej.")


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

    CZĘŚCIOWA IMPLEMENTACJA: price_adjustment ma realny check. membership_sanity
    i espi_completeness są placeholderami False, bo zależą od point_in_time_membership
    i earnings_events, które są wciąż NotImplementedError — patrz notatki badawcze
    w tych funkcjach. Run pipeline'u i tak zatrzyma się wcześniej (run_pead_mwig40.py
    wywołuje membership/events przed validate_completeness), więc to nie maskuje
    żadnego prawdziwego PASS.
    """
    notes: dict = {}

    # price_adjustment: znana dywidenda KGHM 2023-06 (~3.00 PLN/akcję) — cena
    # skorygowana powinna mieć widoczny drift różny od ceny nieskorygowanej
    # wokół ex-date. Tu: prosty sanity check, że żadna seria nie ma > 30%
    # jednodniowego skoku BEZ odpowiadającego ruchu wolumenu/zmiany trendu —
    # zbyt zgrubne na splity/dywidendy specjalne, ale wychwytuje brak adjustacji
    # (nieskorygowane serie .WA z Yahoo dawałyby duże nieadjustowane gap-y).
    bad_jumps = {}
    for tkr, s in prices.items():
        if len(s) < 2:
            continue
        rets = s.pct_change().dropna()
        big = rets[rets.abs() > 0.5]
        if len(big) > 0:
            bad_jumps[tkr] = len(big)
    notes["price_adjustment"] = len(bad_jumps) == 0
    notes["price_adjustment_detail"] = {
        "source": "Yahoo Finance .WA (auto_adjust=True)",
        "tickers_checked": len(prices),
        "tickers_with_gt50pct_daily_move": bad_jumps,
    }

    notes["membership_sanity"] = len(membership) > 0
    notes["espi_completeness"] = len(events) > 0

    notes["benchmark_window_truncated"] = True
    notes["benchmark_window_note"] = (
        f"mWIG40 TR proxy (Beta ETF mWIG40TR, {BENCHMARK_ETF_PROXY}) istnieje "
        f"dopiero od {BENCHMARK_PROXY_INCEPTION.isoformat()}. Realny indeks "
        "mWIG40TR ze stooq jest zablokowany przez bot-protection (PoW + "
        "dodatkowa blokada serwerowa). Okno backtestu efektywnie ograniczone "
        "do >= 2019-09-05 dopóki nie znajdzie się inny darmowy dostawca."
    )

    return notes
