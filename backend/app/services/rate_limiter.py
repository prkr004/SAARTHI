"""Simple in-memory defensive rate limiting helpers."""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

_BUCKETS: dict[tuple[str, str], deque[float]] = {}
_BUCKET_LOCK = Lock()


def allow_request(scope: str, actor_key: str, *, max_requests: int, window_seconds: int) -> bool:
    """Return True when request is allowed under a fixed-window rolling check."""

    now = time.time()
    threshold = now - float(window_seconds)
    bucket_key = (scope, actor_key)

    with _BUCKET_LOCK:
        queue = _BUCKETS.setdefault(bucket_key, deque())
        while queue and queue[0] < threshold:
            queue.popleft()

        if len(queue) >= max_requests:
            return False

        queue.append(now)
        return True
