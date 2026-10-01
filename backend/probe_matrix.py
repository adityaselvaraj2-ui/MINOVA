"""Isolation matrix: which combination triggers BadScheduleActivityAttributes?"""
import asyncio
import time

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker


@activity.defn
async def plain_activity(x: int) -> int:
    return x * 2


@activity.defn
async def decorated_activity(x: int) -> int:
    return x * 3


@workflow.defn
class WfPlainSandboxed:
    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            plain_activity, x, start_to_close_timeout=30
        )


@workflow.defn
class WfDecoratedSandboxed:
    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            decorated_activity, x, start_to_close_timeout=30
        )


@workflow.defn
class WfPlainUnsandboxed:
    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            plain_activity, x, start_to_close_timeout=30
        )


@workflow.defn
class WfDecoratedUnsandboxed:
    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            decorated_activity, x, start_to_close_timeout=30
        )


async def main() -> None:
    client = await Client.connect("localhost:7233", namespace="default")
    cases = [
        ("plain+sandboxed", WfPlainSandboxed, [plain_activity], None),
        ("decorated+sandboxed", WfDecoratedSandboxed, [decorated_activity], None),
        ("plain+unsandboxed", WfPlainUnsandboxed, [plain_activity], UnsandboxedWorkflowRunner()),
        ("decorated+unsandboxed", WfDecoratedUnsandboxed, [decorated_activity], UnsandboxedWorkflowRunner()),
    ]
    for name, wf_cls, acts, runner in cases:
        kwargs = {}
        if runner is not None:
            kwargs["workflow_runner"] = runner
        worker = Worker(
            client,
            task_queue=f"q-{name}",
            workflows=[wf_cls],
            activities=acts,
            **kwargs,
        )
        tag = f"iso-{name}-{int(time.time())}"
        try:
            async with worker:
                h = await client.start_workflow(
                    wf_cls.run, 21, id=tag, task_queue=f"q-{name}"
                )
                res = await asyncio.wait_for(h.result(), timeout=45)
                print(f"CASE {name}: OK -> {res}")
        except Exception as e:
            print(f"CASE {name}: FAIL -> {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
