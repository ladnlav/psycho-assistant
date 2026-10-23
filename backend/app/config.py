from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://compass:compass@localhost:5433/compass"
    kb_dir: Path = REPO_ROOT / "kb"
    scenarios_dir: Path = REPO_ROOT / "scenarios"
    ml_url: str = "http://localhost:8001"

    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_hours: int = 12

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
