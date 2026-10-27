from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import APIError
from app.models import AccessLog, AnalysisRun
from app.schemas import AnalysisRunOut, AnalyzeRequest, DatasetRequest, DatasetResult
from app.services.dataset import generate_and_load
from app.services.pipeline import AnalysisParams, run_analysis

router = APIRouter(tags=["analysis"])


def _run(db: Session, req: AnalyzeRequest) -> AnalysisRun:
    if not db.scalar(select(func.count(AccessLog.id))):
        raise APIError(409, "no_data", "No access logs found. Generate the synthetic dataset first.")
    params = AnalysisParams(
        contamination=req.contamination, alert_threshold=req.alert_threshold,
        rule_weight=req.rule_weight, seed=get_settings().random_seed,
    )
    try:
        return run_analysis(db, params)
    except ValueError as exc:
        raise APIError(422, "analysis_failed", str(exc)) from exc


@router.post("/analyze", response_model=AnalysisRunOut, summary="Run rule + Isolation Forest analysis")
def analyze(req: AnalyzeRequest = Body(default_factory=AnalyzeRequest), db: Session = Depends(get_db)):
    return _run(db, req)


@router.get("/analyze/runs", response_model=list[AnalysisRunOut], summary="Recent analysis runs")
def list_runs(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    return db.scalars(select(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(limit)).all()


@router.get("/analyze/latest", response_model=AnalysisRunOut, summary="Most recent analysis run")
def latest_run(db: Session = Depends(get_db)):
    run = db.scalar(select(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(1))
    if not run:
        raise APIError(404, "not_found", "No analysis has been run yet")
    return run


@router.post("/dataset/generate", response_model=DatasetResult, summary="Regenerate the synthetic dataset")
def generate(req: DatasetRequest = Body(default_factory=DatasetRequest), db: Session = Depends(get_db)):
    try:
        summary = generate_and_load(db, req.seed, req.n_users, req.days, req.n_records)
    except ValueError as exc:
        raise APIError(422, "invalid_dataset_parameters", str(exc)) from exc
    analysis = _run(db, AnalyzeRequest()) if req.run_analysis else None
    return DatasetResult(**summary, analysis=AnalysisRunOut.model_validate(analysis) if analysis else None)
