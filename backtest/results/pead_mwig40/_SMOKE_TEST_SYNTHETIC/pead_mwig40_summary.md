# PEAD mWIG40 — wyniki

> ⚠️ **SMOKE TEST — DANE SYNTETYCZNE, LOSOWE. To dowód, że pipeline
> persystencji działa, NIE wynik rynkowy. Nie interpretować liczb.**

**Werdykt LONG: FAIL**

## Bramki PASS (LONG, net of costs)

| check | wartość | spełniony |
|---|---|---|
| median_edge_t90 | -4.747731932549015 | ❌ |
| win_rate | 46.15384615384615 | ❌ |
| cohort_share | 0.44 | ❌ |
| n | 65 | ✅ |
| beats_placebo | -4.85 | ✅ |
| robust_2x_cost | -5.45 | ❌ |

## Kohorty roczne (LONG)

|   year |   n |   median_edge_pct |   mean_edge_pct |   win_rate_pct | positive   |
|-------:|----:|------------------:|----------------:|---------------:|:-----------|
|   2010 |   2 |            -11.57 |          -11.57 |           50   | False      |
|   2011 |   4 |             -8.37 |           -8.17 |           25   | False      |
|   2012 |   4 |             -7.54 |           -9.49 |           50   | False      |
|   2013 |   6 |              2.09 |            9.22 |           66.7 | True       |
|   2014 |   7 |             -8.32 |           -5.88 |           42.9 | False      |
|   2015 |   2 |              0.51 |            0.51 |           50   | True       |
|   2016 |   8 |             -9.61 |           -8.97 |           12.5 | False      |
|   2017 |   4 |             -5.06 |           -3.09 |           50   | False      |
|   2018 |   5 |            -12.75 |          -13.17 |           20   | False      |
|   2019 |   6 |             -0.62 |           -7.15 |           50   | False      |
|   2020 |   2 |            -25.15 |          -25.15 |            0   | False      |
|   2021 |   2 |             17.32 |           17.32 |          100   | True       |
|   2022 |   2 |             12.03 |           12.03 |          100   | True       |
|   2023 |   3 |             23.56 |           12.56 |           66.7 | True       |
|   2024 |   4 |              6.93 |            7.67 |           50   | True       |
|   2025 |   4 |              2.16 |           -3.47 |           75   | True       |

## Placebo (negative control)

|   placebo_median_edge_t90_pct |
|------------------------------:|
|                         -4.85 |

## Sensitivity kosztu

|   cost_mult |   median_edge_t90_pct |
|------------:|----------------------:|
|           1 |                 -4.75 |
|           2 |                 -5.45 |
|           3 |                 -6.15 |

## Sygnał defensywny SHORT (nietradeowalny na IKE)

median edge T+90: -4.49% (wg Szyszki najczystszy dryf; filtr wyjścia dla Agenta 6)
