"""Behavioural feature engineering for access-log events.

Input: a DataFrame with one row per access event plus the user's ``role``.
Output: the same frame with one numeric column per feature. Baselines (usual
hour, usual IPs, usual country, usual device) are computed per user over the
analysed window, so every feature is relative to that user's own behaviour.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.policy import SENSITIVITY_LEVELS, is_authorised

# Columns fed to the Isolation Forest (order matters for reproducibility).
ML_FEATURES = [
    "hour_deviation",
    "is_weekend",
    "failed_logins_1h",
    "events_1h",
    "ip_user_share",
    "is_foreign_country",
    "device_share",
    "sensitivity_level",
    "unauthorised_access",
    "is_failure",
]

FEATURE_LABELS = {
    "hour_deviation": "Hours away from the user's usual activity time",
    "is_weekend": "Weekend activity",
    "failed_logins_1h": "Failed logins by this user in the previous 60 minutes",
    "events_1h": "Events by this user in the previous 60 minutes",
    "ip_user_share": "Share of the user's events coming from this IP",
    "is_foreign_country": "Country differs from the user's usual country",
    "device_share": "Share of the user's events from this device",
    "sensitivity_level": "Resource sensitivity (0 public - 3 restricted)",
    "unauthorised_access": "Sensitive resource outside the user's role",
    "is_failure": "Request failed or was denied",
}

REQUIRED_COLUMNS = {
    "id", "user_id", "timestamp", "ip_address", "country", "device",
    "action", "resource", "resource_sensitivity", "status", "role",
}


def _circular_mean_hour(hours: pd.Series) -> float:
    angles = hours.to_numpy() / 24.0 * 2 * np.pi
    mean = np.arctan2(np.sin(angles).mean(), np.cos(angles).mean())
    return float((mean / (2 * np.pi) * 24.0) % 24.0)


def _circular_distance(a: pd.Series, b: pd.Series) -> pd.Series:
    diff = (a - b).abs() % 24
    return np.minimum(diff, 24 - diff)


def _rolling_count(df: pd.DataFrame, flag: pd.Series, window: str = "60min") -> pd.Series:
    """Per-user count of ``flag`` events in the trailing window (inclusive)."""
    tmp = pd.DataFrame({"user_id": df["user_id"], "timestamp": df["timestamp"], "flag": flag.astype(float)})
    tmp = tmp.sort_values(["user_id", "timestamp"])
    rolled = (
        tmp.set_index("timestamp")
        .groupby("user_id")["flag"]
        .rolling(window)
        .sum()
        .to_numpy()
    )
    return pd.Series(rolled, index=tmp.index).reindex(df.index).fillna(0).astype(int)


def build_features(logs: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(logs.columns)
    if missing:
        raise ValueError(f"missing columns for feature extraction: {sorted(missing)}")
    if logs.empty:
        return logs.assign(**{c: pd.Series(dtype=float) for c in ML_FEATURES})

    df = logs.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "id"]).reset_index(drop=True)

    # --- time-of-day behaviour -------------------------------------------------
    df["hour"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    usual_hour = df.groupby("user_id")["hour"].apply(_circular_mean_hour)
    df["usual_hour"] = df["user_id"].map(usual_hour)
    df["hour_deviation"] = _circular_distance(df["hour"], df["usual_hour"]).round(2)
    df["is_weekend"] = (df["timestamp"].dt.weekday >= 5).astype(int)

    # --- authentication behaviour ---------------------------------------------
    failed_login = (df["action"] == "login") & (df["status"] == "failure")
    df["failed_logins_1h"] = _rolling_count(df, failed_login)
    df["events_1h"] = _rolling_count(df, pd.Series(True, index=df.index))
    df["is_failure"] = df["status"].isin(["failure", "denied"]).astype(int)

    # --- network / device behaviour -------------------------------------------
    user_total = df.groupby("user_id")["id"].transform("count")
    ip_count = df.groupby(["user_id", "ip_address"])["id"].transform("count")
    df["ip_event_count"] = ip_count
    df["ip_user_share"] = (ip_count / user_total).round(4)
    df["is_rare_ip"] = ((ip_count <= 3) | (df["ip_user_share"] < 0.05)).astype(int)

    usual_country = df.groupby("user_id")["country"].agg(lambda s: s.mode().iloc[0])
    df["usual_country"] = df["user_id"].map(usual_country)
    df["is_foreign_country"] = (df["country"] != df["usual_country"]).astype(int)

    device_count = df.groupby(["user_id", "device"])["id"].transform("count")
    df["device_share"] = (device_count / user_total).round(4)

    # --- resource behaviour ----------------------------------------------------
    df["sensitivity_level"] = df["resource_sensitivity"].map(SENSITIVITY_LEVELS).fillna(1).astype(int)
    authorised = [is_authorised(r, res) for r, res in zip(df["role"], df["resource"])]
    df["unauthorised_access"] = ((~pd.Series(authorised, index=df.index)) & (df["sensitivity_level"] >= 2)).astype(int)

    return df


def top_feature_deviations(df: pd.DataFrame, k: int = 3, min_z: float = 2.0) -> list[list[dict]]:
    """Explainability heuristic: the ``k`` features furthest from the population
    mean (in standard deviations) for each event. This is not a model
    attribution method (e.g. SHAP); it highlights which inputs look unusual."""
    if df.empty:
        return []
    x = df[ML_FEATURES].astype(float)
    z = (x - x.mean()) / x.std(ddof=0).replace(0, 1.0)
    # ip/device share: *low* values are unusual, so flip the sign.
    z["ip_user_share"] *= -1
    z["device_share"] *= -1
    out: list[list[dict]] = []
    for idx in range(len(df)):
        row = z.iloc[idx]
        best = row[row >= min_z].sort_values(ascending=False).head(k)
        out.append(
            [
                {
                    "feature": f,
                    "label": FEATURE_LABELS[f],
                    "value": float(x.iloc[idx][f]),
                    "z_score": round(float(v), 2),
                }
                for f, v in best.items()
            ]
        )
    return out
