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
        self.websocket_disconnect_threshold = config.get(
            "websocket_disconnect_threshold", 3
        )
        self.auto_retry = config.get("auto_retry", True)
        self.retry_delay = config.get("retry_delay", 5)
        self.max_retries = config.get("max_retries", 3)

        self.logger = logging.getLogger(__name__)

        # 状态追踪
        self.error_records: List[ErrorRecord] = []
        self.order_rejects = 0
        self.websocket_disconnects = 0
        self.last_disconnect_time: Optional[datetime] = None
        self.is_exchange_healthy = True

    def check_api_error(self, error: Exception, context: str = "") -> bool:
        """
        检查 API 错误
        返回: 是否需要暂停交易
        """
        self.error_records.append(
            ErrorRecord(
                timestamp=datetime.now(),
                error_type=type(error).__name__,
                message=str(error),
                retry_count=0,
            )
        )

        # 检查错误频率
        recent_errors = self._get_recent_errors(self.api_error_window)
        if len(recent_errors) >= self.max_api_errors:
            self.is_exchange_healthy = False
            self.logger.warning(
                f"Exchange unhealthy: {len(recent_errors)} errors in {self.api_error_window}s"
            )
            return True

        return False

    def report_order_reject(self):
        """报告订单被拒绝"""
        self.order_rejects += 1
        if self.order_rejects >= self.max_order_rejects:
            self.is_exchange_healthy = False
            self.logger.warning(
                f"Exchange unhealthy: {self.order_rejects} order rejects"
            )

    def report_websocket_disconnect(self):
        """报告 WebSocket 断开"""
        self.websocket_disconnects += 1
        self.last_disconnect_time = datetime.now()

        if self.websocket_disconnects >= self.websocket_disconnect_threshold:
            # 检查是否频繁断开（例如 1 分钟内）
            # 这里简化逻辑
            self.logger.warning(
                f"WebSocket disconnected {self.websocket_disconnects} times"
            )

    def _get_recent_errors(self, window_seconds: int) -> List[ErrorRecord]:
        """获取最近的错误记录"""
        cutoff_time = datetime.now() - timedelta(seconds=window_seconds)
        return [r for r in self.error_records if r.timestamp >= cutoff_time]

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
        }

    # ==========================================
    # 🔥 新增/补全的方法 (兼容 main_auto.py)
    # ==========================================

    def record_error(self, msg: str):
        """
        [兼容接口] 记录通用错误
        """
        self.error_records.append(
            ErrorRecord(
                timestamp=datetime.now(),
                error_type="RuntimeError",
                message=msg,
                retry_count=0,
            )
        )
        # 触发健康检查
        recent_errors = self._get_recent_errors(self.api_error_window)
        if len(recent_errors) >= self.max_api_errors:
            self.is_exchange_healthy = False

    def is_healthy(self) -> bool:
        """
        [兼容接口] 获取当前健康状态
        """
        # 简单的一票否决
        return self.is_exchange_healthy