"""Minimal OpenAI-compatible JSON client used by optional model-assisted mode."""

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class LLMProviderError(RuntimeError):
    """Raised when a configured model endpoint fails its JSON contract."""


class JsonLLM(Protocol):
    """Small interface that keeps workflows independent of one model vendor."""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        """Return one JSON object."""


@dataclass(frozen=True)
class OpenAICompatibleJsonClient:
    """Call an OpenAI-compatible chat-completions endpoint for JSON output."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0
    max_tokens: int = 400

    @classmethod
    def from_env(cls) -> "OpenAICompatibleJsonClient | None":
        """Build a client only when all required environment variables exist."""

        base_url = os.getenv("AGENT_LLM_BASE_URL")
        api_key = os.getenv("AGENT_LLM_API_KEY")
        model = os.getenv("AGENT_LLM_MODEL")
        if not (base_url and api_key and model):
            return None
        try:
            configured_max_tokens = int(os.getenv("AGENT_LLM_MAX_TOKENS", "400"))
        except ValueError:
            configured_max_tokens = 400
        max_tokens = max(64, min(800, configured_max_tokens))
        try:
            configured_timeout = float(os.getenv("AGENT_LLM_TIMEOUT_SECONDS", "20"))
        except ValueError:
            configured_timeout = 20.0
        timeout_seconds = max(5.0, min(30.0, configured_timeout))
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        """Request a JSON object and normalize provider failures."""

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                    "max_tokens": self.max_tokens,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise LLMProviderError("Model content must be a JSON string.")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise LLMProviderError("Model output must be one JSON object.")
            return result
        except LLMProviderError:
            raise
        except (
            httpx.HTTPError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise LLMProviderError(
                "The configured model endpoint failed its JSON contract."
            ) from exc
