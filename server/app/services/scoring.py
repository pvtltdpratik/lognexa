"""Risk-score formula and severity classification.

    risk = rule_weight * rule_score + (1 - rule_weight) * ml_score
           + AGREEMENT_BONUS   (only when a rule fired AND the forest flagged it)
    risk is clipped to [0, 100]

Severity bands:  Critical >= 75 | High >= 50 | Medium >= 25 | Low < 25
"""

from __future__ import annotations

SEVERITY_BANDS = [(75.0, "critical"), (50.0, "high"), (25.0, "medium"), (0.0, "low")]
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
AGREEMENT_BONUS = 10.0
DEFAULT_RULE_WEIGHT = 0.6


def combine_scores(
    rule_score: float,
    ml_score: float,
    ml_is_anomaly: bool,
    rule_weight: float = DEFAULT_RULE_WEIGHT,
) -> float:
    if not 0.0 <= rule_weight <= 1.0:
        raise ValueError("rule_weight must be between 0 and 1")
    risk = rule_weight * rule_score + (1.0 - rule_weight) * ml_score
    if rule_score > 0 and ml_is_anomaly:
        risk += AGREEMENT_BONUS
    return round(max(0.0, min(100.0, risk)), 2)


def classify(risk: float) -> str:
    for threshold, label in SEVERITY_BANDS:
        if risk >= threshold:
            return label
    return "low"
