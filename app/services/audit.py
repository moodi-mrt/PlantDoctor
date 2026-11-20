"""Append-only audit trail for security-relevant actions."""
import logging

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from ..db import AuditEvent

log = logging.getLogger("plantdoctor.audit")


def record(db: DBSession, request: Request | None, action: str, actor_id: int | None = None,
           target_type: str | None = None, target_id=None, commit: bool = True, **meta):
    ev = AuditEvent(actor_id=actor_id, action=action, target_type=target_type,
                    target_id=str(target_id) if target_id is not None else None,
                    ip=(request.client.host if request and request.client else None),
                    request_id=getattr(request.state, "request_id", None) if request else None, meta=meta)
    db.add(ev)
    if commit:
        db.commit()
    log.info("audit %s actor=%s target=%s:%s", action, actor_id, target_type, target_id)
