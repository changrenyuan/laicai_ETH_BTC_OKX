"""
🕐 Time Synchronizer - 时间同步器
确保本地时间与交易所服务器时间同步
"""

import asyncio
import logging
import time
from typing import Optional


class TimeSynchronizer:
    """
    时间同步器
    
    功能：
    - 定期同步交易所服务器时间
    - 计算时间偏移
    - 提供同步后的时间戳
    """

    def __init__(self, sync_interval: int = 60, max_offset: float = 1.0):
        """
        Args:
            sync_interval: 同步间隔（秒）
            max_offset: 最大允许偏移（秒）
        """
        self.sync_interval = sync_interval
        self.max_offset = max_offset
        self.logger = logging.getLogger(__name__)
        
        # 时间偏移（服务器时间 - 本地时间）
        self.time_offset: float = 0.0
        
        # 同步状态
        self.is_syncing = False
        self.last_sync_time: Optional[float] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self, get_server_time_func=None):
        """
        启动时间同步
        
        Args:
            get_server_time_func: 获取服务器时间的异步函数
        """
        if self.is_syncing:
            self.logger.warning("⚠️ 时间同步器已在运行")
            return
        
        self.get_server_time_func = get_server_time_func
        self.is_syncing = True
        self._stop_event.clear()
        
        # 立即同步一次
        await self.sync()
        
        # 启动定期同步
        self._sync_task = asyncio.create_task(self._sync_loop())
        
        self.logger.info(f"✅ 时间同步器启动（间隔: {self.sync_interval}s）")

    async def stop(self):
        """停止时间同步"""
        if not self.is_syncing:
            return
        
        self.is_syncing = False
        self._stop_event.set()
        
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("🔌 时间同步器停止")

    async def _sync_loop(self):
        """同步循环"""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.sync_interval
                )
            except asyncio.TimeoutError:
                await self.sync()

    async def sync(self) -> bool:
        """
        执行时间同步
        
        Returns:
            bool: 是否成功
        """
        if not hasattr(self, 'get_server_time_func') or self.get_server_time_func is None:
            self.logger.warning("⚠️ 未配置获取服务器时间的函数")
            return False
        
        try:
            # 获取服务器时间
            server_time = await self.get_server_time_func()
            
            if not server_time:
                self.logger.warning("⚠️ 获取服务器时间失败")
                return False
            
            # 计算时间偏移
            local_time = time.time()
            self.time_offset = server_time - local_time
            
            self.last_sync_time = time.time()
            
            # 检查偏移是否在可接受范围内
            if abs(self.time_offset) > self.max_offset:
                self.logger.warning(
                    f"⚠️ 时间偏移过大: {self.time_offset:.3f}s "
                    f"(最大允许: {self.max_offset}s)"
                )
            else:
                self.logger.debug(
                    f"✅ 时间同步成功 (偏移: {self.time_offset:.3f}s)"
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 时间同步失败: {e}")
            return False

    async def get_server_time(self) -> float:
        """
        获取同步后的服务器时间
        
        Returns:
            float: 服务器时间戳
        """
        return time.time() + self.time_offset

    def get_time_offset(self) -> float:
        """获取时间偏移"""
        return self.time_offset

    def get_status(self) -> dict:
        """获取同步状态"""
        return {
            "is_syncing": self.is_syncing,
            "time_offset": self.time_offset,
            "last_sync_time": self.last_sync_time,
            "sync_interval": self.sync_interval,
            "max_offset": self.max_offset
        }
