from math import ceil
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import APIError
from app.models import AccessLog, Alert, RiskScore, User
from app.schemas import Page, RiskScoreListItem, RiskScoreOut, Severity, UserRisk
from app.services.rules import RULES
from app.services.scoring import AGREEMENT_BONUS, DEFAULT_RULE_WEIGHT, SEVERITY_BANDS

router = APIRouter(prefix="/risk-scores", tags=["risk scores"])


@router.get("", response_model=Page[RiskScoreListItem], summary="List risk scores")
def list_risk_scores(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
    severity: Severity | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    max_score: float | None = Query(None, ge=0, le=100),
    user_id: int | None = Query(None, ge=1),
    rule_code: str | None = Query(None, pattern=r"^R[0-9][A-Z]$"),
    sort: Literal["risk_desc", "risk_asc", "newest"] = "risk_desc",
    db: Session = Depends(get_db),
):
    if min_score is not None and max_score is not None and min_score > max_score:
        raise APIError(422, "validation_error", "min_score must not exceed max_score",
                       [{"field": "min_score", "message": "min_score must not exceed max_score"}])
    q = (
        select(RiskScore, AccessLog, User.username)
        .join(AccessLog, AccessLog.id == RiskScore.log_id)
        .join(User, User.id == AccessLog.user_id)
    )
    if severity:
        q = q.where(RiskScore.severity == severity)
    if min_score is not None:
        q = q.where(RiskScore.risk_score >= min_score)
    if max_score is not None:
        q = q.where(RiskScore.risk_score <= max_score)
    if user_id:
        q = q.where(AccessLog.user_id == user_id)

    order = {
        "risk_desc": [RiskScore.risk_score.desc()],
        "risk_asc": [RiskScore.risk_score.asc()],
        "newest": [AccessLog.timestamp.desc()],
    }[sort]
    rows = db.execute(q.order_by(*order, RiskScore.id)).all()
    if rule_code:  # JSON filtering portable across SQLite/PostgreSQL is done in Python
        rows = [r for r in rows if any(h["code"] == rule_code for h in r[0].triggered_rules)]
    total = len(rows)
    sliced = rows[(page - 1) * page_size: page * page_size]
    items = [
        RiskScoreListItem(
            id=rs.id, log_id=rs.log_id, user_id=log.user_id, username=username, timestamp=log.timestamp,
            action=log.action, resource=log.resource, rule_score=rs.rule_score, ml_score=rs.ml_score,
            risk_score=rs.risk_score, severity=rs.severity,
            rule_codes=[h["code"] for h in rs.triggered_rules],
        )
        for rs, log, username in sliced
    ]
    return Page[RiskScoreListItem](
        items=items, total=total, page=page, page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/users", response_model=list[UserRisk], summary="Per-user risk aggregates")
def user_risk(limit: int = Query(10, ge=1, le=500), db: Session = Depends(get_db)):
    return top_users(db, limit)


def top_users(db: Session, limit: int) -> list[UserRisk]:
    open_alerts = (
        select(Alert.user_id, func.count(Alert.id).label("n"))
        .where(Alert.status == "open").group_by(Alert.user_id).subquery()
    )
    rows = db.execute(
        select(
            User.id, User.username, User.full_name, User.department,
            func.count(RiskScore.id), func.avg(RiskScore.risk_score), func.max(RiskScore.risk_score),
            func.sum(case((RiskScore.risk_score >= 50, 1), else_=0)),
            func.coalesce(func.max(open_alerts.c.n), 0),
        )
        .join(AccessLog, AccessLog.user_id == User.id)
        .join(RiskScore, RiskScore.log_id == AccessLog.id)
        .outerjoin(open_alerts, open_alerts.c.user_id == User.id)
        .group_by(User.id, User.username, User.full_name, User.department)
        .order_by(func.max(RiskScore.risk_score).desc(), func.avg(RiskScore.risk_score).desc())
        .limit(limit)
    ).all()
    return [
        UserRisk(
            user_id=r[0], username=r[1], full_name=r[2], department=r[3], events=r[4],
            avg_risk=round(float(r[5] or 0), 2), max_risk=float(r[6] or 0),
            high_risk_events=int(r[7] or 0), open_alerts=int(r[8] or 0),
        )
        for r in rows
    ]


@router.get("/methodology", summary="Rules, weights and severity bands used for scoring")
def methodology():
    return {
        "formula": "risk = w * rule_score + (1 - w) * ml_score + bonus (if a rule fired and the Isolation Forest flagged the event), clipped to 0-100",
        "default_rule_weight": DEFAULT_RULE_WEIGHT,
        "agreement_bonus": AGREEMENT_BONUS,
        "severity_bands": [{"min": t, "severity": s} for t, s in SEVERITY_BANDS],
        "rules": [
            {"code": r.code, "name": r.name, "category": r.category, "points": r.points} for r in RULES
        ],
    }


@router.get("/log/{log_id}", response_model=RiskScoreOut, summary="Risk score for one log")
def risk_for_log(log_id: int = Path(ge=1), db: Session = Depends(get_db)):
    rs = db.scalar(select(RiskScore).where(RiskScore.log_id == log_id))
    if not rs:
        raise APIError(404, "not_found", f"No risk score for log {log_id}. Run /analyze first.")
    return rs
