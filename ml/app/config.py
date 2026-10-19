from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    # Любой OpenAI-совместимый сервер: Ollama, vLLM, …  Провайдер меняется только этими переменными.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b"
    llm_api_key: str = "ollama"
    llm_timeout_s: float = 120.0
    llm_max_retries: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
