"""End-to-end analysis: load logs -> features -> rules + ML -> risk -> alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AccessLog, Alert, AnalysisRun, RiskScore, User
from app.services.features import build_features, top_feature_deviations
from app.services.ml import isolation_forest_scores
from app.services.rules import apply_rules
from app.services.scoring import DEFAULT_RULE_WEIGHT, classify, combine_scores

CATEGORY_TITLES = {
    "failed_logins": "Repeated failed logins",
    "unusual_hours": "Activity at an unusual hour",
    "new_ip": "Access from a new IP / location",
    "sensitive_access": "Sensitive resource accessed outside role",
}


@dataclass
class AnalysisParams:
    contamination: float = 0.05
    alert_threshold: float = 40.0
    rule_weight: float = DEFAULT_RULE_WEIGHT
    seed: int = 42


def load_log_frame(db: Session) -> pd.DataFrame:
    rows = db.execute(
        select(
            AccessLog.id, AccessLog.user_id, AccessLog.timestamp, AccessLog.ip_address,
            AccessLog.country, AccessLog.city, AccessLog.device, AccessLog.action,
            AccessLog.resource, AccessLog.resource_sensitivity, AccessLog.status,
            AccessLog.injected_anomaly, User.role, User.username,
        ).join(User, User.id == AccessLog.user_id)
    ).all()
    return pd.DataFrame([r._asdict() for r in rows])


def score_frame(df: pd.DataFrame, params: AnalysisParams) -> pd.DataFrame:
    """Pure scoring step (no database) so it can be unit-tested directly."""
    feats = build_features(df)
    rule_scores, rule_hits = apply_rules(feats)
    ml_scores, ml_flags = isolation_forest_scores(feats, params.contamination, params.seed)
    feats["rule_score"] = rule_scores
    feats["triggered_rules"] = rule_hits
    feats["ml_score"] = ml_scores
    feats["ml_is_anomaly"] = ml_flags
    feats["risk_score"] = [
        combine_scores(r, m, a, params.rule_weight)
        for r, m, a in zip(rule_scores, ml_scores, ml_flags)
    ]
    feats["severity"] = feats["risk_score"].map(classify)
    feats["top_features"] = top_feature_deviations(feats)
    feats["explanation"] = [
        explain(rs, ms, fl, hits, tops)
        for rs, ms, fl, hits, tops in zip(
            rule_scores, ml_scores, ml_flags, rule_hits, feats["top_features"]
        )
    ]
    return feats


def explain(rule_score: float, ml_score: float, ml_flag: bool, hits: list[dict], tops: list[dict]) -> str:
    parts: list[str] = []
    if hits:
        parts.append("Rules triggered: " + "; ".join(f"{h['reason']} (+{h['points']})" for h in hits) + ".")
    else:
        parts.append("No detection rule was triggered.")
    if ml_flag:
        parts.append(f"Isolation Forest marked this event as an outlier (ML score {ml_score:.0f}/100).")
    elif ml_score >= 40:
        parts.append(f"Isolation Forest rated it moderately unusual (ML score {ml_score:.0f}/100).")
    else:
        parts.append(f"Isolation Forest considered it typical (ML score {ml_score:.0f}/100).")
    if tops:
        parts.append("Most unusual inputs: " + ", ".join(t["label"].lower() for t in tops) + ".")
    return " ".join(parts)


def evaluation_metrics(df: pd.DataFrame, alert_threshold: float) -> dict:
    """Compare detections with the generator's injected labels.

    Only meaningful for the synthetic dataset; real logs have no ground truth.
    """
    truth = df["injected_anomaly"].notna()
    if truth.sum() == 0:
        return {"note": "No ground-truth labels available for evaluation."}

    def prf(pred: pd.Series) -> dict:
        tp = int((pred & truth).sum())
        fp = int((pred & ~truth).sum())
        fn = int((~pred & truth).sum())
        tn = int((~pred & ~truth).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
        }

    combined = df["risk_score"] >= alert_threshold
    per_type = {}
    for label, group in df[truth].groupby("injected_anomaly"):
        per_type[label] = {
            "injected": int(len(group)),
            "detected": int((group["risk_score"] >= alert_threshold).sum()),
            "recall": round(float((group["risk_score"] >= alert_threshold).mean()), 3),
        }
    return {
        "labelled_anomalies": int(truth.sum()),
        "total_events": int(len(df)),
        "combined": prf(combined),
        "rules_only": prf(df["rule_score"] >= alert_threshold),
        "ml_only": prf(df["ml_is_anomaly"].astype(bool)),
        "per_type": per_type,
        "caveat": "Measured against labels injected by the synthetic generator; not an estimate of real-world accuracy.",
    }


def _alert_title(hits: list[dict], ml_flag: bool) -> str:
    if hits:
        top = max(hits, key=lambda h: h["points"])
        return CATEGORY_TITLES.get(top["category"], top["name"])
    return "Behavioural outlier (Isolation Forest)" if ml_flag else "Elevated risk event"


def run_analysis(db: Session, params: AnalysisParams) -> AnalysisRun:
    run = AnalysisRun(status="running", parameters=params.__dict__.copy(), started_at=datetime.utcnow())
    db.add(run)
    db.commit()

    try:
        df = load_log_frame(db)
        if df.empty:
            raise ValueError("No access logs found. Generate the synthetic dataset first.")
        scored = score_frame(df, params)

        db.execute(delete(RiskScore))
        # Open alerts are regenerated; acknowledged / resolved alerts are kept as history.
        db.execute(delete(Alert).where(Alert.status == "open", Alert.source == "access_log"))
        kept = set(db.scalars(select(Alert.log_id).where(Alert.log_id.is_not(None))).all())

        risk_rows, alert_rows = [], []
        for row in scored.itertuples(index=False):
            risk_rows.append(
                {
                    "log_id": int(row.id), "run_id": run.id,
                    "rule_score": float(row.rule_score), "ml_score": float(row.ml_score),
                    "ml_is_anomaly": bool(row.ml_is_anomaly), "risk_score": float(row.risk_score),
                    "severity": row.severity, "triggered_rules": row.triggered_rules,
                    "features": {
                        k: (float(getattr(row, k)) if not isinstance(getattr(row, k), str) else getattr(row, k))
                        for k in (
                            "hour", "usual_hour", "hour_deviation", "is_weekend", "failed_logins_1h",
                            "events_1h", "ip_event_count", "ip_user_share", "is_rare_ip",
                            "is_foreign_country", "usual_country", "device_share",
                            "sensitivity_level", "unauthorised_access", "is_failure",
                        )
                    } | {"rule_weight": params.rule_weight},
                    "top_features": row.top_features, "explanation": row.explanation,
                }
            )
            if row.risk_score >= params.alert_threshold and int(row.id) not in kept:
                alert_rows.append(
                    {
                        "log_id": int(row.id), "user_id": int(row.user_id), "run_id": run.id,
                        "severity": row.severity, "risk_score": float(row.risk_score),
                        "title": _alert_title(row.triggered_rules, bool(row.ml_is_anomaly)),
                        "description": f"{row.username}: {row.explanation}", "status": "open",
                    }
                )
        db.bulk_insert_mappings(RiskScore, risk_rows)
        if alert_rows:
            db.bulk_insert_mappings(Alert, alert_rows)

        run.status = "completed"
        run.logs_analyzed = len(scored)
        run.alerts_created = len(alert_rows)
        run.metrics = evaluation_metrics(scored, params.alert_threshold)
        run.completed_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(AnalysisRun, run.id)
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise
    return run
