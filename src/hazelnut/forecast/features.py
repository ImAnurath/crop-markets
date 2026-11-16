"""Feature rows for the gradient-boosting method.

Every feature at row t is computed from rows <= t of the history and the inputs frame, and the
inputs frame already respects the information timing rules (see dataset.py), so a feature row
never contains anything that was unknown at the end of month t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "log_price",
    "ret_1",
    "ret_3",
    "ret_6",
    "ret_12",
    "month",
    "months_since_estimate",
    "crop_change",
    "frost_days",
    "exports_yoy",
    "fx_ret_1",
    "fx_ret_12",
    "log_volume",
]


def make_features(
    history: pd.Series, inputs: pd.DataFrame, crop_col: str = "crop_change"
) -> pd.DataFrame:
    """One row per month of ``history``. NaN where a lag reaches before the data.

    The ``crop_change`` feature is taken from the inputs column ``crop_col`` (the Giresun
    estimate by default, or ``nat_crop_change`` for the national estimate).
    """
    idx = history.index
    inp = inputs.reindex(idx)
    log_price = np.log(history.astype(float))
    log_fx = np.log(inp["usd_try"])
    # A month with zero recorded exports has no defined year-on-year log change.
    exports = inp["exports_kg"].where(inp["exports_kg"] > 0)
    month = pd.Series(idx.month, index=idx)
    f = pd.DataFrame(
        {
            "log_price": log_price,
            "ret_1": log_price - log_price.shift(1),
            "ret_3": log_price - log_price.shift(3),
            "ret_6": log_price - log_price.shift(6),
            "ret_12": log_price - log_price.shift(12),
            "month": month,
            "months_since_estimate": (month - 8) % 12,
            "crop_change": inp[crop_col],
            "frost_days": inp["frost_days"],
            "exports_yoy": np.log(exports / exports.shift(12)),
            "fx_ret_1": log_fx - log_fx.shift(1),
            "fx_ret_12": log_fx - log_fx.shift(12),
            "log_volume": np.log1p(inp["volume_kg"]),
        },
        index=idx,
    )
    return f[FEATURES]


def training_set(
    features: pd.DataFrame, history: pd.Series, h: int
) -> tuple[pd.DataFrame, pd.Series]:
    """Rows s with a known label log_price[s+h] - log_price[s]; the last one is origin - h."""
    log_price = np.log(history.astype(float))
    label = log_price.shift(-h) - log_price
    keep = label.notna()
    return features[keep], label[keep]
