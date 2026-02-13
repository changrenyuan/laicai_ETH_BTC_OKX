"""
📊 MultiTrendStrategyV2 - V2 版多趋势策略
===========================================
基于 Hummingbot 架构的改进版趋势策略

主要改进：
1. 集成 PositionSizer 统一仓位计算
2. 集成 Executor 架构进行订单管理
3. 多周期分析（15m/1H 定方向 + 5m 回踩）
4. 限价单入场（减少滑点）
5. 基于 ATR 的结构性止损
6. 移动止盈逻辑
7. Triple Barrier 风控
"""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime

from strategy.base_strategy import BaseStrategy
from strategy import indicators
from core import (
    PositionSizer,
    PositionSizeConfig,
    ExecutorOrchestrator,
    OrderExecutor,
    ExecutorConfig,
    ExecutorType,
    TripleBarrier,
    BarrierAction,
    TrailingStop,
    TrailingStopMode
)
from core.context import Position, MarketData


class MultiTrendStrategyV2(BaseStrategy):
    """
    V2 版多趋势策略
    
    核心特性：
    - 多周期趋势识别（大周期定方向 + 小周期找入场点）
    - 智能仓位计算（PositionSizer）
    - Executor 架构管理订单
    - Triple Barrier 风控
    - 移动止损止盈
    """

    def __init__(self, config: dict, context, state_machine, order_manager, **kwargs):
        super().__init__(config, context, state_machine, order_manager)
        self.logger = logging.getLogger("MultiTrendV2")

        # 配置参数
        self.cfg = config.get("multi_trend_v2", {})

        # 资金配置
        self.total_capital = float(self.cfg.get("total_capital", 40))  # 总资金40U
        self.leverage = int(self.cfg.get("leverage", 3))  # 3倍杠杆

        # 仓位配置
        self.risk_per_position = self.cfg.get("risk_per_position", 0.02)  # 每个仓位风险2%
        self.max_positions = int(self.cfg.get("max_positions", 5))  # 最多5个持仓

        # 止损止盈配置
        self.stop_loss_pct = self.cfg.get("stop_loss_pct", 0.02)  # 止损2%
        self.take_profit_pct = self.cfg.get("take_profit_pct", 0.06)  # 止盈6%
        self.trailing_stop_pct = self.cfg.get("trailing_stop_pct", 0.01)  # 移动止损1%
        self.trailing_activation_pct = self.cfg.get("trailing_activation_pct", 0.02)  # 移动止损激活2%

        # 趋势识别配置
        self.adx_threshold = self.cfg.get("adx_threshold", 25)  # ADX阈值
        self.trend_period = self.cfg.get("trend_period", "1H")  # 趋势周期（大周期）
        self.entry_period = self.cfg.get("entry_period", "5m")  # 入场周期（小周期）
        self.ema_gap_threshold = self.cfg.get("ema_gap_threshold", 0.001)  # EMA差距阈值（0.1%）

        # ATR 配置
        self.atr_period = self.cfg.get("atr_period", 14)  # ATR周期
        self.atr_multiplier = self.cfg.get("atr_multiplier", 1.5)  # ATR倍数（用于止损）

        # 限价单配置
        self.order_type = self.cfg.get("order_type", "limit")  # 订单类型：limit 或 market
        self.limit_order_offset_pct = self.cfg.get("limit_order_offset_pct", 0.001)  # 限价单偏移0.1%

        # 初始化 PositionSizer
        self.position_sizer = PositionSizer(config={
            "risk_per_position": self.risk_per_position,
            "max_position_pct": 0.10,  # 单个仓位最大10%
            "leverage": self.leverage,
            "stop_loss_pct": self.stop_loss_pct,
            "min_position_value": 10.0,  # 最小10U
            "contract_size": 1.0,  # 假设1张=1个币
            "max_risk_multiplier": 1.5
        })

        # Executor Orchestrator
        self.executor_orchestrator = ExecutorOrchestrator()

        # 持仓跟踪
        self.active_positions: Dict[str, Dict] = {}  # symbol -> position_info

        self.logger.info(f"✅ MultiTrendStrategyV2 初始化 (总资金: {self.total_capital}U, 杠杆: {self.leverage}x)")

    async def initialize(self):
        """初始化策略"""
        self.logger.info("正在初始化 MultiTrendStrategyV2...")
        await self.executor_orchestrator.initialize()
        self.is_initialized = True

    async def shutdown(self):
        """策略停止"""
        self.logger.info("正在停止 MultiTrendStrategyV2...")
        await self.executor_orchestrator.stop_all()
        self.is_initialized = False

    async def run_tick(self):
        """每轮行情更新时的逻辑"""
        if not self.is_initialized:
            return

        # 1. 检查并更新现有持仓
        await self._update_positions()

        # 2. 检查是否可以开新仓
        if len(self.active_positions) >= self.max_positions:
            self.logger.info(f"已达到最大持仓数 {self.max_positions}，跳过信号生成")
            return

        # 3. 生成新信号（这个方法需要由外部传入 symbol）
        # 这里暂时留空，实际使用时需要从 Runtime 或 Scanner 获取 symbol 列表
        pass

    async def analyze_signal(self, symbol: str) -> Optional[Dict]:
        """
        分析交易信号 - 多周期分析

        Args:
            symbol: 交易对（如 "BTC-USDT-SWAP"）

        Returns:
            Dict: 交易信号
        """
        try:
            # 1. 大周期趋势判断（定方向）
            trend_result = await self._analyze_trend(symbol)
            if not trend_result:
                return None

            trend_side = trend_result["side"]
            trend_strength = trend_result["strength"]

            # 2. 小周期回踩判断（找入场点）
            entry_result = await self._analyze_entry(symbol, trend_side)
            if not entry_result:
                self.logger.info(f"🔍 {symbol} 趋势方向: {trend_side}，但未找到合适入场点")
                return None

            # 3. 获取当前价格
            ticker = await self.om.client.get_ticker(symbol)
            if not ticker:
                self.logger.warning(f"⚠️ {symbol} 无法获取价格")
                return None

            ticker_data = ticker[0] if isinstance(ticker, list) else ticker
            current_price = float(ticker_data.get("last", 0))
            if current_price == 0:
                self.logger.warning(f"⚠️ {symbol} 价格无效")
                return None

            # 4. 计算止损止盈
            # 优先使用 ATR 止损
            atr_stop_loss = await self._calculate_atr_stop_loss(symbol, current_price, trend_side)
            if atr_stop_loss:
                stop_loss_price = atr_stop_loss
            else:
                # 回退到固定百分比止损
                stop_loss_price = self.position_sizer.calculate_stop_loss(
                    current_price, trend_side, self.stop_loss_pct
                )

            # 计算止盈价格
            take_profit_price = self.position_sizer.calculate_take_profit(
                current_price, trend_side, self.take_profit_pct
            )

            # 5. 计算仓位大小
            position_result = self.position_sizer.calculate_position(
                total_capital=self.total_capital,
                entry_price=current_price,
                side=trend_side,
                stop_loss_pct=self.stop_loss_pct,
                leverage=self.leverage
            )

            if not position_result.is_valid:
                self.logger.warning(f"🚫 {symbol} 仓位计算无效: {position_result.warnings}")
                return None

            # 6. 计算入场价格（限价单）
            if self.order_type == "limit":
                if trend_side == "buy":
                    # 做多：限价单价格稍低于当前价格（等待回踩）
                    entry_price = current_price * (1 - self.limit_order_offset_pct)
                else:  # sell
                    # 做空：限价单价格稍高于当前价格（等待回踩）
                    entry_price = current_price * (1 + self.limit_order_offset_pct)
            else:
                # 市价单
                entry_price = current_price

            # 7. 构建交易信号
            signal = {
                "symbol": symbol,
                "side": trend_side,
                "type": self.order_type,
                "size": f"{position_result.position_size:.4f}",
                "price": f"{entry_price:.6f}",
                "leverage": self.leverage,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "reason": f"Trend (ADX={trend_strength:.1f}, Side={trend_side})",
                "risk_pct": position_result.risk_pct,
                "position_value": position_result.position_value,
                "margin_required": position_result.margin_required
            }

            self.logger.info("=" * 80)
            self.logger.info(f"🎯 [MultiTrendV2] {symbol} 交易信号")
            self.logger.info("-" * 80)
            self.logger.info(f"方向:      {trend_side}")
            self.logger.info(f"入场价格:  {entry_price:.6f}")
            self.logger.info(f"当前价格:  {current_price:.6f}")
            self.logger.info(f"止损价格:  {stop_loss_price:.6f}")
            self.logger.info(f"止盈价格:  {take_profit_price:.6f}")
            self.logger.info(f"仓位大小:  {position_result.position_size} 张")
            self.logger.info(f"仓位价值:  {position_result.position_value:.2f} USDT")
            self.logger.info(f"所需保证金: {position_result.margin_required:.2f} USDT")
            self.logger.info(f"风险比例:  {position_result.risk_pct:.2%}")
            self.logger.info("-" * 80)
            self.logger.info(f"趋势强度:  {trend_strength:.1f}")
            self.logger.info(f"订单类型:  {self.order_type}")
            self.logger.info("=" * 80)

            return signal

        except Exception as e:
            self.logger.error(f"❌ 分析信号失败 {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def execute_signal(self, signal: Dict) -> Optional[str]:
        """
        执行交易信号 - 使用 Executor 架构

        Args:
            signal: 交易信号

        Returns:
            str: 执行器ID
        """
        try:
            symbol = signal["symbol"]
            side = signal["side"]

            # 1. 创建 Executor 配置
            executor_config = ExecutorConfig(
                exchange=self.om.client,
                symbol=symbol,
                side=side,
                size=float(signal["size"]),
                order_type=signal.get("type", "market"),
                price=float(signal.get("price", 0)) if signal.get("type") == "limit" else None,
                stop_loss=float(signal["stop_loss"]),
                take_profit=float(signal["take_profit"]),
                callback=self._executor_callback
            )

            # 2. 创建 Triple Barrier
            triple_barrier = TripleBarrier(
                upper_price=float(signal["take_profit"]),
                lower_price=float(signal["stop_loss"]),
                time_limit_seconds=self.cfg.get("position_time_limit", 86400)  # 默认24小时
            )

            # 3. 创建 Trailing Stop（可选）
            trailing_stop = None
            if self.cfg.get("enable_trailing_stop", True):
                trailing_stop = TrailingStop(
                    activation_price=float(signal["price"]) * (1 + self.trailing_activation_pct) if side == "buy" else float(signal["price"]) * (1 - self.trailing_activation_pct),
                    trailing_distance_pct=self.trailing_stop_pct,
                    mode=TrailingStopMode.PERCENTAGE
                )

            # 4. 创建 Position Executor
            from core.executor.position_executor import PositionExecutor
            executor = PositionExecutor(
                config=executor_config,
                stop_loss=float(signal["stop_loss"]),
                take_profit=float(signal["take_profit"]),
                time_limit_seconds=self.cfg.get("position_time_limit", 86400),
                trailing_stop=trailing_stop,
                callback=self._executor_callback
            )

            # 5. 启动执行器
            executor_id = await self.executor_orchestrator.start_executor(executor)

            # 6. 记录持仓
            self.active_positions[symbol] = {
                "executor_id": executor_id,
                "executor": executor,
                "signal": signal,
                "entry_time": datetime.now(),
                "trailing_stop": trailing_stop
            }

            self.logger.info(f"✅ {symbol} 执行器启动成功: {executor_id}")
            return executor_id

        except Exception as e:
            self.logger.error(f"❌ 执行信号失败 {signal.get('symbol')}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _analyze_trend(self, symbol: str) -> Optional[Dict]:
        """
        大周期趋势判断（定方向）

        使用 EMA + ADX 组合：
        - EMA20 > EMA50 + 差距 > 阈值 → 做多
        - EMA20 < EMA50 + 差距 > 阈值 → 做空
        - ADX > 阈值 → 趋势确认
        """
        try:
            # 获取大周期K线
            klines = await self.om.client.get_candlesticks(
                symbol, bar=self.trend_period, limit=100
            )
            if not klines or len(klines) < 50:
                return None

            # 转换为DataFrame
            df = indicators.normalize_klines(klines)

            # 计算 EMA
            ema20 = indicators.calculate_ema(df, 20)
            ema50 = indicators.calculate_ema(df, 50)

            # 计算 ADX
            adx_series = indicators.calculate_adx(df, 14)

            # 获取最新值
            curr_ema20 = ema20.iloc[-1]
            curr_ema50 = ema50.iloc[-1]
            curr_adx = adx_series.iloc[-1]

            # 计算EMA差距百分比
            ema_gap_pct = (curr_ema20 - curr_ema50) / curr_ema50 if curr_ema50 != 0 else 0

            # 判断趋势
            is_uptrend = ema_gap_pct > self.ema_gap_threshold and curr_adx > self.adx_threshold
            is_downtrend = ema_gap_pct < -self.ema_gap_threshold and curr_adx > self.adx_threshold

            if is_uptrend:
                return {"side": "buy", "strength": curr_adx, "ema_gap": ema_gap_pct}
            elif is_downtrend:
                return {"side": "sell", "strength": curr_adx, "ema_gap": ema_gap_pct}
            else:
                return None

        except Exception as e:
            self.logger.error(f"❌ 趋势判断失败 {symbol}: {e}")
            return None

    async def _analyze_entry(self, symbol: str, trend_side: str) -> Optional[Dict]:
        """
        小周期回踩判断（找入场点）

        使用 RSI + EMA 回踩：
        - RSI 超买/超卖
        - 价格回踩到 EMA
        """
        try:
            # 获取小周期K线
            klines = await self.om.client.get_candlesticks(
                symbol, bar=self.entry_period, limit=50
            )
            if not klines or len(klines) < 30:
                return None

            # 转换为DataFrame
            df = indicators.normalize_klines(klines)

            # 计算 EMA20
            ema20 = indicators.calculate_ema(df, 20)

            # 计算 RSI
            rsi = indicators.calculate_rsi(df, 14)

            # 获取最新值
            curr_price = df["close"].iloc[-1]
            curr_ema20 = ema20.iloc[-1]
            curr_rsi = rsi.iloc[-1]

            # 判断入场条件
            if trend_side == "buy":
                # 做多：RSI < 70（不超买）且价格接近EMA20
                is_entry = curr_rsi < 70 and abs((curr_price - curr_ema20) / curr_ema20) < 0.01
            else:  # sell
                # 做空：RSI > 30（不超卖）且价格接近EMA20
                is_entry = curr_rsi > 30 and abs((curr_price - curr_ema20) / curr_ema20) < 0.01

            if is_entry:
                return {"price": curr_price, "rsi": curr_rsi}
            else:
                return None

        except Exception as e:
            self.logger.error(f"❌ 入场点判断失败 {symbol}: {e}")
            return None

    async def _calculate_atr_stop_loss(
        self,
        symbol: str,
        current_price: float,
        side: str
    ) -> Optional[float]:
        """
        基于 ATR 计算止损价格

        Args:
            symbol: 交易对
            current_price: 当前价格
            side: 交易方向

        Returns:
            float: 止损价格
        """
        try:
            # 获取K线
            klines = await self.om.client.get_candlesticks(
                symbol, bar=self.entry_period, limit=100
            )
            if not klines or len(klines) < self.atr_period:
                return None

            # 转换为DataFrame
            df = indicators.normalize_klines(klines)

            # 计算 ATR
            atr = indicators.calculate_atr(df, self.atr_period)
            curr_atr = atr.iloc[-1]

            # 计算止损价格
            if side == "buy":
                stop_loss_price = current_price - (curr_atr * self.atr_multiplier)
            else:  # sell
                stop_loss_price = current_price + (curr_atr * self.atr_multiplier)

            self.logger.info(f"🔍 [ATR止损] {symbol} ATR={curr_atr:.6f}, 止损={stop_loss_price:.6f}")
            return stop_loss_price

        except Exception as e:
            self.logger.warning(f"⚠️ ATR止损计算失败 {symbol}: {e}")
            return None

    async def _update_positions(self):
        """更新现有持仓状态"""
        for symbol, pos_info in list(self.active_positions.items()):
            try:
                executor = pos_info["executor"]
                
                # 检查执行器状态
                if executor.status.name in ["COMPLETED", "TERMINATED", "FAILED"]:
                    self.logger.info(f"📋 {symbol} 执行器状态: {executor.status.name}")
                    
                    # 移除持仓
                    del self.active_positions[symbol]
                
            except Exception as e:
                self.logger.error(f"❌ 更新持仓失败 {symbol}: {e}")

    async def _executor_callback(self, event_type: str, data: Dict):
        """
        执行器回调函数

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        self.logger.info(f"📢 [Executor回调] {event_type}: {data}")
