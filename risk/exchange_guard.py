"""
🔥 交易所防护
交易所异常 / API错误监控
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from core.events import EventType


@dataclass
class ErrorRecord:
    """错误记录"""

    timestamp: datetime
    error_type: str
    message: str
    retry_count: int


class ExchangeGuard:
    """
    交易所防护类
    监控API错误和异常
    """

    def __init__(self, config: dict):
        self.config = config
        self.max_api_errors = config.get("max_api_errors", 5)
        self.api_error_window = config.get("api_error_window", 60)
        self.max_order_rejects = config.get("max_order_rejects", 3)
        self.order_timeout = config.get("order_timeout", 10)
        self.websocket_disconnect_threshold = config.get("websocket_disconnect_threshold", 3)
        self.auto_retry = config.get("auto_retry", True)
        self.retry_delay = config.get("retry_delay", 5)
        self.max_retries = config.get("max_retries", 3)

        self.logger = logging.getLogger(__name__)

        # 状态追踪
        self.error_records: List[ErrorRecord] = []
        self.order_rejects: int = 0
        self.websocket_disconnects: int = 0
        self.last_disconnect_time: Optional[datetime] = None
        self.is_exchange_healthy: bool = True

    async def check_api_error(self, error: Exception) -> bool:
        """
        检查API错误

        Args:
            error: 错误对象

        Returns:
            bool: 是否应该停止交易
        """
        # 记录错误
        record = ErrorRecord(
            timestamp=datetime.now(),
            error_type=type(error).__name__,
            message=str(error),
            retry_count=0,
        )
        self.error_records.append(record)

        # 计算窗口内的错误数
        recent_errors = self._get_recent_errors(
            window_seconds=self.api_error_window
        )

        if len(recent_errors) >= self.max_api_errors:
            self.is_exchange_healthy = False
            self.logger.error(
                f"API error limit exceeded: {len(recent_errors)} >= {self.max_api_errors}"
            )
            return True

        return False

    async def check_order_reject(self, reason: str) -> bool:
        """
        检查订单拒绝

        Args:
            reason: 拒绝原因

        Returns:
            bool: 是否应该停止交易
        """
        self.order_rejects += 1

        if self.order_rejects >= self.max_order_rejects:
            self.is_exchange_healthy = False
            self.logger.error(
                f"Order reject limit exceeded: {self.order_rejects} >= {self.max_order_rejects}"
            )
            return True

        return False

    async def check_websocket_disconnect(self) -> bool:
        """
        检查WebSocket断连

        Returns:
            bool: 是否应该停止交易
        """
        self.websocket_disconnects += 1
        self.last_disconnect_time = datetime.now()

        # 检查是否在短时间内多次断连
        if self.websocket_disconnects >= self.websocket_disconnect_threshold:
            self.is_exchange_healthy = False
            self.logger.error(
                f"WebSocket disconnect limit exceeded: {self.websocket_disconnects} >= {self.websocket_disconnect_threshold}"
            )
            return True

        # 重置计数器（1小时后）
        if self._get_time_since_last_disconnect() > 3600:
            self.websocket_disconnects = 0

        return False

    async def should_retry(self, error: Exception) -> bool:
        """
        判断是否应该重试

        Args:
            error: 错误对象

        Returns:
            bool: 是否应该重试
        """
        if not self.auto_retry:
            return False

        # 检查重试次数
        recent_errors = [
            r
            for r in self.error_records
            if r.message == str(error)
        ]

        if recent_errors:
            last_error = recent_errors[-1]
            if last_error.retry_count >= self.max_retries:
                self.logger.warning(f"Max retries exceeded for error: {error}")
                return False

            last_error.retry_count += 1

        return True

    async def get_retry_delay(self) -> int:
        """
        获取重试延迟

        Returns:
            int: 延迟秒数
        """
        return self.retry_delay

    def _get_recent_errors(self, window_seconds: int) -> List[ErrorRecord]:
        """获取最近的错误记录"""
        cutoff_time = datetime.now() - timedelta(seconds=window_seconds)
        return [
            r
            for r in self.error_records
            if r.timestamp >= cutoff_time
        ]

    def _get_time_since_last_disconnect(self) -> float:
        """获取距离上次断连的时间（秒）"""
        if not self.last_disconnect_time:
            return float("inf")
        return (datetime.now() - self.last_disconnect_time).total_seconds()

    def reset(self):
        """重置状态"""
        self.error_records.clear()
        self.order_rejects = 0
        self.websocket_disconnects = 0
        self.last_disconnect_time = None
        self.is_exchange_healthy = True
        self.logger.info("Exchange guard state reset")

    def to_dict(self) -> dict:
        """转换为字典"""
        recent_errors = self._get_recent_errors(self.api_error_window)
        return {
            "is_healthy": self.is_exchange_healthy,
            "recent_errors_count": len(recent_errors),
            "max_api_errors": self.max_api_errors,
            "order_rejects": self.order_rejects,
            "max_order_rejects": self.max_order_rejects,
            "websocket_disconnects": self.websocket_disconnects,
            "websocket_disconnect_threshold": self.websocket_disconnect_threshold,
            "auto_retry": self.auto_retry,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
        }
