# 交易系统方案核心共识

本文档整理了两位顾问针对交易系统方案的核心共识，明确了系统的核心定位、架构设计、执行原则与红线规则，作为后续工程开发的核心指导依据。

## 一、核心定位共识
你最适合的交易模式并非「预测行情 / 赌涨跌」，而是以**结构性套利**为核心，做「规则化、工程化」的风险管理者与系统维护者，本质是利用市场结构和赌徒的错误获利（「开赌场收租」而非「当赌徒」）。

## 二、核心架构共识
### 1. 第一层：核心地基（占比 70%-80%，长期稳定收益）
- **核心策略**：资金费率 / 期限套利（Cash & Carry），方向中性（Delta Neutral）。
- **操作逻辑**：
  - 现货与永续合约对冲（如买 1 个 ETH 现货，开 1 个 ETH 空单），不看行情方向、不预测涨跌；
  - 赚取正资金费率收益（每 8 小时自动获利）；
  - 动态再平衡：监控保证金率，价格暴涨时划转 USDT 补保证金防爆仓，价格暴跌时划转盈利加仓现货复利；
- **核心特征**：允许大资金、长期持有、无需盯盘，是稳定收益的核心来源。
- **收益预期**：年化 10%-30%，低风险、几乎无回撤。

### 2. 第二层：辅助增强（占比 20%-30%，可控增量收益）
- **核心逻辑**：捕捉市场无效波动，低频、轻仓、纪律化交易，拒绝扛单 / 逆趋势。
- **具体形式**：
  - 顾问 1：反情绪、低频轻仓交易（非马丁），不逆大趋势、不连续出手、单边行情不硬做；
  - 顾问 2：趋势过滤网格（Trend-Filtered Grid），仅在震荡市（如 ADX<25）启动中性网格，价格突破网格区间立刻止损熔断。
- **风险特征**：承担连续小止损、踏空趋势的可控风险，仅作为增量收益补充。

### 3. 第三层：明确禁止的红线（永久屏蔽）
双方均明确「封印」以下策略，核心原因是不符合「可解释、可复现、低风险」的核心目标：
- ❌ 马丁格尔（Martingale）/ 加仓摊平（哪怕改良版也禁止）；
- ❌ 不止损的「高胜率策略」、高杠杆裸空 / 裸多（杠杆不超 3 倍）；
- ❌ 高频 / 情绪驱动短线、试图预测 K 线涨跌的「黑盒策略」；
- ❌ 寄望一次行情翻身的赌徒式操作。

## 三、落地执行共识
### 核心优先级
先把「资金费率套利」做成可稳定运行 3-6 个月的自动化系统，这是第一要务。

### 开发原则
1. 聚焦核心策略，不扩策略、不追新玩法、不被外界节奏影响；
2. 利用工程思维做系统抗故障设计（监控熔断、滑点、极端行情）；
3. 代码核心目标是自动化风控与套利（而非预测价格）。
```
laicai_funding_engine/
│
├─ config/                     # 🧱 唯一可改参数入口
│   ├─ account.yaml            # 子账户 / 资金比例 / 最大风险
│   ├─ instruments.yaml        # BTC / ETH
│   ├─ strategy.yaml           # 资金费率阈值 / 开关
│   └─ risk.yaml               # 熔断 / 保证金 / 深度 / 滑点
│
├─ core/                       # 🔥 系统内核（不碰交易所）
│   ├─ state_machine.py        # ⭐⭐ 状态机（系统灵魂）
│   ├─ context.py              # 当前账户 / 市场 / 系统快照
│   ├─ scheduler.py            # 8h / 1h / 5min 调度
│   └─ events.py               # 系统事件定义
│
├─ risk/                       # 🔥 第一优先级（任何策略前）
│   ├─ margin_guard.py         # 保证金 / 爆仓防护
│   ├─ fund_guard.py           # ⭐ 资金再平衡 / 自动补保证金
│   ├─ liquidity_guard.py      # 深度 / 滑点 / 插针
│   ├─ circuit_breaker.py      # 连续止损 / 日熔断
│   └─ exchange_guard.py       # 交易所异常 / API错误
│
├─ strategy/                   # 🧠 只表达“要不要做”
│   ├─ cash_and_carry.py       # ⭐ 核心策略（唯一主策略）
│   └─ conditions.py           # 开 / 平 仓条件
│
├─ execution/                  # ✋ 只负责“怎么做”
│   ├─ order_manager.py        # 原子化下单 / 撤单
│   ├─ position_manager.py     # 现货 ↔ 合约 对冲
│   └─ rebalancer.py           # 数量偏差修正
│
├─ exchange/                   # 🔌 交易所适配层
│   ├─ okx_client.py           # REST / WS 封装
│   ├─ market_data.py          # 行情 / 资金费率
│   └─ account_data.py         # 余额 / 仓位
│
├─ monitor/                    # 👀 人机接口
│   ├─ health_check.py         # 系统健康
│   ├─ pnl_tracker.py          # 非方向性 PnL
│   └─ notifier.py             # Telegram / 钉钉
│
├─ scripts/                    # 🛠 运维 & 救命
│   ├─ bootstrap.py            # 启动前自检
│   ├─ close_all.py            # 🔥 一键平仓
│   └─ dry_run.py              # 空跑
│
├─ data/                       # 📦 本地状态
│   ├─ runtime_state.json
│   ├─ trade.db                # SQLite（可选）
│   └─ logs/
│
├─ tests/                      # ✅ 不写测试不上线
│   ├─ test_state.py
│   ├─ test_risk.py
│   └─ test_execution.py
│
├─ main.py                     # ⭐ 唯一入口
└─ README.md                   # 操作手册（你自己）
```
## 四、核心身份与收益逻辑共识
- **核心身份**：不是「交易员」，而是「风险管理者 + 系统维护者」；
- **收益来源**：不是行情涨跌，而是市场结构红利 + 赌徒犯错付出的成本（资金费率、追涨杀跌的无效波动）；
- **核心特质匹配**：契合你「不想赌方向、接受慢 / 低回报、有工程思维、关注系统稳定性」的需求。

## 总结
1. 核心策略高度一致：以资金费率套利为绝对核心，网格 / 低频轻交易为辅助，拒绝一切赌徒式策略；
2. 执行原则一致：先落地核心套利系统并稳定运行 3-6 个月，聚焦工程化、自动化、低风险；
3. 核心逻辑一致：放弃行情预测，靠规则和系统赚「确定性的收租钱」，而非「赌涨跌的投机钱」。

## 实现落地
```
Phase 1: Infra
- config/*
- logs + notifier
- okx_client (read-only)

Phase 2: Safety
- close_all.py
- exchange_guard.py
- margin_guard.py
- circuit_breaker.py
- （state_machine 空壳）

Phase 3: Core
- 完整 state_machine
- context / events
- bootstrap

Phase 4: Trade
- order_manager (原子)
- cash_and_carry

Phase 5: Auto
- fund_guard
- scheduler
- pnl_tracker
```

