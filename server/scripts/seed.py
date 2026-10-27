"""Create tables, load the synthetic dataset, export CSV samples and run analysis.

Usage (from server/):
    .venv\\Scripts\\python -m scripts.seed            # defaults: seed 42, 60 users, 14 days, 2200 logs
    .venv\\Scripts\\python -m scripts.seed --seed 7 --no-analyze
"""

import argparse
import json

from app.config import SERVER_DIR, get_settings
from app.database import SessionLocal, init_db
from app.services.dataset import export_csv, reset_and_load
from app.services.pipeline import AnalysisParams, run_analysis
from app.services.synthetic import generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=get_settings().random_seed)
    parser.add_argument("--users", type=int, default=60)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--records", type=int, default=2200)
    parser.add_argument("--no-analyze", action="store_true")
    args = parser.parse_args()

    init_db()
    dataset = generate_dataset(seed=args.seed, n_users=args.users, days=args.days, n_records=args.records)
    export_csv(dataset, SERVER_DIR / "data")
    with SessionLocal() as db:
        print("Loaded:", reset_and_load(db, dataset))
        if not args.no_analyze:
            run = run_analysis(db, AnalysisParams(seed=args.seed))
            print(f"Analysis run {run.id}: {run.logs_analyzed} logs, {run.alerts_created} alerts")
            print(json.dumps({k: run.metrics[k] for k in ("combined", "rules_only", "ml_only", "per_type")}, indent=2))


if __name__ == "__main__":
    main()
