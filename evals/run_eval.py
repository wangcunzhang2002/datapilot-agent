"""Run the tracked DataPilot evaluation set and write reproducible metrics."""

import json
from pathlib import Path

from app.repository import SQLiteAnalyticsRepository
from app.workflow import DataPilotAgent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Evaluate routing, execution, and verification without a model API."""

    cases = json.loads((PROJECT_ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    repository = SQLiteAnalyticsRepository(
        db_path=PROJECT_ROOT / "runtime" / "eval.db",
        csv_path=PROJECT_ROOT / "data" / "orders.csv",
    )
    repository.initialize()
    agent = DataPilotAgent(repository)

    records = []
    for case in cases:
        try:
            result = agent.analyze(case["question"])
            records.append(
                {
                    "id": case["id"],
                    "route_correct": result.route == case["expected_route"],
                    "execution_success": True,
                    "verification_passed": result.verification.passed,
                }
            )
        except Exception as exc:  # evaluation must record failures instead of hiding them
            records.append(
                {
                    "id": case["id"],
                    "route_correct": False,
                    "execution_success": False,
                    "verification_passed": False,
                    "error": str(exc),
                }
            )

    count = len(records)
    report = {
        "case_count": count,
        "route_accuracy": sum(item["route_correct"] for item in records) / count,
        "execution_success_rate": sum(item["execution_success"] for item in records) / count,
        "verification_pass_rate": sum(item["verification_passed"] for item in records) / count,
        "records": records,
    }
    report_path = PROJECT_ROOT / "evals" / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
