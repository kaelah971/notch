"""Configuration for S5 NEAR AI trend briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .models import PROMPT_VERSION


DEFAULT_BASE_URL = "https://cloud-api.near.ai/v1"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"


@dataclass(frozen=True)
class NearAIConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    model: str = DEFAULT_MODEL
    # GLM reasoning tokens count toward the completion budget before final JSON.
    timeout_seconds: float = 90.0
    max_tokens: int = 8_192
    temperature: float = 0.2
    rate_limit_seconds: float = 2.0
    max_retries: int = 1
    retry_backoff_seconds: float = 1.0
    max_input_chars: int = 32_000
    cache_ttl_seconds: int = 86_400
    data_dir: str = "var/ai_briefs"
    radar_db: str = "var/trend_radar_live_final/radar.sqlite3"
    oracle_db: str = "var/oracle_live_final/oracle.sqlite3"
    prompt_version: str = PROMPT_VERSION
    max_calls_per_run: int = 1

    @property
    def key_present(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "NearAIConfig":
        return cls(
            base_url=os.environ.get("NEAR_AI_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("NEAR_AI_KEY") or None,
            model=os.environ.get("NEAR_AI_MODEL", DEFAULT_MODEL),
            timeout_seconds=float(os.environ.get("NEAR_AI_TIMEOUT_SECONDS", "90")),
            max_tokens=max(256, int(os.environ.get("NEAR_AI_MAX_TOKENS", "8192"))),
            max_retries=max(0, min(2, int(os.environ.get("NEAR_AI_MAX_RETRIES", "1")))),
            retry_backoff_seconds=max(
                0.0, min(4.0, float(os.environ.get("NEAR_AI_RETRY_BACKOFF_SECONDS", "1")))
            ),
            max_input_chars=max(8_000, int(os.environ.get("NEAR_AI_MAX_INPUT_CHARS", "32000"))),
            data_dir=os.environ.get("AI_BRIEFS_DATA_DIR", "var/ai_briefs"),
            radar_db=os.environ.get(
                "RADAR_DB_PATH", "var/trend_radar_live_final/radar.sqlite3"
            ),
            oracle_db=os.environ.get(
                "ORACLE_DB_PATH", "var/oracle_live_final/oracle.sqlite3"
            ),
        )
