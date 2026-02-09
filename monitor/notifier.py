"""
👀 通知器 (修复版：支持代理)
Telegram / 钉钉通知
"""

import os
import logging
import aiohttp
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

class NotificationLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class Notification:
    level: NotificationLevel
    message: str
    timestamp: datetime
    source: str = ""

class Notifier:
    """通知器类"""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.notification_history: List[Notification] = []

        self.enabled = config.get("enabled", True)
        self.telegram_enabled = config.get("telegram_enabled", False)
        self.dingtalk_enabled = config.get("dingtalk_enabled", False)

        self.telegram_bot_token = config.get("telegram_bot_token", "")
        self.telegram_chat_id = config.get("telegram_chat_id", "")
        self.dingtalk_webhook = config.get("dingtalk_webhook", "")

        # 🔥 新增：自动获取系统代理
        self.proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if self.proxy and self.telegram_enabled:
            self.logger.info(f"Notifier using proxy: {self.proxy}")

    async def send_alert(self, message: str, level: str = "info", source: str = "") -> bool:
        """发送告警"""
        if not self.enabled:
            return False

        try:
            notification_level = NotificationLevel(level.lower())
            notification = Notification(
                level=notification_level,
                message=message,
                timestamp=datetime.now(),
                source=source,
            )
            self.notification_history.append(notification)
            if len(self.notification_history) > 1000:
                self.notification_history.pop(0)

            success = False

            # 并行发送（这里串行即可）
            if self.telegram_enabled:
                if await self._send_telegram(message, notification_level):
                    success = True

            if self.dingtalk_enabled:
                if await self._send_dingtalk(message, notification_level):
                    success = True

            if not success:
                self._log_notification(notification)

            return success

        except Exception as e:
            self.logger.error(f"Failed to send alert: {e}")
            return False

    async def _send_telegram(self, message: str, level: NotificationLevel) -> bool:
        """发送 Telegram 通知 (带代理)"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"

        emoji_map = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.ERROR: "❌",
            NotificationLevel.CRITICAL: "🚨"
        }
        text = f"{emoji_map.get(level, '')} [{level.name}] {message}"

        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            # 🔥 修改点：增加 proxy 参数
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=10,
                    proxy=self.proxy  # <--- 关键！
                ) as resp:
                    if resp.status == 200:
                        self.logger.info("Telegram notification sent")
                        return True
                    else:
                        err = await resp.text()
                        self.logger.error(f"Telegram send failed: {resp.status} - {err}")
                        return False
        except Exception as e:
            self.logger.error(f"Telegram connection error: {e}")
            return False

    async def _send_dingtalk(self, message: str, level: NotificationLevel) -> bool:
        """发送钉钉通知 (钉钉通常不需要代理，但加了也无妨)"""
        if not self.dingtalk_webhook:
            return False

        payload = {
            "msgtype": "text",
            "text": {
                "content": f"[{level.name}] OKXBot:\n{message}"
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.dingtalk_webhook,
                    json=payload,
                    timeout=10,
                    # proxy=self.proxy # 钉钉国内直连通常更快，如果需要代理可取消注释
                ) as resp:
                    if resp.status == 200:
                        self.logger.info("DingTalk notification sent")
                        return True
                    else:
                        err = await resp.text()
                        self.logger.error(f"DingTalk send failed: {resp.status} - {err}")
                        return False
        except Exception as e:
            self.logger.error(f"DingTalk connection error: {e}")
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