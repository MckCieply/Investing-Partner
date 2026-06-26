# Group 2 - data source validation notes

Per the handoff requirement: verify each source's time coverage and known
limitations *before* trusting the backtest it feeds. Findings below.

## Setup 8 - openFDA Drugs@FDA bulk download
- URL: `download.open.fda.gov/drug/drugsfda/drug-drugsfda-0001-of-0001.json.zip`
  (~9.3MB zipped, official FDA data, no auth, no pagination - single file).
- Verified directly against all ~187k submission records in the file:
  `submission_status` only ever takes values `AP` (approved) or `TA`
  (tentatively approved). **Zero rejection/CRL records exist in this feed.**
  This is a hard structural limit, not a filter we applied.
- 29,159 total application records; 687 NDA/BLA original approvals fell
  inside the 5y window; 63 resolved to a public ticker via SEC's
  `company_tickers.json` (sponsor-name match, exact-ish normalization -
  under-counts subsidiaries filing under a different legal name than their
  parent ticker).
- Verdict on the source: complete and authoritative for *approvals*,
  structurally incapable of testing the regulatory-catalyst thesis (which
  needs the rejection arm). Setup capped at NOT ELIGIBLE regardless of
  metrics - see setups/s08_fda_regulatory.py docstring.

## Setup 11 / Setup 20 - SEC EDGAR full-text search (8-K)
- `efts.sec.gov/LATEST/search-index`, free, no auth, indexes filings from
  2001 onward (covers our full 5y window).
- Found and fixed a real pagination bug in `data_layer/sec_edgar.py`: the
  API returns 100 hits/page, but the existing code advanced its `from`
  offset by a hardcoded `page_size=10`, causing massive overlapping
  re-fetches (~10x duplicate hits) and an eventual 500 error on a
  small result set (crashed Setup 21's first run). Fixed to advance by the
  actual hit count and stop at the API's own `total`. The bug did not
  corrupt Setup 11/20's already-collected events (downstream per-ticker
  dedup absorbs duplicates), so those runs were not re-executed.
- Setup 11 query design deliberately uses specific "authorized/approved a
  new ... repurchase program" phrases rather than the bare phrase "stock
  repurchase program" (~450 hits/month, dominated by incidental mentions in
  routine earnings 8-Ks) - precision over recall, by design.
- Setup 20 ("uplisted to ...") similarly avoids forward-looking phrasing
  ("uplisting to Nasdaq" alone returns 700+ hits, mostly statements of
  *intent*, not completed events).

## Setup 9 - FINRA bi-weekly equity short interest
- `cdn.finra.org/equity/otcmarket/biweekly/shrt<YYYYMMDD>.csv`, free, no auth.
- Confirmed file-naming pattern (settlement date = 15th and last calendar
  day of month, shifted back a few days on weekends/holidays) by probing
  6 known months across 2021-2023 - all returned 200 on first or second
  probe, no silent gaps found.
- 119 distinct bi-weekly snapshots fetched across the 5y window
  (~130 expected for exactly 5y x 26/year - the small shortfall is the
  partial first/last month at the window edges, not a coverage gap).
- FINRA's own documentation: pre-June-2021 data is OTC-only, exchange-listed
  short interest was added later. Our window starts ~2021-06, right at that
  boundary - the earliest 2021 cohort may be thinner than later years for
  this reason, visible in the yearly cohort table (n=66 vs n=200+ later).
- No float-shares field exists in this feed, so "% of float" from the
  handoff could not be computed; days-to-cover (>=20) was used as the
  proxy, as the handoff itself anticipated would be necessary.

## Setup 21 - SEC EDGAR full-text search (424B4)
- Same source/fix as Setup 11/20 above.
- "initial public offering" inside 424B4 filings returns 2,000-5,000
  hits/year - paged year-by-year, capped at 500/year, so the 1,408-event
  sample is a sample of a larger true population, not its entirety
  (no silent full-population claim).
- Lock-up length (180 days) is a fixed market-convention assumption, not
  extracted per-filing - flagged as the setup's single biggest noise source
  in setups/s21_lockup_expiry.py.
