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
    ollama_primary_model: str = "qwen2.5:7b"
    ollama_secondary_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.0
    ollama_seed: int = 42
    ollama_num_ctx: int = 8192

    embedding_model_path: str = "models/bge-small-en-v1.5"
    paddleocr_model_dir: str = "models/paddleocr"

    shift_length_minutes: int = 480
    shifts_per_day: int = 3
    shift_codes: list[str] = ["A", "B", "C"]

    week_convention: str = "MONTH_CLIPPED"

    stripping_ratio_definition: str = "OB_m3 / production_t"

    @property
    def db_url(self) -> str:
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
