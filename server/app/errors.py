"""Consistent JSON error envelope: {"error": {"code", "message", "details"}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("lognexa")


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError):
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")),
                "location": err["loc"][0] if err["loc"] else None,
                "message": err["msg"].removeprefix("Value error, "),
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(_body("validation_error", "Request validation failed", details)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)))

    @app.exception_handler(SQLAlchemyError)
    async def _db(_: Request, exc: SQLAlchemyError):
        log.exception("database error", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content=_body("database_error", "The database is unavailable or returned an error. Check the server logs."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=_body("internal_error", "An unexpected server error occurred."))
