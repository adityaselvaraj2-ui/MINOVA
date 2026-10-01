"""Probe: can a workflow schedule app.services.workflows.act_apply_decision?"""
import asyncio

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from app.services.workflows import act_apply_decision


@workflow.defn
class ActivityProbe:
    @workflow.run
    async def run(self, entry_id: int) -> dict:
        return await workflow.execute_activity(
            act_apply_decision,
            args=[entry_id, "APPROVE", "amit", "probe"],
            start_to_close_timeout=60,
        )


async def main() -> None:
    client = await Client.connect("localhost:7233", namespace="default")
    worker = Worker(
        client,
        task_queue="probe-act-queue",
        workflows=[ActivityProbe],
        activities=[act_apply_decision],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )
    async with worker:
        import time as _t

        h = await client.start_workflow(
            ActivityProbe.run,
            999998,
            id=f"act-probe-{int(_t.time())}",
            task_queue="probe-act-queue",
        )
        try:
            res = await h.result()
            print("ACTIVITY PROBE RESULT:", res)
        except Exception as e:
            print("ACTIVITY PROBE FAILED:", type(e).__name__, str(e)[:300])


if __name__ == "__main__":
    asyncio.run(main())
