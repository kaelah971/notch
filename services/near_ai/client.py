"""OpenAI-compatible client for NEAR AI Cloud (S5).

Only model discovery and chat completions are used.  The client never logs the
API key, never retries chat completions automatically, and never performs any
chain action.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import NearAIConfig


DEFAULT_USER_AGENT = "NotchNearAI/0.1 (S5 trend briefs; local development)"


class NearAIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retryable: bool = False,
        body_snippet: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.body_snippet = body_snippet
        self.path = path

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "status": self.status,
            "code": self.code,
            "retryable": self.retryable,
            "body_snippet": self.body_snippet,
            "path": self.path,
        }


class NearAIAuthError(NearAIError):
    pass


class NearAIRateLimitError(NearAIError):
    pass


class NearAIRequestError(NearAIError):
    pass


class NearAIProviderError(NearAIError):
    pass


class NearAIResponseError(NearAIError):
    pass


class NearAIModelUnavailable(NearAIError):
    pass


@dataclass(frozen=True)
class AIModel:
    model_id: str
    owned_by: str | None
    pricing: dict[str, Any]
    context_length: int | None
    max_output_length: int | None
    supported_features: list[str]
    is_ready: bool | None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_provider(cls, data: dict[str, Any]) -> "AIModel":
        if not data.get("id"):
            raise ValueError("model missing id")
        return cls(
            model_id=str(data["id"]),
            owned_by=data.get("owned_by"),
            pricing=dict(data.get("pricing") or {}),
            context_length=data.get("context_length"),
            max_output_length=data.get("max_output_length"),
            supported_features=list(data.get("supported_features") or []),
            is_ready=data.get("is_ready"),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "owned_by": self.owned_by,
            "pricing": self.pricing,
            "context_length": self.context_length,
            "max_output_length": self.max_output_length,
            "supported_features": self.supported_features,
            "is_ready": self.is_ready,
        }

    def price_per_million(self) -> tuple[float, float]:
        pricing = self.pricing
        def value(*keys: str) -> float:
            for key in keys:
                if key in pricing and pricing[key] not in (None, ""):
                    try:
                        return float(pricing[key])
                    except (TypeError, ValueError):
                        pass
            return 0.0
        return value("input", "prompt"), value("output", "completion")


@dataclass(frozen=True)
class AICompletion:
    content: dict[str, Any]
    text: str
    model: str
    usage: dict[str, Any]
    request_id: str | None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    def estimated_cost_usd(self, model: AIModel) -> float:
        input_price, output_price = model.price_per_million()
        prompt = float(self.usage.get("prompt_tokens") or 0)
        completion = float(self.usage.get("completion_tokens") or 0)
        return (prompt / 1_000_000.0) * input_price + (completion / 1_000_000.0) * output_price


@dataclass
class RateLimiter:
    interval_seconds: float = 2.0
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    last_request: float | None = None

    def wait(self) -> float:
        if self.interval_seconds <= 0:
            return 0.0
        now = self.clock()
        slept = 0.0
        if self.last_request is not None:
            remaining = self.interval_seconds - (now - self.last_request)
            if remaining > 0:
                self.sleep(remaining)
                slept = remaining
                now = self.clock()
        self.last_request = now
        return slept


Transport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None, float],
    tuple[int, dict[str, str], str],
]


def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, dict[str, str], str]:
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                int(response.status),
                {key.lower(): value for key, value in response.headers.items()},
                response.read().decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        return (
            int(exc.code),
            {key.lower(): value for key, value in (exc.headers or {}).items()},
            exc.read().decode("utf-8", errors="replace"),
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NearAIProviderError(
            f"NEAR AI request failed: {type(exc).__name__}",
            retryable=True,
        ) from exc


class NearAIClient:
    def __init__(
        self,
        *,
        config: NearAIConfig,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.transport = transport or _default_transport
        self.rate_limiter = RateLimiter(
            interval_seconds=config.rate_limit_seconds,
            sleep=sleep,
        )
        self.user_agent = user_agent

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        self.rate_limiter.wait()
        status, headers, text = self.transport(
            method,
            f"{self.base_url}{path}",
            self._headers(),
            body,
            self.config.timeout_seconds,
        )
        if not (200 <= status < 300):
            message, code = _error_message(text)
            kwargs = {
                "status": status,
                "code": code,
                "body_snippet": text[:500],
                "path": path,
            }
            if status in {401, 403}:
                raise NearAIAuthError(message or "NEAR AI authentication failed", **kwargs)
            if status == 429:
                raise NearAIRateLimitError(message or "NEAR AI rate limited", **kwargs)
            if 500 <= status < 600:
                raise NearAIProviderError(
                    message or "NEAR AI provider unavailable",
                    retryable=True,
                    **kwargs,
                )
            raise NearAIRequestError(message or f"NEAR AI HTTP {status}", **kwargs)
        try:
            payload = json.loads(text) if text else {}
        except ValueError as exc:
            raise NearAIResponseError(
                "NEAR AI returned invalid JSON",
                status=status,
                path=path,
                body_snippet=text[:500],
            ) from exc
        if not isinstance(payload, dict):
            raise NearAIResponseError("NEAR AI response is not an object", path=path)
        return payload, headers

    def list_models(self) -> list[AIModel]:
        payload, _ = self._request("GET", "/models")
        data = payload.get("data")
        if not isinstance(data, list):
            raise NearAIResponseError("model catalog missing data array", path="/models")
        try:
            return [AIModel.from_provider(item) for item in data if isinstance(item, dict)]
        except (TypeError, ValueError) as exc:
            raise NearAIResponseError(f"invalid model catalog: {exc}", path="/models") from exc

    def select_model(self, model_id: str | None = None) -> AIModel:
        target = model_id or self.config.model
        models = self.list_models()
        for model in models:
            if model.model_id == target:
                if model.is_ready is False:
                    raise NearAIModelUnavailable(
                        f"model {target} is present but not ready",
                        code="MODEL_NOT_READY",
                    )
                return model
        raise NearAIModelUnavailable(
            f"model {target} is not in the live /models catalog",
            code="MODEL_NOT_FOUND",
        )

    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AICompletion:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        payload, headers = self._request("POST", "/chat/completions", body=body)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise NearAIResponseError("NEAR AI response has no choices", path="/chat/completions")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, dict):
            parsed = content
            text = json.dumps(content, ensure_ascii=False)
        elif isinstance(content, str):
            text = content
            try:
                parsed = _parse_json_content(content)
            except ValueError as exc:
                raise NearAIResponseError(
                    "NEAR AI message content is not valid JSON",
                    path="/chat/completions",
                    body_snippet=content[:500],
                ) from exc
        else:
            raise NearAIResponseError("NEAR AI message has no content", path="/chat/completions")
        if not isinstance(parsed, dict):
            raise NearAIResponseError("NEAR AI content is not a JSON object", path="/chat/completions")
        return AICompletion(
            content=parsed,
            text=text,
            model=str(payload.get("model") or model),
            usage=dict(payload.get("usage") or {}),
            request_id=headers.get("x-request-id"),
            raw=payload,
        )


def _parse_json_content(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    return json.loads(stripped)


def _error_message(text: str) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(text)
    except ValueError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    message = payload.get("message") or payload.get("error") or payload.get("detail")
    code = payload.get("code") or payload.get("type")
    if isinstance(message, dict):
        message = message.get("message")
    return (str(message) if message else None, str(code) if code else None)
