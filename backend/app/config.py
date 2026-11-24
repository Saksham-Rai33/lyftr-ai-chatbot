"""Environment-driven settings. Every knob is an env var (see ../.env.example)."""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, concise assistant. Answer clearly and keep earlier "
    "messages in this conversation in mind."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Comma-separated key pool. Key ids are key_1, key_2, ... in this order.
    llm_api_keys: str = Field(default="", alias="LLM_API_KEYS")
    # Model used by every key unless LLM_MODELS overrides it per key.
    llm_model: str = Field(default="groq/openai/gpt-oss-20b", alias="LLM_MODEL")
    # Optional comma-separated models aligned with LLM_API_KEYS (key_1 -> first model, ...).
    # Lets the pool span providers, e.g. "groq/openai/gpt-oss-20b,gemini/gemini-3.5-flash-lite".
    llm_models: str = Field(default="", alias="LLM_MODELS")
    # Optional: point LiteLLM at an OpenAI-compatible endpoint (used by tests / local fakes).
    llm_api_base: str | None = Field(default=None, alias="LLM_API_BASE")
    llm_timeout_seconds: float = Field(default=30.0, alias="LLM_TIMEOUT_SECONDS")
    cache_ttl_seconds: int = Field(default=3600, alias="CACHE_TTL_SECONDS")

    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    enable_failure_simulation: bool = Field(default=False, alias="ENABLE_FAILURE_SIMULATION")
    default_system_prompt: str = Field(default=DEFAULT_SYSTEM_PROMPT, alias="DEFAULT_SYSTEM_PROMPT")

    @field_validator("llm_api_base", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        return v or None

    @property
    def api_keys(self) -> list[str]:
        return [k.strip() for k in self.llm_api_keys.split(",") if k.strip()]

    @property
    def key_models(self) -> list[str]:
        """Model for each key, in key order. Missing entries reuse the last given model."""
        models = [m.strip() for m in self.llm_models.split(",") if m.strip()] or [self.llm_model]
        return [models[min(i, len(models) - 1)] for i in range(len(self.api_keys))]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def database_path(self) -> str:
        """sqlite:////data/app.db -> /data/app.db ; sqlite:///./x.db -> ./x.db"""
        url = self.database_url
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if url.startswith(prefix):
                return url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
