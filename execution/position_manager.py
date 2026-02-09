"""
✋ 持仓对冲检查器 (Auditor)
只检查，不执行。确保 Spot 数量 == Swap 数量
"""
import logging
from core.context import Context

class PositionManager:
    def __init__(self, context: Context):
        self.context = context
        self.logger = logging.getLogger(__name__)

    def check_hedge_integrity(self, symbol: str) -> bool:
        """
        检查对冲完整性
        返回 True 表示健康，False 表示跛脚
        """
        spot_pos = self.context.positions.get(symbol)
        swap_pos = self.context.positions.get(f"{symbol}-SWAP")

        spot_qty = spot_pos.quantity if spot_pos else 0
        swap_qty = swap_pos.quantity if swap_pos else 0

        # 简单的张数换算 (假设 1张=0.1 ETH)
        # 实际项目需要精确的换算器
        swap_qty_converted = swap_qty * 0.1

        # 容差 (例如 10% 主要是因为张数取整)
        diff = abs(spot_qty - swap_qty_converted)

        if diff > 0.05: # 偏差大于 0.05 个币
            self.logger.error(f"🚨 对冲不平衡! {symbol} Spot:{spot_qty} vs Swap:{swap_qty} (Conv: {swap_qty_converted})")
            return False

        return True