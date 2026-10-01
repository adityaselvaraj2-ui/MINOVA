"""Dump the WorkflowTaskFailed cause + message for a workflow id."""
import asyncio
import sys

from temporalio.client import Client


async def main() -> None:
    wid = sys.argv[1]
    client = await Client.connect("localhost:7233", namespace="default")
    handle = client.get_workflow_handle(wid)
    hist = await handle.fetch_history()
    for e in hist.events:
        et = e.WhichOneof("attributes")
        if et == "workflow_task_failed_event_attributes":
            a = e.workflow_task_failed_event_attributes
            print("CAUSE:", a.cause)
            f = a.failure
            print("FAILURE MSG:", (f.message or "")[:500])
            print("STACK:", (f.stack_trace or "")[:800])
            if f.cause and f.cause.message:
                print("INNER:", (f.cause.message or "")[:500])


if __name__ == "__main__":
    asyncio.run(main())
