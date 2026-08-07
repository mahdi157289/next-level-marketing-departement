"""Application settings loaded from environment / .env."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://admin:secret@localhost:5432/marketing_db"
    litellm_base_url: str = "http://localhost:4000"
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    # Full OpenAI-compatible base URL including `/v1`. Empty → use `lm_studio_base_url` (direct LM Studio).
    openai_api_base: Optional[str] = None
    openai_api_key: str = "lm-studio"
    agent_model_discovery: str = "mistralai/mistral-7b-instruct-v0.3"
    agent_model_head: str = "mistralai/mistral-7b-instruct-v0.3"
    meta_ads_access_token: str = ""
    agent_chat_timeout_s: float = 120.0
    app_port: int = 8000
    debug: bool = True
    janusgraph_base_url: str = "ws://localhost:8182/gremlin"
    redis_url: str = "redis://localhost:6379/2"
    brain_cache_ttl_s: int = 3600

    def openai_base_url(self) -> str:
        base = (self.openai_api_base or "").strip()
        if base:
            return base.rstrip("/")
        return self.lm_studio_base_url.strip().rstrip("/")



@lru_cache
def get_settings() -> Settings:
    return Settings()
