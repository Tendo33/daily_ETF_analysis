from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.repositories.analysis_repository import AnalysisRepositoryMixin
from daily_etf_analysis.repositories.backtest_repository import BacktestRepositoryMixin
from daily_etf_analysis.repositories.config_repository import ConfigRepositoryMixin
from daily_etf_analysis.repositories.market_data_repository import (
    MarketDataRepositoryMixin,
)
from daily_etf_analysis.repositories.models import Base
from daily_etf_analysis.repositories.schema_guard import should_enforce_schema_guard


class EtfRepository(
    AnalysisRepositoryMixin,
    BacktestRepositoryMixin,
    ConfigRepositoryMixin,
    MarketDataRepositoryMixin,
):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = create_engine(self.settings.database_url, future=True)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False
        )
        self.init_db()

    def init_db(self) -> None:
        # Runtime path is Alembic-first. Keep create_all only for isolated test DBs.
        if should_enforce_schema_guard():
            return
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Any:
        db: Session = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
