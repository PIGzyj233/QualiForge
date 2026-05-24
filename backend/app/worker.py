from __future__ import annotations

import asyncio
import concurrent.futures
import logging

from redis.asyncio import Redis
from temporalio.client import Client
from temporalio.worker import Worker

from app.agents.activities import (
    execute_agent_child_task_activity,
    execute_agent_graph_activity,
    mark_agent_run_cancelled_activity,
    mark_agent_run_failed_activity,
)
from app.agents.workflows import AgentChildTaskWorkflow, AgentRunWorkflow
from app.platform.config import get_settings
from app.platform.telemetry import configure_telemetry


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("qualiforge.worker")


async def run_worker() -> None:
    settings = get_settings()
    configure_telemetry(settings)
    logger.info("QualiForge worker started in %s environment", settings.environment)
    if not settings.agent_execute_sync_mode:
        await asyncio.gather(run_heartbeat(settings), run_temporal_worker(settings))
        return

    await run_heartbeat(settings)


async def run_heartbeat(settings) -> None:
    while True:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.set("qualiforge:worker:last_heartbeat", "ok", ex=settings.worker_heartbeat_seconds * 3)
            logger.info("Worker heartbeat recorded")
        except Exception:
            logger.exception("Worker heartbeat failed")
        finally:
            await client.aclose()

        await asyncio.sleep(settings.worker_heartbeat_seconds)


async def run_temporal_worker(settings) -> None:
    logger.info("Starting Temporal worker on %s queue %s", settings.temporal_address, settings.agent_task_queue)
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as activity_executor:
        worker = Worker(
            client,
            task_queue=settings.agent_task_queue,
            workflows=[AgentRunWorkflow, AgentChildTaskWorkflow],
            activities=[
                execute_agent_child_task_activity,
                execute_agent_graph_activity,
                mark_agent_run_cancelled_activity,
                mark_agent_run_failed_activity,
            ],
            activity_executor=activity_executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
