"""
🔥 上下文管理器
维护当前账户、市场、系统的快照
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
from pathlib import Path


@dataclass
class Balance:
    """余额信息"""

    currency: str
    available: float  # 可用余额
    frozen: float  # 冻结余额
    total: float  # 总余额

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "available": self.available,
            "frozen": self.frozen,
            "total": self.total,
        }


@dataclass
class Position:
    """持仓信息"""

    symbol: str
    side: str  # long, short
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    margin_used: float
    leverage: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "margin_used": self.margin_used,
            "leverage": self.leverage,
        }


@dataclass
class MarketData:
    """市场数据"""

    symbol: str
    spot_price: float
    futures_price: float
    funding_rate: float
    next_funding_time: Optional[datetime]
    volume_24h: float
    depth: Dict[str, float]  # 买一卖一深度

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "spot_price": self.spot_price,
            "futures_price": self.futures_price,
            "funding_rate": self.funding_rate,
            "next_funding_time": (
                self.next_funding_time.isoformat() if self.next_funding_time else None
            ),
            "volume_24h": self.volume_24h,
            "depth": self.depth,
        }


@dataclass
class SystemMetrics:
    """系统指标"""

    total_pnl: float = 0.0  # 总盈亏
    daily_pnl: float = 0.0  # 日盈亏
    total_funding_earned: float = 0.0  # 总资金费收益
    daily_funding_earned: float = 0.0  # 日资金费收益
    total_trades: int = 0  # 总交易次数
    daily_trades: int = 0  # 日交易次数
    win_rate: float = 0.0  # 胜率
    max_drawdown: float = 0.0  # 最大回撤
    current_drawdown: float = 0.0  # 当前回撤
    system_uptime: float = 0.0  # 系统运行时间（秒）
    last_update: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pnl": self.total_pnl,
            "daily_pnl": self.daily_pnl,
            "total_funding_earned": self.total_funding_earned,
            "daily_funding_earned": self.daily_funding_earned,
            "total_trades": self.total_trades,
            "daily_trades": self.daily_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "current_drawdown": self.current_drawdown,
            "system_uptime": self.system_uptime,
            "last_update": self.last_update.isoformat(),
        }


class Context:
    """上下文管理器"""

    def __init__(self, config_dir: str = "config", data_dir: str = "data"):
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)

        # 账户状态
        self.balances: Dict[str, Balance] = {}
        self.positions: Dict[str, Position] = {}
        self.margin_ratio: float = 1.0  # 保证金率
        self.available_margin: float = 0.0  # 可用保证金

        # 市场状态
        self.market_data: Dict[str, MarketData] = {}

        # 系统状态
        self.metrics = SystemMetrics()
        self.start_time: datetime = datetime.now()
        self.is_running: bool = False
        self.is_emergency: bool = False  # 紧急状态
        self.last_error: Optional[str] = None

        # 配置缓存
        self._config_cache: Dict[str, Any] = {}

    def update_balance(self, currency: str, available: float, frozen: float):
        """更新余额"""
        self.balances[currency] = Balance(
            currency=currency,
            available=available,
            frozen=frozen,
            total=available + frozen,
        )

    def update_position(self, position: Position):
        """更新持仓"""
        self.positions[position.symbol] = position

    def update_market_data(self, market_data: MarketData):
        """更新市场数据"""
        self.market_data[market_data.symbol] = market_data

    def get_balance(self, currency: str) -> Optional[Balance]:
        """获取余额"""
        return self.balances.get(currency)

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(symbol)

    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """获取市场数据"""
        return self.market_data.get(symbol)

    def get_total_balance(self, currency: str = "USDT") -> float:
        """获取总余额"""
        balance = self.balances.get(currency)
        return balance.total if balance else 0.0

    def get_total_position_value(self) -> float:
        """获取总持仓价值"""
        total_value = 0.0
        for position in self.positions.values():
            total_value += position.quantity * position.current_price
        return total_value

    def calculate_margin_ratio(self) -> float:
        """计算保证金率"""
        total_margin = sum(pos.margin_used for pos in self.positions.values())
        total_equity = self.get_total_balance()

        if total_margin > 0:
            self.margin_ratio = total_equity / total_margin
        else:
            self.margin_ratio = float("inf")

        return self.margin_ratio

    def save_runtime_state(self):
        """保存运行状态到文件"""
        state = {
            "balances": {k: v.to_dict() for k, v in self.balances.items()},
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "metrics": self.metrics.to_dict(),
            "is_running": self.is_running,
            "is_emergency": self.is_emergency,
            "start_time": self.start_time.isoformat(),
        }

        state_file = self.data_dir / "runtime_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_runtime_state(self) -> bool:
        """从文件加载运行状态"""
        state_file = self.data_dir / "runtime_state.json"

        if not state_file.exists():
            return False

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            # 恢复状态
            for currency, balance_data in state.get("balances", {}).items():
                self.balances[currency] = Balance(**balance_data)

            for symbol, position_data in state.get("positions", {}).items():
                self.positions[symbol] = Position(**position_data)

            self.is_running = state.get("is_running", False)
            self.is_emergency = state.get("is_emergency", False)

            if state.get("start_time"):
                self.start_time = datetime.fromisoformat(state["start_time"])

            return True
        except Exception as e:
            print(f"Failed to load runtime state: {e}")
            return False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "balances": {k: v.to_dict() for k, v in self.balances.items()},
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "market_data": {k: v.to_dict() for k, v in self.market_data.items()},
            "metrics": self.metrics.to_dict(),
            "margin_ratio": self.margin_ratio,
            "available_margin": self.available_margin,
            "is_running": self.is_running,
            "is_emergency": self.is_emergency,
            "start_time": self.start_time.isoformat(),
        }
