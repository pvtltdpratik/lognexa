from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.services.features import build_features
from app.services.pipeline import AnalysisParams, evaluation_metrics, score_frame
from app.services.rules import evaluate_row
from app.services.scoring import AGREEMENT_BONUS, classify, combine_scores
from app.services.synthetic import generate_dataset


def _frame(events: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(events)
    df["id"] = range(1, len(df) + 1)
    return df


def _event(minute: int, **kw) -> dict:
    base = {
        "user_id": 1, "timestamp": datetime(2026, 10, 5, 10) + timedelta(minutes=minute),
        "ip_address": "10.0.0.5", "country": "IN", "device": "Windows 11 / Chrome",
        "action": "file_read", "resource": "/eng/wiki", "resource_sensitivity": "internal",
        "status": "success", "role": "developer",
    }
    return base | kw


# --- scoring -----------------------------------------------------------------
@pytest.mark.parametrize(
    "risk,severity",
    [(0, "low"), (24.99, "low"), (25, "medium"), (49.99, "medium"), (50, "high"), (74.99, "high"), (75, "critical"), (100, "critical")],
)
def test_severity_bands(risk, severity):
    assert classify(risk) == severity


def test_combine_scores_formula():
    assert combine_scores(50, 25, False, rule_weight=0.6) == pytest.approx(0.6 * 50 + 0.4 * 25)
    assert combine_scores(50, 25, True, rule_weight=0.6) == pytest.approx(0.6 * 50 + 0.4 * 25 + AGREEMENT_BONUS)
    # No bonus when only the model fires.
    assert combine_scores(0, 80, True) == pytest.approx(0.4 * 80)
    assert combine_scores(100, 100, True) == 100  # clipped


def test_combine_scores_rejects_bad_weight():
    with pytest.raises(ValueError):
        combine_scores(10, 10, False, rule_weight=1.5)


# --- features + rules ----------------------------------------------------------
def test_failed_login_window_and_bruteforce_rule():
    events = [_event(i, action="login", resource="/auth/sso", status="failure") for i in range(6)]
    feats = build_features(_frame(events))
    assert feats["failed_logins_1h"].tolist() == [1, 2, 3, 4, 5, 6]
    _, hits = evaluate_row(feats.iloc[-1])
    assert "R1A" in {h["code"] for h in hits}


def test_failures_outside_window_not_counted():
    events = [
        _event(0, action="login", resource="/auth/sso", status="failure"),
        _event(90, action="login", resource="/auth/sso", status="failure"),
    ]
    assert build_features(_frame(events))["failed_logins_1h"].tolist() == [1, 1]


def test_unauthorised_restricted_access_rule():
    events = [_event(i) for i in range(10)] + [
        _event(20, resource="/finance/payroll", resource_sensitivity="restricted")
    ]
    feats = build_features(_frame(events))
    score, hits = evaluate_row(feats.iloc[-1])
    assert {h["code"] for h in hits} >= {"R4A"}
    assert score >= 75


def test_authorised_role_does_not_trigger_sensitive_rule():
    events = [_event(i, role="financial_analyst", resource="/finance/payroll", resource_sensitivity="restricted") for i in range(5)]
    feats = build_features(_frame(events))
    _, hits = evaluate_row(feats.iloc[0])
    assert not any(h["category"] == "sensitive_access" for h in hits)


def test_normal_event_has_no_rule_hits():
    feats = build_features(_frame([_event(i * 30) for i in range(30)]))
    score, hits = evaluate_row(feats.iloc[5])
    assert score == 0 and hits == []


def test_missing_columns_raise():
    with pytest.raises(ValueError, match="missing columns"):
        build_features(pd.DataFrame([{"id": 1}]))


# --- end-to-end on the synthetic data -----------------------------------------
@pytest.fixture(scope="module")
def scored():
    ds = generate_dataset()
    roles = {u["id"]: u["role"] for u in ds.users}
    df = _frame(ds.logs)
    df["role"] = df["user_id"].map(roles)
    return score_frame(df, AnalysisParams())


def test_scores_within_bounds(scored):
    assert scored["risk_score"].between(0, 100).all()
    assert scored["ml_score"].between(0, 100).all()
    assert set(scored["severity"]) <= {"low", "medium", "high", "critical"}


def test_injected_anomalies_score_higher_than_normal(scored):
    anomalous = scored[scored["injected_anomaly"].notna()]["risk_score"].mean()
    normal = scored[scored["injected_anomaly"].isna()]["risk_score"].mean()
    assert anomalous > normal * 3


def test_detection_is_useful_but_not_perfect(scored):
    m = evaluation_metrics(scored, 40)["combined"]
    assert m["recall"] >= 0.8 and m["precision"] >= 0.6
    # The generator injects benign noise and subtle anomalies on purpose.
    assert m["fp"] > 0 or m["fn"] > 0


def test_every_event_has_an_explanation(scored):
    assert scored["explanation"].str.len().gt(20).all()
