from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from daily_etf_analysis.api.v1.router import router as v1_router
from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.observability import inc_api_request, render_metrics_text

app = FastAPI(
    title="daily_ETF_analysis API",
    version="0.1.0",
    description="ETF intelligent analysis service for CN/HK/US markets.",
)


@app.middleware("http")
async def request_tracking_middleware(request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID", "").strip() or uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    inc_api_request(
        method=request.method,
        path=request.url.path,
        status=response.status_code,
    )
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/metrics")
def metrics() -> PlainTextResponse:
    settings = get_settings()
    if not settings.metrics_enabled:
        return PlainTextResponse(content="metrics disabled", status_code=404)
    return PlainTextResponse(content=render_metrics_text(), media_type="text/plain")


app.include_router(v1_router)
