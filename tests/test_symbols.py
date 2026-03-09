from daily_etf_analysis.domain import (
    Market,
    infer_market,
    normalize_symbol,
    split_symbol,
)


def test_normalize_symbol_with_prefix() -> None:
    assert normalize_symbol("cn:159659") == "CN:159659"
    assert normalize_symbol("US:qqq") == "US:QQQ"


def test_normalize_symbol_without_prefix() -> None:
    assert normalize_symbol("159659") == "CN:159659"
    assert normalize_symbol("02800") == "HK:02800"
    assert normalize_symbol("QQQ") == "US:QQQ"


def test_infer_market_and_split() -> None:
    assert infer_market("NDX") == Market.INDEX
    market, code = split_symbol("US:QQQ")
    assert market == Market.US
    assert code == "QQQ"
