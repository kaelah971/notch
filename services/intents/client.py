"""HTTP client for the Tidepool 1Click-compatible testnet API (S4).

Only the four documented endpoints required by Notch are implemented:
GET /v0/tokens, POST /v0/quote, POST /v0/deposit/submit and GET /v0/status.
No signing or chain transaction is performed here.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .models import (
    DEFAULT_BASE_URL,
    QuoteRequest,
    QuoteResponse,
    StatusResponse,
    Token,
)


DEFAULT_USER_AGENT = "NotchIntents/0.1 (NEAR testnet funding; local development)"


class TidepoolError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        body_snippet: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        self.body_snippet = body_snippet
        self.path = path

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "status": self.status,
            "code": self.code,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
            "body_snippet": self.body_snippet,
            "path": self.path,
        }


class TidepoolTransportError(TidepoolError):
    pass


class TidepoolAPIError(TidepoolError):
    pass


class TidepoolResponseError(TidepoolError):
    pass


@dataclass
class RateLimiter:
    """Minimum interval between provider requests (single process)."""

    interval_seconds: float = 0.25
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
    [str, str, dict[str, Any] | None, dict[str, Any] | None, dict[str, str], float],
    tuple[int, dict[str, str], str],
]


def _default_transport(
    method: str,
    path: str,
    params: dict[str, Any] | None,
    body: dict[str, Any] | None,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, str], str]:
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(params)
    url = f"{path}{query}"
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
        raise TidepoolTransportError(
            f"provider request failed: {type(exc).__name__}",
            retryable=True,
            path=path,
        ) from exc


class TidepoolClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        rate_limiter: RateLimiter | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.rate_limiter = rate_limiter or RateLimiter(sleep=sleep)
        self.transport = transport or _default_transport
        self.sleep = sleep
        self.user_agent = user_agent

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        retry: bool | None = None,
    ) -> Any:
        if retry is None:
            retry = method.upper() == "GET"
        attempts = self.max_retries + 1 if retry else 1
        last_error: TidepoolError | None = None
        for attempt in range(attempts):
            self.rate_limiter.wait()
            headers = self._headers()
            if body is not None:
                headers["Content-Type"] = "application/json"
            try:
                status, response_headers, text = self.transport(
                    method.upper(),
                    self._url(path),
                    params,
                    body,
                    headers,
                    self.timeout_seconds,
                )
            except TidepoolError as exc:
                last_error = exc
                if not exc.retryable or attempt >= attempts - 1:
                    raise
                self.sleep(self.backoff_seconds * (2**attempt))
                continue

            if 200 <= status < 300:
                if not text:
                    return None
                try:
                    return json.loads(text)
                except ValueError as exc:
                    raise TidepoolResponseError(
                        "provider returned invalid JSON",
                        status=status,
                        path=path,
                        body_snippet=text[:500],
                    ) from exc

            retry_after = _retry_after_seconds(response_headers)
            retryable = status == 429 or 500 <= status < 600
            message, code = _error_message(text)
            error = TidepoolAPIError(
                message or f"provider returned HTTP {status}",
                status=status,
                code=code,
                retryable=retryable,
                retry_after=retry_after,
                body_snippet=text[:500],
                path=path,
            )
            last_error = error
            if not retryable or attempt >= attempts - 1:
                raise error
            delay = retry_after if retry_after is not None else self.backoff_seconds * (2**attempt)
            self.sleep(min(max(delay, 0.0), 30.0))
        if last_error is not None:
            raise last_error
        raise TidepoolResponseError("provider request failed without a response", path=path)

    def get_tokens(self, *, include_ondo: bool = False) -> list[Token]:
        params = {"ondoTokens": "1"} if include_ondo else None
        data = self._request("GET", "/v0/tokens", params=params)
        if not isinstance(data, list):
            raise TidepoolResponseError("token list is not a JSON array", path="/v0/tokens")
        try:
            return [Token.from_provider(item) for item in data if isinstance(item, dict)]
        except (TypeError, ValueError) as exc:
            raise TidepoolResponseError(
                f"invalid token metadata: {exc}",
                path="/v0/tokens",
            ) from exc

    def quote(self, request: QuoteRequest) -> QuoteResponse:
        data = self._request(
            "POST",
            "/v0/quote",
            body=request.to_provider_dict(),
            retry=False,
        )
        if not isinstance(data, dict):
            raise TidepoolResponseError("quote response is not a JSON object", path="/v0/quote")
        try:
            return QuoteResponse.from_provider(data)
        except (TypeError, ValueError) as exc:
            raise TidepoolResponseError(
                f"invalid quote response: {exc}",
                path="/v0/quote",
            ) from exc

    def submit_deposit(
        self,
        *,
        tx_hash: str,
        deposit_address: str,
        near_sender_account: str | None = None,
        memo: str | None = None,
    ) -> StatusResponse:
        body: dict[str, Any] = {
            "txHash": tx_hash,
            "depositAddress": deposit_address,
        }
        if near_sender_account:
            body["nearSenderAccount"] = near_sender_account
        if memo:
            body["memo"] = memo
        data = self._request(
            "POST",
            "/v0/deposit/submit",
            body=body,
            retry=True,
        )
        if not isinstance(data, dict):
            raise TidepoolResponseError(
                "deposit response is not a JSON object",
                path="/v0/deposit/submit",
            )
        try:
            return StatusResponse.from_provider(data)
        except (TypeError, ValueError) as exc:
            raise TidepoolResponseError(
                f"invalid deposit response: {exc}",
                path="/v0/deposit/submit",
            ) from exc

    def get_status(self, *, deposit_address: str, memo: str | None = None) -> StatusResponse:
        params: dict[str, Any] = {"depositAddress": deposit_address}
        if memo:
            params["depositMemo"] = memo
        data = self._request("GET", "/v0/status", params=params)
        if not isinstance(data, dict):
            raise TidepoolResponseError("status response is not a JSON object", path="/v0/status")
        try:
            return StatusResponse.from_provider(data)
        except (TypeError, ValueError) as exc:
            raise TidepoolResponseError(
                f"invalid status response: {exc}",
                path="/v0/status",
            ) from exc


def _retry_after_seconds(headers: dict[str, str]) -> float | None:
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _error_message(text: str) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(text)
    except ValueError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    message = payload.get("message") or payload.get("error") or payload.get("detail")
    code = payload.get("code") or payload.get("field")
    return (str(message) if message else None, str(code) if code else None)
