"""Persist a generated synthetic dataset into the database (and CSV samples)."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import AccessLog, Alert, AnalysisRun, RiskScore, User
from app.services.synthetic import Dataset, generate_dataset


def reset_and_load(db: Session, dataset: Dataset) -> dict:
    """Replace all data with ``dataset``. Destructive by design (demo data only)."""
    for model in (Alert, RiskScore, AnalysisRun, AccessLog, User):
        db.execute(delete(model))
    db.bulk_insert_mappings(User, dataset.users)
    db.bulk_insert_mappings(AccessLog, dataset.logs)
    db.commit()
    return {
        "users": len(dataset.users),
        "logs": len(dataset.logs),
        "injected_anomalies": sum(1 for e in dataset.logs if e["injected_anomaly"]),
    }


def generate_and_load(db: Session, seed: int, n_users: int, days: int, n_records: int) -> dict:
    return reset_and_load(db, generate_dataset(seed=seed, n_users=n_users, days=days, n_records=n_records))


def export_csv(dataset: Dataset, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("sample_users.csv", dataset.users), ("sample_access_logs.csv", dataset.logs)):
        with open(out_dir / name, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
