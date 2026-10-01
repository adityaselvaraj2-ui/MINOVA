from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from pydantic_settings import BaseSettings


def _default_data_dir() -> Path:
    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir("minetrace", appauthor=False))
    except ImportError:
        return Path.home() / ".minetrace"


class Settings(BaseSettings):
    model_config = {"env_prefix": "MINETRACE_", "env_file": ".env", "extra": "ignore"}

    def model_post_init(self, _context) -> None:
        # BGE-M3 implies the 1024-dim dense space; keep embedding_dim in sync
        # so the ChromaDB collection name and health probe never disagree with
        # the actual vector width when only the model path is switched.
        if "bge-m3" in self.embedding_model_path.lower() and "EMBEDDING_DIM" not in {
            k.upper().removeprefix("MINETRACE_") for k in os.environ
        }:
            self.embedding_dim = self.bge_m3_dim

    app_name: str = "MineTrace"
    debug: bool = False
    data_dir: Path = _default_data_dir()

    db_name: str = "minetrace.db"
    chroma_dir_name: str = "chroma"
    uploads_dir_name: str = "uploads"
    page_cache_dir_name: str = "page_cache"
    exports_dir_name: str = "exports"

    host: str = "127.0.0.1"
    port: int = 0

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_primary_model: str = "qwen3:8b"
    ollama_fallback_1: str = "qwen2.5:7b"
    ollama_secondary_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.0
    ollama_seed: int = 42
    ollama_num_ctx: int = 8192

    embedding_model_path: str = "models/multilingual-e5-small"
    embedding_dim: int = 384
    reranker_enabled: bool = False
    reranker_model_path: str = "models/bge-reranker-v2-m3"
    paddleocr_model_dir: str = "models/paddleocr"
    bge_m3_dim: int = 1024  # BGE-M3 dense vector size (CLS pooling)

    # --- Enterprise stack (abstract): config-gated, zero-dep fallbacks ---
    # DB: sqlite (default, zero-dependency) | postgres (PostgreSQL/PostGIS+pgvector)
    db_backend: str = "sqlite"
    pg_dsn: str = "postgresql+psycopg://minetrace:minetrace@localhost:5432/minetrace"

    # Object storage: local filesystem (default) | s3 (MinIO/S3-compatible)
    storage_backend: str = "local"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minetrace"
    minio_secret_key: str = "minetrace123"
    minio_bucket: str = "minetrace-documents"

    # Keycloak SSO (auth layer); local argon2+JWT remains the offline fallback
    keycloak_enabled: bool = False
    keycloak_server_url: str = "http://localhost:8180"
    keycloak_realm: str = "minetrace"
    keycloak_client_id: str = "minetrace-api"

    # Temporal workflow orchestration for multi-level approvals;
    # in-process approval state machine remains the offline fallback
    temporal_enabled: bool = False
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "minetrace-approvals"

    # Hindi support (bilingual EN+HI requirement)
    hindi_query_translation: bool = True

    # Weather module: online provider is OFF by default (air-gap constraint).
    weather_online: bool = False
    weather_provider: str = "csv"  # csv | open-meteo
    weather_online_base_url: str = "http://127.0.0.1:9099"  # operator-run gateway
    weather_forecast_stale_days: int = 3

    # Plan engine
    plan_horizon_days: int = 7
    plan_min_sample_n: int = 15
    plan_capacity_pct: int = 95  # P95 cap

    # Fiscal year (Indian FY Apr-Mar by default, configurable)
    fiscal_year_start_month: int = 4

    # Anomaly detection (deterministic)
    anomaly_z_threshold: float = 3.0

    # Text-to-SQL safety
    sql_allow_tables: list[str] = [
        "report", "report_metric", "shift_entry", "downtime_event",
        "mine", "bench", "subsidiary", "target", "equipment",
    ]

    shift_length_minutes: int = 480
    shifts_per_day: int = 3
    shift_codes: list[str] = ["A", "B", "C"]

    week_convention: str = "MONTH_CLIPPED"

    stripping_ratio_definition: str = "OB_m3 / production_t"

    @property
    def models_root(self) -> Path:
        root = Path(__file__).resolve().parents[3] / "models"
        return root

    @property
    def db_url(self) -> str:
        if self.db_backend == "postgres":
            return self.pg_dsn
        return f"sqlite:///{self.data_dir / self.db_name}"

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / self.chroma_dir_name

    @property
    def uploads_path(self) -> Path:
        return self.data_dir / self.uploads_dir_name

    @property
    def page_cache_path(self) -> Path:
        return self.data_dir / self.page_cache_dir_name

    @property
    def exports_path(self) -> Path:
        return self.data_dir / self.exports_dir_name

    @property
    def jwt_secret_path(self) -> Path:
        return self.data_dir / ".jwt_secret"

    def get_jwt_secret(self) -> str:
        path = self.jwt_secret_path
        if path.exists():
            return path.read_text().strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_urlsafe(64)
        path.write_text(secret)
        if os.name != "nt":
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return secret

    def ensure_dirs(self) -> None:
        for d in [
            self.data_dir,
            self.uploads_path,
            self.page_cache_path,
            self.exports_path,
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
