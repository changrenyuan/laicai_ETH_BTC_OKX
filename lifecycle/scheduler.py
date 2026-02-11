"""
⏰ Scheduler Phase
启动调度器
"""

from monitor.dashboard import Dashboard


class SchedulerLifecycle:
    """Scheduler 生命周期阶段 - 启动调度器"""

    def __init__(self, components: dict):
        self.components = components

    async def run(self):
        """启动调度器"""
        Dashboard.log("【6】启动 Scheduler (调度器)...", "INFO")

        pnl_tracker = self.components["pnl_tracker"]
        scheduler = self.components.get("scheduler")

        if not scheduler:
            from core.scheduler import Scheduler
            scheduler = Scheduler(
                context=self.components["context"],
                fund_guard=self.components["fund_guard"],
                pnl_tracker=pnl_tracker,
                position_manager=self.components["position_manager"]
            )
            self.components["scheduler"] = scheduler

        # 如果有multi_trend_strategy，注册到Scheduler
        multi_trend_strategy = self.components.get("multi_trend_strategy")
        if multi_trend_strategy:
            scheduler.set_multi_trend_strategy(multi_trend_strategy, self.components["client"])
            Dashboard.log("✅ MultiTrendStrategy 已注册到 Scheduler", "SUCCESS")

        await scheduler.start()
        Dashboard.log("✅ 调度器已启动", "SUCCESS")
