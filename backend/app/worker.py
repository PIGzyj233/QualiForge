from __future__ import annotations

import asyncio

from app.agent_worker import run_agent_worker, run_heartbeat, run_temporal_worker


async def run_worker() -> None:
    """Compatibility shim for the old `python -m app.worker` entrypoint."""
    await run_agent_worker()


if __name__ == "__main__":
    asyncio.run(run_worker())


__all__ = ["run_agent_worker", "run_heartbeat", "run_temporal_worker", "run_worker"]
