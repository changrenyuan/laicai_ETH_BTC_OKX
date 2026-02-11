"""
🛡️ RiskManager - 统一风控管理器
=====================================
整合所有风控模块，提供统一的交易审批接口
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

from core.context import Context
from core.events import EventType, RiskEvent

from .margin_guard import MarginGuard, MarginCheckResult
from .fund_guard import FundGuard
from .liquidity_guard import LiquidityGuard
from .circuit_breaker import CircuitBreaker
from .exchange_guard import ExchangeGuard


class RiskManager:
    """
    风控管理器 - 整合所有风控模块

    职责：
    1. 交易信号审批
    2. 多维度风险检查
    3. 熔断保护
    """

    def __init__(
        self,
        config: Dict,
        margin_guard: MarginGuard,
        fund_guard: FundGuard,
        liquidity_guard: LiquidityGuard,
        circuit_breaker: CircuitBreaker,
        exchange_guard: ExchangeGuard
    ):
        self.config = config
        self.logger = logging.getLogger("RiskManager")

        # 注入各个风控模块
        self.margin_guard = margin_guard
        self.fund_guard = fund_guard
        self.liquidity_guard = liquidity_guard
        self.circuit_breaker = circuit_breaker
        self.exchange_guard = exchange_guard

        # 风控配置
        self.max_position_risk = config.get("max_position_risk", 0.10)  # 单笔最大风险 10%
        self.max_total_risk = config.get("max_total_risk", 0.30)  # 总风险 30%
        self.max_positions = config.get("max_positions", 5)  # 最多持仓数

        # 交易统计
        self.daily_trades = 0
        self.daily_loss = 0.0
        self.last_reset_date = datetime.now().date()

        self.logger.info("✅ RiskManager 初始化完成")

    async def check_order(self, signal: Dict) -> Dict:
        """
        核心方法：审批交易信号

        Args:
            signal: 交易信号，包含 symbol, side, size, leverage 等

        Returns:
            {
                "approved": bool,  # 是否通过
                "modified_size": float,  # 修改后的数量
                "reason": str  # 原因说明
            }
        """
        try:
            self.logger.info(f"🛡️ [风控] 审批信号: {signal.get('symbol')} {signal.get('side')} {signal.get('size')}")

            # 1. 全局熔断检查
            if self.circuit_breaker.is_triggered():
                return {
                    "approved": False,
                    "modified_size": 0,
                    "reason": "Circuit breaker triggered"
                }

            # 2. 交易所连接检查
            if not self.exchange_guard.is_healthy():
                return {
                    "approved": False,
                    "modified_size": 0,
                    "reason": "Exchange connection unstable"
                }

            # 3. 流动性检查（如果需要）
            # symbol = signal.get("symbol")
            # liquidity_check = await self.liquidity_guard.check_depth(symbol, signal.get("size"))
            # if not liquidity_check["ok"]:
            #     return {
            #         "approved": False,
            #         "modified_size": 0,
            #         "reason": f"Insufficient liquidity: {liquidity_check['reason']}"
            #     }

            # 4. 仓位数量检查
            # context 需要从外部注入，这里暂时跳过

            # 5. 通过审批
            self.logger.info(f"✅ [风控] 审批通过")
            return {
                "approved": True,
                "modified_size": float(signal.get("size", 0)),
                "reason": "Approved"
            }

        except Exception as e:
            self.logger.error(f"❌ [风控] 审批异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "approved": False,
                "modified_size": 0,
                "reason": f"Risk check error: {str(e)}"
            }

    async def approve(self, signal: Dict) -> Dict:
        """
        备用方法：审批交易信号（与 check_order 功能相同）
        """
        return await self.check_order(signal)

    async def check_margin_ratio(self, context: Context) -> MarginCheckResult:
        """
        检查保证金率

        Args:
            context: 上下文

        Returns:
            MarginCheckResult: 保证金检查结果
        """
        return await self.margin_guard.check(context)

    async def check_fund_balance(self, context: Context) -> Dict:
        """
        检查资金余额

        Args:
            context: 上下文

        Returns:
            Dict: 资金检查结果
        """
        # 调用 FundGuard 检查
        result = await self.fund_guard.check_balance(context)
        return result

    def record_trade(self, pnl: float):
        """记录交易结果"""
        self.daily_trades += 1
        if pnl < 0:
            self.daily_loss += abs(pnl)

        # 检查是否需要重置
        now = datetime.now().date()
        if now != self.last_reset_date:
            self.reset_daily_stats()

    def reset_daily_stats(self):
        """重置每日统计"""
        self.daily_trades = 0
        self.daily_loss = 0.0
        self.last_reset_date = datetime.now().date()
        self.logger.info("🔄 [风控] 每日统计已重置")

    def get_stats(self) -> Dict:
        """获取风控统计"""
        return {
            "daily_trades": self.daily_trades,
            "daily_loss": self.daily_loss,
            "circuit_breaker_triggered": self.circuit_breaker.is_triggered(),
            "exchange_healthy": self.exchange_guard.is_healthy(),
        }

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "max_position_risk": self.max_position_risk,
            "max_total_risk": self.max_total_risk,
            "max_positions": self.max_positions,
            "daily_trades": self.daily_trades,
            "daily_loss": self.daily_loss,
            "stats": self.get_stats(),
        }
