"""Consistent error envelope: {"error": {"code", "message", "request_id", "details?"}}."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("plantdoctor.errors")

CODES = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict",
         413: "payload_too_large", 415: "unsupported_media_type", 422: "validation_error",
         429: "rate_limited", 500: "internal_error", 503: "unavailable"}


class AppError(Exception):
    """Raise for expected, user-facing errors."""

    def __init__(self, status: int, message: str, code: str | None = None, details=None, headers=None):
        self.status, self.message, self.code, self.details, self.headers = status, message, code, details, headers
        super().__init__(message)


def _body(request: Request, status: int, message: str, code: str | None = None, details=None):
    err = {"code": code or CODES.get(status, "error"), "message": message,
           "request_id": getattr(request.state, "request_id", None)}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install(app: FastAPI):
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(_body(request, exc.status, exc.message, exc.code, exc.details), exc.status,
                            headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        msg = exc.detail if isinstance(exc.detail, str) else CODES.get(exc.status_code, "error")
        return JSONResponse(_body(request, exc.status_code, msg), exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body(request, 422, "Some fields are missing or invalid.", details=details), 422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(_body(request, 500, "Something went wrong on our side. Please try again."), 500)
