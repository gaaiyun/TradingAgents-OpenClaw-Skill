#!/usr/bin/env python3
"""
TradingAgents OpenClaw Skill — 多智能体交易框架的统一入口。

v2 改进
-------
- 不再依赖 `~/.openclaw/workspace/projects/TradingAgents-Official` 这样的本机
  目录布局假设。优先 `import tradingagents`（PyPI 安装），失败则 fallback 到
  纯技术信号引擎（signals.py）或 mock。
- 三种 engine：
    * "llm"     — TradingAgents 框架（需要 LLM API key）
    * "signals" — 自带的技术指标信号引擎（不需要 API key）
    * "mock"    — 用于 CI / 离线 demo

Usage
-----
>>> from __init__ import TradingAgentsSkill
>>> # 自动选 engine：装了 TradingAgents 用 llm，否则用 signals
>>> skill = TradingAgentsSkill()
>>> result = skill.analyze_stock("NVDA")
>>> # 显式指定 engine
>>> skill = TradingAgentsSkill(engine="signals")
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

# 让 sibling modules（signals.py）能被 import
sys.path.insert(0, str(Path(__file__).parent))

import signals  # noqa: E402


log = logging.getLogger(__name__)

EngineType = Literal["auto", "llm", "signals", "mock"]


# ----------------------------------------------------------------------------
# Engine 检测
# ----------------------------------------------------------------------------

def _try_import_tradingagents():
    """优先 PyPI 包；失败再试常见的本地 sibling 目录。返回 (success, error_msg)。"""
    # 1. PyPI / 已 pip install
    try:
        import tradingagents  # noqa: F401
        return True, None
    except ImportError:
        pass

    # 2. Fallback：兼容历史本地布局（projects/TradingAgents-Official）
    candidates = [
        Path(__file__).resolve().parent.parent / "TradingAgents-Official",
        Path(__file__).resolve().parent.parent.parent / "projects" / "TradingAgents-Official",
        Path.cwd() / "TradingAgents-Official",
        Path(os.environ.get("TRADING_AGENTS_HOME", "")) if os.environ.get("TRADING_AGENTS_HOME") else None,
    ]
    for p in candidates:
        if p and p.exists() and (p / "tradingagents").is_dir():
            sys.path.insert(0, str(p))
            try:
                import tradingagents  # noqa: F401
                return True, None
            except ImportError as e:
                return False, str(e)
    return False, "未找到 tradingagents 包（pip install tradingagents 或 export TRADING_AGENTS_HOME=/path/to/TradingAgents-Official）"


TRADING_AGENTS_AVAILABLE, _IMPORT_ERROR = _try_import_tradingagents()


# ----------------------------------------------------------------------------
# 主类
# ----------------------------------------------------------------------------

class TradingAgentsSkill:
    """
    Multi-engine 交易分析 skill。

    Parameters
    ----------
    config : dict, optional
        传递给 TradingAgents 框架的配置（仅 engine='llm' 时生效）。
    engine : {'auto', 'llm', 'signals', 'mock'}
        - 'auto': 优先 llm，TradingAgents 不可用时退到 signals
        - 'llm': 强制用 TradingAgents（未安装会 raise）
        - 'signals': 强制用内置技术信号引擎（不需要 LLM key）
        - 'mock': 始终返回 stub decision（用于 CI / 演示）
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        engine: EngineType = "auto",
    ) -> None:
        self.engine = self._resolve_engine(engine)
        self.config = self._build_config(config)
        self._llm_graph = None  # 懒加载
        if self.engine == "llm":
            self._load_env()

    # ---------- engine 解析 ----------

    @staticmethod
    def _resolve_engine(requested: EngineType) -> str:
        if requested == "llm":
            if not TRADING_AGENTS_AVAILABLE:
                raise ImportError(
                    f"engine='llm' 但 TradingAgents 未安装：{_IMPORT_ERROR}"
                )
            return "llm"
        if requested == "signals":
            return "signals"
        if requested == "mock":
            return "mock"
        # auto
        return "llm" if TRADING_AGENTS_AVAILABLE else "signals"

    @staticmethod
    def _build_config(user_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if TRADING_AGENTS_AVAILABLE:
            try:
                from tradingagents.default_config import DEFAULT_CONFIG  # type: ignore
                merged = DEFAULT_CONFIG.copy()
                if user_config:
                    merged.update(user_config)
                return merged
            except ImportError:
                pass
        return dict(user_config or {})

    def _load_env(self) -> None:
        """从常见位置加载 .env。"""
        try:
            from dotenv import load_dotenv
        except ImportError:
            log.debug("python-dotenv 未安装，跳过 .env 加载")
            return
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).parent / ".env",
            Path.home() / ".openclaw" / "workspace" / ".env",
        ]
        for p in candidates:
            if p.exists():
                load_dotenv(p)
                return
        load_dotenv()  # 退到系统环境

    # ---------- 主接口 ----------

    def analyze_stock(
        self,
        ticker: str,
        date: Optional[str] = None,
        max_debate_rounds: Optional[int] = None,
        llm_provider: Optional[str] = None,
        deep_think_llm: Optional[str] = None,
        quick_think_llm: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分析股票并生成交易决策。"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        if self.engine == "mock":
            return self._mock_decision(ticker, date)
        if self.engine == "signals":
            return signals.analyze_with_signals(ticker, date=date)
        # llm
        return self._llm_decide(
            ticker=ticker,
            date=date,
            max_debate_rounds=max_debate_rounds,
            llm_provider=llm_provider,
            deep_think_llm=deep_think_llm,
            quick_think_llm=quick_think_llm,
        )

    def quick_analysis(self, ticker: str, date: Optional[str] = None) -> Dict[str, Any]:
        if self.engine == "llm":
            return self.analyze_stock(
                ticker, date, max_debate_rounds=1,
                quick_think_llm=self.config.get("quick_think_llm"),
            )
        return self.analyze_stock(ticker, date)

    def deep_analysis(self, ticker: str, date: Optional[str] = None,
                      debate_rounds: int = 3) -> Dict[str, Any]:
        if self.engine == "llm":
            return self.analyze_stock(
                ticker, date, max_debate_rounds=debate_rounds,
                deep_think_llm=self.config.get("deep_think_llm"),
            )
        return self.analyze_stock(ticker, date)

    def reflect_and_remember(self, position_returns: float) -> Dict[str, Any]:
        if self.engine != "llm":
            return {"success": False, "error": "reflect_and_remember 仅在 engine='llm' 时可用"}
        self._ensure_llm_graph()
        try:
            result = self._llm_graph.reflect_and_remember(position_returns)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_config(self, key: str, value: Any) -> None:
        self.config[key] = value
        self._llm_graph = None  # 触发重建

    def get_config(self) -> Dict[str, Any]:
        return dict(self.config)

    # ---------- LLM engine 内部 ----------

    def _ensure_llm_graph(self) -> None:
        if self._llm_graph is not None:
            return
        from tradingagents.graph.trading_graph import TradingAgentsGraph  # type: ignore
        self._llm_graph = TradingAgentsGraph(debug=True, config=self.config)

    def _llm_decide(self, ticker, date, max_debate_rounds=None,
                    llm_provider=None, deep_think_llm=None, quick_think_llm=None) -> Dict[str, Any]:
        if max_debate_rounds is not None:
            self.config["max_debate_rounds"] = max_debate_rounds
        if llm_provider is not None:
            self.config["llm_provider"] = llm_provider
        if deep_think_llm is not None:
            self.config["deep_think_llm"] = deep_think_llm
        if quick_think_llm is not None:
            self.config["quick_think_llm"] = quick_think_llm

        self._ensure_llm_graph()
        try:
            state, decision = self._llm_graph.propagate(ticker, date)
        except Exception as e:
            return {"error": str(e), "ticker": ticker, "date": date, "action": "ERROR",
                    "engine": "llm"}
        return {
            "ticker": ticker,
            "date": date,
            "action": decision.get("action", "HOLD"),
            "quantity": decision.get("quantity", 0),
            "confidence": decision.get("confidence", 0.5),
            "reasoning": decision.get("reasoning", ""),
            "risk_level": decision.get("risk_level", "MEDIUM"),
            "target_price": decision.get("target_price", 0),
            "stop_loss": decision.get("stop_loss", 0),
            "engine": "llm",
            "analysis_details": {
                "fundamental_analysis": state.get("fundamental_analysis", {}),
                "technical_analysis": state.get("technical_analysis", {}),
                "sentiment_analysis": state.get("sentiment_analysis", {}),
                "news_analysis": state.get("news_analysis", {}),
                "bull_arguments": state.get("bull_arguments", []),
                "bear_arguments": state.get("bear_arguments", []),
                "risk_assessment": state.get("risk_assessment", {}),
            },
        }

    # ---------- mock ----------

    @staticmethod
    def _mock_decision(ticker: str, date: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "date": date,
            "action": "HOLD",
            "quantity": 0,
            "confidence": 0.5,
            "reasoning": "Mock decision — 用于 CI / 演示，无真实分析。设 engine='signals' 或 'llm' 拿真决策。",
            "risk_level": "UNKNOWN",
            "target_price": 0.0,
            "stop_loss": 0.0,
            "engine": "mock",
            "analysis_details": {},
        }


# ----------------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------------

def analyze(ticker: str, date: Optional[str] = None, engine: EngineType = "auto",
            **kwargs) -> Dict[str, Any]:
    """便捷函数：默认 auto-engine 分析。"""
    skill = TradingAgentsSkill(engine=engine)
    return skill.analyze_stock(ticker, date, **kwargs)


def quick_analyze(ticker: str, date: Optional[str] = None,
                  engine: EngineType = "auto") -> Dict[str, Any]:
    return TradingAgentsSkill(engine=engine).quick_analysis(ticker, date)


def deep_analyze(ticker: str, date: Optional[str] = None, debate_rounds: int = 3,
                 engine: EngineType = "auto") -> Dict[str, Any]:
    return TradingAgentsSkill(engine=engine).deep_analysis(ticker, date, debate_rounds)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="trading-agents",
                                     description="TradingAgents OpenClaw Skill")
    parser.add_argument("ticker", help="股票代码（如 NVDA, AAPL）")
    parser.add_argument("--date", "-d", default=None, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--engine", "-e", choices=["auto", "llm", "signals", "mock"],
                        default="auto")
    parser.add_argument("--mode", "-m", choices=["quick", "normal", "deep"], default="normal")
    parser.add_argument("--debate-rounds", "-r", type=int, default=None)
    parser.add_argument("--provider", "-p", default=None)
    parser.add_argument("--output", "-o", default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    skill = TradingAgentsSkill(engine=args.engine)
    if args.mode == "quick":
        result = skill.quick_analysis(args.ticker, args.date)
    elif args.mode == "deep":
        result = skill.deep_analysis(args.ticker, args.date, args.debate_rounds or 3)
    else:
        kwargs: Dict[str, Any] = {}
        if args.debate_rounds is not None:
            kwargs["max_debate_rounds"] = args.debate_rounds
        if args.provider:
            kwargs["llm_provider"] = args.provider
        result = skill.analyze_stock(args.ticker, args.date, **kwargs)

    payload = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"结果已保存到 {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
