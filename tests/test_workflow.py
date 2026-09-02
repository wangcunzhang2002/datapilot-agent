"""Workflow and tool-contract tests."""

from pathlib import Path
from typing import Any

import pytest
from app.repository import QueryRejected, SQLiteAnalyticsRepository
from app.workflow import DataPilotAgent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubRouter:
    """A model stub that exercises the constrained LLM routing path."""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        assert "不要生成 SQL" in system
        assert "Schema:" in user
        return {"route": "monthly_trend"}


class InvalidRouter:
    """A model stub that violates the route allow-list."""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        return {"route": "drop_everything"}


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteAnalyticsRepository:
    repo = SQLiteAnalyticsRepository(
        db_path=tmp_path / "test.db",
        csv_path=PROJECT_ROOT / "data" / "orders.csv",
    )
    repo.initialize()
    return repo


def test_region_analysis_is_verified(repository: SQLiteAnalyticsRepository) -> None:
    result = DataPilotAgent(repository).analyze("哪个地区的销售额最高？")

    assert result.route == "revenue_by_region"
    assert result.rows[0]["region"] == "华东"
    assert result.verification.passed is True
    assert len(result.trace) == 5


def test_model_can_select_only_a_supported_route(
    repository: SQLiteAnalyticsRepository,
) -> None:
    result = DataPilotAgent(repository, llm=StubRouter()).analyze("请分析销售变化")

    assert result.route == "monthly_trend"
    assert result.metrics["model_call_count"] == 1
    assert result.metrics["llm_fallback_count"] == 0


def test_invalid_model_route_falls_back_to_safe_baseline(
    repository: SQLiteAnalyticsRepository,
) -> None:
    result = DataPilotAgent(repository, llm=InvalidRouter()).analyze("按品类汇总收入")

    assert result.route == "revenue_by_category"
    assert result.metrics["llm_fallback_count"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT * FROM users",
        "SELECT * FROM orders; DROP TABLE orders",
        "PRAGMA table_info(orders)",
    ],
)
def test_repository_rejects_unsafe_sql(
    repository: SQLiteAnalyticsRepository, sql: str
) -> None:
    with pytest.raises(QueryRejected):
        repository.execute(sql)
