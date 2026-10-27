"""Unsupervised anomaly detection with scikit-learn's Isolation Forest."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.services.features import ML_FEATURES


def isolation_forest_scores(
    df: pd.DataFrame,
    contamination: float = 0.05,
    seed: int = 42,
    n_estimators: int = 200,
    features: list[str] | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Return (ml_score 0-100, is_anomaly flag) for every row.

    ``score_samples`` is higher for normal points, so it is negated to get an
    anomaly score, then rescaled so the median event maps to 0 and the most
    anomalous event maps to 100. Events at or below the median get 0.
    ``features`` defaults to the access-log feature set; the endpoint engine
    passes its own columns.
    """
    if len(df) < 10:
        # Too few points to fit a meaningful forest.
        zeros = pd.Series(0.0, index=df.index)
        return zeros, pd.Series(False, index=df.index)

    x = StandardScaler().fit_transform(df[features or ML_FEATURES].astype(float).to_numpy())
    model = IsolationForest(
        n_estimators=n_estimators, contamination=contamination, random_state=seed
    )
    model.fit(x)
    raw = -model.score_samples(x)
    median, top = float(np.median(raw)), float(raw.max())
    span = top - median if top > median else 1.0
    scaled = np.clip((raw - median) / span, 0.0, 1.0) * 100.0
    flags = model.predict(x) == -1
    return (
        pd.Series(np.round(scaled, 2), index=df.index),
        pd.Series(flags, index=df.index),
    )
