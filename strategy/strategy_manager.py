import logging
import asyncio
from typing import Dict, Optional, Any

from core.context import Context
from core.events import EventBus
from core.state_machine import StateMachine

# 导入具体策略
from strategy.base_strategy import BaseStrategy
from strategy.futures_grid import FuturesGridStrategy

# 假设有一个趋势策略 (如果还没有，下面提供了一个简单的模板)
# from strategy.trend_following import TrendFollowingStrategy

logger = logging.getLogger("StrategyManager")


class StrategyManager:
    """
    🧠 策略总管 (Strategy Manager)
    --------------------------------
    核心职责：
    1. 接收 (Symbol, Regime)
    2. 路由到对应的策略实例 (Grid vs Trend)
    3. 管理多币种策略实例的生命周期
    """

    def __init__(self, config: Dict, context: Context, state_machine: StateMachine, order_manager: Any,
                 event_bus: EventBus):
        self.config = config
        self.context = context
        self.sm = state_machine
        self.om = order_manager
        self.bus = event_bus
        self.logger = logging.getLogger("StrategyManager")

        # 策略实例缓存池
        # Key格式: "{symbol}_{strategy_type}" (例如 "ETH-USDT-SWAP_grid")
        self.active_strategies: Dict[str, BaseStrategy] = {}

    async def generate(self, symbol: str, regime: str) -> Optional[Dict]:
        """
        核心方法：根据币种和市场状态生成交易信号
        """
        # 1. 确定策略类型
        strategy_type = self._map_regime_to_strategy_type(regime)

        if not strategy_type:
            self.logger.debug(f"Markets ({regime}) 不适合交易，跳过 {symbol}")
            return None

        # 2. 获取或创建策略实例
        strategy_instance = await self._get_or_create_strategy(symbol, strategy_type)

        if not strategy_instance:
            self.logger.error(f"无法初始化策略: {symbol} - {strategy_type}")
            return None

        # 3. 执行策略分析
        try:
            # 确保策略是最新的 Context
            strategy_instance.context = self.context

            self.logger.info(f"⚡ [策略路由] 正在调用 {strategy_type.upper()} 策略分析 {symbol}...")
            signal = await strategy_instance.analyze_signal()

            if signal:
                # 注入 meta 信息
                signal['regime'] = regime
                signal['strategy'] = strategy_type
                self.logger.info(f"🎯 [信号生成] {symbol} 生成信号: {signal}")
                return signal

        except Exception as e:
            self.logger.error(f"策略执行异常 {symbol}: {e}")
            import traceback
            traceback.print_exc()

        return None

    def _map_regime_to_strategy_type(self, regime: str) -> Optional[str]:
        """
        根据市场环境映射策略类型
        """
        if regime == "RANGE":
            return "grid"  # 震荡 -> 网格策略
        elif regime == "TREND":
            return "trend"  # 趋势 -> 趋势策略
        elif regime == "CHAOS":
            return None  # 混乱 -> 不交易
        return None

    async def _get_or_create_strategy(self, symbol: str, strategy_type: str) -> Optional[BaseStrategy]:
        """
        懒加载：获取现有的策略实例，或者为新币种创建一个新实例
        """
        instance_key = f"{symbol}_{strategy_type}"

        # 1. 检查缓存
        if instance_key in self.active_strategies:
            return self.active_strategies[instance_key]

        # 2. 动态构建配置
        # 复制主配置，并强制覆盖 symbol 为当前扫描到的币种
        dynamic_config = self.config.copy()

        # 确保 futures_grid 或 trend 配置块存在
        if "futures_grid" not in dynamic_config:
            dynamic_config["futures_grid"] = {}

        # 注入 Symbol !!!
        dynamic_config["futures_grid"]["symbol"] = symbol
        # 如果有 trend 配置块，也要注入
        dynamic_config["trend_strategy"]["symbol"] = symbol

        # 3. 实例化策略
        strategy = None
        try:
            if strategy_type == "grid":
                self.logger.info(f"✨ 初始化新网格策略实例: {symbol}")
                strategy = FuturesGridStrategy(
                    dynamic_config,
                    self.context,
                    self.sm,
                    self.om,
                    fund_guard=None,  # 如果需要，传递各个Guard
                    margin_guard=None
                )
            elif strategy_type == "trend":
                self.logger.info(f"✨ 初始化新趋势策略实例: {symbol}")
                # 使用上面定义的内部类，或者你实际的 TrendStrategy
                strategy = TrendStrategy(
                    dynamic_config,
                    self.context,
                    self.sm,
                    self.om,
                    fund_guard=None,  # 如果需要，传递各个Guard
                    margin_guard=None
                )
            # 4. 初始化策略 (如果是异步初始化)
            if strategy:
                if hasattr(strategy, 'initialize'):
                    await strategy.initialize()

                # 存入缓存
                self.active_strategies[instance_key] = strategy
                return strategy

        except Exception as e:
            self.logger.error(f"策略实例化失败 {symbol}: {e}")
            return None

        return None