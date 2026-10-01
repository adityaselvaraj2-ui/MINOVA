"""Object-storage layer: MinIO / S3-compatible backend with a local-filesystem
fallback that preserves the same contract (metadata in DB, bytes in object store).

The abstract specifies "scalable object storage" (MinIO/S3). On a single-laptop
SIH demo the `local` backend keeps the platform zero-dependency; switching to
MINETRACE_STORAGE_BACKEND=s3 with docker-compose up activates MinIO. Both
backends store bytes under an opaque key and never expose paths to clients.
"""
from __future__ import annotations

import logging
import uuid as uuid_mod
from pathlib import Path

from app.config import settings

logger = logging.getLogger("minetrace.storage")

_client = None  # boto3 S3 client, created lazily


def backend_name() -> str:
    return "s3" if settings.storage_backend == "s3" else "local"


def _s3_client():
    """Lazy boto3 client pointed at MinIO (S3-compatible API)."""
    global _client
    if _client is not None:
        return _client
    try:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        bucket = settings.minio_bucket
        try:
            _client.head_bucket(Bucket=bucket)
        except _client.exceptions.ClientError:
            _client.create_bucket(Bucket=bucket)
            logger.info("Created bucket %s", bucket)
        return _client
    except Exception:
        logger.exception("MinIO/S3 client unavailable; check MINETRACE_MINIO_* settings")
        raise


def save_bytes(key: str, content: bytes) -> str:
    """Store bytes under `key`; returns the storage key (path-safe, opaque)."""
    if backend_name() == "s3":
        c = _s3_client()
        c.put_object(Bucket=settings.minio_bucket, Key=key, Body=content)
        return key
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return key


def open_bytes(key: str) -> bytes:
    """Read bytes for `key` from the active backend."""
    if backend_name() == "s3":
        c = _s3_client()
        return c.get_object(Bucket=settings.minio_bucket, Key=key)["Body"].read()
    return _local_path(key).read_bytes()


def delete(key: str) -> None:
    if backend_name() == "s3":
        _s3_client().delete_object(Bucket=settings.minio_bucket, Key=key)
        return
    path = _local_path(key)
    if path.exists():
        path.unlink()


def exists(key: str) -> bool:
    if backend_name() == "s3":
        try:
            _s3_client().head_object(Bucket=settings.minio_bucket, Key=key)
            return True
        except Exception:
            return False
    return _local_path(key).exists()


def new_key(filename: str) -> str:
    """Collision-safe opaque object key: <uuid><ext> (no user-controlled path)."""
    suffix = Path(filename).suffix.lower()
    return f"{uuid_mod.uuid4().hex}{suffix}"


def _local_path(key: str) -> Path:
    """Local fallback layout mirrors the legacy uploads dir."""
    safe = key.replace("\\", "/").lstrip("/")
    if ".." in safe.split("/"):
        raise ValueError(f"Illegal storage key: {key}")
    return settings.uploads_path / safe
