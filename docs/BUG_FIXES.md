# Bug 修复记录

## 🔥 严重问题修复（2025-01-XX）

### 1. ✅ TokenBucket 同步阻塞问题

**问题描述**：
- `TokenBucket.wait_for_token` 使用了 `time.sleep`（同步阻塞）
- 会锁死整个 Python 事件循环
- 导致行情更新、订单监控全部停止

**修复方案**：
- 移除同步的 `wait_for_token` 方法
- 只保留异步版本 `RateLimiter._wait_for_token`（使用 `asyncio.sleep`）

**影响文件**：
- `core/rate_limiting/rate_limiter.py`

---

### 2. ✅ TripleBarrier 方向感缺失

**问题描述**：
- `_check_stop_loss` 只支持 Long（`current_price <= stop_price`）
- Short 时会误触发止损
- 移动止损逻辑也没有区分 Long/Short

**修复方案**：
- 添加 `side` 参数（`long`/`short`）
- 根据方向判断止盈止损条件：
  - Long：止盈 `>=`，止损 `<=`
  - Short：止盈 `<=`，止损 `>=`
- 移动止损也根据方向调整

**影响文件**：
- `core/risk/triple_barrier.py`
- `core/executor/executor_base.py`（传递 side 参数）

**示例**：
```python
# Long（做多）
triple_barrier = TripleBarrier(
    take_profit_price=2100.0,  # 价格 >= 2100 触发止盈
    stop_loss_price=1950.0,    # 价格 <= 1950 触发止损
    side="long"
)

# Short（做空）
triple_barrier = TripleBarrier(
    take_profit_price=1950.0,  # 价格 <= 1950 触发止盈
    stop_loss_price=2100.0,    # 价格 >= 2100 触发止损
    side="short"
)
```

---

### 3. ✅ DCAExecutor 填充计算重复累加

**问题描述**：
- `_monitor_order` 中每次循环都执行 `self.filled_size += filled_size`
- `filled_size` 是订单的累计成交量
- 导致成交量被重复计算

**错误示例**：
```
第 1 次查询：filled_size = 0.05，self.filled_size = 0.05 ✅
第 2 次查询：filled_size = 0.05，self.filled_size = 0.10 ❌（错误！）
第 3 次查询：filled_size = 0.05，self.filled_size = 0.15 ❌（错误！）
```

**修复方案**：
- 记录上次成交数量 `last_filled_size`
- 只计算增量：`filled_increment = filled_size - last_filled_size`
- 只更新增量部分

**影响文件**：
- `core/executor/position_executor.py`（DCAExecutor、TWAPExecutor、GridExecutor）

**修复后逻辑**：
```python
last_filled_size = 0.0

while True:
    order_info = await get_order_status(order_id)
    filled_size = order_info["filled_size"]  # 累计值
    
    # 计算增量
    filled_increment = filled_size - last_filled_size
    last_filled_size = filled_size
    
    # 只更新增量
    if filled_increment > 0:
        self.filled_size += filled_increment
```

---

### 4. ✅ ID 生成语法错误

**问题描述**：
- `_generate_id` 方法中，`& 0xFFFFFF` 在 f-string 括号外面
- 导致 ID 字符串包含 `& 0xFFFFFF` 后缀，而不是位运算结果

**错误代码**：
```python
return f"{...}_{hash(self)} & 0xFFFFFF}"  # 错误！
# 结果: "order_20250101120000_12345678 & 0xFFFFFF"
```

**修复方案**：
- 将位运算移到括号内

**修复后代码**：
```python
return f"{...}_{hash(self) & 0xFFFFFF}"  # 正确！
# 结果: "order_20250101120000_16777215"
```

**影响文件**：
- `core/executor/executor_base.py`

---

## 📝 总结

| 问题 | 严重程度 | 状态 | 影响范围 |
|------|---------|------|---------|
| TokenBucket 同步阻塞 | 🔥 严重 | ✅ 已修复 | 全系统（可能导致 Event Loop 死锁） |
| TripleBarrier 方向感缺失 | 🔥 严重 | ✅ 已修复 | Short 策略（会误触发止损） |
| DCAExecutor 填充计算错误 | ⚠️ 中等 | ✅ 已修复 | DCA/TWAP/Grid 策略（成交数据错误） |
| ID 生成语法错误 | 🐛 轻微 | ✅ 已修复 | 所有 Executor（ID 格式错误） |

---

## 🧪 测试建议

1. **TokenBucket 测试**：
   - 确保 `await rate_limiter.acquire()` 不会阻塞其他协程
   - 测试并发请求

2. **TripleBarrier 测试**：
   - 测试 Long 策略（止盈止损正常）
   - 测试 Short 策略（止盈止损正常）
   - 测试移动止损（Long/Short）

3. **DCAExecutor 测试**：
   - 测试订单分批成交
   - 确保 `filled_size` 计算正确

4. **ID 生成测试**：
   - 确保 ID 格式正确（不包含 `& 0xFFFFFF`）
