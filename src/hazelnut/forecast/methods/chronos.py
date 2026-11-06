"""Chronos-Bolt (small): a pretrained time-series model used zero-shot, with no training.

It reads the raw USD price history (missing months dropped; the model scales the series
itself) and returns forecast quantiles. The forecast for horizon h is the median at step h.
Runs on CPU. The weights (~190 MB) download on first use and are cached by Hugging Face.
"""

from __future__ import annotations

from collections.abc import Sequence

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
