from __future__ import annotations

from fastapi import FastAPI

from daily_etf_analysis.api.v1.router import router as v1_router

app = FastAPI(
    title="daily_ETF_analysis API",
    version="0.1.0",
    description="ETF intelligent analysis service for CN/HK/US markets.",
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(v1_router)
