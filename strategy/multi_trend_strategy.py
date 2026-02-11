"""
📊 Multi-Trend Strategy - 多币种趋势滚仓策略（简化版）
=========================================================
适配小资金（40U）的趋势交易策略，完全融入Runtime架构：

架构说明：
- 由Runtime调用MarketScanner动态获取5个趋势合约
- 每个合约由StrategyManager调用analyze_signal生成交易信号
- 由Scheduler每15分钟评估持仓，决定是否平仓换仓
- 由RiskManager审批所有交易
- 由OrderManager执行交易

这个策略只负责：
1. 根据传入的symbol生成趋势交易信号
2. 计算仓位大小、止盈止损
3. 评估持仓表现（供Scheduler调用）
"""

import logging
from typing import Dict, Optional
from datetime import datetime

from strategy.base_strategy import BaseStrategy
from strategy import indicators


class MultiTrendStrategy(BaseStrategy):
    """多币种趋势滚仓策略 - 简化版"""

    def __init__(self, config, context, state_machine, order_manager, **kwargs):
        super().__init__(config, context, state_machine, order_manager)
        self.logger = logging.getLogger("MultiTrend")

        # 配置参数
        self.cfg = config.get("multi_trend", {})

        # 资金配置
        self.total_capital = float(self.cfg.get("total_capital", 40))  # 总资金40U
        self.max_positions = int(self.cfg.get("max_positions", 5))  # 最多5个持仓
        self.leverage = int(self.cfg.get("leverage", 3))  # 3倍杠杆

        # 交易配置
        self.risk_per_position = self.cfg.get("risk_per_position", 0.02)  # 每个仓位风险2%
        self.stop_loss_pct = self.cfg.get("stop_loss_pct", 0.02)  # 止损2%
        self.take_profit_pct = self.cfg.get("take_profit_pct", 0.06)  # 止盈6%

        # 评估配置
        self.evaluation_interval = self.cfg.get("evaluation_interval", 15)  # 评估间隔15分钟
        self.min_profit_threshold = self.cfg.get("min_profit_threshold", 0.01)  # 最小盈利1%

        # 趋势识别配置
        self.adx_threshold = self.cfg.get("adx_threshold", 25)  # ADX阈值
        self.trend_period = self.cfg.get("trend_period", "4H")  # 趋势周期

        self.logger.info(f"✅ 多币种趋势策略初始化 (总资金: {self.total_capital}U, 最大持仓: {self.max_positions})")

    async def initialize(self):
        """初始化策略"""
        self.logger.info("正在初始化多币种趋势策略...")
        self.is_initialized = True

    async def analyze_signal(self) -> Optional[Dict]:
        """
        核心信号分析函数 - 由Runtime/StrategyManager调用

        注意：这个方法会收到一个symbol（从Runtime的扫描结果传入），
        但BaseStrategy的analyze_signal方法没有参数。我需要修改调用方式。

        由于架构限制，这里暂时返回None，实际信号生成需要在Runtime层处理。
        """
        return None

    async def generate_trend_signal(self, symbol: str) -> Optional[Dict]:
        """
        生成趋势信号 - 由Runtime调用

        Args:
            symbol: 交易对（如 "BTC-USDT-SWAP"）

        Returns:
            Dict: 交易信号
        """
        try:
            # 获取K线数据
            klines = await self.om.client.get_candlesticks(symbol, bar=self.trend_period, limit=100)
            if not klines or len(klines) < 50:
                return None

            # 转换为DataFrame
            df = indicators.normalize_klines(klines)

            # 计算指标
            ema20 = indicators.calculate_ema(df, 20)
            ema50 = indicators.calculate_ema(df, 50)
            adx_series = indicators.calculate_adx(df, 14)

            curr_price = df["close"].iloc[-1]
            curr_ema20 = ema20.iloc[-1]
            curr_ema50 = ema50.iloc[-1]
            curr_adx = adx_series.iloc[-1]

            # 判断趋势
            # 做多：EMA20 > EMA50, 价格 > EMA20, ADX > 25
            is_uptrend = curr_ema20 > curr_ema50 and curr_price > curr_ema20 and curr_adx > self.adx_threshold

            # 做空：EMA20 < EMA50, 价格 < EMA20, ADX > 25
            is_downtrend = curr_ema20 < curr_ema50 and curr_price < curr_ema20 and curr_adx > self.adx_threshold

            if not (is_uptrend or is_downtrend):
                return None

            side = "buy" if is_uptrend else "sell"

            # 计算止盈止损
            stop_loss_price = curr_price * (1 + self.stop_loss_pct) if side == "sell" else curr_price * (1 - self.stop_loss_pct)
            take_profit_price = curr_price * (1 - self.take_profit_pct) if side == "sell" else curr_price * (1 + self.take_profit_pct)

            # 计算仓位大小
            # 单个仓位风险 = 总资金 * 风险比例
            risk_amount = self.total_capital * self.risk_per_position

            # 仓位大小 = 风险金额 / 止损距离
            stop_distance = abs(stop_loss_price - curr_price)
            position_size = risk_amount / stop_distance

            self.logger.info(f"🎯 [趋势信号] {symbol} {side} 价格={curr_price:.4f} ADX={curr_adx:.1f}")

            return {
                "symbol": symbol,
                "side": side,
                "type": "market",
                "size": f"{position_size:.4f}",
                "leverage": self.leverage,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "reason": f"Trend (ADX={curr_adx:.1f})"
            }

        except Exception as e:
            self.logger.error(f"❌ 生成趋势信号失败 {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def evaluate_position(self, symbol: str) -> Dict:
        """
        评估持仓表现 - 供Scheduler调用

        Args:
            symbol: 交易对

        Returns:
            {
                "action": "hold" | "close",
                "reason": "原因说明",
                "pnl_pct": 0.05,
                "should_rebalance": bool
            }
        """
        try:
            # 获取当前持仓
            pos = self.context.get_position(symbol)
            if not pos or float(pos.quantity) == 0:
                return {"action": "hold", "reason": "无持仓", "should_rebalance": False}

            # 获取当前价格
            ticker = await self.om.client.get_ticker(symbol)
            if not ticker:
                return {"action": "hold", "reason": "无法获取价格", "should_rebalance": False}

            curr_price = float(ticker.get("last", 0))
            if curr_price == 0:
                return {"action": "hold", "reason": "价格无效", "should_rebalance": False}

            # 计算盈亏
            entry_price = float(pos.avg_price) if pos.avg_price else 0
            quantity = float(pos.quantity)

            if quantity > 0:  # 做多
                pnl_pct = (curr_price - entry_price) / entry_price
            else:  # 做空
                pnl_pct = (entry_price - curr_price) / entry_price

            # 止损检查
            if pnl_pct <= -self.stop_loss_pct:
                return {
                    "action": "close",
                    "reason": f"止损触发 (盈亏: {pnl_pct:.2%})",
                    "pnl_pct": pnl_pct,
                    "should_rebalance": True
                }

            # 止盈检查
            if pnl_pct >= self.take_profit_pct:
                return {
                    "action": "close",
                    "reason": f"止盈触发 (盈亏: {pnl_pct:.2%})",
                    "pnl_pct": pnl_pct,
                    "should_rebalance": True
                }

            # 评估：如果盈利不足且亏损扩大，建议换仓
            if pnl_pct < self.min_profit_threshold and pnl_pct < -0.005:
                return {
                    "action": "close",
                    "reason": f"盈利不足且趋势反转 (盈亏: {pnl_pct:.2%})",
                    "pnl_pct": pnl_pct,
                    "should_rebalance": True
                }

            # 持有
            return {
                "action": "hold",
                "reason": f"正常持有 (盈亏: {pnl_pct:.2%})",
                "pnl_pct": pnl_pct,
                "should_rebalance": False
            }

        except Exception as e:
            self.logger.error(f"❌ 评估持仓 {symbol} 失败: {e}")
            return {"action": "hold", "reason": f"评估失败: {str(e)}", "should_rebalance": False}

    async def run_tick(self):
        """每轮Tick执行（由Scheduler调用）"""
        pass

    async def shutdown(self):
        """策略停止"""
        self.logger.info("🛑 多币种趋势策略停止")
