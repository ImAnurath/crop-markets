# Crop estimates: timing and a national input

Dev period only (target months 2005-02 to 2024-09). The holdout was not touched.
Data: `data/manual/crop_estimate_announcements.csv` (timing table) and
`data/manual/national_crop_estimate.csv` (the national series used as an input). Each row has a source URL.
Rerun with `scripts/run_backtest.py ... --seasons` and `scripts/crop_estimate_check.py`.

## 1. When the estimates come out

- **The Giresun estimate is the Ministry's Giresun figure.** The exchange's 2026 estimate
  (86,440 t) matches the Giresun row of the Ministry of Agriculture's provincial-commission table. The exchange
  page also stores a national figure for each year (`turkiyeRekolte`, 1996-2026). It is a
  pre-harvest estimate, not the final TÜİK number (2014: 388k estimated vs 450k final; 2016: 468k vs 420k).
- **Ministry announcements with a date I could check:** 2016-07-12, 2020-07-17, 2022-07-21,
  July 2023, 2024-07-18, 2025-08-06 (TMO), 2026-07-28. The national figures match the exchange's
  numbers to within 1%.
  KFMİB (exporters) publishes a rival, usually higher estimate a day or so later (2026: 805k against the Ministry's 705k).
  USDA GAIN reports come out in September (2016-09-09, 2017-09-29, 2023-09), which is later than the Ministry's figures.
  TÜİK's first estimate comes out earlier, around May or June, but I verified its numbers for only a few years.
- **2018 is the exception.** No official Ministry estimate had been published by Sep-Oct 2018,
  yet the exchange page shows one. The national input holds 2018 back to November.
  2017, 2019 and 2021 have a known figure but no date I could find. **Nothing before 2014 could be dated.**

**Verdict on "August of Y":** in every year I could check, it is **not a leak**. It is late by
0-1 month: the estimate was usually out by the end of July, and in 2025 it was out on 6 August.
Moving it to July would leak in 2025, so I left the rule as it is. 2018 and the years before 2014 remain unverified.

## 2. What changed

- `dataset.py`: new `national_crop_feature` adds the input columns `nat_crop_estimate_t` and `nat_crop_change`.
  A year's estimate becomes visible in the month given in its `visible_from` column, which is August of Y except for 2018.
  Two new tests check this rule and that later years never leak into earlier rows.
- Each of the three methods that use inputs has a version with the national estimate
  **in place of** the Giresun one: `sarimax_nat`, `season_reg_nat` and `lightgbm_nat` (a new `crop_col` argument, with existing defaults unchanged).
- Baseline scores are reproduced exactly (adding the columns changes nothing). Tests: 46 pass, 43 old and 3 new.

## 3. Dev-period scores: MAE / naive MAE (below 1 beats naive)

| Method | h=1 | h=3 | h=6 |
|:--|--:|--:|--:|
| Naive (MAE 0.230 / 0.456 / 0.711 USD/kg) | 1.000 | 1.000 | 1.000 |
| SARIMAX, Giresun crop | 1.122 | 1.022 | 1.043 |
| SARIMAX, national crop | 1.132 | 1.047 | 1.071 |
| LightGBM, Giresun crop | 1.054 | 1.134 | 1.106 |
| LightGBM, national crop | 1.064 | 1.138 | 1.132 |
| Season regression, Giresun crop | 3.159 | 1.633 | 1.094 |
| Season regression, national crop | 3.609 | 1.849 | 1.207 |

At season level (19 August forecasts): the Giresun crop gives an MAE of 0.688 and the national crop 0.740.
"Same as last season" gives 0.933 and "take the August price" 0.655.
The national version stays worse when season 2018 is left out (0.732 vs 0.700),
and also when its 2018 estimate is allowed to show from August (0.726).

**Timing sensitivity** (every crop estimate one month later; the 2018 Giresun estimate held back to November).
The ratios move by at most 0.03, and sometimes in the better direction.
SARIMAX goes to 1.120/1.016/1.039 and LightGBM to 1.058/1.108/1.086.
So the old results do not depend on the exact publication month, and there is no sign that they gained from a leak.

## 4. Verdict

**Negative result.** A national crop estimate with honest timing does not help.
It is slightly worse than the Giresun estimate in every method and at every horizon, and nothing beats naive.
The publication-timing rule was safe, so the old results stand.
The two crop series are closely correlated (r = 0.76 in August), so the national one adds little new information.
A plausible reason, which I have not tested: the price already reflects supply news before any official figure comes out (rival estimates in June and July, and frost reports).
