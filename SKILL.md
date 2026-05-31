---
name: trading-agents
description: 当用户需要使用多智能体交易框架分析股票、获取交易信号或进行量化投资决策时使用。基于 TradingAgents 项目，提供专业的基本面分析、情绪分析、技术分析和风险管理。
---

# TradingAgents 多智能体交易框架

## 1. 什么时候用我？

当用户说：
- "分析 NVDA 股票"
- "AAPL 现在能买吗"
- "用多智能体分析 MSFT"
- "获取交易信号"
- "进行股票基本面分析"
- "技术面分析 TSLA"
- "风险评估"
- 任何需要专业量化分析的交易决策

## 2. 我能做什么？

### 核心功能
- **多智能体协作分析**：模拟真实交易公司的团队决策流程
- **基本面分析**：评估公司财务和业绩指标
- **情绪分析**：分析社交媒体和公众情绪
- **新闻分析**：监控全球新闻和宏观经济指标
- **技术分析**：使用 MACD、RSI 等技术指标
- **多空辩论**：牛市和熊市研究员进行结构化辩论
- **风险管理**：评估市场波动性、流动性等风险因素
- **交易决策**：生成买入/卖出/持有建议

### 支持的 LLM 提供商
- OpenAI (GPT-5.x, GPT-4.x)
- Google (Gemini 3.x, 2.x)
- Anthropic (Claude 4.x, 3.x)
- xAI (Grok 4.x)
- OpenRouter
- Ollama (本地模型)

### 数据源
- yfinance（默认，无需 API key）
- Alpha Vantage（需要 API key）

## 3. 快速使用

### 3.1 基本用法
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 初始化
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 分析股票
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

### 3.2 自定义配置
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"     # 复杂推理模型
config["quick_think_llm"] = "gpt-5-mini" # 快速任务模型
config["max_debate_rounds"] = 2          # 辩论轮数

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("AAPL", "2024-05-10")
```

### 3.3 配置数据源
```python
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # alpha_vantage, yfinance
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}
```

## 4. 配置 API Keys

### 方法 1：环境变量
```bash
export OPENAI_API_KEY=...          # OpenAI
export GOOGLE_API_KEY=...          # Google
export ANTHROPIC_API_KEY=...       # Anthropic
export XAI_API_KEY=...             # xAI
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

### 方法 2：.env 文件
在 `~/.openclaw/workspace/.env` 添加：
```
OPENAI_API_KEY=sk-...
ALPHA_VANTAGE_API_KEY=...
```

## 5. 智能体架构

### 分析团队
| 智能体 | 职责 |
|--------|------|
| Fundamentals Analyst | 评估公司财务和内在价值 |
| Sentiment Analyst | 分析社交媒体情绪评分 |
| News Analyst | 监控全球新闻和宏观指标 |
| Technical Analyst | 技术指标分析（MACD, RSI） |

### 研究团队
- **Bull Researcher**：牛市观点，寻找上涨机会
- **Bear Researcher**：熊市观点，识别潜在风险

### 交易团队
- **Trader**：综合报告，做出交易决策
- **Risk Manager**：评估和调整风险
- **Portfolio Manager**：最终审批交易

## 6. 输出示例

```python
{
    "ticker": "NVDA",
    "date": "2024-05-10",
    "action": "BUY",
    "quantity": 100,
    "confidence": 0.75,
    "reasoning": "基本面强劲，AI 需求增长，技术面突破...",
    "risk_level": "MEDIUM",
    "target_price": 950.00,
    "stop_loss": 800.00
}
```

## 7. 文件结构

本 Skill 自身（signals engine 开箱即用，不依赖外部目录布局）：

```
TradingAgents-OpenClaw-Skill/
├── __init__.py             # TradingAgentsSkill + CLI（多 engine 路由）
├── signals.py              # 本地技术信号引擎（无需 API key）
├── requirements.txt
├── tests/                  # pytest（合成数据，无网络）
├── example_usage.py        # 端到端示例
└── SKILL.md                # 本文件
```

启用 LLM engine 时另需 TradingAgents 框架（PyPI 包或本地 clone）：

```
tradingagents/              # pip install tradingagents 后可直接 import
├── agents/                 # 智能体定义
├── dataflows/              # 数据流
├── graph/                  # LangGraph 流程
└── default_config.py       # 默认配置
```

## 8. 本地运行

### signals engine（无需 API key）
```bash
pip install -r requirements.txt
python __init__.py NVDA --engine signals
```

### LLM engine（需要 TradingAgents + API key）
```bash
pip install tradingagents
export OPENAI_API_KEY=sk-...
# 若为本地 clone，可改用环境变量指向：
#   export TRADING_AGENTS_HOME=/path/to/TradingAgents-Official
python __init__.py NVDA --engine llm
```

## 9. 在 OpenClaw 中使用

### 示例对话
```
用户：分析一下 NVDA 股票
助手：正在用 TradingAgents 多智能体框架分析 NVDA……
     [基本面分析师] 公司财务表现强劲
     [技术分析师] MACD 金叉，RSI 处于健康区间
     [风险管理] 波动性中等，建议控制仓位
     综合建议：BUY，目标价 $950，止损 $800
```

## 10. 注意事项

⚠️ **重要声明**：
- 本框架仅供研究使用
- 不构成投资建议
- 交易表现受多种因素影响（模型、温度、数据质量等）
- 请勿用于真实交易决策，除非你完全理解风险

## 11. 依赖

```txt
langgraph>=0.2.0
langchain>=0.3.0
openai>=1.0.0
google-generativeai>=0.8.0
anthropic>=0.40.0
yfinance>=0.2.40
alpha-vantage>=3.0.0
pandas>=2.0.0
numpy>=1.24.0
python-dotenv>=1.0.0
```

## 12. 参考资料

- **论文**: [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)
- **GitHub**: https://github.com/TauricResearch/TradingAgents
- **Discord**: https://discord.com/invite/hk9PGKShPK
- **技术报告**: [Trading-R1](https://arxiv.org/abs/2509.11420)
