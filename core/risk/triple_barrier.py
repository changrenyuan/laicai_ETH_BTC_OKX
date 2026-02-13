"""
🛡️ Triple Barrier - 三重风控框架
止盈、止损、时间限制
"""

import logging
from datetime import datetime
from typing import Optional, Literal
from enum import Enum


class BarrierAction(Enum):
    """风控动作"""
    NONE = "none"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TIME_LIMIT = "time_limit"
    TRAILING_STOP = "trailing_stop"


class TripleBarrier:
    """
    三重风控框架
    
    核心概念（来自 Advances in Financial Machine Learning）：
    1. 止盈（Upper Barrier）：价格达到目标利润时触发
    2. 止损（Lower Barrier）：价格达到止损位时触发
    3. 时间限制（Time Barrier）：超过时间限制时触发
    
    扩展功能：
    - 移动止损（Trailing Stop）：动态调整止损位
    """

    def __init__(
        self,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        time_limit_seconds: Optional[int] = None,
        trailing_stop_config: Optional[dict] = None
    ):
        """
        Args:
            take_profit_price: 止盈价格
            stop_loss_price: 止损价格
            time_limit_seconds: 时间限制（秒）
            trailing_stop_config: 移动止损配置
                {
                    "activation_distance": 0.02,  # 激活距离（百分比）
                    "trailing_distance": 0.01     # 跟踪距离（百分比）
                }
        """
        self.take_profit_price = take_profit_price
        self.stop_loss_price = stop_loss_price
        self.time_limit_seconds = time_limit_seconds
        
        # 移动止损
        self.trailing_stop_config = trailing_stop_config or {}
        self.is_trailing_stop_activated = False
        self.peak_price = None
        self.trough_price = None
        self.dynamic_stop_price = stop_loss_price
        
        # 时间追踪
        self.start_time: Optional[datetime] = None
        self.is_active = False
        
        self.logger = logging.getLogger(__name__)

    def activate(self, start_price: float = None):
        """激活风控"""
        self.start_time = datetime.now()
        self.is_active = True
        
        # 初始化移动止损
        if start_price and self.trailing_stop_config:
            self.peak_price = start_price
            self.trough_price = start_price
        
        self.logger.info(
            f"🛡️ Triple Barrier 激活 "
            f"(止盈: {self.take_profit_price}, "
            f"止损: {self.stop_loss_price}, "
            f"时间限制: {self.time_limit_seconds}s)"
        )

    def check(self, current_price: float, current_time: datetime) -> BarrierAction:
        """
        检查是否触发风控
        
        Args:
            current_price: 当前价格
            current_time: 当前时间
            
        Returns:
            BarrierAction: 触发的风控动作
        """
        if not self.is_active:
            return BarrierAction.NONE
        
        # 1. 检查止盈
        if self._check_take_profit(current_price):
            return BarrierAction.TAKE_PROFIT
        
        # 2. 检查止损
        if self._check_stop_loss(current_price):
            return BarrierAction.STOP_LOSS
        
        # 3. 检查时间限制
        if self._check_time_limit(current_time):
            return BarrierAction.TIME_LIMIT
        
        # 4. 检查移动止损
        trailing_action = self._check_trailing_stop(current_price)
        if trailing_action != BarrierAction.NONE:
            return trailing_action
        
        return BarrierAction.NONE

    def _check_take_profit(self, current_price: float) -> bool:
        """检查止盈"""
        if self.take_profit_price is None:
            return False
        
        if current_price >= self.take_profit_price:
            self.logger.info(f"✅ 触发止盈: {current_price} >= {self.take_profit_price}")
            return True
        
        return False

    def _check_stop_loss(self, current_price: float) -> bool:
        """检查止损"""
        if self.stop_loss_price is None:
            return False
        
        stop_price = self.dynamic_stop_price if self.is_trailing_stop_activated else self.stop_loss_price
        
        if current_price <= stop_price:
            self.logger.warning(f"⛔ 触发止损: {current_price} <= {stop_price}")
            return True
        
        return False

    def _check_time_limit(self, current_time: datetime) -> bool:
        """检查时间限制"""
        if self.time_limit_seconds is None:
            return False
        
        elapsed = (current_time - self.start_time).total_seconds()
        
        if elapsed >= self.time_limit_seconds:
            self.logger.warning(f"⏰ 触发时间限制: {elapsed}s >= {self.time_limit_seconds}s")
            return True
        
        return False

    def _check_trailing_stop(self, current_price: float) -> BarrierAction:
        """
        检查移动止损
        
        移动止损逻辑：
        1. 价格达到激活距离后，激活移动止损
        2. 价格上升时，动态提高止损位
        3. 价格下跌时，保持在跟踪距离内
        """
        if not self.trailing_stop_config:
            return BarrierAction.NONE
        
        activation_distance = self.trailing_stop_config.get("activation_distance", 0.02)
        trailing_distance = self.trailing_stop_config.get("trailing_distance", 0.01)
        
        if self.stop_loss_price is None:
            return BarrierAction.NONE
        
        # 更新最高价/最低价
        if self.peak_price is None:
            self.peak_price = current_price
            self.trough_price = current_price
        else:
            self.peak_price = max(self.peak_price, current_price)
            self.trough_price = min(self.trough_price, current_price)
        
        # 计算价格变化
        price_change = (current_price - self.stop_loss_price) / self.stop_loss_price
        
        # 激活移动止损
        if not self.is_trailing_stop_activated and price_change >= activation_distance:
            self.is_trailing_stop_activated = True
            self.dynamic_stop_price = current_price * (1 - trailing_distance)
            self.logger.info(
                f"🔥 移动止损激活: "
                f"价格变化 {price_change:.2%} >= {activation_distance:.2%}, "
                f"动态止损 {self.dynamic_stop_price}"
            )
            return BarrierAction.NONE
        
        # 执行移动止损
        if self.is_trailing_stop_activated:
            # 价格上升，动态提高止损位
            if current_price > self.peak_price:
                self.peak_price = current_price
                new_stop = current_price * (1 - trailing_distance)
                if new_stop > self.dynamic_stop_price:
                    self.dynamic_stop_price = new_stop
                    self.logger.debug(
                        f"📈 移动止损上移: {self.dynamic_stop_price} "
                        f"(峰值: {self.peak_price})"
                    )
            
            # 价格下跌，检查是否触发
            if current_price <= self.dynamic_stop_price:
                self.logger.warning(
                    f"⛔ 触发移动止损: {current_price} <= {self.dynamic_stop_price}"
                )
                return BarrierAction.TRAILING_STOP
        
        return BarrierAction.NONE

    def get_status(self) -> dict:
        """获取状态"""
        return {
            "is_active": self.is_active,
            "take_profit_price": self.take_profit_price,
            "stop_loss_price": self.stop_loss_price,
            "dynamic_stop_price": self.dynamic_stop_price,
            "time_limit_seconds": self.time_limit_seconds,
            "elapsed_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            "is_trailing_stop_activated": self.is_trailing_stop_activated,
            "peak_price": self.peak_price,
            "trough_price": self.trough_price,
            "trailing_stop_config": self.trailing_stop_config
        }

    def reset(self):
        """重置风控"""
        self.is_active = False
        self.is_trailing_stop_activated = False
        self.peak_price = None
        self.trough_price = None
        self.dynamic_stop_price = self.stop_loss_price
        self.start_time = None
        self.logger.info("🔄 Triple Barrier 重置")
