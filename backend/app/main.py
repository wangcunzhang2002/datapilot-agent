"""FastAPI entry point for DataPilot."""

import os
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .llm import OpenAICompatibleJsonClient
from .models import AnalysisRequest, AnalysisResponse, HealthResponse
from .repository import QueryRejected, SQLiteAnalyticsRepository
from .security import (
    PublicAccessGuard,
    SecurityLimits,
    rejection_response,
    request_client_ip,
    session_id_from_request,
    set_session_cookie,
    validate_public_text,
)
from .workflow import DataPilotAgent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_runtime_root = Path(os.getenv("AGENT_RUNTIME_DIR", PROJECT_ROOT / "runtime"))
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def _ensure_runtime_directory() -> Path:
    """Create the writable runtime directory used by the SQLite demo state."""

    runtime_dir = _runtime_root
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


RUNTIME_DIR = _ensure_runtime_directory()
repository = SQLiteAnalyticsRepository(
    db_path=RUNTIME_DIR / "datapilot.db",
    csv_path=PROJECT_ROOT / "data" / "orders.csv",
)
repository.initialize()
agent = DataPilotAgent(repository, llm=OpenAICompatibleJsonClient.from_env())
recent_runs: deque[AnalysisResponse] = deque(maxlen=20)
security_limits = SecurityLimits.from_env()
access_guard = PublicAccessGuard(security_limits)

app = FastAPI(
    title="DataPilot API",
    version="0.1.0",
    description="Traceable natural-language analytics over a constrained local dataset.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_public_responses(request: Request, call_next):
    """Add a private session cookie and keep unexpected failures demo-safe."""

    try:
        response = await call_next(request)
    except Exception:
        response = rejection_response(
            code="backend_unavailable",
            message="演示服务暂时不可用，页面将展示预录制示例。",
            status_code=503,
        )
    set_session_cookie(request, response)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _request: Request, _exc: RequestValidationError
):
    """Hide framework validation details behind the public error contract."""

    return rejection_response(
        code="input_rejected",
        message="输入格式或长度不符合演示限制，请修改后重试。",
        status_code=400,
    )


def _admit_analysis(request: Request):
    decision = access_guard.allow(
        ip=request_client_ip(request),
        session_id=session_id_from_request(request),
    )
    if decision.allowed:
        return None
    return rejection_response(
        code=decision.code or "rate_limited",
        message=decision.message or "请求暂时受限，请稍后再试。",
        retry_after=decision.retry_after,
    )


@app.get("/health", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report service readiness and the explicit execution mode."""

    mode = "llm-assisted" if agent.llm is not None else "deterministic-demo"
    return HealthResponse(status="ok", mode=mode)


@app.get("/api/schema")
def schema() -> dict[str, str]:
    """Expose the exact schema available to the Agent."""

    return {"schema": repository.schema_summary()}


@app.post("/api/analyze", response_model=None)
def analyze(payload: AnalysisRequest, http_request: Request):
    """Execute a complete analysis workflow."""

    try:
        question = validate_public_text(
            payload.question, max_chars=security_limits.max_input_chars
        )
    except ValueError as exc:
        return rejection_response(
            code="input_rejected", message=str(exc), status_code=400
        )
    denied = _admit_analysis(http_request)
    if denied is not None:
        return denied
    try:
        result = agent.analyze(question)
    except QueryRejected:
        return rejection_response(
            code="query_rejected", message="该问题无法映射到受控的只读查询。", status_code=400
        )
    except Exception:
        return rejection_response(
            code="backend_unavailable",
            message="本次分析暂时不可用，页面将展示预录制示例。",
            status_code=503,
        )
    recent_runs.appendleft(result)
    return result


@app.get("/api/runs", response_model=list[AnalysisResponse])
def runs() -> list[AnalysisResponse]:
    """Return recent in-process demo runs for UI inspection."""

    return list(recent_runs)


if (FRONTEND_DIST / "index.html").is_file():

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        """Serve the built React app and fall back to index.html for SPA paths."""

        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        dist_root = FRONTEND_DIST.resolve()
        requested = (FRONTEND_DIST / path).resolve()
        if requested.is_file() and dist_root in requested.parents:
            return FileResponse(requested)
        return FileResponse(dist_root / "index.html")
