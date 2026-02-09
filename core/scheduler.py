"""
⏰ 调度器 (Phase 5 实战版)
负责定期执行低频任务：资金再平衡、健康检查、每日报告
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Callable

from core.context import Context
from risk.fund_guard import FundGuard
from monitor.pnl_tracker import PnLTracker
from execution.position_manager import PositionManager

class Scheduler:
    """
    调度器类
    """
    def __init__(self,
                 context: Context,
                 fund_guard: FundGuard,
                 pnl_tracker: PnLTracker,
                 position_manager: PositionManager):
        self.context = context
        self.fund_guard = fund_guard
        self.pnl_tracker = pnl_tracker
        self.pos_manager = position_manager
        self.logger = logging.getLogger(__name__)
        self.is_running = False

    async def start(self):
        """启动后台任务"""
        self.is_running = True
        self.logger.info("⏰ 调度器已启动")

        # 启动并发任务循环
        asyncio.create_task(self._run_minutely_tasks()) # 1分钟
        asyncio.create_task(self._run_hourly_tasks())   # 1小时
        asyncio.create_task(self._run_daily_tasks())    # 24小时

    async def stop(self):
        self.is_running = False
        self.logger.info("⏰ 调度器已停止")

    async def _run_minutely_tasks(self):
        """每分钟任务: 保证金检查 (高频安全检查)"""
        while self.is_running:
            try:
                # 1. 资金卫士检查 (自动补仓/止盈)
                await self.fund_guard.check_and_transfer(self.context)

            except Exception as e:
                self.logger.error(f"Minutely task failed: {e}")

            await asyncio.sleep(60)

    async def _run_hourly_tasks(self):
        """每小时任务: 对冲审计 & PnL更新"""
        while self.is_running:
            try:
                # 1. 审计对冲平衡性
                # 假设只跑 ETH-USDT
                self.pos_manager.check_hedge_integrity("ETH-USDT")

                # 2. 更新 PnL
                # (这里简化处理，实际应遍历所有持仓)
                # await self.pnl_tracker.calculate_realized_pnl("ETH-USDT", self.context)

                # 3. 打印心跳日志
                self.logger.info(f"📊 [Hourly] Margin: {self.context.margin_ratio:.2f}")

            except Exception as e:
                self.logger.error(f"Hourly task failed: {e}")

            await asyncio.sleep(3600)

    async def _run_daily_tasks(self):
        """每日任务: 资金费率统计结算"""
        while self.is_running:
            # 简单的每日报告
            self.logger.info("📅 [Daily] Generating report...")
            # Phase 6 可以加个发邮件功能
            await asyncio.sleep(86400)