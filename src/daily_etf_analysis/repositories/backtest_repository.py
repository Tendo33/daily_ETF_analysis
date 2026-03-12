from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select

from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.repositories.models import (
    BacktestResultORM,
    BacktestRunORM,
    EtfAnalysisReportORM,
    EtfDailyBarORM,
)
from daily_etf_analysis.repositories.shared import float_or_none


class BacktestRepositoryMixin:
    def session(self) -> Any:
        raise NotImplementedError

    def create_backtest_run(
        self, eval_window_days: int, symbols: list[str], disclaimer: str
    ) -> str:
        run_id = utc_now_naive().strftime("%Y%m%d%H%M%S%f")
        with self.session() as db:
            db.add(
                BacktestRunORM(
                    run_id=run_id,
                    eval_window_days=eval_window_days,
                    symbols_json=json.dumps([s.upper() for s in symbols]),
                    disclaimer=disclaimer,
                )
            )
        return run_id

    def update_backtest_run_summary(
        self,
        run_id: str,
        total_samples: int,
        evaluated_samples: int,
        skipped_count: int,
        direction_hit_rate: float | None,
        avg_return: float | None,
        max_drawdown: float | None,
        win_rate: float | None,
    ) -> None:
        with self.session() as db:
            row = db.execute(
                select(BacktestRunORM).where(BacktestRunORM.run_id == run_id)
            ).scalar_one()
            row.total_samples = total_samples
            row.evaluated_samples = evaluated_samples
            row.skipped_count = skipped_count
            row.direction_hit_rate = direction_hit_rate
            row.avg_return = avg_return
            row.max_drawdown = max_drawdown
            row.win_rate = win_rate

    def save_backtest_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        with self.session() as db:
            db.query(BacktestResultORM).filter(
                BacktestResultORM.run_id == run_id
            ).delete()
            for item in results:
                db.add(
                    BacktestResultORM(
                        run_id=run_id,
                        symbol=str(item.get("symbol", "")).upper(),
                        trade_date=item.get("trade_date"),
                        sample_count=int(item.get("sample_count", 0)),
                        evaluated_count=int(item.get("evaluated_count", 0)),
                        skipped_count=int(item.get("skipped_count", 0)),
                        direction_hit_rate=float_or_none(
                            item.get("direction_hit_rate")
                        ),
                        avg_return=float_or_none(item.get("avg_return")),
                        max_drawdown=float_or_none(item.get("max_drawdown")),
                        win_rate=float_or_none(item.get("win_rate")),
                        details_json=json.dumps(
                            item.get("details", {}), ensure_ascii=False
                        ),
                    )
                )

    def get_backtest_run(self, run_id: str) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute(
                select(BacktestRunORM).where(BacktestRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "run_id": row.run_id,
                "eval_window_days": row.eval_window_days,
                "symbols": json.loads(row.symbols_json),
                "total_samples": row.total_samples,
                "evaluated_samples": row.evaluated_samples,
                "skipped_count": row.skipped_count,
                "direction_hit_rate": row.direction_hit_rate,
                "avg_return": row.avg_return,
                "max_drawdown": row.max_drawdown,
                "win_rate": row.win_rate,
                "disclaimer": row.disclaimer,
                "created_at": row.created_at.isoformat(),
            }

    def get_latest_backtest_run(self) -> dict[str, Any] | None:
        with self.session() as db:
            row = (
                db.execute(
                    select(BacktestRunORM).order_by(desc(BacktestRunORM.created_at))
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return {
                "run_id": row.run_id,
                "eval_window_days": row.eval_window_days,
                "symbols": json.loads(row.symbols_json),
                "total_samples": row.total_samples,
                "evaluated_samples": row.evaluated_samples,
                "skipped_count": row.skipped_count,
                "direction_hit_rate": row.direction_hit_rate,
                "avg_return": row.avg_return,
                "max_drawdown": row.max_drawdown,
                "win_rate": row.win_rate,
                "disclaimer": row.disclaimer,
                "created_at": row.created_at.isoformat(),
            }

    def get_backtest_results(self, run_id: str) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = (
                db.execute(
                    select(BacktestResultORM)
                    .where(BacktestResultORM.run_id == run_id)
                    .order_by(BacktestResultORM.symbol)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "symbol": row.symbol,
                    "trade_date": row.trade_date.isoformat()
                    if row.trade_date is not None
                    else None,
                    "sample_count": row.sample_count,
                    "evaluated_count": row.evaluated_count,
                    "skipped_count": row.skipped_count,
                    "direction_hit_rate": row.direction_hit_rate,
                    "avg_return": row.avg_return,
                    "max_drawdown": row.max_drawdown,
                    "win_rate": row.win_rate,
                    "details": json.loads(row.details_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def get_backtest_symbol_performance(
        self, run_id: str, symbol: str
    ) -> dict[str, Any] | None:
        normalized = symbol.upper()
        with self.session() as db:
            row = (
                db.execute(
                    select(BacktestResultORM)
                    .where(
                        BacktestResultORM.run_id == run_id,
                        BacktestResultORM.symbol == normalized,
                    )
                    .order_by(desc(BacktestResultORM.created_at))
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return {
                "symbol": row.symbol,
                "sample_count": row.sample_count,
                "evaluated_count": row.evaluated_count,
                "skipped_count": row.skipped_count,
                "direction_hit_rate": row.direction_hit_rate,
                "avg_return": row.avg_return,
                "max_drawdown": row.max_drawdown,
                "win_rate": row.win_rate,
            }

    def get_backtest_signals(self, symbols: list[str]) -> list[dict[str, Any]]:
        normalized_symbols = [s.upper() for s in symbols]
        if not normalized_symbols:
            return []
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfAnalysisReportORM)
                    .where(EtfAnalysisReportORM.symbol.in_(normalized_symbols))
                    .order_by(
                        EtfAnalysisReportORM.symbol,
                        EtfAnalysisReportORM.trade_date,
                        EtfAnalysisReportORM.id,
                    )
                )
                .scalars()
                .all()
            )
            return [
                {
                    "symbol": row.symbol,
                    "trade_date": row.trade_date,
                    "action": row.action,
                }
                for row in rows
            ]

    def get_price_series(self, symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
        normalized_symbols = [s.upper() for s in symbols]
        if not normalized_symbols:
            return {}
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfDailyBarORM)
                    .where(EtfDailyBarORM.symbol.in_(normalized_symbols))
                    .order_by(EtfDailyBarORM.symbol, EtfDailyBarORM.trade_date)
                )
                .scalars()
                .all()
            )
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(row.symbol, []).append(
                    {"trade_date": row.trade_date, "close": row.close}
                )
            return grouped
