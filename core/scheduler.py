"""
🔥 调度器
8h / 1h / 5min 定时任务调度
"""

import asyncio
from typing import Callable, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging


@dataclass
class ScheduledTask:
    """定时任务"""

    name: str
    interval: int  # 执行间隔（秒）
    callback: Callable  # 回调函数
    last_run: datetime = None
    next_run: datetime = None
    enabled: bool = True
    run_immediately: bool = False

    def should_run(self) -> bool:
        """检查是否应该运行"""
        if not self.enabled:
            return False

        if self.run_immediately:
            return True

        if self.next_run is None:
            return True

        return datetime.now() >= self.next_run

    def schedule_next(self):
        """调度下一次运行"""
        now = datetime.now()
        self.last_run = now
        self.next_run = now + timedelta(seconds=self.interval)
        self.run_immediately = False


class Scheduler:
    """
    调度器类
    管理所有定时任务的调度
    """

    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self.is_running = False
        self._stop_event = asyncio.Event()
        self.logger = logging.getLogger(__name__)

    def add_task(
        self,
        name: str,
        interval: int,
        callback: Callable,
        enabled: bool = True,
        run_immediately: bool = False,
    ):
        """
        添加定时任务

        Args:
            name: 任务名称
            interval: 执行间隔（秒）
            callback: 回调函数
            enabled: 是否启用
            run_immediately: 是否立即运行
        """
        task = ScheduledTask(
            name=name,
            interval=interval,
            callback=callback,
            enabled=enabled,
            run_immediately=run_immediately,
        )
        self.tasks[name] = task
        self.logger.info(f"Added scheduled task: {name} (interval: {interval}s)")

    def remove_task(self, name: str):
        """移除定时任务"""
        if name in self.tasks:
            del self.tasks[name]
            self.logger.info(f"Removed scheduled task: {name}")

    def enable_task(self, name: str):
        """启用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = True
            self.logger.info(f"Enabled task: {name}")

    def disable_task(self, name: str):
        """禁用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = False
            self.logger.info(f"Disabled task: {name}")

    def get_task(self, name: str) -> ScheduledTask | None:
        """获取任务"""
        return self.tasks.get(name)

    async def start(self):
        """启动调度器"""
        if self.is_running:
            self.logger.warning("Scheduler is already running")
            return

        self.is_running = True
        self._stop_event.clear()
        self.logger.info("Scheduler started")

        await self._run_loop()

    async def stop(self):
        """停止调度器"""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()
        self.logger.info("Scheduler stopped")

    async def _run_loop(self):
        """主运行循环"""
        while self.is_running:
            try:
                # 检查所有任务
                for task_name, task in self.tasks.items():
                    if task.should_run():
                        await self._execute_task(task)

                # 等待一小段时间再检查
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(5)

    async def _execute_task(self, task: ScheduledTask):
        """执行任务"""
        try:
            self.logger.info(f"Executing task: {task.name}")

            if asyncio.iscoroutinefunction(task.callback):
                await task.callback()
            else:
                task.callback()

            # 调度下一次运行
            task.schedule_next()

            self.logger.info(f"Task completed: {task.name} (next run: {task.next_run})")

        except Exception as e:
            self.logger.error(f"Task execution error ({task.name}): {e}")

    def get_task_status(self) -> Dict[str, Dict]:
        """获取所有任务状态"""
        status = {}
        for name, task in self.tasks.items():
            status[name] = {
                "interval": task.interval,
                "enabled": task.enabled,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
            }
        return status

    def setup_default_tasks(self, context, exchange_client, risk_manager, strategy, execution, notifier):
        """
        设置默认任务
        8h: 资金费率结算检查
        1h: 持仓再平衡检查
        5min: 市场数据更新和持仓监控
        """

        # 5分钟任务：市场数据更新和持仓监控
        self.add_task(
            name="market_update",
            interval=5 * 60,  # 5分钟
            callback=lambda: self._market_update_task(context, exchange_client),
        )

        # 5分钟任务：风险检查
        self.add_task(
            name="risk_check",
            interval=5 * 60,  # 5分钟
            callback=lambda: self._risk_check_task(context, risk_manager, notifier),
        )

        # 1小时任务：持仓再平衡检查
        self.add_task(
            name="rebalance_check",
            interval=60 * 60,  # 1小时
            callback=lambda: self._rebalance_check_task(context, strategy, execution, notifier),
        )

        # 8小时任务：资金费率结算检查
        self.add_task(
            name="funding_settlement",
            interval=8 * 60 * 60,  # 8小时
            callback=lambda: self._funding_settlement_task(context, notifier),
        )

        # 1分钟任务：系统健康检查
        self.add_task(
            name="health_check",
            interval=60,  # 1分钟
            callback=lambda: self._health_check_task(context, notifier),
        )

        self.logger.info("Default tasks setup completed")

    async def _market_update_task(self, context, exchange_client):
        """市场数据更新任务"""
        # 更新市场数据
        instruments = ["BTC-USDT", "ETH-USDT"]
        for symbol in instruments:
            try:
                market_data = await exchange_client.get_market_data(symbol)
                context.update_market_data(market_data)
            except Exception as e:
                print(f"Failed to update market data for {symbol}: {e}")

    async def _risk_check_task(self, context, risk_manager, notifier):
        """风险检查任务"""
        # 运行所有风险检查
        await risk_manager.check_all(context, notifier)

    async def _rebalance_check_task(self, context, strategy, execution, notifier):
        """再平衡检查任务"""
        # 检查是否需要再平衡
        need_rebalance = await strategy.check_rebalance(context)

        if need_rebalance:
            await execution.rebalance_positions(context, notifier)

    async def _funding_settlement_task(self, context, notifier):
        """资金费率结算任务"""
        # 记录资金费收益
        funding_income = await context.calculate_funding_income()
        context.metrics.daily_funding_earned = funding_income
        context.metrics.total_funding_earned += funding_income

        # 发送通知
        if funding_income > 0:
            await notifier.send_alert(
                f"Funding settlement: +${funding_income:.2f}",
                level="info",
            )

    async def _health_check_task(self, context, notifier):
        """系统健康检查任务"""
        # 更新系统运行时间
        uptime = (datetime.now() - context.start_time).total_seconds()
        context.metrics.system_uptime = uptime

        # 检查连接状态
        is_healthy = uptime > 0 and not context.is_emergency

        if not is_healthy:
            await notifier.send_alert(
                "System health check failed!",
                level="warning",
            )
