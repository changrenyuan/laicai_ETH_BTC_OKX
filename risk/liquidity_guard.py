"""
🔥 流动性防护
深度 / 滑点 / 插针检测
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict
import logging

from core.events import EventType
from core.context import Context, MarketData


@dataclass
class LiquidityCheckResult:
    """流动性检查结果"""

    is_adequate: bool  # 是否充足
    depth_value: float  # 深度值（USDT）
    estimated_slippage: float  # 预估滑点
    message: str  # 消息


class LiquidityGuard:
    """
    流动性防护类
    检测市场深度和滑点
    """

    def __init__(self, config: dict):
        self.config = config
        self.min_depth_threshold = config.get("min_depth_threshold", 10000)
        self.max_slippage_ratio = config.get("max_slippage_ratio", 0.001)
        self.volume_check_window = config.get("volume_check_window", 5)
        self.min_volume_ratio = config.get("min_volume_ratio", 0.1)

        self.logger = logging.getLogger(__name__)

        # 状态追踪
        self.last_check_time: Optional[datetime] = None
        self.depth_history: Dict[str, list] = {}  # {symbol: [depth_values]}

    async def check(
        self,
        symbol: str,
        order_quantity: float,
        context: Context,
    ) -> LiquidityCheckResult:
        """
        检查流动性是否充足

        Args:
            symbol: 交易品种
            order_quantity: 订单数量
            context: 上下文

        Returns:
            LiquidityCheckResult: 检查结果
        """
        # 获取市场数据
        market_data = context.get_market_data(symbol)
        if not market_data:
            return LiquidityCheckResult(
                is_adequate=False,
                depth_value=0.0,
                estimated_slippage=1.0,
                message="No market data available",
            )

        # 检查深度
        depth_value = self._calculate_depth(market_data)
        depth_adequate = depth_value >= self.min_depth_threshold

        # 计算预估滑点
        estimated_slippage = self._estimate_slippage(market_data, order_quantity)
        slippage_ok = estimated_slippage <= self.max_slippage_ratio

        # 检查成交量
        volume_ok = await self._check_volume(market_data)

        # 综合判断
        is_adequate = depth_adequate and slippage_ok and volume_ok

        # 记录深度历史
        if symbol not in self.depth_history:
            self.depth_history[symbol] = []
        self.depth_history[symbol].append(depth_value)
        if len(self.depth_history[symbol]) > 100:
            self.depth_history[symbol].pop(0)

        # 生成消息
        message = self._generate_message(
            depth_value,
            estimated_slippage,
            depth_adequate,
            slippage_ok,
            volume_ok,
        )

        # 记录检查时间
        self.last_check_time = datetime.now()

        self.logger.info(f"Liquidity check for {symbol}: {message}")

        return LiquidityCheckResult(
            is_adequate=is_adequate,
            depth_value=depth_value,
            estimated_slippage=estimated_slippage,
            message=message,
        )

    async def check_liquidity(self, context: Context) -> bool:
        """
        简化版流动性检查，用于主循环快速调用
        返回 True 表示流动性充足，False 表示不足
        """
        # 使用 Context 中的流动性深度
        if context.liquidity_depth <= 0:
            return False

        # 检查深度是否满足最小阈值
        depth_ok = context.liquidity_depth >= self.min_depth_threshold

        self.last_check_time = datetime.now()

        return depth_ok

    def _calculate_depth(self, market_data: MarketData) -> float:
        """计算深度"""
        # 获取买一卖一深度
        depth = market_data.depth
        bid_depth = depth.get("bid_1_amount", 0) * depth.get("bid_1_price", 0)
        ask_depth = depth.get("ask_1_amount", 0) * depth.get("ask_1_price", 0)

        # 取较小值
        return min(bid_depth, ask_depth)

    def _estimate_slippage(
        self,
        market_data: MarketData,
        order_quantity: float,
    ) -> float:
        """预估滑点"""
        # 简单的滑点估算模型
        depth = market_data.depth
        ask_depth = depth.get("ask_1_amount", 0)

        if ask_depth <= 0:
            return 1.0  # 无深度，100%滑点

        # 订单占深度的比例
        ratio = order_quantity / ask_depth

        # 简单的滑点公式（实际应该使用更复杂的模型）
        slippage = ratio * 0.1  # 假设每消耗10%深度产生1%滑点

        return min(slippage, 1.0)

    async def _check_volume(self, market_data: MarketData) -> bool:
        """检查成交量"""
        # 简化：假设24h成交量足够
        return market_data.volume_24h > self.min_depth_threshold

    def _generate_message(
        self,
        depth_value: float,
        estimated_slippage: float,
        depth_adequate: bool,
        slippage_ok: bool,
        volume_ok: bool,
    ) -> str:
        """生成消息"""
        if not depth_adequate:
            return f"Low liquidity: depth ${depth_value:.2f} < ${self.min_depth_threshold:.2f}"
        elif not slippage_ok:
            return f"High slippage: {estimated_slippage:.2%} > {self.max_slippage_ratio:.2%}"
        elif not volume_ok:
            return "Low volume"
        else:
            return f"OK: depth ${depth_value:.2f}, slippage {estimated_slippage:.2%}"

    def get_depth_history(self, symbol: str, limit: int = 20) -> list:
        """获取深度历史"""
        if symbol not in self.depth_history:
            return []
        return self.depth_history[symbol][-limit:]

    def reset(self):
        """重置状态"""
        self.depth_history.clear()
        self.logger.info("Liquidity guard state reset")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "min_depth_threshold": self.min_depth_threshold,
            "max_slippage_ratio": self.max_slippage_ratio,
            "tracked_symbols": list(self.depth_history.keys()),
            "last_check_time": (
                self.last_check_time.isoformat() if self.last_check_time else None
            ),
        }
