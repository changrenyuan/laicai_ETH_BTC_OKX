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
import time
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

            # 🔥 关键修复：引入滞后阈值（Hysteresis）防止震荡市频繁开平仓
            # 计算EMA差距百分比
            ema_gap_pct = (curr_ema20 - curr_ema50) / curr_ema50 if curr_ema50 != 0 else 0

            # 开仓条件：需要 0.1% 的明确趋势余量
            # 做多：EMA20 必须超过 EMA50 0.1%，价格 > EMA20, ADX > 25
            is_uptrend = ema_gap_pct > 0.001 and curr_price > curr_ema20 and curr_adx > self.adx_threshold

            # 做空：EMA20 必须低于 EMA50 0.1%，价格 < EMA20, ADX > 25
            is_downtrend = ema_gap_pct < -0.001 and curr_price < curr_ema20 and curr_adx > self.adx_threshold

            # 调试日志
            self.logger.info(f"🔍 [趋势判断] {symbol} EMA20={curr_ema20:.6f} EMA50={curr_ema50:.6f} 差距={ema_gap_pct:.4%} ADX={curr_adx:.1f}")

            if not (is_uptrend or is_downtrend):
                return None

            side = "buy" if is_uptrend else "sell"
            reason = f"Trend (EMA差距={ema_gap_pct:.3%}, ADX={curr_adx:.1f})"

            # ✅ 修复：使用实时价格而非 K 线收盘价计算止损止盈
            try:
                ticker = await self.om.client.get_ticker(symbol)
                if ticker:
                    # 兼容处理：如果返回是 list，取第一个元素；如果是 dict，直接使用
                    if isinstance(ticker, list) and len(ticker) > 0:
                        ticker_data = ticker[0]
                    elif isinstance(ticker, dict):
                        ticker_data = ticker
                    else:
                        ticker_data = {}

                    real_time_price = float(ticker_data.get("last", 0))
                    if real_time_price > 0:
                        curr_price = real_time_price
                        self.logger.info(f"✅ [价格更新] 使用实时价格: {curr_price:.6f}")
                    else:
                        self.logger.warning(f"⚠️ [价格异常] 实时价格为0，使用K线收盘价: {curr_price:.6f}")
                else:
                    self.logger.warning(f"⚠️ [价格异常] 无法获取实时价格，使用K线收盘价: {curr_price:.6f}")
            except Exception as e:
                self.logger.warning(f"⚠️ [价格异常] 获取实时价格失败 ({e})，使用K线收盘价: {curr_price:.6f}")

            # 🔍 调试：打印止损比例
            self.logger.info(f"🔍 [Debug] side={side}, curr_price={curr_price:.6f}, stop_loss_pct={self.stop_loss_pct}, take_profit_pct={self.take_profit_pct}")

            # 确保止损比例是正数
            if self.stop_loss_pct < 0:
                self.logger.warning(f"⚠️ [止损比例异常] stop_loss_pct 为负数: {self.stop_loss_pct}，强制使用 0.03")
                self.stop_loss_pct = abs(self.stop_loss_pct) if abs(self.stop_loss_pct) > 0 else 0.03

            # 计算止盈止损
            # 做多：止损 = 价格 × (1 - 止损%)
            # 做空：止损 = 价格 × (1 + 止损%)
            stop_loss_price = curr_price * (1 + self.stop_loss_pct) if side == "sell" else curr_price * (1 - self.stop_loss_pct)
            # 做多：止盈 = 价格 × (1 + 止盈%)
            # 做空：止盈 = 价格 × (1 - 止盈%)
            take_profit_price = curr_price * (1 - self.take_profit_pct) if side == "sell" else curr_price * (1 + self.take_profit_pct)

            # 🔍 调试：打印计算后的止损止盈价格
            self.logger.info(f"🔍 [Debug] stop_loss_price={stop_loss_price:.6f}, take_profit_price={take_profit_price:.6f}")

            # 计算仓位大小
            # 单个仓位风险 = 总资金 * 风险比例
            risk_amount = self.total_capital * self.risk_per_position

            # 仓位大小 = 风险金额 / 止损距离
            stop_distance = abs(stop_loss_price - curr_price)
            raw_position_size = risk_amount / stop_distance

            # --- 🔥 智能取整逻辑 (Smart Rounding) ---

            # 1. 针对合约 (SWAP/FUTURES) 必须取整
            # 假设 1 张合约 = 1 个币 (大部分币种适用，如 BTC/ETH/RIVER)
            # 某些币种如 DOGE 可能是 1张=100币，这里简化处理，如有需要需查询 ctVal

            target_sz = int(raw_position_size)

            # 2. 如果算出来是 0 张 (例如 0.74 张)
            if target_sz < 1:
                # 检查: 1张合约到底多少钱?
                contract_value = curr_price * 1.0  # 假设面值=1
                required_margin = contract_value / self.leverage

                # 获取当前可用余额 (预估)
                # 如果没有余额信息，就用 total_capital 估算
                estimated_balance = self.total_capital

                # 💡 判定:
                # A. 余额够不够付保证金? (余额 > 1张的保证金)
                # B. 风险能不能承受? (1张的潜在亏损 < 2倍的预设风控) -> 允许稍微超一点风险

                one_contract_risk = stop_distance * 1.0

                if estimated_balance > required_margin:
                    # 如果风险不是太离谱 (例如 1张的亏损不超过 2.5U，即允许风险放大到 ~6%)
                    # 原定风险 0.8U。如果买1张亏 1.5U，对于40U本金还在可接受范围
                    if one_contract_risk < (self.total_capital * 0.08):
                        self.logger.info(f"⚠️ {symbol} 原始仓位 {raw_position_size:.2f} 不足1张，强制升级为 1 张")
                        target_sz = 1
                    else:
                        self.logger.warning(f"🚫 {symbol} 1张风险过大 ({one_contract_risk:.2f}U)，放弃交易")
                        return None
                else:
                    self.logger.warning(f"🚫 {symbol} 余额不足以支付1张保证金，放弃")
                    return None

            position_size = target_sz

            # 计算订单价值和保证金
            order_value = curr_price * position_size
            margin = order_value / self.leverage

            # 打印详细的资金计算信息
            self.logger.info("=" * 80)
            self.logger.info("💰 [资金计算] 仓位信息")
            self.logger.info("-" * 80)
            self.logger.info(f"总资金:      {self.total_capital:.2f} USDT")
            self.logger.info(f"风险比例:    {self.risk_per_position:.2%}")
            self.logger.info(f"单笔风险:    {risk_amount:.4f} USDT")
            self.logger.info(f"止损幅度:    {self.stop_loss_pct:.2%}")
            self.logger.info(f"止损距离:    {stop_distance:.6f} USDT")
            self.logger.info("-" * 80)
            self.logger.info(f"当前价格:    {curr_price:.6f} USDT")
            self.logger.info(f"仓位大小:    {position_size:.6f}")
            self.logger.info(f"订单价值:    {order_value:.2f} USDT")
            self.logger.info(f"杠杆倍数:    {self.leverage}x")
            self.logger.info(f"保证金占用:  {margin:.2f} USDT")
            self.logger.info("-" * 80)
            self.logger.info(f"预计最多开仓数: {int(self.total_capital / margin)} 单")
            self.logger.info(f"当前配置最大仓位: {self.max_positions} 单")
            self.logger.info("=" * 80)

            self.logger.info(f"🎯 [趋势信号] {symbol} {side} 价格={curr_price:.4f} ADX={curr_adx:.1f}")

            return {
                "symbol": symbol,
                "side": side,
                "type": "market",
                "size": f"{position_size:.4f}",
                "leverage": self.leverage,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "reason": reason  # 🔥 使用包含 EMA 差距的详细原因
            }

        except Exception as e:
            self.logger.error(f"❌ 生成趋势信号失败 {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def evaluate_position(self, symbol: str) -> Dict:
        """
        评估持仓表现 (增强版：加入趋势反转检测)
        供 Scheduler 定时调用 (默认每15分钟)
        """
        try:
            # 1. 获取当前持仓
            pos = self.context.get_position(symbol)
            if not pos or float(pos.quantity) == 0:
                return {"action": "hold", "reason": "无持仓", "should_rebalance": False}

            # 2. 获取实时行情
            ticker = await self.om.client.get_ticker(symbol)
            if not ticker:
                return {"action": "hold", "reason": "无法获取价格", "should_rebalance": False}

            # 兼容处理 Ticker 格式
            t_data = ticker[0] if isinstance(ticker, list) else ticker
            curr_price = float(t_data.get("last", 0))

            if curr_price == 0:
                return {"action": "hold", "reason": "价格无效", "should_rebalance": False}

            # 3. 计算盈亏 (PnL)
            entry_price = float(pos.entry_price) if pos.entry_price else 0
            quantity = float(pos.quantity)

            # 确定持仓方向
            is_long = quantity > 0

            if is_long:
                pnl_pct = (curr_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - curr_price) / entry_price

            # --- A. 硬性止盈止损检查 (优先级最高) ---
            if pnl_pct <= -self.stop_loss_pct:
                return {
                    "action": "close",
                    "reason": f"🛑 止损触发 (当前: {pnl_pct:.2%}, 阈值: -{self.stop_loss_pct:.2%})",
                    "pnl_pct": pnl_pct,
                    "should_rebalance": True
                }

            if pnl_pct >= self.take_profit_pct:
                return {
                    "action": "close",
                    "reason": f"🎉 止盈触发 (当前: {pnl_pct:.2%}, 阈值: {self.take_profit_pct:.2%})",
                    "pnl_pct": pnl_pct,
                    "should_rebalance": True
                }

            # --- B. 趋势健康度检查 (关键新增逻辑) ---
            # 重新获取 K 线，判断趋势是否已经反转
            try:
                klines = await self.om.client.get_candlesticks(symbol, bar=self.trend_period, limit=50)
                if klines and len(klines) >= 50:
                    df = indicators.normalize_klines(klines)
                    ema20 = indicators.calculate_ema(df, 20).iloc[-1]
                    ema50 = indicators.calculate_ema(df, 50).iloc[-1]

                    # 💡 逻辑 1: 均线反转 (Death Cross)
                    # 如果做多，但 EMA20 跌破 EMA50，说明趋势变成空头 -> 平仓
                    if is_long and ema20 < ema50:
                        return {
                            "action": "close",
                            "reason": f"📉 趋势反转: EMA20死叉EMA50 (价格: {curr_price:.4f})",
                            "pnl_pct": pnl_pct,
                            "should_rebalance": True
                        }
                    # 如果做空，但 EMA20 突破 EMA50，说明趋势变成多头 -> 平仓
                    elif not is_long and ema20 > ema50:
                        return {
                            "action": "close",
                            "reason": f"📈 趋势反转: EMA20金叉EMA50 (价格: {curr_price:.4f})",
                            "pnl_pct": pnl_pct,
                            "should_rebalance": True
                        }

                    # 💡 逻辑 2: 价格跌破关键均线 (弱势离场)
                    # 如果做多，价格跌破 EMA50，即使没到止损也先跑
                    if is_long and curr_price < ema50:
                         return {
                            "action": "close",
                            "reason": f"🏃 跌破趋势线: 价格({curr_price:.4f}) < EMA50({ema50:.4f})",
                            "pnl_pct": pnl_pct,
                            "should_rebalance": True
                        }
                    # 如果做空，价格站上 EMA50
                    elif not is_long and curr_price > ema50:
                        return {
                            "action": "close",
                            "reason": f"🏃 突破趋势线: 价格({curr_price:.4f}) > EMA50({ema50:.4f})",
                            "pnl_pct": pnl_pct,
                            "should_rebalance": True
                        }

            except Exception as e:
                self.logger.warning(f"⚠️ 趋势检查失败，仅依赖PnL: {e}")

            # --- C. 滞涨检查 (可选) ---
            # 如果持仓很久但这期间微亏且趋势不明显，可以考虑换仓
            if pnl_pct < self.min_profit_threshold and pnl_pct < -0.005:
                return {
                    "action": "close",
                    "reason": f"盈利不足且趋势不明 (盈亏: {pnl_pct:.2%})",
                    "pnl_pct": pnl_pct,
                    "should_rebalance": True
                }

            return {
                "action": "hold",
                "reason": f"持仓正常 (盈亏: {pnl_pct:.2%})",
                "pnl_pct": pnl_pct,
                "should_rebalance": False
            }

        except Exception as e:
            self.logger.error(f"❌ 评估持仓 {symbol} 失败: {e}")
            import traceback
            traceback.print_exc()
            return {"action": "hold", "reason": f"评估失败: {str(e)}", "should_rebalance": False}

    async def run_tick(self):
        """每轮Tick执行（由Scheduler调用）"""
        pass

    async def shutdown(self):
        """策略停止"""
        self.logger.info("🛑 多币种趋势策略停止")
