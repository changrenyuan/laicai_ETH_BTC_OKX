"""
📈 DirectionalTradingControllerBase - 方向性交易控制器基类
==============================================================
用于实现趋势跟踪、突破等方向性交易策略

核心特性：
- 做多/做空信号生成
- 支持多个交易对
- 集成 PositionSizer 计算仓位
- 支持 Triple Barrier 风控
"""

import logging
from abc import abstractmethod
from typing import Dict, Optional, List
from datetime import datetime

from core.controller.controller_base import ControllerBase, EventType
from core.events import Event
from core.executor.executor_base import ExecutorConfig, ExecutorType
from core.position_sizer import PositionSizer, PositionSizeConfig


class DirectionalTradingControllerBase(ControllerBase):
    """
    方向性交易控制器基类
    
    适用于：
    - 趋势跟踪策略
    - 突破策略
    - 动量策略
    """

    def __init__(
        self,
        config: Dict,
        exchanges: Dict,
        executor_orchestrator,
        position_sizer: Optional[PositionSizer] = None
    ):
        super().__init__(config, exchanges, executor_orchestrator)
        
        # 仓位计算器
        if position_sizer:
            self.position_sizer = position_sizer
        else:
            # 创建默认的 PositionSizer
            self.position_sizer = PositionSizer(config={
                "risk_per_position": config.get("risk_per_position", 0.02),
                "max_position_pct": config.get("max_position_pct", 0.10),
                "leverage": config.get("leverage", 3),
                "stop_loss_pct": config.get("stop_loss_pct", 0.02),
                "min_position_value": config.get("min_position_value", 10.0),
                "contract_size": config.get("contract_size", 1.0),
                "max_risk_multiplier": config.get("max_risk_multiplier", 1.5)
            })
        
        # 方向性交易参数
        self.max_positions = config.get("max_positions", 5)
        self.allow_long = config.get("allow_long", True)
        self.allow_short = config.get("allow_short", True)
        
        # 持仓跟踪
        self.active_positions: Dict[str, Dict] = {}  # symbol -> position_info
        self.symbol_signals: Dict[str, Dict] = {}  # symbol -> latest_signal
        
        # 止盈止损配置
        self.stop_loss_pct = config.get("stop_loss_pct", 0.02)
        self.take_profit_pct = config.get("take_profit_pct", 0.06)
        self.trailing_stop_pct = config.get("trailing_stop_pct", 0.01)
        self.trailing_activation_pct = config.get("trailing_activation_pct", 0.02)
        
        # 订单类型
        self.order_type = config.get("order_type", "market")
        self.limit_order_offset_pct = config.get("limit_order_offset_pct", 0.001)

    @property
    def controller_type(self) -> str:
        return "directional_trading"

    async def _initialize_strategy_state(self):
        """初始化策略状态"""
        self.logger.info("初始化方向性交易策略状态...")
        
        # 加载历史数据
        # 初始化指标
        # 设置初始参数

    async def process_tick(self, event: Event):
        """
        处理行情更新
        
        1. 更新统计信息
        2. 分析信号
        3. 生成执行器配置
        4. 创建执行器
        """
        if not self.is_active:
            return
        
        self.stats["ticks_processed"] += 1
        self.last_tick_time = datetime.now()
        
        try:
            # 获取行情数据
            data = event.data
            symbol = data.get("symbol")
            
            if not symbol:
                return
            
            # 检查是否在监控列表中
            if self.trading_pairs and symbol not in self.trading_pairs:
                return
            
            # 检查是否已有持仓
            if symbol in self.active_positions:
                # 更新持仓状态
                await self._update_position(symbol, data)
                return
            
            # 检查是否达到最大持仓数
            if len(self.active_positions) >= self.max_positions:
                return
            
            # 分析信号
            signal = await self._analyze_signal(symbol, data)
            
            if signal:
                self.stats["signals_generated"] += 1
                self.symbol_signals[symbol] = signal
                
                self.logger.info(f"📈 [信号] {symbol} {signal.get('side')} "
                               f"强度={signal.get('strength', 0):.2f}")
                
                # 生成执行器配置
                executor_config = self.determine_executor_config(signal)
                
                if executor_config:
                    # 创建执行器
                    executor_id = await self.create_executor(executor_config)
                    
                    if executor_id:
                        # 记录持仓
                        self.active_positions[symbol] = {
                            "executor_id": executor_id,
                            "signal": signal,
                            "entry_time": datetime.now(),
                            "entry_price": signal.get("entry_price", 0)
                        }
                        
                        # 发布事件
                        await self._emit_event(EventType.ORDER_FILLED, {
                            "symbol": symbol,
                            "side": signal["side"],
                            "executor_id": executor_id
                        })
        
        except Exception as e:
            self.logger.error(f"❌ 处理 Tick 失败: {e}")
            import traceback
            traceback.print_exc()

    @abstractmethod
    async def _analyze_signal(self, symbol: str, market_data: Dict) -> Optional[Dict]:
        """
        分析交易信号（由子类实现）
        
        Args:
            symbol: 交易对
            market_data: 市场数据
            
        Returns:
            Dict: 交易信号
            {
                "symbol": "BTC-USDT-SWAP",
                "side": "buy" | "sell",
                "strength": 0.8,  # 信号强度 0-1
                "entry_price": 50000.0,
                "reason": "...",
                "metrics": {...}
            }
        """
        pass

    def determine_executor_config(self, signal: Dict) -> Optional[ExecutorConfig]:
        """
        根据信号生成 ExecutorConfig
        
        Args:
            signal: 交易信号
            
        Returns:
            ExecutorConfig: 执行器配置
        """
        try:
            symbol = signal["symbol"]
            side = signal["side"]
            entry_price = signal.get("entry_price", 0)
            
            if entry_price == 0:
                self.logger.error(f"❌ 入场价格为0: {symbol}")
                return None
            
            # 1. 计算仓位大小
            position_result = self.position_sizer.calculate_position(
                total_capital=self.config.get("total_capital", 1000),
                entry_price=entry_price,
                side=side,
                stop_loss_pct=self.stop_loss_pct,
                leverage=self.config.get("leverage", 3)
            )
            
            if not position_result.is_valid:
                self.logger.warning(f"🚫 {symbol} 仓位计算无效: {position_result.warnings}")
                return None
            
            # 2. 计算入场价格（限价单）
            if self.order_type == "limit":
                if side == "buy":
                    # 做多：限价单价格稍低于当前价格
                    order_price = entry_price * (1 - self.limit_order_offset_pct)
                else:  # sell
                    # 做空：限价单价格稍高于当前价格
                    order_price = entry_price * (1 + self.limit_order_offset_pct)
            else:
                # 市价单
                order_price = entry_price
            
            # 3. 计算止盈止损价格
            stop_loss_price = self.position_sizer.calculate_stop_loss(
                entry_price, side, self.stop_loss_pct
            )
            
            take_profit_price = self.position_sizer.calculate_take_profit(
                entry_price, side, self.take_profit_pct
            )
            
            # 4. 创建 ExecutorConfig
            executor_config = ExecutorConfig(
                exchange=self._get_exchange_for_symbol(symbol),
                symbol=symbol,
                side=side,
                size=position_result.position_size,
                order_type=self.order_type,
                price=order_price if self.order_type == "limit" else None,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
                callback=self._executor_callback
            )
            
            # 附加信息
            executor_config.metadata = {
                "signal": signal,
                "position_value": position_result.position_value,
                "margin_required": position_result.margin_required,
                "risk_pct": position_result.risk_pct
            }
            
            return executor_config
            
        except Exception as e:
            self.logger.error(f"❌ 生成 ExecutorConfig 失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_exchange_for_symbol(self, symbol: str):
        """
        获取指定交易对对应的交易所
        
        Args:
            symbol: 交易对
            
        Returns:
            Exchange: 交易所实例
        """
        # 简单实现：返回第一个交易所
        # 实际可以根据 symbol 前缀判断
        return next(iter(self.exchanges.values()), None)

    async def _update_position(self, symbol: str, market_data: Dict):
        """
        更新持仓状态
        
        Args:
            symbol: 交易对
            market_data: 市场数据
        """
        # 检查持仓是否需要平仓
        # 检查移动止损
        # 更新盈亏统计
        pass

    async def _executor_callback(self, event_type: str, data: Dict):
        """
        执行器回调函数
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        self.logger.info(f"📢 [Executor回调] {event_type}: {data}")
        
        if event_type == "completed":
            # 执行器完成，移除持仓
            symbol = data.get("symbol")
            if symbol and symbol in self.active_positions:
                del self.active_positions[symbol]
                self.logger.info(f"✅ 持仓已平仓: {symbol}")

    def get_position_stats(self) -> Dict:
        """
        获取持仓统计
        
        Returns:
            Dict: 持仓统计信息
        """
        return {
            "active_positions": len(self.active_positions),
            "max_positions": self.max_positions,
            "positions": {
                symbol: {
                    "executor_id": pos["executor_id"],
                    "side": pos["signal"]["side"],
                    "entry_price": pos["entry_price"],
                    "entry_time": pos["entry_time"].isoformat()
                }
                for symbol, pos in self.active_positions.items()
            }
        }


# 导出
__all__ = ["DirectionalTradingControllerBase"]
