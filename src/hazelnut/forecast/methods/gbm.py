"""LightGBM, one model per horizon (direct multi-horizon forecasting).

For horizon h the model learns log_price[s+h] - log_price[s] from the feature row at s, using
only labelled rows inside the history (the last one is origin - h). It is refit at every origin
with fixed parameters (no tuning against backtest results). The forecast is the last price
times exp(prediction on the origin's feature row).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from hazelnut.forecast.features import make_features, training_set

MIN_ROWS = 60
PARAMS = dict(
    objective="l1",
    n_estimators=300,
    learning_rate=0.03,
    num_leaves=15,
    min_child_samples=10,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    random_state=0,
    verbose=-1,
)


class Gbm:
    name = "lightgbm"

    def __init__(self):
        self.models: dict[int, LGBMRegressor] = {}  # the last fitted model per horizon

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        features = make_features(history, inputs)
        last_price = float(history.dropna().iloc[-1])
        origin_row = features.iloc[[-1]]
        out: dict[int, float | None] = {}
        for h in horizons:
            X, y = training_set(features, history, h)
            if len(X) < MIN_ROWS:
                out[h] = None
                continue
            model = LGBMRegressor(**PARAMS).fit(X, y)
            self.models[h] = model
            out[h] = float(last_price * np.exp(model.predict(origin_row)[0]))
        return out


def importances(model: LGBMRegressor, top: int = 8) -> pd.Series:
    """Feature importance by total gain, largest first."""
    gain = model.booster_.feature_importance(importance_type="gain")
    return pd.Series(gain, index=model.booster_.feature_name()).sort_values(ascending=False)[:top]
