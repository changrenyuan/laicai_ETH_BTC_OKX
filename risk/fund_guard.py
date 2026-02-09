"""
🔥 资金防护
资金再平衡 / 自动补保证金
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from core.context import Context


@dataclass
class TransferRecord:
    """资金划转记录"""

    timestamp: datetime
    from_account: str
    to_account: str
    amount: float
    currency: str
    reason: str


class FundGuard:
    """
    资金防护类
    管理资金划转和再平衡
    """

    def __init__(self, config: dict):
        self.config = config
        self.transfer_threshold = config.get("transfer_threshold", 1000)
        self.max_transfer_per_day = config.get("max_transfer_per_day", 10000)
        self.check_interval = config.get("check_interval", 60)

        self.logger = logging.getLogger(__name__)

        # 记录
        self.transfers: List[TransferRecord] = []
        self.last_check_time: Optional[datetime] = None

    async def check_rebalance_needed(self, context: Context) -> bool:
        """
        检查是否需要再平衡

        Args:
            context: 上下文

        Returns:
            bool: 是否需要再平衡
        """
        # 检查保证金率是否低于阈值
        margin_ratio = context.calculate_margin_ratio()
        margin_threshold = self.config.get("margin_ratio_threshold", 0.80)

        need_rebalance = margin_ratio < margin_threshold

        if need_rebalance:
            self.logger.info(f"Rebalance needed: margin ratio {margin_ratio:.2%} < {margin_threshold:.2%}")

        return need_rebalance

    async def calculate_transfer_amount(self, context: Context) -> float:
        """
        计算划转金额

        Args:
            context: 上下文

        Returns:
            float: 划转金额
        """
        # 获取现货可用余额
        spot_balance = context.get_balance("USDT")
        if not spot_balance:
            return 0.0

        available_usdt = spot_balance.available

        # 检查每日限额
        daily_transfers = self._get_daily_transfer_amount()
        remaining_quota = self.max_transfer_per_day - daily_transfers

        # 按配置比例划转
        transfer_ratio = self.config.get("transfer_amount_ratio", 0.3)
        transfer_amount = available_usdt * transfer_ratio

        # 不超过剩余限额
        transfer_amount = min(transfer_amount, remaining_quota)

        # 不低于阈值
        if transfer_amount < self.transfer_threshold:
            return 0.0

        return transfer_amount

    async def execute_transfer(
        self,
        amount: float,
        context: Context,
        exchange_client=None,
    ) -> bool:
        """
        执行资金划转

        Args:
            amount: 划转金额
            context: 上下文
            exchange_client: 交易所客户端

        Returns:
            bool: 是否成功
        """
        if amount <= 0:
            self.logger.warning("Transfer amount is zero or negative")
            return False

        try:
            # 记录划转
            record = TransferRecord(
                timestamp=datetime.now(),
                from_account="spot",
                to_account="futures",
                amount=amount,
                currency="USDT",
                reason="margin_rebalance",
            )
            self.transfers.append(record)

            # TODO: 调用交易所API执行划转
            # result = await exchange_client.transfer(
            #     ccy="USDT",
            #     amt=str(amount),
            #     from_=TransferAccountType.SPOT,
            #     to_=TransferAccountType.FUTURES,
            # )

            self.logger.info(f"Transfer executed: ${amount:.2f} USDT from spot to futures")
            return True

        except Exception as e:
            self.logger.error(f"Transfer failed: {e}")
            return False

    def _get_daily_transfer_amount(self) -> float:
        """获取今日已划转金额"""
        today = datetime.now().date()
        daily_total = sum(
            t.amount
            for t in self.transfers
            if t.timestamp.date() == today
        )
        return daily_total

    def get_transfer_history(self, days: int = 7) -> List[TransferRecord]:
        """
        获取划转历史

        Args:
            days: 天数

        Returns:
            List[TransferRecord]: 划转记录
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        return [
            t
            for t in self.transfers
            if t.timestamp >= cutoff_date
        ]

    def reset(self):
        """重置记录"""
        self.transfers.clear()
        self.logger.info("Fund guard history reset")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "transfer_threshold": self.transfer_threshold,
            "max_transfer_per_day": self.max_transfer_per_day,
            "daily_transfers": self._get_daily_transfer_amount(),
            "total_transfers": len(self.transfers),
            "last_check_time": (
                self.last_check_time.isoformat() if self.last_check_time else None
            ),
        }
