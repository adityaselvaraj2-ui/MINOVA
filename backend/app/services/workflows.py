"""Temporal approval workflows (enterprise orchestration layer).

The abstract specifies Temporal for managing multi-level approval workflows.
MineTrace's in-process approval state machine (app/services/approvals.py +
hash-chained audit log) remains the offline fallback; when
MINETRACE_TEMPORAL_ENABLED=true this module runs the same multi-level flow as
durable Temporal workflows:

- One ShiftEntryApprovalWorkflow per shift entry; escalation on inactivity SLA
- Signal: decide(approve/return, actor) - mirrors the REST actions
- Query: status() - current step, history, outcome
- Activities persist transitions through app.services.approvals so the audit
  trail is identical regardless of which orchestrator advanced the step.

Run the worker:  python -m app.services.workflows
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from app.config import settings

logger = logging.getLogger("minetrace.workflows")

ESCALATE_AFTER_S = 24 * 3600  # escalate a stuck step after 24h


@dataclass
class WorkflowInput:
    entry_id: int
    mine_id: int | None
    started_by: str


@dataclass
class WorkflowState:
    entry_id: int
    current_step: int = 1
    history: list[str] = field(default_factory=list)
    outcome: str = "PENDING"  # PENDING | APPROVED | RETURNED


def temporal_available() -> bool:
    """Import probe so /health can report Temporal support without importing
    temporalio at app startup (optional dependency)."""
    try:
        import temporalio  # noqa: F401

        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------
# Activities (DB side effects through the in-process service layer)
# --------------------------------------------------------------------------

async def _apply_decision_impl(entry_id: int, decision: str,
                               actor_username: str, note: str) -> dict:
    """Advance one approval step via app.services.approvals, so the audit
    trail is identical whether the in-process API or Temporal advanced it."""

    def _sync() -> dict:
        from app.db.models import ShiftEntry, User
        from app.db.session import get_session_factory
        from app.services.approvals import approve_entry, return_entry

        with get_session_factory()() as db:
            entry = db.get(ShiftEntry, entry_id)
            if entry is None:
                raise RuntimeError(f"entry {entry_id} not found")
            actor = db.query(User).filter(User.username == actor_username).first()
            if actor is None:
                raise RuntimeError(f"actor '{actor_username}' not found")
            if decision == "APPROVE":
                approve_entry(db, entry, actor)
            elif decision == "RETURN":
                return_entry(db, entry, actor, note or "returned via workflow")
            else:
                raise ValueError(f"unsupported decision: {decision}")
            db.commit()
            return {
                "status": entry.status,
                "current_step": entry.current_step,
                "final_status": entry.status if entry.status != "SUBMITTED" else None,
            }

    return await asyncio.to_thread(_sync)


# --------------------------------------------------------------------------
# Workflow definition (temporalio imported lazily via a factory so this module
# imports cleanly when temporalio is not installed)
# --------------------------------------------------------------------------

# The workflow class MUST be defined at module scope: temporalio rejects
# @workflow.defn on classes created inside a function (qualname check).
# The try/except keeps this module importable when temporalio (optional
# enterprise dependency) is not installed.
try:
    from temporalio import workflow as _workflow
except ImportError:  # temporalio is an optional enterprise dependency
    _workflow = None

if _workflow is not None:
    from temporalio import activity as _activity

    @_activity.defn
    async def act_apply_decision(entry_id: int, decision: str,
                                 actor_username: str, note: str) -> dict:
        return await _apply_decision_impl(entry_id, decision, actor_username,
                                          note)

    @_workflow.defn
    class ShiftEntryApprovalWorkflow:
        def __init__(self) -> None:
            self._decision: tuple[str, str, str] | None = None
            self._state = WorkflowState(entry_id=0)

        @_workflow.run
        async def run(self, inp: WorkflowInput) -> WorkflowState:
            self._state = WorkflowState(entry_id=inp.entry_id)
            self._state.history.append(f"STARTED:{inp.started_by}")
            while self._state.outcome == "PENDING":
                # wait_condition RAISES TimeoutError on timeout (it does not
                # return a truthy/falsy "got it" flag).
                try:
                    await _workflow.wait_condition(
                        lambda: self._decision is not None,
                        timeout=ESCALATE_AFTER_S,
                    )
                    got_decision = True
                except TimeoutError:
                    got_decision = False
                if not got_decision:
                    # Inactivity SLA breach: record escalation, keep waiting.
                    # NOTE: no logging inside workflow code — blocking IO in
                    # the workflow thread trips Temporal's deadlock detector.
                    self._state.history.append("ESCALATED:sla_breach")
                    continue
                decision, actor, note = self._decision
                self._decision = None
                try:
                    result = await _workflow.execute_activity(
                        act_apply_decision,
                        args=[inp.entry_id, decision, actor, note],
                        # temporalio requires timedelta here (ints are rejected
                        # at activation time: "Fail to convert to Duration").
                        start_to_close_timeout=timedelta(seconds=60),
                    )
                except Exception:  # noqa: BLE001 - workflow must not crash
                    # No logging here either (deadlock detector); the error
                    # is preserved in the durable history instead.
                    self._state.history.append(f"ERROR:{decision}:{actor}")
                    continue
                self._state.history.append(f"{decision}:{actor}")
                self._state.current_step = result.get("current_step",
                                                      self._state.current_step)
                if result.get("final_status"):
                    self._state.outcome = result["final_status"]
            return self._state

        @_workflow.signal
        async def decide(self, decision: str, actor: str, note: str = "") -> None:
            self._decision = (decision, actor, note)

        @_workflow.query
        def status(self) -> WorkflowState:
            return self._state

    _WORKFLOW_CLS: type | None = ShiftEntryApprovalWorkflow
else:
    _WORKFLOW_CLS = None

    async def act_apply_decision(entry_id: int, decision: str,
                                 actor_username: str, note: str) -> dict:
        """Plain (undecorated) form for when temporalio is absent."""
        return await _apply_decision_impl(entry_id, decision, actor_username,
                                          note)


def get_workflow_cls():
    if _WORKFLOW_CLS is None:
        raise RuntimeError("temporalio not installed; offline fallback active")
    return _WORKFLOW_CLS


# --------------------------------------------------------------------------
# Client helpers (used by the REST layer when temporal_enabled)
# --------------------------------------------------------------------------

def workflow_id_for(entry_id: int) -> str:
    return f"approval-entry-{entry_id}"


async def start_entry_workflow(entry_id: int, mine_id: int | None,
                               started_by: str) -> str | None:
    """Start a Temporal workflow for a shift entry; returns workflow id/None."""
    if not settings.temporal_enabled or not temporal_available():
        return None
    try:
        from temporalio.client import Client

        client = await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )
        handle = await client.start_workflow(
            get_workflow_cls().run,
            WorkflowInput(entry_id=entry_id, mine_id=mine_id, started_by=started_by),
            id=workflow_id_for(entry_id),
            task_queue=settings.temporal_task_queue,
        )
        return handle.id
    except Exception as exc:
        # A running execution for the same entry is fine: the workflow is
        # durable, so resume signalling it instead of failing the request.
        if type(exc).__name__ == "WorkflowAlreadyStartedError":
            return workflow_id_for(entry_id)
        logger.exception("failed to start Temporal workflow for entry %s", entry_id)
        return None


async def signal_entry_workflow(entry_id: int, decision: str, actor: str,
                                note: str = "") -> bool:
    """Signal a running workflow with a decision; True on success."""
    if not settings.temporal_enabled or not temporal_available():
        return False
    try:
        from temporalio.client import Client

        client = await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )
        get_workflow_cls()
        handle = client.get_workflow_handle(workflow_id_for(entry_id))
        await handle.signal(
            "decide",
            args=[decision, actor, note],
        )
        return True
    except Exception:
        logger.exception("failed to signal workflow for entry %s", entry_id)
        return False


async def run_worker() -> None:  # pragma: no cover - long-running process
    """Blocking worker entrypoint: python -m app.services.workflows"""
    from temporalio.client import Client
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker

    client = await Client.connect(
        settings.temporal_host, namespace=settings.temporal_namespace
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[get_workflow_cls()],
        activities=[act_apply_decision],
        # The workflow module imports app.config (paths resolved at import
        # time), which the default sandbox flags. Determinism is preserved by
        # construction (wait_condition on a signal, no wall-clock reads).
        workflow_runner=UnsandboxedWorkflowRunner(),
    )
    logger.info("Temporal worker started on queue %s", settings.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
