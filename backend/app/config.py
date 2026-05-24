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
    model_gateway_provider: str = "litellm"
    model_gateway_api_base_url: str = "http://litellm:4000/v1"
    model_gateway_api_key: str = "dev-litellm-key"
    model_gateway_default_model: str = "qf-supervisor-strong"
    model_gateway_timeout_seconds: int = 30
    model_gateway_max_attempts: int = 3
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    agent_task_queue: str = "qualiforge-agent-runs"
    agent_execute_sync_mode: bool = True
    agent_workflow_timeout_minutes: int = 30
    agent_activity_start_to_close_timeout_minutes: int = 25
    agent_activity_heartbeat_timeout_seconds: int = 30
    agent_activity_retry_attempts: int = 3
    agent_default_max_tool_calls: int = 60
    agent_default_max_subagents: int = 4
    agent_default_max_parallel_subagents: int = 3
    agent_default_max_model_calls: int = 20
    agent_default_max_case_candidates_per_run: int = 30
    agent_default_max_wall_time_minutes: int = 20
    agent_default_max_total_source_chars_sent: int = 200000
    agent_system_max_tool_calls: int = 200
    agent_system_max_subagents: int = 12
    agent_system_max_parallel_subagents: int = 6
    agent_system_max_model_calls: int = 40
    agent_system_max_case_candidates_per_run: int = 100
    agent_system_max_wall_time_minutes: int = 60
    agent_system_max_total_source_chars_sent: int = 500000
    agent_memory_root: str = ".qualiforge/agent-memory"
    telemetry_service_name: str = "qualiforge-backend"
    telemetry_otlp_enabled: bool = False
    telemetry_otlp_endpoint: str = ""
    telemetry_otlp_headers: str = ""
    telemetry_trace_console_enabled: bool = False
    telemetry_prometheus_enabled: bool = True
    telemetry_langfuse_enabled: bool = False
    telemetry_langfuse_host: str = ""
    telemetry_langfuse_public_key: str = ""
    telemetry_langfuse_secret_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
