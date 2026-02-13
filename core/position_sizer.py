"""
💰 PositionSizer - 仓位计算器
统一的仓位计算逻辑，支持风险控制、杠杆、合约面值等
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PositionSizeConfig:
    """仓位计算配置"""
    risk_per_position: float = 0.02  # 每个仓位风险比例（默认2%）
    max_position_pct: float = 0.10  # 单个仓位最大占总资金比例（默认10%）
    leverage: int = 1  # 杠杆倍数
    stop_loss_pct: float = 0.02  # 止损百分比（默认2%）
    min_position_value: float = 10.0  # 最小仓位价值（USDT）
    contract_size: float = 1.0  # 合约面值（ctVal，默认1张=1个币）
    max_risk_multiplier: float = 1.5  # 最大风险倍数（允许超出预设风险的倍数）


@dataclass
class PositionSizeResult:
    """仓位计算结果"""
    position_size: float  # 仓位大小（张数或数量）
    position_value: float  # 仓位价值（USDT）
    margin_required: float  # 所需保证金（USDT）
    risk_amount: float  # 风险金额（USDT）
    stop_loss_price: float  # 止损价格
    stop_distance: float  # 止损距离
    risk_pct: float  # 实际风险比例
    warnings: list  # 警告信息
    is_valid: bool  # 是否有效


class PositionSizer:
    """
    仓位计算器

    功能：
    - 基于风险控制计算仓位大小
    - 支持杠杆
    - 支持合约面值（ctVal）
    - 智能取整（针对合约）
    - 小资金适配（自动调整最小仓位）
    """

    def __init__(self, config: Optional[Dict] = None):
        self.logger = logging.getLogger("PositionSizer")
        
        # 默认配置
        default_config = PositionSizeConfig()
        
        if config:
            self.cfg = PositionSizeConfig(
                risk_per_position=config.get("risk_per_position", default_config.risk_per_position),
                max_position_pct=config.get("max_position_pct", default_config.max_position_pct),
                leverage=config.get("leverage", default_config.leverage),
                stop_loss_pct=config.get("stop_loss_pct", default_config.stop_loss_pct),
                min_position_value=config.get("min_position_value", default_config.min_position_value),
                contract_size=config.get("contract_size", default_config.contract_size),
                max_risk_multiplier=config.get("max_risk_multiplier", default_config.max_risk_multiplier)
            )
        else:
            self.cfg = default_config
        
        self.logger.info(f"✅ PositionSizer 初始化 - 风险比例: {self.cfg.risk_per_position:.2%}, 杠杆: {self.cfg.leverage}x")

    def calculate_position(
        self,
        total_capital: float,
        entry_price: float,
        side: str,
        stop_loss_pct: Optional[float] = None,
        leverage: Optional[int] = None,
        contract_size: Optional[float] = None,
        min_balance: Optional[float] = None
    ) -> PositionSizeResult:
        """
        计算仓位大小

        Args:
            total_capital: 总资金（USDT）
            entry_price: 入场价格
            side: 交易方向 ("buy" 或 "sell")
            stop_loss_pct: 止损百分比（可选，覆盖默认配置）
            leverage: 杠杆倍数（可选，覆盖默认配置）
            contract_size: 合约面值（可选，覆盖默认配置）
            min_balance: 最小可用余额（可选，用于保证金检查）

        Returns:
            PositionSizeResult: 仓位计算结果
        """
        warnings = []
        
        # 1. 使用传入参数或默认配置
        stop_loss_pct = stop_loss_pct or self.cfg.stop_loss_pct
        leverage = leverage or self.cfg.leverage
        contract_size = contract_size or self.cfg.contract_size
        
        # 2. 计算风险金额
        risk_amount = total_capital * self.cfg.risk_per_position
        
        # 3. 计算止损距离
        stop_distance = entry_price * stop_loss_pct
        
        # 4. 基于风险计算原始仓位大小（不考虑杠杆和合约面值）
        # 公式：仓位大小 = 风险金额 / 止损距离
        if stop_distance > 0:
            raw_position_size = risk_amount / stop_distance
        else:
            raw_position_size = 0
            warnings.append("止损距离为0，无法计算仓位")
        
        # 5. 考虑杠杆：实际需要的数量 = raw_position_size / leverage
        if leverage > 0:
            raw_position_size = raw_position_size / leverage
        else:
            warnings.append("杠杆倍数为0，已调整为1")
            leverage = 1
        
        # 6. 转换为合约张数（智能取整）
        # 合约张数 = raw_position_size / contract_size
        raw_contracts = raw_position_size / contract_size
        
        # 向下取整为整数张数
        position_size = int(raw_contracts)
        
        # 7. 如果算出来是 0 张，进行小资金适配
        if position_size == 0:
            position_size, warnings = self._handle_small_capital(
                entry_price,
                leverage,
                contract_size,
                stop_distance,
                total_capital,
                min_balance
            )
        
        # 8. 检查是否有效
        if position_size <= 0:
            return PositionSizeResult(
                position_size=0,
                position_value=0,
                margin_required=0,
                risk_amount=0,
                stop_loss_price=0,
                stop_distance=stop_distance,
                risk_pct=0,
                warnings=warnings,
                is_valid=False
            )
        
        # 9. 计算仓位价值和保证金
        position_value = entry_price * position_size * contract_size
        margin_required = position_value / leverage
        
        # 10. 计算实际风险
        actual_risk = stop_distance * position_size * contract_size
        actual_risk_pct = actual_risk / total_capital
        
        # 11. 计算止损价格
        if side == "buy":
            stop_loss_price = entry_price * (1 - stop_loss_pct)
        else:  # sell
            stop_loss_price = entry_price * (1 + stop_loss_pct)
        
        # 12. 检查仓位价值是否超过最大限制
        max_position_value = total_capital * self.cfg.max_position_pct
        if position_value > max_position_value:
            warnings.append(f"⚠️ 仓位价值 {position_value:.2f}U 超过最大限制 {max_position_value:.2f}U")
        
        # 13. 检查保证金是否足够
        if min_balance and margin_required > min_balance:
            warnings.append(f"⚠️ 保证金不足：需要 {margin_required:.2f}U，可用 {min_balance:.2f}U")
        
        # 14. 检查风险是否超限
        max_allowed_risk = total_capital * self.cfg.risk_per_position * self.cfg.max_risk_multiplier
        if actual_risk > max_allowed_risk:
            warnings.append(f"⚠️ 风险超限：实际风险 {actual_risk:.2f}U > 最大允许 {max_allowed_risk:.2f}U")
        
        # 15. 检查仓位价值是否过小
        if position_value < self.cfg.min_position_value:
            warnings.append(f"⚠️ 仓位价值过小：{position_value:.2f}U < 最小要求 {self.cfg.min_position_value}U")
        
        is_valid = len([w for w in warnings if w.startswith("🚫")]) == 0
        
        self.logger.info("=" * 80)
        self.logger.info("💰 [PositionSizer] 仓位计算结果")
        self.logger.info("-" * 80)
        self.logger.info(f"总资金:      {total_capital:.2f} USDT")
        self.logger.info(f"入场价格:    {entry_price:.6f} USDT")
        self.logger.info(f"交易方向:    {side}")
        self.logger.info(f"杠杆倍数:    {leverage}x")
        self.logger.info(f"止损比例:    {stop_loss_pct:.2%}")
        self.logger.info("-" * 80)
        self.logger.info(f"仓位大小:    {position_size} 张")
        self.logger.info(f"仓位价值:    {position_value:.2f} USDT")
        self.logger.info(f"所需保证金:  {margin_required:.2f} USDT")
        self.logger.info(f"止损距离:    {stop_distance:.6f} USDT")
        self.logger.info(f"止损价格:    {stop_loss_price:.6f} USDT")
        self.logger.info(f"实际风险:    {actual_risk:.4f} USDT ({actual_risk_pct:.2%})")
        self.logger.info("-" * 80)
        for warning in warnings:
            self.logger.info(warning)
        self.logger.info("=" * 80)
        
        return PositionSizeResult(
            position_size=position_size,
            position_value=position_value,
            margin_required=margin_required,
            risk_amount=actual_risk,
            stop_loss_price=stop_loss_price,
            stop_distance=stop_distance,
            risk_pct=actual_risk_pct,
            warnings=warnings,
            is_valid=is_valid
        )

    def _handle_small_capital(
        self,
        entry_price: float,
        leverage: int,
        contract_size: float,
        stop_distance: float,
        total_capital: float,
        min_balance: Optional[float]
    ) -> Tuple[int, list]:
        """
        处理小资金情况
        
        当计算出的仓位不足1张时，智能判断是否可以升级为1张
        """
        warnings = []
        
        # 计算 1 张合约的价值和保证金
        one_contract_value = entry_price * contract_size
        one_contract_margin = one_contract_value / leverage
        
        # 计算 1 张合约的风险
        one_contract_risk = stop_distance * contract_size
        
        # 获取可用余额
        available_balance = min_balance if min_balance else total_capital
        
        # 判断条件：
        # 1. 余额是否够付保证金
        # 2. 风险是否在可接受范围内（最大允许风险的倍数）
        max_allowed_risk = total_capital * self.cfg.risk_per_position * self.cfg.max_risk_multiplier
        
        if available_balance < one_contract_margin:
            warnings.append("🚫 余额不足以支付1张合约的保证金")
            return 0, warnings
        
        if one_contract_risk > max_allowed_risk:
            warnings.append(f"🚫 1张合约风险过大 ({one_contract_risk:.2f}U)，放弃交易")
            return 0, warnings
        
        # 如果仓位价值过小
        if one_contract_value < self.cfg.min_position_value:
            warnings.append(f"🚫 1张合约价值过小 ({one_contract_value:.2f}U)，放弃交易")
            return 0, warnings
        
        # 通过所有检查，可以升级为1张
        warnings.append(f"⚠️ 原始仓位不足1张，强制升级为 1 张 (风险: {one_contract_risk:.2f}U)")
        return 1, warnings

    def calculate_take_profit(
        self,
        entry_price: float,
        side: str,
        take_profit_pct: float
    ) -> float:
        """
        计算止盈价格

        Args:
            entry_price: 入场价格
            side: 交易方向 ("buy" 或 "sell")
            take_profit_pct: 止盈百分比

        Returns:
            float: 止盈价格
        """
        if side == "buy":
            return entry_price * (1 + take_profit_pct)
        else:  # sell
            return entry_price * (1 - take_profit_pct)

    def calculate_stop_loss(
        self,
        entry_price: float,
        side: str,
        stop_loss_pct: Optional[float] = None
    ) -> float:
        """
        计算止损价格

        Args:
            entry_price: 入场价格
            side: 交易方向 ("buy" 或 "sell")
            stop_loss_pct: 止损百分比（可选，使用默认配置如果未提供）

        Returns:
            float: 止损价格
        """
        if stop_loss_pct is None:
            stop_loss_pct = self.cfg.stop_loss_pct
        
        if side == "buy":
            return entry_price * (1 - stop_loss_pct)
        else:  # sell
            return entry_price * (1 + stop_loss_pct)

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        side: str,
        trailing_pct: float,
        activation_pct: float = 0.01
    ) -> Tuple[float, bool]:
        """
        计算移动止损价格

        Args:
            entry_price: 入场价格
            current_price: 当前价格
            side: 交易方向 ("buy" 或 "sell")
            trailing_pct: 移动止损百分比
            activation_pct: 激活价格百分比（盈利达到此比例后开始移动止损）

        Returns:
            Tuple[float, bool]: (止损价格, 是否激活)
        """
        # 计算盈亏比例
        if side == "buy":
            pnl_pct = (current_price - entry_price) / entry_price
        else:  # sell
            pnl_pct = (entry_price - current_price) / entry_price
        
        # 检查是否激活移动止损
        is_activated = pnl_pct >= activation_pct
        
        if not is_activated:
            # 未激活，使用原始止损
            if side == "buy":
                stop_price = entry_price * (1 - self.cfg.stop_loss_pct)
            else:
                stop_price = entry_price * (1 + self.cfg.stop_loss_pct)
        else:
            # 已激活，使用移动止损
            if side == "buy":
                stop_price = current_price * (1 - trailing_pct)
                # 确保止损价格不低于入场价格（锁住至少不亏损）
                stop_price = max(stop_price, entry_price)
            else:
                stop_price = current_price * (1 + trailing_pct)
                # 确保止损价格不高于入场价格
                stop_price = min(stop_price, entry_price)
        
        return stop_price, is_activated


# 导出
__all__ = [
    "PositionSizer",
    "PositionSizeConfig",
    "PositionSizeResult"
]
