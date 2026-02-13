"""
📈 Trailing Stop - 移动止损
动态调整止损位，锁定利润
"""

import logging
from typing import Optional, Literal
from enum import Enum


class TrailingStopMode(Enum):
    """移动止损模式"""
    PERCENTAGE = "percentage"  # 基于百分比
    FIXED_AMOUNT = "fixed_amount"  # 基于固定金额
    ATR = "atr"  # 基于平均真实波幅
    VOLATILITY = "volatility"  # 基于波动率


class TrailingStop:
    """
    移动止损
    
    核心概念：
    - 当价格向有利方向移动时，动态调整止损位
    - 当价格逆转时，锁定利润，防止回吐
    
    应用场景：
    - 趋势跟踪策略
    - 保护已实现的利润
    """

    def __init__(
        self,
        mode: str = "percentage",
        activation_distance: float = 0.02,
        trailing_distance: float = 0.01,
        min_profit: float = 0.01,
        side: Literal["long", "short"] = "long",
        atr_multiplier: float = 2.0,
        atr_period: int = 14
    ):
        """
        Args:
            mode: 移动止损模式
                - percentage: 基于百分比
                - fixed_amount: 基于固定金额
                - atr: 基于平均真实波幅
                - volatility: 基于波动率
            activation_distance: 激活距离（价格需要移动多少才能激活移动止损）
            trailing_distance: 跟踪距离（止损位跟随价格的距离）
            min_profit: 最小利润要求（低于此利润不触发移动止损）
            side: 仓位方向（long/short）
            atr_multiplier: ATR 乘数
            atr_period: ATR 周期
        """
        self.mode = TrailingStopMode(mode)
        self.activation_distance = activation_distance
        self.trailing_distance = trailing_distance
        self.min_profit = min_profit
        self.side = side
        self.atr_multiplier = atr_multiplier
        self.atr_period = atr_period
        
        # 状态
        self.entry_price: Optional[float] = None
        self.current_stop_price: Optional[float] = None
        self.is_activated = False
        
        # 价格追踪
        self.peak_price: Optional[float] = None
        self.trough_price: Optional[float] = None
        
        # ATR 计算
        self.atr_values: list = []
        
        self.logger = logging.getLogger(__name__)

    def activate(self, entry_price: float):
        """
        激活移动止损
        
        Args:
            entry_price: 入场价格
        """
        self.entry_price = entry_price
        self.peak_price = entry_price
        self.trough_price = entry_price
        
        # 初始止损位
        if self.side == "long":
            self.current_stop_price = entry_price * (1 - self.min_profit)
        else:
            self.current_stop_price = entry_price * (1 + self.min_profit)
        
        self.logger.info(
            f"📈 移动止损初始化: "
            f"入场价={entry_price}, "
            f"初始止损={self.current_stop_price}, "
            f"模式={self.mode.value}, "
            f"激活距离={self.activation_distance:.2%}, "
            f"跟踪距离={self.trailing_distance:.2%}"
        )

    def update(self, current_price: float, atr: Optional[float] = None) -> tuple:
        """
        更新移动止损
        
        Args:
            current_price: 当前价格
            atr: 当前 ATR 值（用于 ATR 模式）
            
        Returns:
            (is_triggered, stop_price, reason)
        """
        if self.entry_price is None:
            self.logger.warning("⚠️ 移动止损未激活，请先调用 activate()")
            return False, None, "not_activated"
        
        # 更新峰值/谷值
        self.peak_price = max(self.peak_price, current_price)
        self.trough_price = min(self.trough_price, current_price)
        
        # 检查是否激活
        if not self.is_activated:
            if self._should_activate(current_price):
                self.is_activated = True
                self._update_stop_price(current_price, atr)
                self.logger.info(
                    f"🔥 移动止损激活: "
                    f"价格={current_price}, "
                    f"止损={self.current_stop_price}"
                )
                return False, self.current_stop_price, "activated"
            return False, None, "not_activated"
        
        # 更新止损位
        self._update_stop_price(current_price, atr)
        
        # 检查是否触发
        if self._should_trigger(current_price):
            self.logger.warning(
                f"⛔ 移动止损触发: "
                f"价格={current_price}, "
                f"止损={self.current_stop_price}"
            )
            return True, self.current_stop_price, "triggered"
        
        return False, self.current_stop_price, "updated"

    def _should_activate(self, current_price: float) -> bool:
        """检查是否应该激活"""
        price_change = 0
        
        if self.side == "long":
            price_change = (current_price - self.entry_price) / self.entry_price
        else:
            price_change = (self.entry_price - current_price) / self.entry_price
        
        return price_change >= self.activation_distance

    def _should_trigger(self, current_price: float) -> bool:
        """检查是否应该触发"""
        if self.current_stop_price is None:
            return False
        
        if self.side == "long":
            return current_price <= self.current_stop_price
        else:
            return current_price >= self.current_stop_price

    def _update_stop_price(self, current_price: float, atr: Optional[float]):
        """更新止损位"""
        if self.mode == TrailingStopMode.PERCENTAGE:
            if self.side == "long":
                new_stop = current_price * (1 - self.trailing_distance)
                self.current_stop_price = max(self.current_stop_price, new_stop)
            else:
                new_stop = current_price * (1 + self.trailing_distance)
                self.current_stop_price = min(self.current_stop_price, new_stop)
        
        elif self.mode == TrailingStopMode.FIXED_AMOUNT:
            if self.side == "long":
                new_stop = current_price - self.trailing_distance
                self.current_stop_price = max(self.current_stop_price, new_stop)
            else:
                new_stop = current_price + self.trailing_distance
                self.current_stop_price = min(self.current_stop_price, new_stop)
        
        elif self.mode == TrailingStopMode.ATR:
            if atr is None:
                self.logger.warning("⚠️ ATR 模式需要提供 ATR 值")
                return
            
            stop_distance = atr * self.atr_multiplier
            
            if self.side == "long":
                new_stop = current_price - stop_distance
                self.current_stop_price = max(self.current_stop_price, new_stop)
            else:
                new_stop = current_price + stop_distance
                self.current_stop_price = min(self.current_stop_price, new_stop)
        
        elif self.mode == TrailingStopMode.VOLATILITY:
            # 基于波动率调整跟踪距离
            # 这里可以接入具体的波动率计算
            pass

    def get_status(self) -> dict:
        """获取状态"""
        profit = 0
        if self.entry_price and self.peak_price:
            if self.side == "long":
                profit = (self.peak_price - self.entry_price) / self.entry_price
            else:
                profit = (self.entry_price - self.peak_price) / self.entry_price
        
        return {
            "is_activated": self.is_activated,
            "entry_price": self.entry_price,
            "current_stop_price": self.current_stop_price,
            "peak_price": self.peak_price,
            "trough_price": self.trough_price,
            "max_profit": profit,
            "mode": self.mode.value,
            "activation_distance": self.activation_distance,
            "trailing_distance": self.trailing_distance,
            "side": self.side
        }

    def reset(self):
        """重置"""
        self.entry_price = None
        self.current_stop_price = None
        self.is_activated = False
        self.peak_price = None
        self.trough_price = None
        self.atr_values = []
        self.logger.info("🔄 移动止损重置")
