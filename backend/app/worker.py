from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

from app.config import get_settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("qualiforge.worker")


async def run_worker() -> None:
    settings = get_settings()
    logger.info("QualiForge worker started in %s environment", settings.environment)

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


if __name__ == "__main__":
    asyncio.run(run_worker())

