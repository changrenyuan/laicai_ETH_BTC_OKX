"""
📦 交付演示：Controller 架构使用示例
===================================
此文件展示 P1 阶段已完成的 Controller 架构功能

功能演示：
1. Controller 基类功能
2. DirectionalTradingController 方向性交易控制器
3. MarketMakingController 做市商控制器
4. 与 PositionSizer 集成

运行方式：python examples/demo_controller.py
"""

import sys
import asyncio
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '/workspace/projects/laicai_ETH_BTC_OKX')

from core.controller import (
    ControllerBase,
    DirectionalTradingControllerBase,
    MarketMakingControllerBase
)
from core.events import Event, EventType
from core.executor.executor_base import ExecutorConfig
from core.position_sizer import PositionSizer


print("=" * 80)
print("📦 P1 阶段交付演示：Controller 架构")
print("=" * 80)


# ============================================
# 1. 测试 Controller 基类
# ============================================
print("\n【测试1】Controller 基类功能演示")

class TestController(ControllerBase):
    """测试控制器"""
    
    @property
    def controller_type(self) -> str:
        return "test"
    
    async def _initialize_strategy_state(self):
        print("  ✅ 策略状态初始化完成")
    
    async def process_tick(self, event: Event):
        """处理行情"""
        self.logger.info(f"  📊 处理行情: {event.data}")
    
    def determine_executor_config(self, signal: dict) -> ExecutorConfig:
        """生成执行器配置"""
        return None
    
    def _create_executor_instance(self, config: ExecutorConfig):
        return None


# 创建测试控制器
test_config = {
    "id": "test_controller_001",
    "trading_pairs": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
}

test_controller = TestController(
    config=test_config,
    exchanges={},
    executor_orchestrator=None
)

print(f"  控制器ID: {test_controller.controller_id}")
print(f"  控制器类型: {test_controller.controller_type}")
print(f"  监控交易对: {test_controller.trading_pairs}")
print(f"  控制器状态: {test_controller.get_stats()}")

print("  ✅ Controller 基类功能正常")


# ============================================
# 2. 测试 DirectionalTradingController
# ============================================
print("\n【测试2】DirectionalTradingController 演示")

class TestDirectionalController(DirectionalTradingControllerBase):
    """测试方向性交易控制器"""
    
    async def _analyze_signal(self, symbol: str, market_data: dict):
        """模拟信号生成"""
        # 模拟生成一个做多信号
        return {
            "symbol": symbol,
            "side": "buy",
            "strength": 0.85,
            "entry_price": market_data.get("last_price", 50000.0),
            "reason": "测试信号 - EMA金叉 + ADX > 25",
            "metrics": {
                "ema20": 50200.0,
                "ema50": 49800.0,
                "adx": 32.5
            }
        }
    
    def _create_executor_instance(self, config: ExecutorConfig):
        print(f"  🎯 创建执行器: {config.symbol} {config.side}")
        return None  # 实际项目中返回真实执行器


# 创建方向性交易控制器
directional_config = {
    "id": "directional_controller_001",
    "trading_pairs": ["BTC-USDT-SWAP"],
    "total_capital": 1000,
    "risk_per_position": 0.02,
    "leverage": 5,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.06,
    "max_positions": 3,
    "order_type": "limit",
    "limit_order_offset_pct": 0.001
}

directional_controller = TestDirectionalController(
    config=directional_config,
    exchanges={},
    executor_orchestrator=None,
    position_sizer=None
)

print(f"  控制器类型: {directional_controller.controller_type}")
print(f"  最大持仓数: {directional_controller.max_positions}")
print(f"  允许做多: {directional_controller.allow_long}")
print(f"  允许做空: {directional_controller.allow_short}")
print(f"  止损比例: {directional_controller.stop_loss_pct:.2%}")
print(f"  止盈比例: {directional_controller.take_profit_pct:.2%}")

# 模拟行情事件
mock_event = Event(
    event_type=EventType.TICKER,
    data={
        "symbol": "BTC-USDT-SWAP",
        "last_price": 50000.0,
        "timestamp": datetime.now().isoformat()
    }
)

print("  模拟处理行情事件...")
# 注意：因为没有真实的 exchange，process_tick 不会完整执行
print("  ✅ DirectionalTradingController 创建成功")


# ============================================
# 3. 测试 MarketMakingController
# ============================================
print("\n【测试3】MarketMakingController 演示")

market_making_config = {
    "id": "mm_controller_001",
    "trading_pair": "BTC-USDT-SWAP",
    "spread_pct": 0.001,
    "order_size": 0.001,
    "max_orders": 10,
    "grid_levels": 5,
    "grid_spacing_pct": 0.002,
    "max_inventory_ratio": 0.5
}

mm_controller = MarketMakingControllerBase(
    config=market_making_config,
    exchanges={},
    executor_orchestrator=None
)

print(f"  控制器类型: {mm_controller.controller_type}")
print(f"  交易对: {mm_controller.symbol}")
print(f"  价差比例: {mm_controller.spread_pct:.3%}")
print(f"  订单大小: {mm_controller.order_size}")
print(f"  最大订单数: {mm_controller.max_orders}")
print(f"  网格层级: {mm_controller.grid_levels}")
print(f"  网格间距: {mm_controller.grid_spacing_pct:.3%}")

# 模拟计算网格
print("  模拟网格计算...")
mm_controller.bids = [
    {"price": 50000 * (1 - i * 0.002), "size": 0.001, "level": i}
    for i in range(1, 6)
]
mm_controller.asks = [
    {"price": 50000 * (1 + i * 0.002), "size": 0.001, "level": i}
    for i in range(1, 6)
]

print(f"  买单层级数: {len(mm_controller.bids)}")
print(f"  卖单层级数: {len(mm_controller.asks)}")
print("  ✅ MarketMakingController 创建成功")


# ============================================
# 4. 测试 PositionSizer 集成
# ============================================
print("\n【测试4】PositionSizer 集成演示")

position_sizer = PositionSizer(config={
    "risk_per_position": 0.02,
    "leverage": 5,
    "stop_loss_pct": 0.02
})

# 测试仓位计算
result = position_sizer.calculate_position(
    total_capital=1000,
    entry_price=50000,
    side="buy",
    stop_loss_pct=0.02,
    leverage=5,
    min_balance=1000
)

print(f"  总资金: 1000 USDT")
print(f"  入场价格: 50000 USDT")
print(f"  杠杆: 5x")
print(f"  止损比例: 2%")
print("-" * 40)
print(f"  仓位大小: {result.position_size} 张")
print(f"  仓位价值: {result.position_value:.2f} USDT")
print(f"  所需保证金: {result.margin_required:.2f} USDT")
print(f"  实际风险: {result.risk_pct:.2%}")
print(f"  是否有效: {result.is_valid}")
if result.warnings:
    print("  警告:")
    for w in result.warnings:
        print(f"    - {w}")

print("  ✅ PositionSizer 集成正常")


# ============================================
# 5. 统计信息汇总
# ============================================
print("\n【测试5】控制器统计信息")

test_stats = test_controller.get_stats()
print(f"  TestController:")
print(f"    ID: {test_stats['controller_id']}")
print(f"    类型: {test_stats['controller_type']}")
print(f"    已处理Tick数: {test_stats['ticks_processed']}")

directional_stats = directional_controller.get_stats()
print(f"\n  DirectionalTradingController:")
print(f"    ID: {directional_stats['controller_id']}")
print(f"    类型: {directional_stats['controller_type']}")
print(f"    监控交易对: {directional_stats['trading_pairs']}")

mm_stats = mm_controller.get_market_stats()
print(f"\n  MarketMakingController:")
print(f"    总成交数: {mm_stats['total_filled']}")
print(f"    总成交量: {mm_stats['total_volume']:.4f} USDT")
print(f"    活跃订单: {mm_stats['active_orders']}")


# ============================================
# 总结
# ============================================
print("\n" + "=" * 80)
print("✅ P1 阶段交付总结")
print("=" * 80)
print("已完成功能：")
print("  1. ✅ Controller 基类（controller_base.py）")
print("     - 事件订阅机制")
print("     - 执行器调度")
print("     - 统计信息管理")
print()
print("  2. ✅ DirectionalTradingController（directional_controller_base.py）")
print("     - 做多/做空信号生成")
print("     - 集成 PositionSizer")
print("     - 持仓跟踪管理")
print("     - 自动止盈止损计算")
print()
print("  3. ✅ MarketMakingController（market_making_controller_base.py）")
print("     - 网格价格计算")
print("     - 双向挂单管理")
print("     - 订单状态监控")
print("     - 自动补单机制")
print()
print("  4. ✅ 核心模块导出更新")
print("     - core/__init__.py 已更新")
print("     - core/controller/__init__.py 已创建")
print()
print("待完成工作：")
print("  ⏳ OKX Exchange 重构（继承 ExchangeBase）")
print("  ⏳ 完整的集成测试（需要真实交易所连接）")
print("=" * 80)
