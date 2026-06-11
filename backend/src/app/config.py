from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root, not in backend/. In prod the file won't exist
# and settings come from real environment variables (pydantic-settings skips
# missing env files).
REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV_FILE, extra="ignore")

    app_env: str = "dev"
    database_url: str

    session_cookie_name: str = "askharder_session"
    session_ttl_days: int = 14

    # mock: deterministic flow, no API keys (tests + offline dev)
    # deepseek: real intake + plan + interviewer + Anthropic judge
    llm_backend: Literal["mock", "deepseek"] = "mock"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_intake_model: str = "deepseek-chat"
    deepseek_plan_model: str = "deepseek-chat"
    deepseek_interviewer_model: str = "deepseek-chat"
    # v4 thinking mode — global for intake, plan, and interviewer (Pure A)
    deepseek_thinking: Literal["enabled", "disabled"] = "enabled"
    deepseek_reasoning_effort: Literal["high", "max"] = "high"
    deepseek_intake_max_tokens: int = 1024
    deepseek_plan_max_tokens: int = 4096
    deepseek_interviewer_max_tokens: int = 512
    anthropic_api_key: str | None = None
    anthropic_judge_model: str = "claude-sonnet-4-6"
    anthropic_judge_max_tokens: int = 4096


# required fields are populated from the environment at runtime, which the
# type checker can't see
settings = Settings()  # type: ignore[call-arg]
