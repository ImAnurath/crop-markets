# Price forecasting: every checkpoint, in plain words

Date: 2026-11-06. Branch: `forecasting` (12 commits, not pushed, not merged).
Plan: `docs/superpowers/plans/2026-11-06-price-forecasting.md`. Spec: `docs/superpowers/specs/2026-11-05-price-forecasting-design.md`.
Full results write-up: `reports/forecast_results.md`.

The plan had six "stop and show the user" checkpoints. You asked for the whole plan to be run
and explained afterwards, so this file is those checkpoints written down in order. Each one says
what was built, how the method works, what the numbers say, and what it means.

---

## The headline first

**No method reliably beats the simplest possible forecast, "next month's price = this month's
price" (called *naive*).** That held over 20 years of backtesting (2005-2024) and on the final
24 months that were kept hidden until the very end. The spec says this is a valid, reportable
result: the Giresun USD hazelnut price behaves close to a random walk over 1 to 6 months.

---

## How to read the numbers (once, for all checkpoints)

- **Target:** Giresun exchange monthly average in-shell price, in USD/kg.
- **Horizons:** forecasts are made 1, 3 and 6 months ahead (`h=1`, `h=3`, `h=6`).
- **Walk-forward backtest:** pretend it is January 2005, give each method only what was known at
  that moment, and ask for forecasts. Then step to February 2005 and repeat, through 2024. That
  gives about 230 forecasts per horizon, all made without seeing the future.
- **MAE:** average error in USD/kg. `0.23` means "off by 23 cents per kg on average".
- **MAPE:** the same error as a percentage of the price.
- **Skill:** how much better than naive. `0` = same as naive, `+0.10` = 10% smaller errors than
  naive, `-0.10` = 10% bigger errors. **Above 0 is the only thing that counts as a win.**
- **Fallback share:** how often the method had nothing to say and naive was used instead.
- **Calm vs shock:** the same scores split into the price-spike periods (2005, 2014-15, 2025)
  and everything else, because averages hide where models break.
- **Development period vs holdout:** the last 24 months (Oct 2024 to Sep 2026) were locked away
  while methods were built, then scored once at the end. That stops anyone, including me, from
  tuning a model until it looks good on the test.

---

## Groundwork (Tasks 1-3, no checkpoint)

**Task 1, package skeleton.** The forecasting code lives in an installable package,
`src/hazelnut/forecast/`, with `pytest` tests in `tests/`.

**Task 2, the modelling dataset** (`dataset.py`). This is the part that keeps the results honest.
It builds one table where the row for month *t* holds only what you could have known at the end
of month *t*:

| Input | Row *t* holds | Why |
|---|---|---|
| USD/TRY rate | month *t* | published daily |
| Turkish CPI | month *t-1* | released early the next month |
| Exports (shelled, to World) | month *t-3* | trade data comes ~3 months late |
| FAO production for year *Y* | from December of *Y+1* | annual release lag |
| Giresun crop estimate for *Y* | from August of *Y* | estimate comes out around harvest |
| Spring frost days for *Y* | from May of *Y* | March-April weather is complete by then |
| Giresun traded volume | month *t* | published monthly |

Each rule has its own test, so if someone breaks one, a test fails.

**Task 3, the backtest harness and scoring** (`backtest.py`, `metrics.py`). The harness cuts the
data at each forecast date before handing it to a method, so a method physically cannot see the
future. If a method crashes or gives no answer, that forecast falls back to naive and is marked
as a fallback rather than crashing the run.

---

## Checkpoint 1 (after Task 4): the baselines

**What was built:** two baselines and the script that runs everything
(`scripts/run_backtest.py`).

- **Naive:** the forecast for any horizon is the last price.
- **Seasonal naive:** the last price, adjusted by how much the price has usually moved between
  this calendar month and the target month in past years. For example, "from March to June the
  price has gone up 5% on average, so forecast +5%".

| Method | Skill h=1 | Skill h=3 | Skill h=6 |
|---|---|---|---|
| Naive (MAE 0.23 / 0.46 / 0.71 USD/kg) | 0 | 0 | 0 |
| Seasonal naive | -0.022 | -0.041 | -0.031 |

**What it means:** even the seasonal pattern doesn't help. Hazelnut prices don't follow a
calendar pattern reliable enough to beat "it stays where it is". In shock periods naive's errors
are 2 to 2.5 times bigger than in calm periods. That sets the bar every other method has to clear.

---

## Checkpoint 2 (after Task 5): SARIMA and SARIMAX

**How it works:** SARIMA is the classic statistics tool for time series. It looks at how the
(log) price moved in recent months, and at the same month a year ago, and projects that
forward. It also has a small "drift" term: the average long-run trend. Once a year it tries 36
model shapes and keeps the one that best fits the past. SARIMAX is the same model plus two
outside inputs: the change in the crop estimate and the change in the lira exchange rate.

| Method | Skill h=1 | Skill h=3 | Skill h=6 |
|---|---|---|---|
| SARIMA | -0.043 | -0.019 | -0.039 |
| SARIMAX | -0.122 | -0.022 | -0.043 |

**What it means:** SARIMA comes close to naive (within 2-4%) but never beats it. Adding the crop
and exchange-rate inputs made things *worse* at 1 month (-12%) and no better further out. Those
inputs were not usable as given. Two things contribute: the inputs barely change from month to
month, and for future months the model has to assume them (crop change held flat, exchange
rate unchanged).

---

## Checkpoint 3 (after Task 6): the season-ahead regression

**How it works:** this one thinks in harvest seasons (September to August), not months. Each
August, when the Giresun crop estimate comes out, it asks "last time the crop estimate changed by
this much, how much did the season's average price change?" It fits a straight line through the
past seasons. A big crop should mean lower prices, a small crop higher prices. To fit the
monthly table, every month of the coming season gets that predicted season average. Before
August it has no estimate yet, so it falls back to naive. That is why its fallback share is 17%
at 3 months and 42% at 6 months.

**Monthly table:** skill -2.16 / -0.63 / -0.09. Much worse than naive at short horizons, which is
expected: it predicts one flat number for a whole year, while the real price moves every month.

**Season table (the fairer test, 19 seasons 2005-2023):**

| One forecast per August for the season's average | MAE (USD/kg) |
|---|---|
| Season regression | 0.69 |
| "Same as last season's average" | 0.93 |
| "Same as the August price" | 0.66 |

**What it means:** the crop estimate carries real information. The regression beats "same as last
season" by a clear margin. But simply taking the August price is just as good, because the
market already prices the crop news in by August. With only 19 seasons, treat this as a hint, not
proof.

---

## Checkpoint 4 (after Task 7): LightGBM

**How it works:** LightGBM is a machine-learning method that builds hundreds of small decision
trees ("if the price rose more than 10% over 3 months and the crop estimate fell, then…"). There
is one model per horizon, retrained every month on 13 features: recent price changes, the
month, crop change, frost days, export growth, exchange-rate changes and traded volume.
Parameters were fixed in advance, with no tuning against results.

| Method | Skill h=1 | Skill h=3 | Skill h=6 |
|---|---|---|---|
| LightGBM | -0.054 | -0.134 | -0.106 |

Most-used features (for the model trained on all development data): the price's own recent
changes (1, 3, 6, 12 months), export growth, and the 12-month exchange-rate change. Crop
change and frost only appear near the bottom of the 6-month list.

**What it means:** more inputs and a more flexible model gave worse forecasts, not better. With
only ~230 months of training data, LightGBM learns patterns that don't repeat. It does
especially badly during price spikes (-30% at 3 and 6 months). This is a common and honest
finding on small economic datasets.

**One fix along the way:** in March 2022 the export figure is exactly zero. That produced an
"infinite" export-growth value. It now counts as "unknown" instead, and has a test.

---

## Checkpoint 5 (after Task 8): Chronos-Bolt

**How it works:** Chronos-Bolt is a pretrained "foundation model" for time series, made by Amazon
and trained on a huge number of unrelated series. It gets nothing but the price history and is
not trained on our data at all ("zero-shot"). It runs on a normal CPU, takes about 9 seconds for
the whole backtest, and downloaded about 190 MB of model weights once.

| Method | Skill h=1 | Skill h=3 | Skill h=6 |
|---|---|---|---|
| Chronos-Bolt | -0.082 | -0.072 | -0.064 |

**What it means:** a general-purpose pretrained model is respectable (within 6-8% of naive with
zero setup) but does not know anything special about hazelnuts. It also loses most during shocks.

---

## Checkpoint 6 (after Task 10): the comparison and the final holdout

**Development period, all methods together** (also in `reports/forecast_results.md`, with the
chart `reports/figures/10_skill_vs_naive.png` and the forecast-vs-actual panels
`reports/figures/11_forecast_3m_vs_actual.png`):

| Method | Skill h=1 | Skill h=3 | Skill h=6 |
|---|---|---|---|
| Seasonal naive | -0.022 | -0.041 | -0.031 |
| SARIMA | -0.043 | -0.019 | -0.039 |
| SARIMAX | -0.122 | -0.022 | -0.043 |
| Season regression | -2.159 | -0.633 | -0.094 |
| LightGBM | -0.054 | -0.134 | -0.106 |
| Chronos-Bolt | -0.082 | -0.072 | -0.064 |

Every number is negative: nothing beats naive.

**Final holdout (Oct 2024 to Sep 2026, 24 forecasts per horizon, scored once):**

| Method | Skill h=1 | Skill h=3 | Skill h=6 |
|---|---|---|---|
| Seasonal naive | -0.031 | -0.063 | -0.031 |
| SARIMA | **+0.047** | -0.016 | -0.011 |
| SARIMAX | -0.048 | -0.013 | -0.009 |
| Season regression | -2.084 | -0.148 | **+0.176** |
| LightGBM | **+0.052** | -0.044 | -0.216 |
| Chronos-Bolt | -0.146 | +0.002 | +0.008 |

**What it means:** a few methods squeak ahead at one horizon on the holdout, but each of them
loses at another horizon, and none of them won on the 20-year development period. With only 24
forecasts, half of them inside the 2025 price spike, one or two big misses swing these numbers.
The honest conclusion stays the same: at 1-6 months, "the price stays where it is" is very hard
to beat for this market.

**What this means for the project:** the forecasting part is a solid, defensible portfolio piece
*because* it reports the losing result honestly with a leak-free test. Possible next steps, if you
want them later: a national crop estimate (TÜİK) instead of Giresun's regional one, verifying
when the crop estimate really gets published, forecast ranges instead of single numbers, and
the lira price (USD forecast times exchange rate).

---

## Decisions I made on your behalf

These are the places where I chose something the plan didn't spell out. Each one says what it
costs if I was wrong.

1. **Worked on branch `forecasting` in the main folder**, not a separate copy. Cost if wrong: none.
2. **Didn't stop at each checkpoint.** You asked for the full run plus this file instead.
   Cost if wrong: you didn't get to steer between steps.
3. **Ran the one-time holdout without a separate go-ahead**, because you asked for the whole
   plan. Nothing was changed after seeing it. Cost if wrong: the holdout is now "used up"
   before you saw the development results.
4. **Lock file written without the machine-specific `-e file:///D:/...` line.** Cost: none.
5. **If a method fails for all horizons at once, the harness retries one horizon at a time.**
   This was needed so one failing horizon doesn't wipe out the others. Cost: a bit slower when
   something fails.
6. **Forecasts that are missing, infinite or ≤ 0 count as fallbacks.** Cost: a broken model
   output shows up as fallback share rather than a crash.
7. **Only the horizons that will be scored are requested.** Cost: none.
8. **SARIMA/SARIMAX include a drift (long-run trend) term.** The plan didn't say, and its own
   test needs it. Cost: if the drift hurts, it shows as worse skill, which it may partly explain.
9. **`season_backtest` has an optional `first_season` setting** (default 2005, as planned). Cost: none.
10. **Added `scikit-learn`** because LightGBM's interface requires it. Cost: one extra package.
11. **Zero exports count as "unknown"** in the export-growth feature. Cost: LightGBM loses one
    month of export signal.
12. **LightGBM feature importances are printed for a model trained on all development data.**
    Cost: none.
13. **The holdout safety check runs for every method before any of them starts**, and holdout
    mode prints seasons from 2024 only. Cost: none.
14. **Figures are named `10_…` and `11_…`** because `05_`/`06_` were already used by the first
    notebook. Cost: none.
15. **`reports/figures/` stays out of git** (your existing setting), so the images in the
    results file only show after you run the notebook. They are broken links on GitHub. Cost:
    commit the figures if you want them on GitHub.
16. **The plain-language summaries are written inside the notebook** after reading the numbers.
    Cost: they go stale if results change.
17. **The final review's report fix was checked against the data, not a unit test.** Cost: a
    later rerun could make the prose stale unnoticed.
18. **Crop-estimate timing is still unverified.** The spec flags August as an assumption. If the
    file holds later-revised estimates rather than the first published ones, the methods that
    use crop data look slightly better than they should. They still lose to naive, so the
    headline holds.

## Review

The plan calls for a fresh reviewer at the end. That call was blocked: a plugin hook rewrites
subagent calls, so auto mode couldn't check it. I did the review myself instead, which is weaker
than a fresh pair of eyes. It found one real problem: two sentences in the report contradicted
its own calm-vs-shock table. That is fixed and committed. Small things noted but not fixed:

- A coding bug inside a method would show up as 100% fallback rather than a crash.
- `pytest` runs the slow Chronos test by default (~190 MB download on a fresh machine).
- A method returning a non-number would stop the run instead of falling back.
- The notebook repeats a small file-loading helper from the run script.

## How to rerun things

```bash
.venv/Scripts/python -m pytest -q                                   # 43 tests, ~40 s
.venv/Scripts/python scripts/run_backtest.py naive seasonal_naive    # development backtest
.venv/Scripts/python scripts/run_backtest.py season_reg --seasons    # + season table
PYTHONIOENCODING=utf-8 .venv/Scripts/python notebooks/02_forecast_comparison.py   # report + charts
```

The holdout (`--holdout`) refuses to run a second time unless you add `--force`, on purpose.
