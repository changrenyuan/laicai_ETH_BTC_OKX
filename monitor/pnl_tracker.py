"""
👀 PnL 跟踪器
非方向性 PnL 计算
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from core.context import Context, Position


@dataclass
class PnLRecord:
    """PnL 记录"""

    timestamp: datetime
    symbol: str
    realized_pnl: float
    unrealized_pnl: float
    funding_income: float
    total_pnl: float


class PnLTracker:
    """
    PnL 跟踪器
    计算和跟踪非方向性盈亏
    """

    def __init__(self, config: dict):
        self.config = config

        self.logger = logging.getLogger(__name__)

        # PnL 记录
        self.pnl_history: List[PnLRecord] = []
        self.daily_pnl: Dict[str, float] = {}  # {date: total_pnl}

    async def calculate_realized_pnl(
        self,
        symbol: str,
        context: Context,
    ) -> float:
        """
        计算已实现盈亏

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            float: 已实现盈亏
        """
        # 已实现盈亏 = 交易盈亏 + 资金费收益
        total_pnl = context.metrics.total_pnl
        funding_income = context.metrics.total_funding_earned

        realized_pnl = total_pnl - funding_income

        return realized_pnl

    async def calculate_unrealized_pnl(
        self,
        symbol: str,
        context: Context,
    ) -> float:
        """
        计算未实现盈亏

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            float: 未实现盈亏
        """
        position = context.get_position(symbol)

        if not position or position.quantity == 0:
            return 0.0

        # 未实现盈亏 = 持仓盈亏
        # Cash & Carry 策略中，现货和合约对冲，主要盈亏来自资金费
        # 持仓的盈亏应该接近于 0（因为现货和合约对冲）

        return position.unrealized_pnl

    async def calculate_total_pnl(
        self,
        symbol: str,
        context: Context,
    ) -> float:
        """
        计算总盈亏

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            float: 总盈亏
        """
        realized_pnl = await self.calculate_realized_pnl(symbol, context)
        unrealized_pnl = await self.calculate_unrealized_pnl(symbol, context)
        funding_income = context.metrics.total_funding_earned

        total_pnl = realized_pnl + unrealized_pnl + funding_income

        return total_pnl

    async def record_pnl(
        self,
        symbol: str,
        context: Context,
    ):
        """
        记录 PnL

        Args:
            symbol: 交易品种
            context: 上下文
        """
        realized_pnl = await self.calculate_realized_pnl(symbol, context)
        unrealized_pnl = await self.calculate_unrealized_pnl(symbol, context)
        funding_income = context.metrics.total_funding_earned
        total_pnl = await self.calculate_total_pnl(symbol, context)

        record = PnLRecord(
            timestamp=datetime.now(),
            symbol=symbol,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            funding_income=funding_income,
            total_pnl=total_pnl,
        )

        self.pnl_history.append(record)

        # 限制历史记录数量
        if len(self.pnl_history) > 1000:
            self.pnl_history.pop(0)

        # 更新日 PnL
        today = datetime.now().date()
        if today not in self.daily_pnl:
            self.daily_pnl[today] = 0.0

        self.daily_pnl[today] = total_pnl

        self.logger.info(
            f"PnL recorded for {symbol}: "
            f"realized=${realized_pnl:.2f}, "
            f"unrealized=${unrealized_pnl:.2f}, "
            f"funding=${funding_income:.2f}, "
            f"total=${total_pnl:.2f}"
        )

    def get_daily_pnl(self, days: int = 1) -> List[Dict]:
        """
        获取日 PnL

        Args:
            days: 天数

        Returns:
            List[Dict]: 日 PnL 列表
        """
        cutoff_date = datetime.now().date() - timedelta(days=days)

        daily_pnl_list = []

        for date, pnl in sorted(self.daily_pnl.items()):
            if date >= cutoff_date:
                daily_pnl_list.append({
                    "date": date.isoformat(),
                    "pnl": pnl,
                })

        return daily_pnl_list

    def get_pnl_summary(self) -> Dict:
        """获取 PnL 摘要"""
        if not self.pnl_history:
            return {
                "total_pnl": 0.0,
                "total_realized": 0.0,
                "total_unrealized": 0.0,
                "total_funding": 0.0,
                "daily_pnl": 0.0,
                "record_count": 0,
            }

        latest = self.pnl_history[-1]
        today = datetime.now().date()

        return {
            "total_pnl": latest.total_pnl,
            "total_realized": latest.realized_pnl,
            "total_unrealized": latest.unrealized_pnl,
            "total_funding": latest.funding_income,
            "daily_pnl": self.daily_pnl.get(today, 0.0),
            "record_count": len(self.pnl_history),
        }

    def get_pnl_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        获取 PnL 历史

        Args:
            symbol: 可选，指定交易品种
            limit: 数量限制

        Returns:
            List[Dict]: PnL 历史记录
        """
        history = self.pnl_history

        if symbol:
            history = [r for r in history if r.symbol == symbol]

        history = history[-limit:]

        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "symbol": r.symbol,
                "realized_pnl": r.realized_pnl,
                "unrealized_pnl": r.unrealized_pnl,
                "funding_income": r.funding_income,
                "total_pnl": r.total_pnl,
            }
            for r in history
        ]

    def calculate_win_rate(self) -> float:
        """计算胜率"""
        if not self.daily_pnl:
            return 0.0

        win_days = sum(1 for pnl in self.daily_pnl.values() if pnl > 0)
        total_days = len(self.daily_pnl)

        return win_days / total_days if total_days > 0 else 0.0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "summary": self.get_pnl_summary(),
            "daily_pnl": self.get_daily_pnl(7),
            "win_rate": self.calculate_win_rate(),
        }
