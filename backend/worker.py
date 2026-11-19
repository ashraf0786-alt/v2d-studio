"""Redis queue worker: `python -m worker` (set REDIS_URL)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from app.config import settings
from app.jobs import execute, execute_url
from app.queue import PRIORITIES, get_redis
from app.storage import get_local_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("v2d.worker")


def main() -> None:
    if settings.queue_backend != "redis":
        raise SystemExit("Set REDIS_URL (or QUEUE_BACKEND=redis) before starting the worker")
    redis = get_redis()
    log.info("worker_ready", extra={"queues": PRIORITIES})
    while True:
        did_work = False
        for priority in PRIORITIES:
            item = redis.brpop(f"v2d:jobs:{priority}", timeout=1)
            if not item:
                continue
            payload = json.loads(item[1])
            try:
                if payload.get("kind") == "url":
                    execute_url(payload["job_id"], payload["user_id"], payload["mode"],
                                payload["url"], payload.get("headers", {}), payload["params"])
                    did_work = True
                    break
                input_path = Path(payload["input_path"])
                if not input_path.exists():
                    fetched = get_local_path(payload["user_id"], payload["job_id"],
                                             payload["input_filename"])
                    if not fetched:
                        raise RuntimeError("Input file unavailable (check shared storage/S3)")
                    input_path = fetched
                execute(payload["job_id"], payload["user_id"], payload["mode"],
                        input_path, payload["params"])
            except Exception:
                log.exception("worker_job_failed", extra={"job_id": payload.get("job_id")})
            did_work = True
            break
        if not did_work:
            time.sleep(0.2)


if __name__ == "__main__":
    main()
