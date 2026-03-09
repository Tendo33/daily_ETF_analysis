from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class RunAnalysisRequest(BaseModel):
    symbols: list[str] | None = None
    markets: list[str] | None = None
    force_refresh: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: str
    symbols: list[str]
    force_refresh: bool
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class RunAnalysisResponse(BaseModel):
    task_id: str
    status: str


class ReplaceEtfsRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class ReplaceIndexMappingsRequest(BaseModel):
    mappings: dict[str, list[str]]


class DailyReportQuery(BaseModel):
    date: date
    market: str = "all"
