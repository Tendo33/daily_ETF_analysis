from __future__ import annotations

import argparse
import json

from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.llm import EtfAnalyzer
from daily_etf_analysis.providers.market_data import DataFetcherManager


def check_config() -> int:
    settings = get_settings()
    issues = settings.validate_structured()
    if not issues:
        print("Config check: OK")
        return 0
    has_error = False
    for issue in issues:
        prefix = {"error": "✗", "warning": "⚠", "info": "·"}.get(issue.severity, "?")
        print(f"{prefix} [{issue.severity.upper()}] {issue.message}")
        if issue.severity == "error":
            has_error = True
    return 1 if has_error else 0


def check_fetch(symbol: str) -> int:
    manager = DataFetcherManager(get_settings())
    bars, source = manager.get_daily_bars(symbol, days=30)
    quote, quote_source = manager.get_realtime_quote(symbol)
    print(f"Daily bars source: {source}, rows={len(bars)}")
    print(f"Realtime source: {quote_source}, quote={quote}")
    return 0


def check_llm() -> int:
    analyzer = EtfAnalyzer(get_settings())
    if not analyzer.is_available():
        print("LLM unavailable: configure LITELLM_MODEL / channels first")
        return 1
    print("LLM is configured and available.")
    print(
        json.dumps(
            {
                "litellm_model": get_settings().litellm_model,
                "fallbacks": get_settings().litellm_fallback_models,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Environment checks for daily_ETF_analysis"
    )
    parser.add_argument("--config", action="store_true", help="Validate settings")
    parser.add_argument(
        "--fetch", action="store_true", help="Run market data fetch check"
    )
    parser.add_argument("--llm", action="store_true", help="Run LLM availability check")
    parser.add_argument(
        "--symbol", default="CN:159659", help="Symbol used in --fetch mode"
    )
    args = parser.parse_args()

    if not any([args.config, args.fetch, args.llm]):
        args.config = True

    if args.config:
        rc = check_config()
        if rc != 0:
            return rc
    if args.fetch:
        rc = check_fetch(args.symbol)
        if rc != 0:
            return rc
    if args.llm:
        rc = check_llm()
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
