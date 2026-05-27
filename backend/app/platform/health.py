from datetime import timedelta

from redis.asyncio import Redis
from temporalio.client import Client

from app.platform.config import Settings


AGENT_WORKER_HEARTBEAT_KEY = "qualiforge:agent_worker:last_heartbeat"
LEGACY_WORKER_HEARTBEAT_KEY = "qualiforge:worker:last_heartbeat"


async def check_redis(settings: Settings) -> dict[str, str]:
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    try:
        await client.ping()
    except Exception as exc:  # pragma: no cover - exact driver failures vary by environment
        return {"status": "unavailable", "detail": exc.__class__.__name__}
    finally:
        await client.aclose()

    return {"status": "ok", "detail": "reachable"}


async def check_temporal(settings: Settings) -> dict[str, str]:
    if settings.agent_execute_sync_mode:
        return {"status": "skipped", "detail": "agent execute sync mode is enabled"}

    try:
        client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
        healthy = await client.service_client.check_health(timeout=timedelta(seconds=2))
    except Exception as exc:  # pragma: no cover - exact SDK/network failures vary by environment
        return {"status": "unavailable", "detail": exc.__class__.__name__}

    if not healthy:
        return {"status": "unavailable", "detail": "health check returned false"}
    return {
        "status": "ok",
        "detail": "reachable",
        "address": settings.temporal_address,
        "namespace": settings.temporal_namespace,
    }


async def check_agent_worker(settings: Settings) -> dict[str, str | int]:
    if settings.agent_execute_sync_mode:
        return {"status": "skipped", "detail": "agent execute sync mode is enabled"}

    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    try:
        ttl = await client.ttl(AGENT_WORKER_HEARTBEAT_KEY)
        if ttl > 0:
            return {"status": "ok", "detail": "heartbeat fresh", "key": AGENT_WORKER_HEARTBEAT_KEY, "ttl_seconds": ttl}

        legacy_ttl = await client.ttl(LEGACY_WORKER_HEARTBEAT_KEY)
        if legacy_ttl > 0:
            return {
                "status": "ok",
                "detail": "legacy heartbeat fresh",
                "key": LEGACY_WORKER_HEARTBEAT_KEY,
                "ttl_seconds": legacy_ttl,
            }
    except Exception as exc:  # pragma: no cover - exact driver failures vary by environment
        return {"status": "unavailable", "detail": exc.__class__.__name__}
    finally:
        await client.aclose()

    return {"status": "unavailable", "detail": "heartbeat missing", "key": AGENT_WORKER_HEARTBEAT_KEY}
