"""
👀 通知器
Telegram / 钉钉通知
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import logging

from enum import Enum


class NotificationLevel(Enum):
    """通知级别"""

    INFO = "info"  # 信息
    WARNING = "warning"  # 警告
    ERROR = "error"  # 错误
    CRITICAL = "critical"  # 紧急


@dataclass
class Notification:
    """通知"""

    level: NotificationLevel
    message: str
    timestamp: datetime
    source: str = ""  # 来源


class Notifier:
    """
    通知器类
    发送各种通知
    """

    def __init__(self, config: dict):
        self.config = config

        self.logger = logging.getLogger(__name__)

        # 通知历史
        self.notification_history: List[Notification] = []

        # 通知配置
        self.enabled = config.get("enabled", True)
        self.telegram_enabled = config.get("telegram_enabled", False)
        self.dingtalk_enabled = config.get("dingtalk_enabled", False)

        # Telegram 配置
        self.telegram_bot_token = config.get("telegram_bot_token", "")
        self.telegram_chat_id = config.get("telegram_chat_id", "")

        # 钉钉配置
        self.dingtalk_webhook = config.get("dingtalk_webhook", "")

    async def send_alert(
        self,
        message: str,
        level: str = "info",
        source: str = "",
    ) -> bool:
        """
        发送告警

        Args:
            message: 消息内容
            level: 级别 (info, warning, error, critical)
            source: 来源

        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return False

        try:
            # 转换级别
            notification_level = NotificationLevel(level.lower())

            # 创建通知对象
            notification = Notification(
                level=notification_level,
                message=message,
                timestamp=datetime.now(),
                source=source,
            )

            # 记录历史
            self.notification_history.append(notification)

            if len(self.notification_history) > 1000:
                self.notification_history.pop(0)

            # 发送通知
            success = False

            if self.telegram_enabled:
                telegram_success = await self._send_telegram(message, notification_level)
                success = success or telegram_success

            if self.dingtalk_enabled:
                dingtalk_success = await self._send_dingtalk(message, notification_level)
                success = success or dingtalk_success

            # 如果没有启用任何通知渠道，至少记录日志
            if not success:
                self._log_notification(notification)

            return success

        except Exception as e:
            self.logger.error(f"Failed to send alert: {e}")
            return False

    async def _send_telegram(
        self,
        message: str,
        level: NotificationLevel,
    ) -> bool:
        """发送 Telegram 通知"""
        if not self.telegram_enabled:
            return False

        try:
            # TODO: 实现 Telegram 发送逻辑
            # import aiohttp
            # url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            # ...

            self.logger.info(f"Telegram notification: {message}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send Telegram notification: {e}")
            return False

    async def _send_dingtalk(
        self,
        message: str,
        level: NotificationLevel,
    ) -> bool:
        """发送钉钉通知"""
        if not self.dingtalk_enabled:
            return False

        try:
            # TODO: 实现钉钉发送逻辑
            # import aiohttp
            # ...

            self.logger.info(f"DingTalk notification: {message}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send DingTalk notification: {e}")
            return False

    def _log_notification(self, notification: Notification):
        """记录通知到日志"""
        level_map = {
            NotificationLevel.INFO: logging.INFO,
            NotificationLevel.WARNING: logging.WARNING,
            NotificationLevel.ERROR: logging.ERROR,
            NotificationLevel.CRITICAL: logging.CRITICAL,
        }

        log_level = level_map.get(notification.level, logging.INFO)
        self.logger.log(log_level, f"Notification: {notification.message}")

    async def send_startup_notification(self):
        """发送启动通知"""
        await self.send_alert(
            "🚀 Trading System Started",
            level="info",
            source="system",
        )

    async def send_shutdown_notification(self):
        """发送关闭通知"""
        await self.send_alert(
            "⏹️ Trading System Stopped",
            level="info",
            source="system",
        )

    async def send_error_notification(self, error: str):
        """发送错误通知"""
        await self.send_alert(
            f"❌ Error: {error}",
            level="error",
            source="system",
        )

    async def send_trade_notification(
        self,
        action: str,
        symbol: str,
        quantity: float,
        price: float,
    ):
        """发送交易通知"""
        message = f"📊 Trade: {action.upper()} {quantity} {symbol} @ ${price:.2f}"
        await self.send_alert(
            message,
            level="info",
            source="trade",
        )

    async def send_pnl_notification(self, pnl: float, funding: float):
        """发送盈亏通知"""
        emoji = "📈" if pnl >= 0 else "📉"
        message = f"{emoji} PnL Update: Total=${pnl:.2f}, Funding=${funding:.2f}"
        await self.send_alert(
            message,
            level="info",
            source="pnl",
        )

    def get_notification_history(
        self,
        level: Optional[NotificationLevel] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        获取通知历史

        Args:
            level: 可选，指定级别
            limit: 数量限制

        Returns:
            List[Dict]: 通知历史
        """
        history = self.notification_history

        if level:
            history = [n for n in history if n.level == level]

        history = history[-limit:]

        return [
            {
                "timestamp": n.timestamp.isoformat(),
                "level": n.level.value,
                "message": n.message,
                "source": n.source,
            }
            for n in history
        ]

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "telegram_enabled": self.telegram_enabled,
            "dingtalk_enabled": self.dingtalk_enabled,
            "notification_count": len(self.notification_history),
        }
