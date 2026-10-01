"""Sanity probe: does wait_condition(timeout=3) really take ~3s on this box?"""
import asyncio
import time

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker


@workflow.defn
class TimerProbe:
    def __init__(self):
        self.fired = False

    @workflow.run
    async def run(self) -> bool:
        try:
            await workflow.wait_condition(lambda: self.fired, timeout=3)
            return False
        except TimeoutError:
            return True


async def main() -> None:
    client = await Client.connect("localhost:7233", namespace="default")
    worker = Worker(client, task_queue="probe-queue", workflows=[TimerProbe])
    async with worker:
        h = await client.start_workflow(
            TimerProbe.run, id="timer-probe-2", task_queue="probe-queue"
        )
        t0 = time.monotonic()
        fired = await h.result()
        print(f"TIMER PROBE: fired={fired} elapsed={time.monotonic()-t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
