# TradingAgents Skill 快速入门

本 Skill 有三档 engine：`signals`（本地技术信号，开箱即用，无需 API key）、
`llm`（TradingAgents 多智能体框架，需要 API key）、`mock`（CI / 演示）。
下面从最省事的 signals 开始。

## 1. 安装

```bash
pip install -r requirements.txt
```

signals engine 只依赖 numpy / pandas / yfinance，装完即可用。

## 2. 立刻能跑（signals engine，无需 API key）

命令行：

```bash
python __init__.py NVDA --engine signals
python __init__.py AAPL --engine signals --mode quick
```

Python：

```python
from __init__ import TradingAgentsSkill

skill = TradingAgentsSkill(engine="signals")
result = skill.analyze_stock("NVDA")
print(f"建议：{result['action']}")
print(f"置信度：{result['confidence']:.0%}")
print(f"理由：{result['reasoning']}")
```

## 3. 启用 LLM engine（需要 TradingAgents + API key）

```bash
pip install tradingagents
export OPENAI_API_KEY=sk-your-api-key-here
python __init__.py NVDA --engine llm --mode deep --debate-rounds 3
```

若用本地 clone 的 TradingAgents（未发布到 PyPI 的 dev 版），用环境变量指路：

```bash
export TRADING_AGENTS_HOME=/path/to/TradingAgents-Official
```

获取 API Key：

- OpenAI: https://platform.openai.com/api-keys
- Google: https://makersuite.google.com/app/apikey
- Anthropic: https://console.anthropic.com/settings/keys

## 4. 理解输出

三档 engine 返回同一套 schema：

```json
{
  "action": "BUY",
  "confidence": 0.75,
  "reasoning": "...",
  "risk_level": "MEDIUM",
  "target_price": 950.00,
  "stop_loss": 800.00,
  "engine": "signals-v2"
}
```

## 5. 常见配置（仅 llm engine 生效）

```python
skill = TradingAgentsSkill(engine="llm")
skill.set_config("llm_provider", "anthropic")     # 或 google / xai
skill.set_config("max_debate_rounds", 3)          # 辩论轮数，越多越慢越深
skill.set_config("deep_think_llm", "gpt-5.2")     # 强模型
skill.set_config("quick_think_llm", "gpt-5-mini") # 快模型
```

## 6. 常见问题

**导入错误 "No module named 'tradingagents'"**：未装 TradingAgents 时这是预期的——
auto engine 会自动降级到 signals。需要 LLM 决策时执行 `pip install tradingagents`，
或设 `TRADING_AGENTS_HOME` 指向本地 clone。

**LLM engine 慢**：多智能体多轮辩论本身耗时。用 `--mode quick`、减少
`max_debate_rounds`、或换更快的 `quick_think_llm`。

**signals engine 报数据不足**：某些标的历史不足 50 个交易日，换标的或缩短
分析截止日期。

## 7. 下一步

- 完整说明见 [README.md](README.md)
- 功能细节见 [SKILL.md](SKILL.md)
- 端到端示例见 [example_usage.py](example_usage.py)
- 框架论文：[TradingAgents](https://arxiv.org/abs/2412.20138)

## 重要提醒

TradingAgents / signals 都是研究工具，不构成投资建议，不保证交易表现，使用风险自负。
