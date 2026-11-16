"""Chronos-Bolt (small): a pretrained time-series model used zero-shot, with no training.

It reads the raw USD price history (missing months dropped; the model scales the series
itself) and returns forecast quantiles. The forecast for horizon h is the median at step h.
Runs on CPU. The weights (~190 MB) download on first use and are cached by Hugging Face.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

MODEL_ID = "amazon/chronos-bolt-small"


class ChronosBolt:
    name = "chronos"

    def __init__(self, model_id: str = MODEL_ID):
        self.model_id = model_id
        self._pipeline = None

    @property
    def pipeline(self):
        if self._pipeline is None:
            from chronos import BaseChronosPipeline  # heavy import, only when used

            self._pipeline = BaseChronosPipeline.from_pretrained(self.model_id, device_map="cpu")
        return self._pipeline

    def forecast(self, history: pd.Series, inputs: pd.DataFrame, horizons: Sequence[int]):
        import torch

        context = torch.tensor(history.dropna().to_numpy(dtype="float32"))
        quantiles, _ = self.pipeline.predict_quantiles(
            context, prediction_length=max(horizons), quantile_levels=[0.5]
        )
        median = quantiles[0, :, 0].numpy()
        return {h: float(median[h - 1]) for h in horizons}

    def quantiles(self, history, inputs, horizons: Sequence[int], levels: Sequence[float]):
        """Native quantiles. Chronos-Bolt is trained on levels 0.1 to 0.9 only (beyond that it
        just repeats the 0.1 / 0.9 values), so outer levels are extrapolated, see ``extend_tails``."""
        import torch

        context = torch.tensor(history.dropna().to_numpy(dtype="float32"))
        q, _ = self.pipeline.predict_quantiles(
            context, prediction_length=max(horizons), quantile_levels=list(NATIVE)
        )
        q = q[0].numpy()  # (steps, len(NATIVE))
        return {h: extend_tails(dict(zip(NATIVE, q[h - 1])), levels) for h in horizons}


NATIVE = (0.1, 0.5, 0.9)


def extend_tails(native: dict[float, float], levels: Sequence[float]) -> list[float]:
    """Quantiles at ``levels`` from the 0.1 / 0.5 / 0.9 ones. Levels below 0.1 (above 0.9) are
    extrapolated as if log price were normal: log q = log q50 + (log q10 - log q50) * z(level) /
    z(0.1). Native levels are returned as they are."""
    from scipy.stats import norm

    log_mid = np.log(native[0.5])
    out = []
    for lv in levels:
        if lv in native:
            out.append(float(native[lv]))
            continue
        edge = 0.1 if lv < 0.5 else 0.9
        ratio = norm.ppf(lv) / norm.ppf(edge)
        out.append(float(np.exp(log_mid + (np.log(native[edge]) - log_mid) * ratio)))
    return out
