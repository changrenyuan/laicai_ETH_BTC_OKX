# 待办任务清单（保留 Runtime 完整版）

## 🔥 当前状态
- 已回退到 `cda56b3 (ddd)` 版本
- Runtime 保持完整（包含所有交易流程）
- ✅ **核心架构重构完成**（借鉴 Hummingbot）
- 丢失的功能：需要重新实现

---

## ✅ 已完成任务

### P0 - 核心架构重构（借鉴 Hummingbot）

#### ✅ ExchangeBase - 交易所基类
- ✅ 创建 `exchange/base.py`
- ✅ 统一的交易所接口（订单管理、账户管理、持仓管理、行情数据）
- ✅ 集成 Rate Limiting
- ✅ 集成 Time Synchronizer
- ✅ 统一的 API 请求方法（包含错误处理）

#### ✅ Rate Limiting - API 频率限制器
- ✅ 创建 `core/rate_limiting/rate_limiter.py`
- ✅ 实现 Token Bucket 算法
- ✅ 支持多端点限流
- ✅ 支持动态限流规则

#### ✅ Time Synchronizer - 时间同步器
- ✅ 创建 `core/time_synchronizer.py`
- ✅ 定期同步交易所服务器时间
- ✅ 计算时间偏移
- ✅ 提供同步后的时间戳

#### ✅ Executor - 执行器架构
- ✅ 创建 `core/executor/executor_base.py`（执行器基类）
- ✅ 创建 `core/executor/order_executor.py`（单订单执行器）
- ✅ 创建 `core/executor/position_executor.py`（持仓执行器）
  - ✅ DCAExecutor（定投）
  - ✅ TWAPExecutor（时间加权平均）
  - ✅ GridExecutor（网格）
- ✅ 创建 `core/executor/orchestrator.py`（执行器编排器）
- ✅ 集成 Triple Barrier 风控
- ✅ 支持事件系统

#### ✅ Triple Barrier - 三重风控框架
- ✅ 创建 `core/risk/triple_barrier.py`
- ✅ 止盈（Upper Barrier）
- ✅ 止损（Lower Barrier）
- ✅ 时间限制（Time Barrier）
- ✅ 集成移动止损（Trailing Stop）

#### ✅ Trailing Stop - 移动止损
- ✅ 创建 `core/risk/trailing_stop.py`
- ✅ 基于百分比的移动止损
- ✅ 基于固定金额的移动止损
- ✅ 基于 ATR 的移动止损
- ✅ 支持多模式（long/short）

---

## 📋 待办任务列表

### 1. 核心功能恢复

#### 1.1 MultiTrendStrategyV2（V2 策略）- **高优先级**
- [ ] 重新创建 `strategy/multi_trend_strategy_v2.py`
- [ ] 实现多周期分析（15m/1H 定方向 + 5m 回踩）
- [ ] 实现限价单入场（而非市价追涨）
- [ ] 实现结构性止损（基于 ATR）
- [ ] 实现移动止盈逻辑

#### 1.2 PositionSizer（仓位计算器）- **高优先级**
- [ ] 重新创建 `core/position_sizer.py`
- [ ] 实现统一仓位计算逻辑
- [ ] 支持风险控制（每个仓位 2% 风险）
- [ ] 支持杠杆计算
- [ ] 支持合约面值（ctVal）处理

#### 1.3 PrivateWS（私有 WebSocket）- **中优先级**
- [ ] 重新创建 `private_ws/private_ws_client.py`
- [ ] 实现私有频道订阅（账户、持仓、订单）
- [ ] 实现实时成交回调
- [ ] 实现 FillEvent 事件发布

#### 1.4 FillEvent（成交事件）- **中优先级**
- [ ] 重新创建 `core/fill_event.py`
- [ ] 定义成交事件结构
- [ ] 实现事件发布机制

#### 1.5 TradeRecorder（交易记录）- **中优先级**
- [ ] 重新创建 `persistence/trade_recorder.py`
- [ ] 实现成交记录持久化（CSV）
- [ ] 实现交易审计日志

---

### 2. 优化改进

#### 2.1 FundGuard 修复 - **高优先级**
- [ ] 修复 `fund_guard` 误报"资金账户没钱"的问题
- [ ] 小资金策略（< 100U）完全禁用自动划转

#### 2.2 MarginGuard 优化 - **中优先级**
- [ ] 小资金策略（< 100U）跳过保证金率检查

#### 2.3 Context 优化 - **中优先级**
- [ ] 修复 `margin_ratio` 初始化问题

---

### 3. UI 界面开发

#### 3.1 技术选型
**推荐方案**：Next.js + shadcn/ui

**理由**：
- ✅ 现代、美观的 UI 组件库
- ✅ 快速开发，支持实时 WebSocket 更新
- ✅ 可以在浏览器访问，方便远程查看
- ✅ 适合展示交易系统的仪表盘
- ✅ 支持响应式设计

**备选方案**：
- Streamlit（最快，但定制性差）
- PyQt5/PySide6（本地应用，适合个人使用）

#### 3.2 UI 功能需求
- [ ] 实时行情展示（K线图、价格）
- [ ] 持仓管理（当前持仓、盈亏、止损止盈）
- [ ] 订单管理（挂单、历史订单）
- [ ] 账户信息（余额、保证金率）
- [ ] 系统状态（运行状态、日志）
- [ ] 策略控制（启动/停止、参数调整）

#### 3.3 UI 开发任务
- [ ] 初始化 Next.js 项目
- [ ] 安装 shadcn/ui 组件库
- [ ] 设计页面布局（Dashboard）
- [ ] 实现后端 API（WebSocket/HTTP）
- [ ] 实现前端组件
- [ ] 实现实时数据更新（WebSocket）

---

### 4. 测试与验证

#### 4.1 单元测试
- [ ] 测试 V2 策略信号生成
- [ ] 测试 PositionSizer 仓位计算
- [ ] 测试 PrivateWS 连接与订阅
- [ ] 测试 TradeRecorder 持久化

#### 4.2 集成测试
- [ ] 测试完整交易流程
- [ ] 测试限价单执行
- [ ] 测试止损止盈触发

---

### 5. 文档更新

- [ ] 更新 README.md
- [ ] 更新架构文档
- [ ] 更新 API 文档
- [ ] 更新部署文档

---

## 🎯 优先级排序

1. **P0（立即执行）**：
   - FundGuard 修复
   - UI 界面开发（Next.js + shadcn/ui）

2. **P1（本周完成）**：
   - PositionSizer
   - MultiTrendStrategyV2

3. **P2（下周完成）**：
   - PrivateWS
   - FillEvent
   - TradeRecorder

4. **P3（后续迭代）**：
   - 测试与验证
   - 文档更新

---

## 📝 备注

### 为什么保留 Runtime 完整版？
- Runtime 包含完整的交易流程（Scanner → Regime → Strategy → Portfolio → Risk → Execution → Analytics）
- 拆分为事件驱动版本后，很多功能无法正常工作
- 完整版更容易理解和调试

### 为什么选择 Web UI？
- 可以远程访问（不需要在同一台机器）
- 更容易团队协作
- 可以展示实时数据（WebSocket）
- 可以做数据可视化（图表）

### 技术栈建议

**后端（Python）**：
- FastAPI（提供 HTTP API）
- WebSocket（实时数据推送）
- SQLAlchemy（数据库 ORM，如果需要）

**前端（Next.js + shadcn/ui）**：
- Next.js 14+（App Router）
- shadcn/ui（UI 组件库）
- Recharts（图表库）
- Socket.io-client（WebSocket 客户端）

---

## 🔗 相关链接

- [shadcn/ui 官网](https://ui.shadcn.com/)
- [Next.js 官网](https://nextjs.org/)
- [Recharts 官网](https://recharts.org/)
- [Socket.io 官网](https://socket.io/)
