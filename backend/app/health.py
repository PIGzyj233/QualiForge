from redis.asyncio import Redis

from app.config import Settings


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
