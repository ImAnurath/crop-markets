# Lira (TRY/kg) forecasts: findings

Target: Giresun monthly average in-shell price in TRY/kg (pre-2005 old lira / 1,000,000).
Dev period only (target months 2005-02 to 2024-09, 231-236 forecasts per horizon); the
holdout was not touched. Runs: `run_backtest.py --currency try ...`, numbers:
`scripts/lira_findings.py`. Ratios are vs lira naive on the same rows (below 1 = better).
MAPE is the fair measure here: lira MAE is dominated by 2021-24, when prices were 10x higher.

| method (h = 1 / 3 / 6)            | MAPE ratio          | MAE ratio           |
|-----------------------------------|---------------------|---------------------|
| lira naive (MAPE %, MAE TRY/kg)   | 5.8 / 12.8 / 21.8 % | 1.05 / 2.45 / 4.43  |
| lira drift, 36 m                  | 1.07 / 1.12 / 1.17  | 1.08 / 0.99 / 0.86  |
| lira drift, 12 m                  | 1.14 / 1.22 / 1.30  | 1.17 / 1.10 / 0.93  |
| USD naive x FX drift, 36 m        | 1.00 / 0.97 / 0.93  | 1.02 / 0.90 / 0.75  |
| USD naive x FX drift, 12 m        | 1.01 / 0.98 / 0.96  | 1.01 / 0.89 / 0.78  |
| USD naive x FX infl. differential | 1.01 / 0.97 / 0.94  | 1.04 / 0.91 / 0.74  |
| USD naive x FX spot (end of month)| 1.05 / 0.99 / 0.99  | 1.04 / 0.96 / 0.97  |
| USD naive x spot + drift 36 m     | 1.06 / 0.97 / 0.94  | 1.06 / 0.89 / 0.75  |
| SARIMA on log TRY                 | 1.06 / 1.08 / 1.08  | 1.04 / 0.94 / 0.84  |
| LightGBM on TRY (existing inputs) | 1.05 / 1.12 / 1.17  | 1.04 / 0.98 / 0.88  |

USD naive x FX naive is identically lira naive (USD price = TRY price / monthly USD/TRY), so
only a non-trivial FX forecast can add anything. Window: 36 months, chosen for both drifts
on target months up to 2014-12 only (mean MAPE ratio 0.971 vs 0.975 for FX, 1.16 vs 1.31 for
lira drift); 12-month rows are shown so nothing is hidden. Inflation rule: TR CPI 12-month
change (CPI lagged one month) minus a fixed 2.5%/yr for the US (no US CPI in the data).

**Where the gain comes from (MAPE ratio, USD naive x FX drift 36 m, h = 1 / 3 / 6)**

| split (by target month)                     | MAPE ratio          |
|---------------------------------------------|---------------------|
| 2005-2017                                   | 1.01 / 1.02 / 1.02  |
| 2018-2024                                   | 1.00 / 0.85 / 0.71  |
| calm months                                 | 1.02 / 1.01 / 0.99  |
| lira crises (2018-05..12, 2021-09..2023-12) | 0.93 / 0.74 / 0.61  |

Diebold-Mariano on |log error| vs lira naive (Newey-West, h-1 lags): FX drift 36 m p = 0.70 /
0.06 / 0.01; inflation rule p = 0.94 / 0.05 / 0.01; SARIMA and LightGBM never significantly
better (LightGBM worse, p = 0.08 / 0.06 / 0.13). Six FX variants were tried, so treat
p = 0.01 as suggestive, not conclusive.

FX oracle (USD naive x the *realised* USD/TRY of the target month, not a forecast): MAPE
ratio 1.14 / 1.08 / 1.00. Even perfect FX knowledge does not help at 1-3 months: the lira
price is sticky and the USD price absorbs short-run FX moves.

## Verdict

- **Lira naive is hard to beat too.** In percent terms nothing beats it at 1 month. The
  price's own trend (lira drift), SARIMA and LightGBM are all worse than naive, by 5-30%.
- **The one real gain is a smooth nominal trend at 3-6 months**: last price x expected lira
  depreciation (FX drift or inflation differential, interchangeable), 3-7% lower MAPE,
  10-25% lower MAE (MAE is driven by the high-inflation years).
- **It is just the lira's depreciation trend, and only in 2018-24.** In 2005-17 and in calm
  months it is no better than naive. Gains sit in the lira crises and high-inflation years,
  when the lira price catches up with depreciation over a few months. FX news (end-of-month
  spot) adds nothing and hurts at 1 month. There is no hazelnut-market signal here beyond
  what the USD result already said.
- Practical use: for lira planning at 3-6 months, use "last price x trailing 36-month
  USD/TRY depreciation". Expect real gains only while lira inflation is high.
