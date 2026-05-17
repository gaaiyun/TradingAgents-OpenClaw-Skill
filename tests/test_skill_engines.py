"""__init__.py 中 TradingAgentsSkill 的 engine 路由测试。"""
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 用 importlib 而不是 from __init__ import（因 __init__.py 在仓库根没有 package 结构）
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "skill_module", Path(__file__).resolve().parents[1] / "__init__.py"
)
skill_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_module)
TradingAgentsSkill = skill_module.TradingAgentsSkill


def test_engine_auto_falls_back_to_signals_if_no_tradingagents():
    """没有 tradingagents 包时，auto 应当退到 signals。"""
    with patch.object(skill_module, "TRADING_AGENTS_AVAILABLE", False):
        s = TradingAgentsSkill(engine="auto")
        assert s.engine == "signals"


def test_engine_llm_raises_when_unavailable():
    with patch.object(skill_module, "TRADING_AGENTS_AVAILABLE", False):
        with pytest.raises(ImportError):
            TradingAgentsSkill(engine="llm")


def test_engine_signals_works_offline_via_mock_ohlcv():
    """signals engine：用 mock 的 OHLCV 数据跑 analyze_stock 不应炸。"""
    # 给 signals.load_ohlcv 打 mock，返回合成数据
    import numpy as np
    rng = np.random.default_rng(0)
    n = 250
    close = 100 * np.cumprod(1 + rng.normal(0.001, 0.015, n))
    fake = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": close * (1 + np.abs(rng.normal(0, 0.005, n))),
        "low": close * (1 - np.abs(rng.normal(0, 0.005, n))),
        "close": close,
        "volume": rng.integers(10_000, 100_000, n),
    })

    with patch.object(skill_module.signals, "load_ohlcv", return_value=fake):
        s = TradingAgentsSkill(engine="signals")
        result = s.analyze_stock("NVDA")
    assert result["ticker"] == "NVDA"
    assert result["action"] in {"BUY", "SELL", "HOLD"}
    assert 0 <= result["confidence"] <= 1
    assert "reasoning" in result
    assert result["engine"] == "signals-v2"


def test_engine_mock_returns_stub():
    s = TradingAgentsSkill(engine="mock")
    result = s.analyze_stock("ANYTHING", date="2024-05-10")
    assert result["engine"] == "mock"
    assert result["action"] == "HOLD"
    assert result["ticker"] == "ANYTHING"


def test_quick_deep_analyze_delegate_correctly():
    s = TradingAgentsSkill(engine="mock")
    quick = s.quick_analysis("AAPL")
    deep = s.deep_analysis("AAPL", debate_rounds=2)
    assert quick["engine"] == "mock"
    assert deep["engine"] == "mock"


def test_set_get_config():
    s = TradingAgentsSkill(engine="mock")
    s.set_config("test_key", "test_value")
    assert s.get_config()["test_key"] == "test_value"


def test_reflect_unavailable_when_not_llm():
    s = TradingAgentsSkill(engine="signals")
    r = s.reflect_and_remember(0.1)
    assert r["success"] is False
    assert "engine='llm'" in r["error"]


def test_convenience_analyze():
    """analyze() 顶层函数应当 work。"""
    result = skill_module.analyze("TSLA", engine="mock")
    assert result["ticker"] == "TSLA"
    assert result["engine"] == "mock"
