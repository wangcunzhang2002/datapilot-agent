"""Public access controls for the portfolio demo.

The guard is intentionally process-local. It protects a single Railway
instance from accidental or casual abuse, but it is not a replacement for
provider-side budgets or a shared rate-limit store when running replicas.
"""

from __future__ import annotations

import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

SESSION_COOKIE = "agent_session"
_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_INJECTION_PATTERN = re.compile(
    r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+"
    r"(?:instructions?|messages?)|"
    r"(?:system|developer)\s+prompt|"
    r"(?:reveal|show|print|泄露|显示|输出).{0,24}"
    r"(?:api\s*[_ -]?key|token|密钥|系统提示|凭证)|"
    r"(?:绕过|越过|忽略).{0,24}(?:规则|安全|限制)",
    re.IGNORECASE,
)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None else default
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class SecurityLimits:
    """Bounded defaults; environment values are clamped to safe ranges."""

    ip_window_seconds: float = 60.0
    ip_max_requests: int = 20
    global_window_seconds: float = 1.0
    global_max_requests: int = 5
    session_max_rounds: int = 12
    daily_call_limit: int = 100
    max_input_chars: int = 500
    llm_max_tokens: int = 400

    @classmethod
    def from_env(cls) -> SecurityLimits:
        return cls(
            ip_window_seconds=_env_float(
                "AGENT_IP_WINDOW_SECONDS", 60.0, minimum=10.0, maximum=3600.0
            ),
            ip_max_requests=_env_int(
                "AGENT_IP_MAX_REQUESTS", 20, minimum=1, maximum=100
            ),
            global_window_seconds=_env_float(
                "AGENT_GLOBAL_WINDOW_SECONDS", 1.0, minimum=0.25, maximum=10.0
            ),
            global_max_requests=_env_int(
                "AGENT_GLOBAL_QPS", 5, minimum=1, maximum=50
            ),
            session_max_rounds=_env_int(
                "AGENT_SESSION_MAX_ROUNDS", 12, minimum=1, maximum=100
            ),
            daily_call_limit=_env_int(
                "AGENT_DAILY_CALL_LIMIT", 100, minimum=1, maximum=10000
            ),
            max_input_chars=_env_int(
                "AGENT_MAX_INPUT_CHARS", 500, minimum=32, maximum=2000
            ),
            llm_max_tokens=_env_int(
                "AGENT_LLM_MAX_TOKENS", 400, minimum=64, maximum=800
            ),
        )


@dataclass(frozen=True)
class GuardDecision:
    """Result of one admission check."""

    allowed: bool
    code: str | None = None
    message: str | None = None
    retry_after: int | None = None


class PublicAccessGuard:
    """Thread-safe in-process IP, QPS, session and daily admission guard."""

    def __init__(self, limits: SecurityLimits | None = None) -> None:
        self.limits = limits or SecurityLimits.from_env()
        self._lock = threading.Lock()
        self._global_events: deque[float] = deque()
        self._ip_events: dict[str, deque[float]] = defaultdict(deque)
        self._session_rounds: dict[str, int] = defaultdict(int)
        self._daily_calls = 0
        self._day = self._today()

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    def reset(self) -> None:
        """Reset counters; intended for deterministic local tests."""

        with self._lock:
            self._global_events.clear()
            self._ip_events.clear()
            self._session_rounds.clear()
            self._daily_calls = 0
            self._day = self._today()

    def _roll_day_if_needed(self) -> None:
        day = self._today()
        if day != self._day:
            self._day = day
            self._daily_calls = 0
            self._session_rounds.clear()

    @staticmethod
    def _prune(events: deque[float], now: float, window: float) -> None:
        cutoff = now - window
        while events and events[0] <= cutoff:
            events.popleft()

    def allow(self, *, ip: str, session_id: str) -> GuardDecision:
        """Admit one analysis call or return a friendly non-5xx decision."""

        now = time.monotonic()
        with self._lock:
            self._roll_day_if_needed()
            self._prune(self._global_events, now, self.limits.global_window_seconds)
            ip_events = self._ip_events[ip]
            self._prune(ip_events, now, self.limits.ip_window_seconds)

            if len(self._global_events) >= self.limits.global_max_requests:
                return GuardDecision(
                    False,
                    "global_qps_limit",
                    "当前访问较多，请稍等几秒后再试。页面将展示预录制示例。",
                    1,
                )
            if len(ip_events) >= self.limits.ip_max_requests:
                return GuardDecision(
                    False,
                    "ip_rate_limit",
                    "同一网络的请求频率已达到演示上限，请稍后再试。页面将展示预录制示例。",
                    max(1, int(self.limits.ip_window_seconds)),
                )
            if self._session_rounds[session_id] >= self.limits.session_max_rounds:
                return GuardDecision(
                    False,
                    "session_limit",
                    "本次演示会话已达到轮次上限，请稍后重新打开页面。页面将展示预录制示例。",
                    60,
                )
            if self._daily_calls >= self.limits.daily_call_limit:
                return GuardDecision(
                    False,
                    "daily_limit",
                    "今日演示额度已用完，页面将切换到预录制示例。",
                    3600,
                )

            self._global_events.append(now)
            ip_events.append(now)
            self._session_rounds[session_id] += 1
            self._daily_calls += 1
            return GuardDecision(True)


def request_client_ip(request: Request) -> str:
    """Resolve a client IP without trusting spoofable proxy headers by default."""

    trust_proxy = os.getenv("TRUST_PROXY_HEADERS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            if candidate:
                return candidate[:128]
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip[:128]
    return (request.client.host if request.client else "unknown")[:128]


def session_id_for(request: Request) -> tuple[str, bool]:
    """Return a bounded cookie value and whether a new one was generated."""

    cached = getattr(request.state, "agent_session", None)
    if cached is not None:
        return cached
    existing = request.cookies.get(SESSION_COOKIE, "")
    if _SESSION_PATTERN.fullmatch(existing):
        value = (existing, False)
    else:
        value = (secrets.token_urlsafe(24), True)
    request.state.agent_session = value
    return value


def set_session_cookie(request: Request, response: Response) -> None:
    """Attach a browser session cookie without exposing any secret."""

    session_id, is_new = session_id_for(request)
    if not is_new:
        return
    secure = request.url.scheme == "https" or os.getenv(
        "AGENT_COOKIE_SECURE", ""
    ).lower() in {"1", "true", "yes"}
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def session_id_from_request(request: Request) -> str:
    """Read or generate the ID used by the guard for this request."""

    return session_id_for(request)[0]


def validate_public_text(value: str, *, max_chars: int) -> str:
    """Normalize and reject obvious prompt-injection/control-character payloads."""

    normalized = value.strip()
    if len(normalized) > max_chars:
        raise ValueError(f"输入长度不能超过 {max_chars} 个字符。")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in normalized):
        raise ValueError("输入包含不支持的控制字符。")
    if _INJECTION_PATTERN.search(normalized):
        raise ValueError("输入包含疑似提示注入指令；请只描述业务问题或研究目标。")
    return normalized


def rejection_response(
    *,
    code: str,
    message: str,
    status_code: int = 429,
    retry_after: int | None = None,
) -> JSONResponse:
    """Build the stable error contract consumed by the fallback UI."""

    response = JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "code": code,
                "message": message,
                "fallback_available": True,
            }
        },
    )
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response
