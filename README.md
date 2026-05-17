# TradingAgents OpenClaw Skill

> 一个**三引擎**的股票分析 Skill：装了就能跑，没 LLM key 也能用，CI 友好。

把 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（多 LLM agent 辩论交易决策框架）包装成统一接口。v2 加了两件**别处没有**的事：

1. **本地技术信号引擎**（`signals.py`）—— 不调 LLM、不需要 API key、就靠 yfinance + numpy 给可解释的交易信号。
2. **三档 engine**（auto / llm / signals / mock）—— 装了 TradingAgents 用 LLM，没装自动降级到 signals，CI 用 mock。

## 快速开始

```bash
pip install -r requirements.txt
```

### 1) 不需要 API key 的"立刻能跑"

```python
from __init__ import TradingAgentsSkill

skill = TradingAgentsSkill(engine="signals")   # 强制用本地信号引擎
result = skill.analyze_stock("NVDA")
print(result["action"], result["confidence"])
print(result["reasoning"])
```

或者 CLI：

```bash
python __init__.py NVDA --engine signals
```

### 2) 需要 LLM 时启用 TradingAgents

```bash
pip install tradingagents
export OPENAI_API_KEY=sk-...
python __init__.py NVDA --engine llm
```

> **注**：`tradingagents` 在 PyPI 上的版本 / 包名以官方仓库为准。如果是 dev 版本本地 clone 的，也可以：
> ```bash
> export TRADING_AGENTS_HOME=/path/to/TradingAgents-Official
> ```
> Skill 会自动加到 sys.path。

### 3) CI / 演示用 mock

```python
result = TradingAgentsSkill(engine="mock").analyze_stock("AAPL")
# 返回 stub decision，不联网、不调 LLM
```

## 输出统一 schema

不管哪个 engine，都返回相同结构：

```json
{
  "ticker": "NVDA",
  "date": "2024-05-10",
  "action": "BUY" | "SELL" | "HOLD" | "ERROR",
  "confidence": 0.78,
  "reasoning": "...",
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "target_price": 1234.5,
  "stop_loss": 1100.0,
  "engine": "llm" | "signals-v2" | "mock",
  "analysis_details": { ... }
}
```

UI / 上层调用方一套代码就能消费三种 engine。

## signals.py 在做什么

| 指标 | 用法 |
|---|---|
| RSI(14) Wilder | 超买/超卖 |
| MACD(12,26,9) | 金叉/死叉 |
| Bollinger(20, 2σ) | 短期超买/超卖 |
| MA stack(20/50/200) | 多头/空头排列 |
| OBV 5d slope | 资金净流入/出 |
| ATR(14) | 动态止损（默认 2×ATR） |

每个指标都附带 `bullish / bearish / neutral` 判断和文字 rationale，加权投票得最终 action + 置信度。结果可以直接喂给 LLM 做"上下文摘要"——所以即使你之后接上 TradingAgents，这套数据也不会浪费。

## 文件清单

```
.
├─ __init__.py            # TradingAgentsSkill + CLI（多 engine 路由）
├─ signals.py             # 本地技术信号引擎（v2 新增）
├─ requirements.txt
├─ tests/
│   ├─ test_signals.py        # 13 个指标 + 聚合测试
│   └─ test_skill_engines.py  # 8 个 engine 路由 + mock 测试
├─ example_usage.py       # 端到端示例
├─ SKILL.md               # OpenClaw 描述
└─ _meta.json             # OpenClaw metadata
```

## v2 修了什么

- 不再硬编码 `~/.openclaw/workspace/projects/TradingAgents-Official` 路径假设
- 优先 `import tradingagents`（PyPI），失败再 fallback 到本地路径 + `TRADING_AGENTS_HOME` 环境变量
- 不再要求 LLM key 才能 import skill（之前没装 TradingAgents 就 raise）
- 加 21 个 pytest 测试（v1 是手动验证脚本）
- README 去掉本机绝对路径

## 路线图

- 实时数据源切换（akshare / alpaca / polygon）
- 期权希腊值与隐含波动率
- 多 ticker 批量扫描 CLI（`--batch tickers.txt`）

## 许可

MIT
