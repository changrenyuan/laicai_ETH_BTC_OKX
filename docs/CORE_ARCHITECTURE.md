# 核心架构文档

## 📖 概述
本项目借鉴 Hummingbot 的成熟架构，实现了核心的执行器和风控系统。

---

## 🏗️ 架构分层

```
┌─────────────────────────────────────────────────┐
│              策略层 (Strategy)                   │
│  MultiTrendStrategy, FundStrategy, etc.        │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│         执行器编排层 (Orchestrator)              │
│  ExecutorOrchestrator                           │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│         执行器层 (Executor)                      │
│  OrderExecutor, PositionExecutor                │
│  DCAExecutor, TWAPExecutor, GridExecutor        │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│          风控层 (Risk Management)                │
│  TripleBarrier, TrailingStop                    │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│          交易所层 (Exchange)                     │
│  ExchangeBase, RateLimiter, TimeSynchronizer    │
└─────────────────────────────────────────────────┘
```

---

## 📦 核心模块

### 1. ExchangeBase（交易所基类）

**文件**：`exchange/base.py`

**职责**：
- 统一的交易所接口
- API 频率限制
- 时间同步
- 错误处理

**核心接口**：
```python
class ExchangeBase:
    async def place_order(self, data: Dict) -> Tuple[bool, str, str]
    async def cancel_order(self, order_id: str, symbol: str) -> Tuple[bool, str, str]
    async def get_order_status(self, order_id: str, symbol: str) -> Optional[Dict]
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict]
    async def get_ticker(self, symbol: str) -> Optional[Dict]
    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict]
```

**使用示例**：
```python
exchange = OKXExchange(config)
await exchange.connect()

# 下单
success, order_id, error = await exchange.place_order({
    "symbol": "ETH-USDT-SWAP",
    "side": "buy",
    "size": 0.1,
    "type": "limit",
    "price": 2000.0
})

# 获取持仓
positions = await exchange.get_positions("ETH-USDT-SWAP")
```

---

### 2. RateLimiter（API 频率限制器）

**文件**：`core/rate_limiting/rate_limiter.py`

**算法**：Token Bucket

**职责**：
- 防止 API 限流
- 自动排队
- 多端点限流

**使用示例**：
```python
# 初始化
rate_limiter = RateLimiter({
    "strategy": "token_bucket",
    "default_capacity": 10,
    "default_refill_rate": 1.0,
    "rules": {
        "/api/v5/trade/order": {
            "capacity": 20,
            "refill_rate": 2.0
        }
    }
})

# 使用
await rate_limiter.acquire("/api/v5/trade/order")
```

---

### 3. TimeSynchronizer（时间同步器）

**文件**：`core/time_synchronizer.py`

**职责**：
- 同步交易所服务器时间
- 计算时间偏移
- 防止时间戳错误

**使用示例**：
```python
time_sync = TimeSynchronizer(sync_interval=60)

# 启动
await time_sync.start(get_server_time_func=exchange.get_server_time)

# 获取同步时间
server_time = await time_sync.get_server_time()
```

---

### 4. ExecutorBase（执行器基类）

**文件**：`core/executor/executor_base.py`

**职责**：
- 执行器生命周期管理
- 事件发布
- Triple Barrier 集成

**状态机**：
```
IDLE → RUNNING → COMPLETED
                 → FAILED
                 → CANCELLED
```

**使用示例**：
```python
from core.executor.executor_base import ExecutorConfig

config = ExecutorConfig(
    exchange=exchange,
    symbol="ETH-USDT-SWAP",
    side="buy",
    size=0.1,
    price=2000.0,
    stop_price=1950.0,
    take_profit_price=2100.0
)

executor = OrderExecutor(config)
await executor.start()
```

---

### 5. OrderExecutor（单订单执行器）

**文件**：`core/executor/order_executor.py`

**职责**：
- 执行单个订单
- 监控订单状态
- 更新填充信息

**支持的订单类型**：
- `limit`：限价单
- `market`：市价单
- `post_only`：只挂单
- `ioc`：立即成交或取消
- `fok`：全部成交或取消

---

### 6. PositionExecutor（持仓执行器）

**文件**：`core/executor/position_executor.py`

**职责**：
- 执行多个订单
- 支持多种执行策略

**支持的策略**：

#### 6.1 DCAExecutor（定投）
```python
dca_executor = DCAExecutor(
    config=config,
    num_orders=5,
    time_interval=60
)
```

#### 6.2 TWAPExecutor（时间加权平均）
```python
twap_executor = TWAPExecutor(
    config=config,
    duration=300,
    num_orders=10
)
```

#### 6.3 GridExecutor（网格）
```python
grid_executor = GridExecutor(
    config=config,
    grid_upper=2100.0,
    grid_lower=1900.0,
    grid_count=10
)
```

---

### 7. TripleBarrier（三重风控框架）

**文件**：`core/risk/triple_barrier.py`

**职责**：
- 止盈（Upper Barrier）
- 止损（Lower Barrier）
- 时间限制（Time Barrier）

**使用示例**：
```python
triple_barrier = TripleBarrier(
    take_profit_price=2100.0,
    stop_loss_price=1950.0,
    time_limit_seconds=3600
)

triple_barrier.activate()

# 检查风控
action = triple_barrier.check(current_price, current_time)
if action == BarrierAction.STOP_LOSS:
    # 触发止损
    pass
```

---

### 8. TrailingStop（移动止损）

**文件**：`core/risk/trailing_stop.py`

**职责**：
- 动态调整止损位
- 锁定利润

**支持的模式**：
- `percentage`：基于百分比
- `fixed_amount`：基于固定金额
- `atr`：基于 ATR
- `volatility`：基于波动率

**使用示例**：
```python
trailing_stop = TrailingStop(
    mode="percentage",
    activation_distance=0.02,  # 2%
    trailing_distance=0.01,     # 1%
    side="long"
)

trailing_stop.activate(entry_price=2000.0)

# 更新
is_triggered, stop_price, reason = trailing_stop.update(current_price)
```

---

### 9. ExecutorOrchestrator（执行器编排器）

**文件**：`core/executor/orchestrator.py`

**职责**：
- 管理多个执行器
- 并发控制
- 执行器协调

**使用示例**：
```python
orchestrator = ExecutorOrchestrator(max_concurrent_executors=10)

# 添加执行器
executor = orchestrator.create_order_executor(
    exchange=exchange,
    symbol="ETH-USDT-SWAP",
    side="buy",
    size=0.1,
    price=2000.0
)
orchestrator.add_executor(executor)

# 启动
await orchestrator.start()

# 查询状态
status = orchestrator.get_orchestrator_status()
```

---

## 🔄 工作流程

### 典型的交易流程

```
1. 策略生成信号
   ↓
2. 创建 Executor 配置
   ↓
3. 创建 Executor 实例
   ↓
4. 添加到 Orchestrator
   ↓
5. Orchestrator 启动 Executor
   ↓
6. Executor 执行订单
   ↓
7. Triple Barrier 监控风控
   ↓
8. 触发止盈/止损/完成
   ↓
9. 发布事件
   ↓
10. 更新持仓和账户
```

---

## 📊 事件系统

**支持的事件类型**：
- `EXECUTOR_START`：执行器启动
- `EXECUTOR_COMPLETED`：执行器完成
- `EXECUTOR_FAILED`：执行器失败
- `EXECUTOR_CANCELLED`：执行器取消
- `ORDER_CREATED`：订单创建
- `ORDER_FILLED`：订单成交

**使用示例**：
```python
def on_event(event):
    print(f"Event: {event.type}, Data: {event.data}")

executor.add_event_listener(on_event)
```

---

## 🎯 设计原则

1. **单一职责**：每个类只负责一件事
2. **开闭原则**：对扩展开放，对修改关闭
3. **依赖倒置**：依赖抽象而非具体实现
4. **接口隔离**：使用最小化接口
5. **组合优于继承**：优先使用组合

---

## 🚀 下一步计划

1. **重构 OKX Exchange**：继承 ExchangeBase
2. **创建 Controller 架构**：策略控制器
3. **增强事件系统**：更多事件类型
4. **UI 界面开发**：Next.js + shadcn/ui
