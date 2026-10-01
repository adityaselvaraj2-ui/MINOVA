from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.services import workflows

router = APIRouter(prefix="/workflows", tags=["Workflow Orchestration (Temporal)"])


@router.get("/status")
def status():
    """Live status of the Temporal orchestration layer and its fallback."""
    return {
        "temporal_enabled": settings.temporal_enabled,
        "temporal_available": workflows.temporal_available(),
        "host": settings.temporal_host,
        "namespace": settings.temporal_namespace,
        "task_queue": settings.temporal_task_queue,
        "workflow_pattern": "approval-entry-{entry_id}",
        "fallback": None if settings.temporal_enabled
        else "in-process approval state machine + hash-chained audit log",
    }
