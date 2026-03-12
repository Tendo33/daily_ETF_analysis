from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

load_dotenv(override=False)


@dataclass(slots=True)
class ConfigIssue:
    severity: str
    message: str
    field: str = ""


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/app.log")

    etf_list: CsvList = Field(
        default_factory=lambda: ["CN:159659", "US:QQQ", "HK:02800"]
    )
    index_proxy_map: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "NDX": ["US:QQQ", "CN:159659"],
            "SPX": ["US:SPY", "CN:513500"],
            "HSI": ["HK:02800", "CN:159920"],
        }
    )
    industry_map: dict[str, list[str]] = Field(default_factory=dict)
    markets_enabled: CsvList = Field(default_factory=lambda: ["cn", "hk", "us"])
    database_url: str = Field(default="sqlite:///./data/daily_etf_analysis.db")

    openai_model: str = Field(default="gpt-4o-mini")
    openai_api_key: str | None = Field(default=None)
    openai_api_keys: CsvList = Field(default_factory=list)
    openai_base_url: str | None = Field(default=None)

    llm_temperature: float = Field(default=0.7)
    llm_max_tokens: int = Field(default=4096)
    llm_timeout_seconds: int = Field(default=60)

    tavily_api_keys: CsvList = Field(default_factory=list)
    tavily_base_url: str | None = Field(default=None)
    news_max_age_days: int = Field(default=3)
    news_provider_priority: CsvList = Field(default_factory=lambda: ["tavily"])

    realtime_source_priority: CsvList = Field(
        default_factory=lambda: [
            "efinance",
            "akshare",
            "tushare",
            "pytdx",
            "baostock",
            "yfinance",
        ]
    )
    tushare_token: str | None = Field(default=None)
    pytdx_host: str = Field(default="119.147.212.81")
    pytdx_port: int = Field(default=7709)
    provider_max_retries: int = Field(default=1, ge=0, le=5)
    provider_backoff_ms: int = Field(default=200, ge=0, le=10_000)
    provider_circuit_fail_threshold: int = Field(default=3, ge=1, le=20)
    provider_circuit_reset_seconds: int = Field(default=60, ge=1, le=3600)

    notify_channels: CsvList = Field(default_factory=lambda: ["feishu"])
    feishu_webhook_url: str | None = Field(default=None)
    wechat_webhook_url: str | None = Field(default=None)
    telegram_bot_token: str | None = Field(default=None)
    telegram_chat_id: str | None = Field(default=None)
    email_smtp_host: str | None = Field(default=None)
    email_smtp_port: int = Field(default=25, ge=1, le=65535)
    email_username: str | None = Field(default=None)
    email_password: str | None = Field(default=None)
    email_from: str | None = Field(default=None)
    email_to: CsvList = Field(default_factory=list)
    report_templates_dir: str = Field(default="templates")
    report_renderer_enabled: bool = Field(default=False)
    report_integrity_enabled: bool = Field(default=True)
    report_history_compare_n: int = Field(default=0, ge=0, le=60)
    markdown_to_image_channels: CsvList = Field(default_factory=list)
    markdown_to_image_max_chars: int = Field(default=15000, ge=1000, le=50000)
    md2img_engine: str = Field(default="imgkit")
    metrics_enabled: bool = Field(default=True)

    task_max_concurrency: int = Field(default=2, ge=1, le=32)
    task_queue_max_size: int = Field(default=50, ge=1, le=1000)
    task_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    task_dedup_window_seconds: int = Field(default=300, ge=0, le=86_400)

    retention_task_days: int = Field(default=30, ge=1, le=3650)
    retention_report_days: int = Field(default=60, ge=1, le=3650)
    retention_quote_days: int = Field(default=14, ge=1, le=3650)

    industry_trend_window_days: int = Field(default=5, ge=1, le=60)
    industry_risk_top_n: int = Field(default=3, ge=1, le=20)
    industry_recommend_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "buy": 1.0,
            "hold": 0.0,
            "sell": -1.0,
            "score_weight": 0.5,
        }
    )

    api_auth_enabled: bool = Field(default=False)
    api_admin_token: str | None = Field(default=None)

    schedule_enabled: bool = Field(default=False)
    schedule_cron_cn: str = Field(default="0 30 15 * * 1-5")
    schedule_cron_hk: str = Field(default="0 10 16 * * 1-5")
    schedule_cron_us: str = Field(default="0 10 22 * * 1-5")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production"}
        if value not in allowed:
            raise ValueError(f"Environment must be one of {sorted(allowed)}")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        allowed = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
        val = value.upper()
        if val not in allowed:
            raise ValueError(f"Log level must be one of {sorted(allowed)}")
        return val

    @field_validator("md2img_engine")
    @classmethod
    def validate_md2img_engine(cls, value: str) -> str:
        allowed = {"imgkit", "markdown-to-file"}
        val = value.strip().lower()
        if val not in allowed:
            raise ValueError(f"md2img_engine must be one of {sorted(allowed)}")
        return val

    @field_validator("tavily_base_url")
    @classmethod
    def normalize_tavily_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator(
        "etf_list",
        "markets_enabled",
        "openai_api_keys",
        "tavily_api_keys",
        "news_provider_priority",
        "realtime_source_priority",
        "notify_channels",
        "email_to",
        "markdown_to_image_channels",
        mode="before",
    )
    @classmethod
    def parse_list_values(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                parsed = json.loads(text)
                if not isinstance(parsed, list):
                    raise ValueError("List value JSON must be an array")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return _parse_csv(text)
        raise ValueError("List value must be list or comma-separated string")

    @field_validator("index_proxy_map", mode="before")
    @classmethod
    def parse_index_proxy_map(cls, value: Any) -> dict[str, list[str]]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {
                str(k).upper(): [str(x).upper() for x in v] for k, v in value.items()
            }
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("INDEX_PROXY_MAP must be a JSON object")
            return {
                str(k).upper(): [
                    str(x).upper() for x in (v if isinstance(v, list) else [])
                ]
                for k, v in parsed.items()
            }
        raise ValueError("Invalid INDEX_PROXY_MAP value")

    @field_validator("industry_map", mode="before")
    @classmethod
    def parse_industry_map(cls, value: Any) -> dict[str, list[str]]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(k): [str(x).upper() for x in v] for k, v in value.items()}
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("INDUSTRY_MAP must be a JSON object")
            return {
                str(k): [str(x).upper() for x in (v if isinstance(v, list) else [])]
                for k, v in parsed.items()
            }
        raise ValueError("Invalid INDUSTRY_MAP value")

    @field_validator("industry_recommend_weights", mode="before")
    @classmethod
    def parse_industry_recommend_weights(cls, value: Any) -> dict[str, float]:
        if value is None:
            return {
                "buy": 1.0,
                "hold": 0.0,
                "sell": -1.0,
                "score_weight": 0.5,
            }
        payload = value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {
                    "buy": 1.0,
                    "hold": 0.0,
                    "sell": -1.0,
                    "score_weight": 0.5,
                }
            payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("INDUSTRY_RECOMMEND_WEIGHTS must be a JSON object")
        result = {
            "buy": float(payload.get("buy", 1.0)),
            "hold": float(payload.get("hold", 0.0)),
            "sell": float(payload.get("sell", -1.0)),
            "score_weight": float(payload.get("score_weight", 0.5)),
        }
        score_weight = result["score_weight"]
        if score_weight < 0 or score_weight > 1:
            raise ValueError("score_weight must be in [0, 1]")
        return result

    @model_validator(mode="after")
    def finalize_settings(self) -> Settings:
        self._normalize_key_lists()
        return self

    def _normalize_key_lists(self) -> None:
        if not self.openai_api_keys and self.openai_api_key:
            self.openai_api_keys = [self.openai_api_key]

    def validate_structured(self) -> list[ConfigIssue]:
        issues: list[ConfigIssue] = []
        if not self.etf_list:
            issues.append(ConfigIssue("error", "ETF_LIST is empty.", "ETF_LIST"))
        if not self.openai_api_keys:
            issues.append(
                ConfigIssue(
                    "error",
                    "No LLM configured. Set OPENAI_API_KEY(S).",
                    "OPENAI_API_KEY",
                )
            )
        if not self.openai_model:
            issues.append(
                ConfigIssue(
                    "warning",
                    "OPENAI_MODEL is empty. Default model will be used.",
                    "OPENAI_MODEL",
                )
            )
        if not self.tavily_api_keys:
            issues.append(
                ConfigIssue(
                    "warning",
                    "TAVILY_API_KEYS not configured. News context will be unavailable.",
                    "TAVILY_API_KEYS",
                )
            )
        if not self.feishu_webhook_url:
            issues.append(
                ConfigIssue(
                    "info",
                    "FEISHU_WEBHOOK_URL not configured. Daily analysis notifications are disabled.",
                    "FEISHU_WEBHOOK_URL",
                )
            )
        return issues

    def get_project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent.parent

    def get_log_file_path(self) -> Path:
        path = Path(self.log_file)
        if path.is_absolute():
            return path
        return self.get_project_root() / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings(env_file: Path | None = None) -> Settings:
    get_settings.cache_clear()
    if env_file is None:
        return get_settings()
    return Settings(_env_file=str(env_file))  # type: ignore[call-arg]
