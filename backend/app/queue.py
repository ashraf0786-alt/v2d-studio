"""Redis-backed durable job queue and progress bridge."""
from __future__ import annotations

import json
from pathlib import Path

from .config import settings

PRIORITIES = (3, 2, 1, 0)
_client = None


def get_redis():  # pragma: no cover - requires a Redis server
    global _client
    if _client is None:
        import redis
        _client = redis.from_url(settings.REDIS_URL)
    return _client


def enqueue(job_id: str, user_id: int, mode: str, input_path: Path, params: dict,
            priority: int = 0) -> None:  # pragma: no cover
    priority = int(priority) if int(priority) in PRIORITIES else 0
    payload = json.dumps({
        "job_id": job_id, "user_id": user_id, "mode": mode,
        "input_path": str(input_path), "input_filename": Path(input_path).name,
        "params": params,
    })
    get_redis().lpush(f"v2d:jobs:{priority}", payload)


def publish(event: dict) -> None:  # pragma: no cover
    get_redis().publish("v2d:progress", json.dumps(event))


async def bridge_progress(hub) -> None:  # pragma: no cover
    """Forward worker progress events from Redis into the API's local event hub."""
    import asyncio
    import redis.asyncio as aioredis
    client = aioredis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe("v2d:progress")
    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                event = json.loads(message["data"])
                event["from_redis"] = True
                hub.publish(event.get("job_id", ""), event)
        except Exception:
            await asyncio.sleep(1.0)
        await asyncio.sleep(0.01)
