"""
📈 Trend Roll Strategy - 趋势滚仓策略
=====================================
策略逻辑：
1. 趋势识别：EMA20 < EMA50 (做空示例) + ADX > 25 + 价格 < EMA20
2. 资金管理：总风险控制在账户 6% 以内
3. 滚仓逻辑：盈利 1R/2R/3R 时分批加仓，最大 3 层
4. 风控逻辑：加仓后移动止损，确保单笔交易不亏损
"""

import logging
from typing import Dict, Optional
import pandas as pd

from strategy.base_strategy import BaseStrategy
from strategy import indicators  # 引用上传的 indicators.py


class TrendRollStrategy(BaseStrategy):
    def __init__(self, config, context, state_machine, order_manager, **kwargs):
        super().__init__(config, context, state_machine, order_manager)
        self.logger = logging.getLogger("TrendRoll")

        # 配置参数读取
        self.cfg = config.get("trend_strategy", {})
        self.symbol = self.cfg.get("symbol", "ETH-USDT-SWAP")

        # --- 核心规则配置 ---
        self.max_risk_pct = 0.06  # 最大总风险 6%
        self.max_layers = 3  # 最大加仓次数
        self.adx_threshold = 25  # ADX 阈值
        self.leverage = 3  # 默认杠杆

        # 内部状态记录
        self.entry_price = 0.0  # 初始开仓价
        self.initial_atr = 0.0  # 开仓时的 ATR (用于计算 R)
        self.current_layers = 0  # 当前层数

    async def initialize(self):
        """初始化策略"""
        self.logger.info(f"✅ 趋势滚仓策略 ({self.symbol}) 初始化完成")
        self.is_initialized = True
        # 可以在这里请求设置杠杆
        # await self.om.client.set_leverage(self.symbol, self.leverage)

    async def analyze_signal(self) -> Optional[Dict]:
        """
        核心信号分析函数
        """
        if not self.is_initialized:
            await self.initialize()

        # 1. 获取 4H K线数据 (根据规则要求 4H)
        klines = await self.om.client.get_candlesticks(self.symbol, bar="4H", limit=100)
        if not klines or len(klines) < 60:
            return None

        # 2. 调用 indicators.py 计算指标
        # 注意：indicators.py 中的函数需要 DataFrame
        df = indicators.normalize_klines(klines)

        # 计算 EMA
        ema20_series = indicators.calculate_ema(df, 20)
        ema50_series = indicators.calculate_ema(df, 50)

        # 计算 ADX
        adx_series = indicators.calculate_adx(df, 14)

        # 计算 ATR (用于止损 R 计算)
        atr_series = indicators.calculate_atr(df, 14)

        # 获取最新值
        curr_price = df["close"].iloc[-1]
        curr_ema20 = ema20_series.iloc[-1]
        curr_ema50 = ema50_series.iloc[-1]
        curr_adx = adx_series.iloc[-1]
        curr_atr = atr_series.iloc[-1]

        # 3. 获取当前持仓状态
        position = self.context.get_position(self.symbol)
        has_position = position and float(position.quantity) != 0

        # --- 场景 A: 无持仓，检查开仓条件 ---
        if not has_position:
            self.current_layers = 0

            # 1️⃣ 趋势确认条件 (根据 Prompt: EMA20 < EMA50, ADX > 25, Price < EMA20)
            # 这里实现的是做空逻辑。如果是做多，符号反过来即可。
            is_downtrend = (curr_ema20 < curr_ema50)
            is_strong_trend = (curr_adx > self.adx_threshold)
            price_below_ema = (curr_price < curr_ema20)

            if is_downtrend and is_strong_trend and price_below_ema:
                # 计算 R (初始止损距离)
                # 假设止损设在 2倍 ATR 处
                sl_distance = 2 * curr_atr
                stop_loss_price = curr_price + sl_distance  # 做空止损在上方

                # 资金管理：第一层仓位风险 = 总账户的 2% (总共允许 6%，分3次)
                risk_per_layer = self.context.get_total_balance() * (self.max_risk_pct / self.max_layers)
                position_size = risk_per_layer / sl_distance  # 数量 = 风险金额 / 单个止损价差

                self.logger.info(f"📉 [开仓信号] 趋势确认: ADX={curr_adx:.1f}, EMA20<EMA50")

                # 记录状态供后续加仓使用
                self.entry_price = curr_price
                self.initial_atr = curr_atr

                return {
                    "symbol": self.symbol,
                    "side": "sell",  # 做空
                    "type": "market",
                    "size": f"{position_size:.4f}",
                    "leverage": self.leverage,
                    "stop_loss": stop_loss_price,
                    "reason": "Trend Start (Layer 1)"
                }

        # --- 场景 B: 有持仓，检查滚仓(加仓)或平仓条件 ---
        else:
            if self.initial_atr == 0: return None  # 数据缺失保护

            # R = 初始止损距离
            R = 2 * self.initial_atr
            avg_price = float(position.avg_price)

            # 计算当前盈利 (做空：开仓价 - 当前价)
            unrealized_profit_dist = avg_price - curr_price

            # 2️⃣ 盈利确认才加仓
            # 规则：盈利 >= 1R 加第二层, >= 2R 加第三层

            signal = None
            new_sl = None

            # 检查是否可以加第二层
            if self.current_layers == 0 and unrealized_profit_dist >= 1 * R:
                self.logger.info(f"💰 [滚仓信号] 盈利达 1R ({unrealized_profit_dist:.2f}), 加仓 Layer 2")
                self.current_layers = 1  # 标记为已加过一次

                # 3️⃣ 止损必须上移 (做空则是下移)
                # 此时止损移到 成本价 (保本)
                new_sl = avg_price
                signal = self._create_add_signal("sell", new_sl, "Roll Layer 2 (1R)")

            # 检查是否可以加第三层
            elif self.current_layers == 1 and unrealized_profit_dist >= 2 * R:
                self.logger.info(f"💰 [滚仓信号] 盈利达 2R, 加仓 Layer 3")
                self.current_layers = 2

                # 止损移到 +1R 处 (锁定部分利润)
                new_sl = avg_price - R
                signal = self._create_add_signal("sell", new_sl, "Roll Layer 3 (2R)")

            # 趋势反转平仓保护 (例如价格回到 EMA50 上方)
            if curr_price > curr_ema50:
                return {
                    "symbol": self.symbol,
                    "side": "buy",  # 买入平空
                    "type": "market",
                    "size": position.quantity,  # 全平
                    "reduce_only": True,
                    "reason": "Trend Reversal (Price > EMA50)"
                }

            return signal

        return None

    def _create_add_signal(self, side, stop_loss, reason):
        """生成加仓信号辅助函数"""
        # 加仓数量保持风险恒定，或者简单采用等额加仓
        # 这里演示等额加仓，实际可根据 update 后的余额计算
        risk_per_layer = self.context.get_total_balance() * (self.max_risk_pct / self.max_layers)
        # 重新计算 size，因为 ATR 可能变了，或者沿用初始 ATR 保持一致性
        size = risk_per_layer / (2 * self.initial_atr)

        return {
            "symbol": self.symbol,
            "side": side,
            "type": "market",
            "size": f"{size:.4f}",
            "leverage": self.leverage,
            "stop_loss": stop_loss,  # 带上新的止损价格发送给执行层
            "reason": reason
        }

    async def run_tick(self):
        """生命周期 tick"""
        pass

    async def shutdown(self):
        """策略停止"""
        self.logger.info("趋势策略停止")