# Group 3 (narrative setups) - data-source validation & methodology notes

Group 3 carries the **strictest bar** of the project (median edge vs SPY at T+90
> +7%, win rate > 58%, positive edge in >=4/5 yearly cohorts, n >= 50, AND the
placebo/negative control must be clearly weaker than the real sample, AND the edge
must survive transaction costs). Reason: this is the 12th-16th setup tested on the
same market data, so the multiple-testing risk of a false positive is at its
highest - the bar is raised to compensate.

Every Group 3 setup ships a **placebo / negative control** so we can tell whether
any measured edge comes from the narrative condition or merely from the underlying
technical mechanics.

---

## Setup 4 - Sector out of favour -> SMA50 rebound

- **Source:** yfinance only (11 SPDR sector ETFs + SPY). No external feed, nothing
  to validate for completeness; the trigger is 100% mechanical and ex-ante.
- **Sample is the full population, not a sample:** every >20%-below-52wk-high +
  SMA50-reclaim episode across all 11 ETFs over 2015-2026 is taken (n=34). The low
  n is the honest count of how rarely this regime+turn co-occurs - it is NOT a cap
  we imposed, and was deliberately not loosened to manufacture n>=50.
- **Placebo:** the identical SMA50-reclaim signal in the *opposite* regime (within
  5% of the 52wk high). 383 events - so the "near highs" reclaim is ~11x more
  common than the "out of favour" reclaim.
- **Extended (single-stock) version deliberately omitted:** correct construction
  needs point-in-time sector membership; using today's holdings to trade a
  historical signal is look-ahead/survivorship bias. Per the handoff's own rule,
  left out rather than done with bias.

## Setup 3 - Catalyst Rerating (non-earnings volume+price spike)

- **Price source:** yfinance (current S&P 500 constituents from Wikipedia).
- **Earnings-exclusion source:** SEC EDGAR submissions API
  (`data.sec.gov/submissions/CIK##########.json`), on the default allowlist.
  Completeness matters here: an incomplete earnings feed would let PEAD events leak
  into the "narrative" sample and contaminate the whole test.
  - "Earnings date" = 8-K carrying **item 2.02** (Results of Operations - the
    press-release date that moves the stock) OR a periodic report (10-Q / 10-K).
  - **Completeness verified:** spot-checked AAPL 2016-2026 = 8 such filings/year
    every year (4 quarters x [earnings-8K + periodic]), no gaps. The recent block
    (1000 filings) already spans the whole 2016-2026 window for active large-cap
    filers; older shards are pulled only when their date range overlaps the window.
  - Exclusion window = +-3 calendar days around the spike.
- **Known limitations (flagged, not corrected):**
  1. *Survivorship:* using the *current* S&P 500 excludes names that crashed out of
     the index - mildly biases the up-spike sample toward survivors. Point-in-time
     membership is not freely available.
  2. *mWIG40 excluded:* no free, structured, verifiable archive of Polish
     earnings-announcement dates exists, so the +-3d earnings strip cannot be done
     completely for those tickers. Including them would reintroduce the exact PEAD
     contamination this setup removes. Honest exclusion over a biased sample (same
     principle as the Group 2 openFDA cap).
- **Placebo:** random normal-volume, small-move (|ret|<3%), earnings-free days on
  the same universe, count-matched per ticker, seeded (RANDOM_SEED=42) for
  reproducibility.

## Setup 10 - Geopolitical Arbitrage -> **UNTESTABLE WITHOUT BIAS**

Assessed and **not run**. The conclusion is a methodological one, not a data-access
one. Data access was confirmed available:
- Federal Register API (`federalregister.gov/api/v1`) returns dated final rules
  (publication_date, sometimes effective_on). EUR-Lex similarly archives dated EU
  legislation. So *effective/publication dates are obtainable*.

The setup is nonetheless untestable without bias, for three independent reasons -
any one is disqualifying:

1. **The beneficiary-sector mapping cannot be frozen genuinely blind to outcomes.**
   The test requires a pre-registered "legislation type X -> beneficiary sector Y"
   map defined *before* looking at returns. But whoever builds that map today
   (human or AI) already knows the historical outcomes (IRA -> solar/EV boom then
   bust, CHIPS -> semis, 2022 Russia sanctions -> energy/defence). That knowledge
   cannot be un-known, so any mapping is hindsight-contaminated. The handoff's
   explicit rule: if the beneficiary list can't be built without looking at
   results -> mark UNTESTABLE. It can't.

2. **Selection of *which* legislation counts is discretionary.** The Federal
   Register returns 5,565 rules merely matching "sanctions"; the vast majority move
   nothing. Choosing the "market-moving" ones is a judgment call, and done in
   hindsight it self-selects the memorable hits - textbook survivorship bias in the
   sample-construction step, the single biggest threat the handoff warns about.

3. **The "effective date" is the wrong, and maximally stale, entry date.**
   Legislation is priced when it becomes *probable* (committee -> vote -> signing),
   often months before it takes effect. By the effective date the move is long
   over, so a null result would be uninformative - it would reflect entering late,
   not the absence of a narrative edge. (Immediately-effective surprise sanctions
   are the one partial exception, but reasons 1-2 still apply to them.)

**Decision:** marked UNTESTABLE WITHOUT BIAS rather than fabricating a biased
PASS/FAIL. This is the same discipline as the Group 2 openFDA cap: an honest
"cannot fairly test this" beats a fake number.

---

## RESULTS (T+90, net of round-trip costs)

| setup | n | win rate | median raw return | **edge vs SPY** | placebo edge vs SPY | cohorts positive | verdict |
|---|---|---|---|---|---|---|---|
| s04 sector rebound | 34 | 67.6% | +7.7% | **-2.8%** | -1.1% | 3/5 | **FAIL** |
| s03 catalyst rerating | 254 | 63.4% | +8.5% | **-0.1%** | +1.2% | 5/11 | **FAIL** |
| s10 geopolitical arb | - | - | - | - | - | - | **UNTESTABLE** |

**The trap both setups spring, and why the placebo matters.** In isolation both
look attractive: high win rates (63-68%) and solid positive *raw* returns (+7.7%,
+8.5%). That is exactly the survivorship-flavoured illusion the handoff warned
about. Measured against the only benchmark that counts - SPY - the edge collapses
to roughly zero or negative, because the absolute gains are just market beta plus,
for s03, a handful of fat right-tail winners (mean +16.5% vs median +8.5%, with
single-name drawdowns reaching -58% to -84%).

The placebos are the clincher:
- **s04:** the "out of favour" reclaim (-2.8% vs SPY) is *worse* than the same
  SMA50 reclaim near the highs (-1.1%). The depressed-sector narrative subtracts
  value; you are buying beta in a downtrend.
- **s03:** entering after a real non-earnings narrative spike (-0.1% vs SPY) does
  *no better* than entering on a random normal day (+1.2%). By T+1 the move is
  already in the price. The "catalyst" carries no exploitable information at the
  entry point available to us.

Both also fail the cohort-consistency bar honestly: s04's only positive years are
n=1 noise (its two real cohorts, COVID-2020 n=10 and the 2022 bear n=14, both
underperform SPY); s03 is positive in only 5 of 11 years, carried by the 2020
rebound cohort.

## Group 3 conclusion -> project conclusion

Group 3 was the last group testable with free data, the strictest-bar group, and
the one closest to the user's central thesis (narrative drives the edge). All
testable setups FAIL; the most narrative-pure one (s10) is untestable without bias.

This does NOT contradict "narrative moves the market" - it does. What it shows is
that narrative cannot be turned, *ex ante and after costs, with these tools*, into
a backtestable entry edge: you cannot know in advance which narrative will catch,
and once it visibly has (the spike, the reclaim), the move is already gone.

Across all three groups: ~12-16 entry setups tested, **zero** survive the bar with
a placebo-confirmed edge. That is a strong structural signal that *new-entry
generation* is not where retail edge lives. It redirects the project toward
**position management** (Agent 6) - consistent with the earlier 84-trade analysis
where gains accrued in untouched positions and active trading was net-negative.
