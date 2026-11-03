import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from . import admin, api, evidence, governance, portfolio, security, oversight, people
from .config import settings
from .db import engine

logger = logging.getLogger("okr.api")
app = FastAPI(
    title="OKR Enterprise API",
    version="0.1.0",
    docs_url="/api/docs" if settings().env != "production" else None,
    openapi_url="/api/openapi.json" if settings().env != "production" else None,
)
app.include_router(security.router)
app.include_router(api.router)
app.include_router(evidence.router)
app.include_router(governance.router)
app.include_router(admin.router)
app.include_router(portfolio.router)
app.include_router(oversight.router)
app.include_router(people.router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error("Unhandled request %s (%s)", request.state.request_id, type(exc).__name__)
        response = JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "服务暂不可用", "request_id": request.state.request_id})
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code, content={"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "request_id": request.state.request_id}
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    details = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422, content={"code": "VALIDATION_ERROR", "message": "输入数据不符合要求", "details": details, "request_id": request.state.request_id}
    )


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(
        status_code=409, content={"code": "CONFLICT", "message": "数据冲突或关联记录无效，请刷新后重试", "request_id": request.state.request_id}
    )


@app.exception_handler(DBAPIError)
async def database_error(request, exc):
    logger.error("Database request failed %s (%s)", request.state.request_id, type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"code": "DATABASE_UNAVAILABLE", "message": "SQL Server暂不可用，请检查连接和数据库迁移", "request_id": request.state.request_id},
    )


@app.get("/health/live")
def live():
    return {"status": "alive", "version": app.version}


@app.get("/health/ready")
@app.get("/api/status", include_in_schema=False)
def ready():
    try:
        with engine().connect() as db:
            version = db.execute(text("SELECT TOP 1 version_num FROM alembic_version")).scalar()
            if version != "0006":
                raise RuntimeError("Migration version mismatch")
        root = settings().storage_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".probe-{uuid.uuid4().hex}"
        probe.write_bytes(b"ok")
        probe.unlink()
    except Exception:
        raise HTTPException(503, "数据库迁移或存储尚未就绪") from None
    return {"status": "ready"}
