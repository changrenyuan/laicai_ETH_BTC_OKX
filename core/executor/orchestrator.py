"""
🎼 Executor Orchestrator - 执行器编排器
管理和协调多个执行器
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from enum import Enum

from core.executor.executor_base import ExecutorBase, ExecutorStatus
from core.events.event_base import Event, EventType


class OrchestratorStatus(Enum):
    """编排器状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class ExecutorOrchestrator:
    """
    执行器编排器
    
    功能：
    - 管理多个执行器
    - 执行器生命周期管理
    - 执行器之间的协调
    - 全局风险控制
    """

    def __init__(self, max_concurrent_executors: int = 10):
        self.max_concurrent_executors = max_concurrent_executors
        self.logger = logging.getLogger(__name__)
        
        # 执行器管理
        self.executors: Dict[str, ExecutorBase] = {}
        self.active_executors: Dict[str, ExecutorBase] = {}
        self.completed_executors: Dict[str, ExecutorBase] = {}
        self.failed_executors: Dict[str, ExecutorBase] = {}
        
        # 状态
        self.status = OrchestratorStatus.IDLE
        self._stop_event = asyncio.Event()
        self._orchestration_task: Optional[asyncio.Task] = None
        
        # 统计
        self.total_executors = 0
        self.success_count = 0
        self.failure_count = 0
        
        # 事件监听
        self._event_listeners: List[Callable] = []

    def add_executor(self, executor: ExecutorBase) -> str:
        """
        添加执行器
        
        Returns:
            str: 执行器 ID
        """
        executor_id = executor.executor_id
        self.executors[executor_id] = executor
        self.total_executors += 1
        
        # 添加事件监听
        executor.add_event_listener(self._on_executor_event)
        
        self.logger.info(f"➕ 添加执行器: {executor_id}")
        return executor_id

    async def start(self):
        """启动编排器"""
        if self.status == OrchestratorStatus.RUNNING:
            self.logger.warning("⚠️ 编排器已在运行")
            return
        
        self.status = OrchestratorStatus.RUNNING
        self._stop_event.clear()
        
        # 启动编排任务
        self._orchestration_task = asyncio.create_task(self._orchestration_loop())
        
        self.logger.info(f"🚀 编排器启动（最大并发: {self.max_concurrent_executors}）")

    async def stop(self):
        """停止编排器"""
        if self.status != OrchestratorStatus.RUNNING:
            return
        
        self.status = OrchestratorStatus.STOPPED
        self._stop_event.set()
        
        # 停止所有活动执行器
        for executor_id, executor in list(self.active_executors.items()):
            await executor.stop("orchestrator_stopped")
        
        # 停止编排任务
        if self._orchestration_task:
            self._orchestration_task.cancel()
            try:
                await self._orchestration_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("🛑 编排器停止")

    async def pause(self):
        """暂停编排器"""
        if self.status != OrchestratorStatus.RUNNING:
            return
        
        self.status = OrchestratorStatus.PAUSED
        self.logger.info("⏸️ 编排器暂停")

    async def resume(self):
        """恢复编排器"""
        if self.status != OrchestratorStatus.PAUSED:
            return
        
        self.status = OrchestratorStatus.RUNNING
        self.logger.info("▶️ 编排器恢复")

    async def _orchestration_loop(self):
        """编排循环"""
        while not self._stop_event.is_set():
            try:
                if self.status != OrchestratorStatus.RUNNING:
                    await asyncio.sleep(1)
                    continue
                
                # 检查并发限制
                if len(self.active_executors) < self.max_concurrent_executors:
                    # 启动待执行器
                    await self._start_pending_executors()
                
                # 清理已完成执行器
                self._cleanup_executors()
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 编排循环错误: {e}")
                await asyncio.sleep(1)

    async def _start_pending_executors(self):
        """启动待执行器"""
        # 获取待启动的执行器（状态为 IDLE）
        pending_executors = [
            executor
            for executor_id, executor in self.executors.items()
            if executor.status == ExecutorStatus.IDLE
        ]
        
        slots_available = self.max_concurrent_executors - len(self.active_executors)
        
        for executor in pending_executors[:slots_available]:
            try:
                await executor.start()
                self.active_executors[executor.executor_id] = executor
                self.logger.info(f"🚀 启动执行器: {executor.executor_id}")
            except Exception as e:
                self.logger.error(f"❌ 启动执行器失败 {executor.executor_id}: {e}")

    def _cleanup_executors(self):
        """清理已完成执行器"""
        # 移除已完成的执行器
        to_remove = []
        
        for executor_id, executor in self.active_executors.items():
            if executor.status in [
                ExecutorStatus.COMPLETED,
                ExecutorStatus.FAILED,
                ExecutorStatus.CANCELLED
            ]:
                to_remove.append(executor_id)
                
                # 分类统计
                if executor.status == ExecutorStatus.COMPLETED:
                    self.completed_executors[executor_id] = executor
                    self.success_count += 1
                else:
                    self.failed_executors[executor_id] = executor
                    self.failure_count += 1
        
        for executor_id in to_remove:
            del self.active_executors[executor_id]

    async def _on_executor_event(self, event: Event):
        """处理执行器事件"""
        self.logger.info(f"📢 执行器事件: {event.type.value} - {event.data}")
        
        # 转发事件
        await self._emit_event(event)
        
        # 特殊事件处理
        if event.type == EventType.EXECUTOR_FAILED:
            executor_id = event.data.get("executor_id")
            self.logger.error(f"❌ 执行器失败: {executor_id}")

    # ========== 执行器控制 ==========

    async def stop_executor(self, executor_id: str, reason: str = "user_cancelled"):
        """停止指定执行器"""
        if executor_id in self.active_executors:
            await self.active_executors[executor_id].stop(reason)
            self.logger.info(f"🛑 停止执行器: {executor_id}")

    async def pause_executor(self, executor_id: str):
        """暂停指定执行器"""
        # TODO: 实现暂停功能
        self.logger.info(f"⏸️ 暂停执行器: {executor_id}")

    async def resume_executor(self, executor_id: str):
        """恢复指定执行器"""
        # TODO: 实现恢复功能
        self.logger.info(f"▶️ 恢复执行器: {executor_id}")

    # ========== 查询 ==========

    def get_executor_status(self, executor_id: str) -> Optional[dict]:
        """获取执行器状态"""
        if executor_id in self.executors:
            return self.executors[executor_id].get_status()
        return None

    def get_all_executors_status(self) -> Dict[str, dict]:
        """获取所有执行器状态"""
        return {
            executor_id: executor.get_status()
            for executor_id, executor in self.executors.items()
        }

    def get_orchestrator_status(self) -> dict:
        """获取编排器状态"""
        return {
            "status": self.status.value,
            "total_executors": self.total_executors,
            "active_executors": len(self.active_executors),
            "completed_executors": len(self.completed_executors),
            "failed_executors": len(self.failed_executors),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "max_concurrent": self.max_concurrent_executors
        }

    # ========== 事件系统 ==========

    def add_event_listener(self, listener: Callable):
        """添加事件监听器"""
        self._event_listeners.append(listener)

    async def _emit_event(self, event: Event):
        """发送事件"""
        for listener in self._event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                self.logger.error(f"❌ 事件监听器错误: {e}")

    # ========== 工厂方法 ==========

    @staticmethod
    def create_order_executor(
        exchange,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "limit",
        **kwargs
    ) -> "ExecutorBase":
        """创建订单执行器"""
        from core.executor.executor_base import ExecutorConfig
        from core.executor.order_executor import OrderExecutor
        
        config = ExecutorConfig(
            exchange=exchange,
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            order_type=order_type,
            **kwargs
        )
        return OrderExecutor(config)

    @staticmethod
    def create_dca_executor(
        exchange,
        symbol: str,
        side: str,
        size: float,
        num_orders: int = 5,
        time_interval: int = 60,
        **kwargs
    ) -> "ExecutorBase":
        """创建定投执行器"""
        from core.executor.executor_base import ExecutorConfig
        from core.executor.position_executor import DCAExecutor
        
        config = ExecutorConfig(
            exchange=exchange,
            symbol=symbol,
            side=side,
            size=size,
            **kwargs
        )
        return DCAExecutor(config, num_orders=num_orders, time_interval=time_interval)

    @staticmethod
    def create_twap_executor(
        exchange,
        symbol: str,
        side: str,
        size: float,
        duration: int = 300,
        num_orders: int = 10,
        **kwargs
    ) -> "ExecutorBase":
        """创建 TWAP 执行器"""
        from core.executor.executor_base import ExecutorConfig
        from core.executor.position_executor import TWAPExecutor
        
        config = ExecutorConfig(
            exchange=exchange,
            symbol=symbol,
            side=side,
            size=size,
            **kwargs
        )
        return TWAPExecutor(config, duration=duration, num_orders=num_orders)

    @staticmethod
    def create_grid_executor(
        exchange,
        symbol: str,
        side: str,
        size: float,
        grid_upper: float,
        grid_lower: float,
        grid_count: int = 10,
        **kwargs
    ) -> "ExecutorBase":
        """创建网格执行器"""
        from core.executor.executor_base import ExecutorConfig
        from core.executor.position_executor import GridExecutor
        
        config = ExecutorConfig(
            exchange=exchange,
            symbol=symbol,
            side=side,
            size=size,
            **kwargs
        )
        return GridExecutor(
            config,
            grid_upper=grid_upper,
            grid_lower=grid_lower,
            grid_count=grid_count
        )
