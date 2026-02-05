from okx import MarketData, Account
from loguru import logger


class OKXClient:
    def __init__(self, api_key, secret_key, passphrase, flag="0"):
        self.market = MarketData.MarketAPI(flag=flag)
        self.account = Account.AccountAPI(
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
