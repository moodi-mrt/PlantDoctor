"""Small in-process sliding-window rate limiter.

Good for a single-process deployment (the MVP). For several workers / hosts, swap the store for
Redis — the `hit()` interface stays the same.
"""
import threading
import time
from collections import defaultdict, deque

from .errors import AppError

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def hit(key: str, limit: int, window_s: int, message: str = "Too many requests. Please wait and try again."):
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_s - (now - q[0])) + 1
            raise AppError(429, message, headers={"Retry-After": str(retry)}, details={"retry_after_s": retry})
        q.append(now)


def reset():
    with _lock:
        _hits.clear()


def client_ip(request) -> str:
    # Behind a reverse proxy, uvicorn --proxy-headers sets request.client from X-Forwarded-For.
    return request.client.host if request.client else "unknown"
