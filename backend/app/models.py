"""API and workflow models for DataPilot."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """A natural-language analytics request."""

    question: str = Field(min_length=2, max_length=2000)


class TraceStep(BaseModel):
    """One inspectable workflow step."""

    name: str
    status: Literal["completed", "failed"]
    summary: str
    duration_ms: float = Field(ge=0)


class ChartPoint(BaseModel):
    """One chart datum."""

    label: str
    value: float


class ChartSpec(BaseModel):
    """A deliberately small chart contract rendered by the frontend."""

    title: str
    value_label: str
    points: list[ChartPoint]


class VerificationResult(BaseModel):
    """Post-execution checks that support the final answer."""

    passed: bool
    checks: list[str]


class AnalysisResponse(BaseModel):
    """A complete, traceable analytics run."""

    run_id: str
    question: str
    route: str
    answer: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    chart: ChartSpec | None
    verification: VerificationResult
    trace: list[TraceStep]
    metrics: dict[str, float | int]


class HealthResponse(BaseModel):
    """Service readiness response."""

    status: Literal["ok"]
    mode: Literal["deterministic-demo", "llm-assisted"]
