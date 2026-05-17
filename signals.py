"""
内置技术信号引擎 — 不依赖 TradingAgents / LLM 也能给出可解释的交易信号。

为什么有这个模块？
-----------------
v1 的这个 Skill 完全依赖 TauricResearch/TradingAgents 框架（需要 OpenAI/
Anthropic key + 大量 LLM 调用 + langgraph）。在以下场景里这套很重：
- 用户只是想看一只股票的常规指标
- CI / 测试环境没有 API key
- 想做小规模批量扫描，不想烧 LLM 钱

这个模块用 yfinance 抓 OHLCV，本地算 RSI / MACD / 布林带 / MA 交叉 / OBV
等指标，给出**带置信度的交易信号**——是"轻量决策树"而不是 LLM agent。

输出和 TradingAgents 兼容
-----------------------
返回 dict 的 schema 与 `__init__.TradingAgentsSkill.analyze_stock` 输出
一致（action / confidence / reasoning / risk_level / target_price /
stop_loss / analysis_details），方便上层 UI 一套代码同时消费。
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# 数据加载（yfinance 可选）
# ----------------------------------------------------------------------------

def load_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    用 yfinance 拉 OHLCV。失败时 raise，由调用方决定降级。

    Returns
    -------
    DataFrame[date, open, high, low, close, volume]，按日期升序。
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError(
            "需要 yfinance：pip install yfinance"
        ) from e

    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        raise ValueError(f"yfinance 未返回 {ticker} 的数据")
    # yfinance 在某些版本下返回 MultiIndex columns，flatten 一下
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df = df.reset_index().rename(columns={"date": "date", "datetime": "date"})
    # 保证至少有 close/volume
    if "close" not in df.columns or "volume" not in df.columns:
        raise ValueError(f"yfinance 返回的列不符合预期：{list(df.columns)}")
    return df.sort_values("date").reset_index(drop=True)


# ----------------------------------------------------------------------------
# 技术指标
# ----------------------------------------------------------------------------

def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    # 用 Wilder smoothing（EMA with alpha=1/window）
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line})


def bollinger(close: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    return pd.DataFrame({
        "mid": mid,
        "upper": mid + n_std * std,
        "lower": mid - n_std * std,
    })


def moving_averages(close: pd.Series, windows=(20, 50, 200)) -> pd.DataFrame:
    return pd.DataFrame({f"ma{w}": close.rolling(w).mean() for w in windows})


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume — 资金流方向指标。"""
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).cumsum()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range — 用于止损 / 仓位 sizing。"""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False).mean()


# ----------------------------------------------------------------------------
# 信号聚合
# ----------------------------------------------------------------------------

@dataclass
class SignalContribution:
    indicator: str
    value: float
    direction: str   # 'bullish' / 'bearish' / 'neutral'
    weight: float
    rationale: str


def aggregate_signals(df: pd.DataFrame) -> Tuple[str, float, List[SignalContribution]]:
    """
    把多个技术指标的最后一日信号汇总成一个交易方向 + 置信度。

    Returns
    -------
    action : 'BUY' / 'SELL' / 'HOLD'
    confidence : 0~1
    contributions : 每个指标的解释（用于 reasoning）
    """
    close = df["close"]
    high = df.get("high", close)
    low = df.get("low", close)
    volume = df.get("volume", pd.Series([np.nan] * len(df)))

    contribs: List[SignalContribution] = []

    # RSI（超买/超卖）
    rsi_val = rsi(close).iloc[-1]
    if rsi_val < 30:
        contribs.append(SignalContribution("RSI", float(rsi_val), "bullish", 1.0,
                                           "RSI<30 超卖，常见反弹信号"))
    elif rsi_val > 70:
        contribs.append(SignalContribution("RSI", float(rsi_val), "bearish", 1.0,
                                           "RSI>70 超买，常见回调信号"))
    else:
        contribs.append(SignalContribution("RSI", float(rsi_val), "neutral", 0.3,
                                           f"RSI={rsi_val:.1f}，中性区间"))

    # MACD（金叉/死叉 + 柱状图方向）
    m = macd(close).iloc[-1]
    if m["macd"] > m["signal"] and m["hist"] > 0:
        contribs.append(SignalContribution("MACD", float(m["hist"]), "bullish", 1.0,
                                           "MACD 上穿信号线且柱状图正，趋势上行"))
    elif m["macd"] < m["signal"] and m["hist"] < 0:
        contribs.append(SignalContribution("MACD", float(m["hist"]), "bearish", 1.0,
                                           "MACD 下穿信号线且柱状图负，趋势下行"))
    else:
        contribs.append(SignalContribution("MACD", float(m["hist"]), "neutral", 0.3,
                                           "MACD 与信号线交叉中，方向不明"))

    # MA 排列
    mas = moving_averages(close, windows=(20, 50, 200)).iloc[-1]
    price = close.iloc[-1]
    if not mas.isna().any():
        if price > mas["ma20"] > mas["ma50"] > mas["ma200"]:
            contribs.append(SignalContribution("MA-stack", float(price), "bullish", 1.2,
                                               "价格在 MA20>MA50>MA200 上方，多头排列"))
        elif price < mas["ma20"] < mas["ma50"] < mas["ma200"]:
            contribs.append(SignalContribution("MA-stack", float(price), "bearish", 1.2,
                                               "价格在 MA20<MA50<MA200 下方，空头排列"))
        else:
            contribs.append(SignalContribution("MA-stack", float(price), "neutral", 0.3,
                                               "MA 排列纠缠，趋势不明"))

    # Bollinger 位置
    bb = bollinger(close).iloc[-1]
    if not pd.isna(bb["upper"]):
        if price >= bb["upper"]:
            contribs.append(SignalContribution("Bollinger", float(price), "bearish", 0.8,
                                               "价格触及/突破上轨，短期超买"))
        elif price <= bb["lower"]:
            contribs.append(SignalContribution("Bollinger", float(price), "bullish", 0.8,
                                               "价格触及/跌破下轨，短期超卖"))
        else:
            contribs.append(SignalContribution("Bollinger", float(price), "neutral", 0.2,
                                               "价格位于布林带中部"))

    # OBV 趋势（5 日斜率）
    if volume.notna().any():
        o = obv(close, volume.fillna(0))
        if len(o) >= 6:
            slope = o.iloc[-1] - o.iloc[-6]
            if slope > 0:
                contribs.append(SignalContribution("OBV", float(slope), "bullish", 0.6,
                                                   "近 5 日 OBV 上升，资金净流入"))
            elif slope < 0:
                contribs.append(SignalContribution("OBV", float(slope), "bearish", 0.6,
                                                   "近 5 日 OBV 下降，资金净流出"))
            else:
                contribs.append(SignalContribution("OBV", 0.0, "neutral", 0.2, "OBV 横盘"))

    # 聚合：加权投票
    score = 0.0
    total_weight = 0.0
    for c in contribs:
        s = {"bullish": 1, "bearish": -1, "neutral": 0}[c.direction]
        score += s * c.weight
        total_weight += c.weight

    normalized = score / total_weight if total_weight > 0 else 0.0  # -1 ~ +1
    if normalized >= 0.35:
        action = "BUY"
    elif normalized <= -0.35:
        action = "SELL"
    else:
        action = "HOLD"
    confidence = min(abs(normalized), 1.0)
    return action, float(confidence), contribs


# ----------------------------------------------------------------------------
# 顶层 API
# ----------------------------------------------------------------------------

def analyze_with_signals(ticker: str, date: Optional[str] = None,
                         period: str = "1y") -> Dict:
    """
    用纯技术信号引擎给出交易决策（不调 LLM、不需要 API key）。

    Returns
    -------
    与 TradingAgentsSkill.analyze_stock 兼容的 dict。
    """
    df = load_ohlcv(ticker, period=period)
    if date:
        cutoff = pd.to_datetime(date)
        df = df[df["date"] <= cutoff].reset_index(drop=True)
        if len(df) < 50:
            raise ValueError(f"{ticker} 在 {date} 之前的数据不足（仅 {len(df)} 行）")

    action, confidence, contributions = aggregate_signals(df)

    close = df["close"].iloc[-1]
    atr_now = atr(df["high"], df["low"], df["close"]).iloc[-1] if "high" in df else close * 0.02
    target_price = close * (1 + 0.06 * (1 if action == "BUY" else -1 if action == "SELL" else 0))
    stop_loss = close - 2.0 * atr_now * (1 if action == "BUY" else -1 if action == "SELL" else 0)

    bull = [c for c in contributions if c.direction == "bullish"]
    bear = [c for c in contributions if c.direction == "bearish"]
    reasoning = (
        f"基于 {len(contributions)} 个技术指标聚合（多头 {len(bull)} / 空头 {len(bear)} / "
        f"中性 {len(contributions) - len(bull) - len(bear)}），加权得分 {confidence:.2f}。\n"
        + "\n".join(f"- {c.indicator}: {c.direction} ({c.rationale})" for c in contributions)
    )

    risk_level = "HIGH" if confidence < 0.4 else ("MEDIUM" if confidence < 0.7 else "LOW")

    return {
        "ticker": ticker,
        "date": date or _dt.datetime.now().strftime("%Y-%m-%d"),
        "action": action,
        "quantity": 0,                # 让上层根据账户资金决定
        "confidence": confidence,
        "reasoning": reasoning,
        "risk_level": risk_level,
        "target_price": float(target_price),
        "stop_loss": float(stop_loss),
        "engine": "signals-v2",       # 区分于 TradingAgents LLM 决策
        "analysis_details": {
            "current_price": float(close),
            "atr_14d": float(atr_now),
            "contributions": [c.__dict__ for c in contributions],
            "bull_arguments": [c.rationale for c in bull],
            "bear_arguments": [c.rationale for c in bear],
        },
    }
