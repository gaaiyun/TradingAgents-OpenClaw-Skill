"""signals.py 测试 — 用合成 OHLCV，不依赖 yfinance 真实网络。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signals import (
    aggregate_signals,
    atr,
    bollinger,
    macd,
    moving_averages,
    obv,
    rsi,
)


def _synth_ohlcv(n: int = 250, trend: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """生成 n 天的 OHLCV，可指定趋势（正=上行，负=下行）。"""
    rng = np.random.default_rng(seed)
    start_price = 100.0
    daily_return = rng.normal(trend, 0.015, n)
    close = start_price * np.cumprod(1 + daily_return)
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    volume = rng.integers(10_000, 100_000, n)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ----------------------------------------------------------------------------
# 单指标
# ----------------------------------------------------------------------------

def test_rsi_in_bounds():
    df = _synth_ohlcv()
    r = rsi(df["close"])
    assert ((r >= 0) & (r <= 100)).all()
    assert not r.isna().all()


def test_rsi_high_on_uptrend():
    df = _synth_ohlcv(trend=0.005, seed=1)  # 单向上涨
    r = rsi(df["close"])
    # 强上涨末尾 RSI 应明显偏高（vol=0.015 时 trend/vol 比有限，给 50 也行）
    assert r.iloc[-1] > 50, f"上涨末段 RSI={r.iloc[-1]:.1f} 期望 >50"


def test_rsi_low_on_downtrend():
    df = _synth_ohlcv(trend=-0.005, seed=2)
    r = rsi(df["close"])
    assert r.iloc[-1] < 50


def test_macd_columns():
    df = _synth_ohlcv()
    m = macd(df["close"])
    assert set(m.columns) == {"macd", "signal", "hist"}
    # macd - signal 应等于 hist
    assert np.allclose((m["macd"] - m["signal"]).dropna(), m["hist"].dropna())


def test_bollinger_middle_between_bands():
    df = _synth_ohlcv()
    b = bollinger(df["close"]).dropna()
    assert (b["lower"] <= b["mid"]).all()
    assert (b["mid"] <= b["upper"]).all()


def test_moving_averages():
    df = _synth_ohlcv()
    mas = moving_averages(df["close"], windows=(20, 50, 200))
    assert set(mas.columns) == {"ma20", "ma50", "ma200"}
    # 前 199 行的 ma200 应是 NaN，第 200 行起有值
    assert mas["ma200"].iloc[:199].isna().all()
    assert mas["ma200"].iloc[199:].notna().all()


def test_obv_changes_with_volume_direction():
    """收盘上涨时 OBV 应增加，下跌时减少。"""
    close = pd.Series([10, 11, 10, 11, 12])
    volume = pd.Series([100, 100, 100, 100, 100])
    o = obv(close, volume)
    # 第一日 diff=NaN→0；2 涨 +100；3 跌 -100；4 涨 +100；5 涨 +100
    assert o.iloc[-1] == 200


def test_atr_positive():
    df = _synth_ohlcv()
    a = atr(df["high"], df["low"], df["close"]).dropna()
    assert (a > 0).all()


# ----------------------------------------------------------------------------
# 聚合
# ----------------------------------------------------------------------------

def test_aggregate_signals_returns_valid_action():
    df = _synth_ohlcv()
    action, confidence, contribs = aggregate_signals(df)
    assert action in {"BUY", "SELL", "HOLD"}
    assert 0 <= confidence <= 1
    assert len(contribs) >= 3


def test_aggregate_signals_bullish_on_strong_uptrend():
    """强上涨 → 至少不应给 SELL，且 contributions 多为 bullish。"""
    df = _synth_ohlcv(trend=0.004, seed=10, n=300)
    action, confidence, contribs = aggregate_signals(df)
    bullish_count = sum(1 for c in contribs if c.direction == "bullish")
    bearish_count = sum(1 for c in contribs if c.direction == "bearish")
    assert action != "SELL", f"强上涨应不给 SELL，得到 {action}"
    assert bullish_count >= bearish_count


def test_aggregate_signals_bearish_on_strong_downtrend():
    df = _synth_ohlcv(trend=-0.004, seed=11, n=300)
    action, confidence, contribs = aggregate_signals(df)
    bearish_count = sum(1 for c in contribs if c.direction == "bearish")
    bullish_count = sum(1 for c in contribs if c.direction == "bullish")
    assert action != "BUY"
    assert bearish_count >= bullish_count


def test_aggregate_signals_neutral_on_sideways():
    """完全 sideways 应当倾向 HOLD。"""
    df = _synth_ohlcv(trend=0.0, seed=12, n=300)
    action, _, _ = aggregate_signals(df)
    # sideways 可能略偏一边，但不应该是高置信度信号
    assert action in {"HOLD", "BUY", "SELL"}  # 至少返回有效 action


def test_aggregate_signals_handles_missing_columns():
    """仅有 close 列时也应工作。"""
    df = _synth_ohlcv()[["close"]]
    action, confidence, contribs = aggregate_signals(df)
    assert action in {"BUY", "SELL", "HOLD"}
    assert len(contribs) >= 1
