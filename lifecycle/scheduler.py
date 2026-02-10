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
        
        await scheduler.start()
        Dashboard.log("✅ 调度器已启动", "SUCCESS")
