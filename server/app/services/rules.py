"""Explainable rule-based detection.

Each rule adds a fixed number of points and a human-readable reason. The rule
score for an event is the sum of points, capped at 100.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    category: str
    points: int
    condition: Callable[[pd.Series], bool]
    reason: Callable[[pd.Series], str]


RULES: list[Rule] = [
    Rule(
        "R1A", "Brute-force burst", "failed_logins", 70,
        lambda r: r["failed_logins_1h"] >= 5,
        lambda r: f"{int(r['failed_logins_1h'])} failed logins for this account within 60 minutes",
    ),
    Rule(
        "R1B", "Repeated failed logins", "failed_logins", 40,
        lambda r: 3 <= r["failed_logins_1h"] < 5,
        lambda r: f"{int(r['failed_logins_1h'])} failed logins for this account within 60 minutes",
    ),
    Rule(
        "R1C", "Success after failures", "failed_logins", 25,
        lambda r: r["action"] == "login" and r["status"] == "success" and r["failed_logins_1h"] >= 3,
        lambda r: "Successful login immediately after repeated failures (possible account takeover)",
    ),
    Rule(
        "R2A", "Highly unusual hour", "unusual_hours", 60,
        lambda r: r["hour_deviation"] >= 7,
        lambda r: f"Activity at {r['timestamp']:%H:%M}, {r['hour_deviation']:.1f} h from the user's usual time ({r['usual_hour']:.1f} h)",
    ),
    Rule(
        "R2B", "Unusual hour", "unusual_hours", 25,
        lambda r: 5 <= r["hour_deviation"] < 7,
        lambda r: f"Activity at {r['timestamp']:%H:%M}, {r['hour_deviation']:.1f} h from the user's usual time",
    ),
    Rule(
        "R3A", "Rare IP address", "new_ip", 30,
        lambda r: bool(r["is_rare_ip"]),
        lambda r: f"IP {r['ip_address']} used in only {int(r['ip_event_count'])} of this user's events",
    ),
    Rule(
        "R3B", "Unusual country", "new_ip", 35,
        lambda r: bool(r["is_foreign_country"]),
        lambda r: f"Request from {r['country']} while the user normally connects from {r['usual_country']}",
    ),
    Rule(
        "R3C", "Unfamiliar device", "new_ip", 15,
        lambda r: r["device_share"] < 0.05,
        lambda r: f"Device '{r['device']}' rarely or never used by this user",
    ),
    Rule(
        "R4A", "Restricted resource outside role", "sensitive_access", 75,
        lambda r: bool(r["unauthorised_access"]) and r["sensitivity_level"] == 3,
        lambda r: f"Role '{r['role']}' accessed restricted resource {r['resource']}",
    ),
    Rule(
        "R4B", "Confidential resource outside role", "sensitive_access", 45,
        lambda r: bool(r["unauthorised_access"]) and r["sensitivity_level"] == 2,
        lambda r: f"Role '{r['role']}' accessed confidential resource {r['resource']}",
    ),
    Rule(
        "R4C", "Denied sensitive request", "sensitive_access", 15,
        lambda r: r["status"] == "denied" and r["sensitivity_level"] >= 2,
        lambda r: f"Access to {r['resource']} was denied",
    ),
]

RULES_BY_CODE = {rule.code: rule for rule in RULES}


def evaluate_row(row: pd.Series) -> tuple[float, list[dict]]:
    hits = []
    for rule in RULES:
        if rule.condition(row):
            hits.append(
                {
                    "code": rule.code,
                    "name": rule.name,
                    "category": rule.category,
                    "points": rule.points,
                    "reason": rule.reason(row),
                }
            )
    return float(min(100, sum(h["points"] for h in hits))), hits


def apply_rules(df: pd.DataFrame) -> tuple[pd.Series, list[list[dict]]]:
    scores, hits = [], []
    for _, row in df.iterrows():
        s, h = evaluate_row(row)
        scores.append(s)
        hits.append(h)
    return pd.Series(scores, index=df.index, dtype=float), hits
