from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AccessLog, Alert, AnalysisRun, Device, EndpointEvent, RiskScore, User
from app.routers.risk import top_users
from app.schemas import AnalysisRunOut, Health, Overview, UserOut
from app.services.rules import RULES_BY_CODE

router = APIRouter(tags=["analytics"])

SEVERITIES = ["low", "medium", "high", "critical"]


@router.get("/health", response_model=Health, summary="Service and database health")
def health(db: Session = Depends(get_db)):
    settings = get_settings()
    backend = settings.database_url.split(":", 1)[0].split("+", 1)[0]
    try:
        db.execute(text("SELECT 1"))
        counts = {
            "users": db.scalar(select(func.count(User.id))) or 0,
            "logs": db.scalar(select(func.count(AccessLog.id))) or 0,
            "risk_scores": db.scalar(select(func.count(RiskScore.id))) or 0,
            "alerts": db.scalar(select(func.count(Alert.id))) or 0,
            "devices": db.scalar(select(func.count(Device.id))) or 0,
            "endpoint_events": db.scalar(select(func.count(EndpointEvent.id))) or 0,
        }
        return Health(status="ok", database="ok", database_backend=backend, version=settings.version, counts=counts)
    except SQLAlchemyError as exc:
        return Health(
            status="degraded", database="error", database_backend=backend, version=settings.version,
            detail=type(exc).__name__,
        )


@router.get("/users", response_model=list[UserOut], tags=["users"], summary="List users")
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.get("/analytics/overview", response_model=Overview, summary="Dashboard statistics")
def overview(db: Session = Depends(get_db)):
    total_logs = db.scalar(select(func.count(AccessLog.id))) or 0
    v1 = Alert.source == "access_log"
    alert_status = dict(db.execute(select(Alert.status, func.count()).where(v1).group_by(Alert.status)).all())
    sev = dict(db.execute(select(RiskScore.severity, func.count()).group_by(RiskScore.severity)).all())
    alert_sev = dict(
        db.execute(select(Alert.severity, func.count()).where(Alert.status != "resolved", v1).group_by(Alert.severity)).all()
    )

    # Rule hit frequency (JSON column aggregated in Python for DB portability).
    hits = Counter(
        h["code"] for rules in db.scalars(select(RiskScore.triggered_rules)) for h in (rules or [])
    )
    rule_hits = [
        {"code": c, "name": RULES_BY_CODE[c].name, "category": RULES_BY_CODE[c].category, "count": n}
        for c, n in hits.most_common() if c in RULES_BY_CODE
    ]

    # Daily / hourly aggregates computed in Python so SQLite and PostgreSQL behave identically.
    rows = db.execute(
        select(AccessLog.timestamp, AccessLog.status, RiskScore.risk_score, Alert.id)
        .outerjoin(RiskScore, RiskScore.log_id == AccessLog.id)
        .outerjoin(Alert, Alert.log_id == AccessLog.id)
    ).all()
    daily: dict[str, dict] = {}
    hourly = [{"hour": h, "events": 0, "high_risk": 0} for h in range(24)]
    for ts, status, risk, alert_id in rows:
        d = daily.setdefault(ts.date().isoformat(), {"date": ts.date().isoformat(), "events": 0, "failed": 0, "alerts": 0, "risk_sum": 0.0})
        d["events"] += 1
        d["failed"] += status != "success"
        d["alerts"] += alert_id is not None
        d["risk_sum"] += risk or 0.0
        hourly[ts.hour]["events"] += 1
        hourly[ts.hour]["high_risk"] += (risk or 0) >= 50
    daily_list = [
        {k: v for k, v in d.items() if k != "risk_sum"} | {"avg_risk": round(d["risk_sum"] / d["events"], 2)}
        for d in sorted(daily.values(), key=lambda x: x["date"])
    ]

    latest = db.scalar(select(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(1))
    period = db.execute(select(func.min(AccessLog.timestamp), func.max(AccessLog.timestamp))).one()
    return Overview(
        total_logs=total_logs,
        total_users=db.scalar(select(func.count(User.id))) or 0,
        failed_events=db.scalar(select(func.count(AccessLog.id)).where(AccessLog.status != "success")) or 0,
        open_alerts=alert_status.get("open", 0),
        acknowledged_alerts=alert_status.get("acknowledged", 0),
        resolved_alerts=alert_status.get("resolved", 0),
        avg_risk=round(float(db.scalar(select(func.avg(RiskScore.risk_score))) or 0), 2),
        severity_counts={s: sev.get(s, 0) for s in SEVERITIES},
        alert_severity_counts={s: alert_sev.get(s, 0) for s in SEVERITIES},
        rule_hits=rule_hits,
        daily=daily_list,
        hourly=hourly,
        top_users=top_users(db, 8),
        latest_run=AnalysisRunOut.model_validate(latest) if latest else None,
        period_start=period[0],
        period_end=period[1],
    )
