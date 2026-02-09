"""
🔌 账户数据获取
余额 / 仓位
"""

from typing import Optional, Dict
import logging

from core.context import Balance, Position
from .okx_client import OKXClient


class AccountDataFetcher:
    """
    账户数据获取器
    从交易所获取账户余额和仓位信息
    """

    def __init__(self, okx_client: OKXClient, config: dict):
        self.okx_client = okx_client
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def get_balance(self, currency: str = "USDT") -> Optional[Balance]:
        """
        获取余额

        Args:
            currency: 货币单位

        Returns:
            Balance: 余额对象
        """
        try:
            result = await self.okx_client.get_balance(currency)

            if not result or len(result) == 0:
                return None

            balance_data = result[0]
            details = balance_data.get("details", [])

            if len(details) == 0:
                return Balance(
                    currency=currency,
                    available=0.0,
                    frozen=0.0,
                    total=0.0,
                )

            detail = details[0]

            available = float(detail.get("availBal", 0))
            frozen = float(detail.get("frozenBal", 0))
            total = float(detail.get("bal", 0))

            balance = Balance(
                currency=currency,
                available=available,
                frozen=frozen,
                total=total,
            )

            self.logger.info(
                f"Balance for {currency}: "
                f"available=${available:.2f}, frozen=${frozen:.2f}, total=${total:.2f}"
            )

            return balance

        except Exception as e:
            self.logger.error(f"Failed to get balance for {currency}: {e}")
            return None

    async def get_all_balances(self) -> Dict[str, Balance]:
        """
        获取所有余额

        Returns:
            Dict[str, Balance]: {currency: Balance}
        """
        try:
            result = await self.okx_client.get_balance()

            if not result or len(result) == 0:
                return {}

            balances = {}

            for balance_data in result:
                for detail in balance_data.get("details", []):
                    currency = detail.get("ccy", "")
                    available = float(detail.get("availBal", 0))
                    frozen = float(detail.get("frozenBal", 0))
                    total = float(detail.get("bal", 0))

                    if total > 0:  # 只记录有余额的货币
                        balances[currency] = Balance(
                            currency=currency,
                            available=available,
                            frozen=frozen,
                            total=total,
                        )

            return balances

        except Exception as e:
            self.logger.error(f"Failed to get all balances: {e}")
            return {}

    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取持仓

        Args:
            symbol: 交易品种

        Returns:
            Position: 持仓对象
        """
        try:
            result = await self.okx_client.get_positions(inst_type="SWAP")

            if not result:
                return None

            # 查找指定品种的持仓
            futures_symbol = f"{symbol}-SWAP"

            for pos_data in result:
                if pos_data.get("instId") == futures_symbol:
                    pos = float(pos_data.get("pos", 0))

                    if pos == 0:
                        return None

                    # 解析持仓信息
                    side = pos_data.get("posSide", "net")
                    entry_price = float(pos_data.get("avgPx", 0))
                    mark_price = float(pos_data.get("markPx", 0))
                    unrealized_pnl = float(pos_data.get("upl", 0))
                    margin = float(pos_data.get("margin", 0))
                    leverage = float(pos_data.get("lever", 1))

                    position = Position(
                        symbol=symbol,
                        side=side,
                        quantity=abs(pos),
                        entry_price=entry_price,
                        current_price=mark_price,
                        unrealized_pnl=unrealized_pnl,
                        margin_used=margin,
                        leverage=leverage,
                    )

                    self.logger.info(
                        f"Position for {symbol}: "
                        f"{side} {position.quantity} @ ${entry_price:.2f}, "
                        f"PnL=${unrealized_pnl:.2f}"
                    )

                    return position

            return None

        except Exception as e:
            self.logger.error(f"Failed to get position for {symbol}: {e}")
            return None

    async def get_all_positions(self) -> Dict[str, Position]:
        """
        获取所有持仓

        Returns:
            Dict[str, Position]: {symbol: Position}
        """
        try:
            result = await self.okx_client.get_positions(inst_type="SWAP")

            if not result:
                return {}

            positions = {}

            for pos_data in result:
                pos = float(pos_data.get("pos", 0))

                if pos == 0:
                    continue

                # 解析品种
                inst_id = pos_data.get("instId", "")
                # 移除 -SWAP 后缀
                symbol = inst_id.replace("-SWAP", "")

                # 解析持仓信息
                side = pos_data.get("posSide", "net")
                entry_price = float(pos_data.get("avgPx", 0))
                mark_price = float(pos_data.get("markPx", 0))
                unrealized_pnl = float(pos_data.get("upl", 0))
                margin = float(pos_data.get("margin", 0))
                leverage = float(pos_data.get("lever", 1))

                positions[symbol] = Position(
                    symbol=symbol,
                    side=side,
                    quantity=abs(pos),
                    entry_price=entry_price,
                    current_price=mark_price,
                    unrealized_pnl=unrealized_pnl,
                    margin_used=margin,
                    leverage=leverage,
                )

            return positions

        except Exception as e:
            self.logger.error(f"Failed to get all positions: {e}")
            return {}

    async def get_account_config(self) -> Optional[Dict]:
        """
        获取账户配置

        Returns:
            Dict: 账户配置
        """
        try:
            result = await self.okx_client.get_account_config()

            if not result:
                return None

            return result

        except Exception as e:
            self.logger.error(f"Failed to get account config: {e}")
            return None
