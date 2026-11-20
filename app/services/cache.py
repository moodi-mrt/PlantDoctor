"""SQLite-backed TTL cache for external API responses.

Every cached value is returned wrapped with its source name and fetch time so the UI can
always show "Source · updated <time>".
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..db import ApiCache, SessionLocal

log = logging.getLogger("plantdoctor.cache")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cached(key: str, source: str, ttl_s: int, fetch: Callable[[], dict], allow_stale=True) -> dict:
    """Return {"data", "source", "fetched_at", "cached", "stale"}.

    On a fetch error a stale value is served (flagged) if one exists; otherwise the error propagates.
    """
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        row = s.get(ApiCache, key)
        if row and _aware(row.expires_at) > now:
            return {"data": row.value, "source": row.source, "fetched_at": _aware(row.fetched_at).isoformat(),
                    "cached": True, "stale": False}
        try:
            value = fetch()
        except Exception as e:
            if row and allow_stale:
                log.warning("fetch failed for %s (%s); serving stale copy", key, e)
                return {"data": row.value, "source": row.source, "fetched_at": _aware(row.fetched_at).isoformat(),
                        "cached": True, "stale": True}
            raise
        if row is None:
            row = ApiCache(key=key)
            s.add(row)
        row.source, row.value, row.fetched_at, row.expires_at = source, value, now, now + timedelta(seconds=ttl_s)
        s.commit()
        return {"data": value, "source": source, "fetched_at": now.isoformat(), "cached": False, "stale": False}


def purge_expired(older_than_days: int = 7):
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    with SessionLocal() as s:
        n = s.query(ApiCache).filter(ApiCache.expires_at < cutoff).delete()
        s.commit()
        return n
