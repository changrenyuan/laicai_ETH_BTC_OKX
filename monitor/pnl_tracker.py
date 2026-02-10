"""
👀 PnL 跟踪器 (Phase 5 实战版)
非方向性 PnL 计算：只关注总权益的增长
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import logging

from core.context import Context

@dataclass
class PnLRecord:
    timestamp: datetime
    total_equity: float    # 总权益 (USDT)
    unrealized_pnl: float  # 未实现盈亏
    day_profit: float      # 当日盈利

class PnLTracker:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.history: List[PnLRecord] = []

        # 初始本金 (建议从 config 读取，这里为演示先写死或动态获取)
        self.initial_capital = 0.0
        self.last_day_equity = 0.0

    def initialize_capital(self, current_equity: float):
        """初始化本金"""
        if self.initial_capital == 0:
            self.initial_capital = current_equity
            self.last_day_equity = current_equity
            self.logger.info(f"💰 Initial Capital Set: ${self.initial_capital:.2f}")

    async def snapshot(self, context: Context):
        """记录当前权益快照"""
        # 计算总权益 = 余额 + 未实现盈亏
        usdt_bal = context.balances.get("USDT")
        if not usdt_bal:
            return

        # 简单版：直接取 total (包含冻结) + 所有持仓 upl
        total_equity = usdt_balance.total # 注意：需确保 upstream data 包含 upl 调整

        # 为了更准确，通常直接用 OKX 接口返回的 eq (Equity) 字段
        # 这里假设 context.metrics 已经存了 total_equity
        # 我们用 context.get_total_equity() 方法

        current_equity = context.get_total_equity()
        if current_equity <= 0: return

        if self.initial_capital == 0:
            self.initialize_capital(current_equity)

        day_profit = current_equity - self.last_day_equity
        total_profit = current_equity - self.initial_capital

        rec = PnLRecord(
            timestamp=datetime.now(),
            total_equity=current_equity,
            unrealized_pnl=0.0, # 需从 positions 聚合
            day_profit=day_profit
        )
        self.history.append(rec)

        self.logger.info(f"📈 PnL Snapshot: Total=${current_equity:.2f} (Profit: ${total_profit:.2f})")

    async def update_pnl(self, position: dict):
        """
        更新 PnL
        在交易完成后调用
        """
        # 这里可以根据 position 信息更新 PnL
        # 暂时留空，实际需要实现详细的 PnL 计算
        self.logger.debug(f"Updating PnL for position: {position}")
        pass