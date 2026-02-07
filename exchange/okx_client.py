from okx import MarketData, Account, Trade, PublicData
from loguru import logger


class OKXClient:
    def __init__(self, api_key, secret_key, passphrase, flag="0"):
        self.market = MarketData.MarketAPI(flag=flag)
        self.public = PublicData.PublicAPI(flag=flag)
        # 1. 账户模块：用于查余额、设杠杆
        self.account = Account.AccountAPI(
            api_key=api_key,
            api_secret_key=secret_key,
            passphrase=passphrase,
            flag=flag
        )
        # 2. 交易模块：用于下单、撤单 (关键修改)
        self.trade = Trade.TradeAPI(
            api_key=api_key,
            api_secret_key=secret_key,
            passphrase=passphrase,
            flag=flag
        )

    def get_ticker(self, inst_id: str) -> dict:
        """获取最新行情"""
        result = self.market.get_ticker(instId=inst_id)
        if result.get("code") != "0":
            raise RuntimeError(f"Ticker error: {result}")
        return result["data"][0]

    def get_account_balance(self) -> dict:
        """获取账户余额"""
        result = self.account.get_account_balance()
        if result.get("code") != "0":
            raise RuntimeError(f"Balance error: {result}")
        return result["data"][0]

    def get_instrument_info(self, inst_id: str):
        """获取产品精度、最小下单量等信息"""
        # 使用公开接口，无需私钥

        result = self.public.get_instruments(instType="SWAP", instId=inst_id)
        if result.get("code") == "0":
            return result["data"][0]
        return None

    def place_limit_order(self, instId, side, px, sz):
        return self.trade.place_order(
            instId=instId,
            tdMode="cross",
            side=side,
            ordType="limit",
            px=str(px),
            sz=str(sz)
        )