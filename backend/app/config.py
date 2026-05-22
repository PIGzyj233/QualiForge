from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QUALIFORGE_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "QualiForge"
    environment: str = "local"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "postgresql://qualiforge:qualiforge@localhost:5432/qualiforge"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    worker_heartbeat_seconds: int = 15
    git_sandbox_root: str = ".qualiforge/git-sandbox"
    git_sync_timeout_seconds: int = 120
    git_repo_size_limit_mb: int = 1024
    git_diff_file_limit: int = 500
    import_storage_root: str = ".qualiforge/imports"
    evidence_storage_root: str = ".qualiforge/evidence"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
