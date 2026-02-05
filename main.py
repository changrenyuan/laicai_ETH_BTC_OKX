from dotenv import load_dotenv
from loguru import logger
import time

from config import config
from exchange.okx_client import OKXClient
from data.market import MarketService


def main():
    logger.info("来财小猪 为小主服务开启OKX ing...")

    client = OKXClient(
        api_key=config.OKX_API_KEY,
        secret_key=config.OKX_SECRET_KEY,
        passphrase=config.OKX_PASSPHRASE,
        flag=config.OKX_FLAG
    )

    market_service = MarketService(client)

    # 启动时打印账户余额（只读）
    balance = client.get_account_balance()
    # logger.info(f"小主的账户信息: {balance}")
    logger.info(f"小主的账户总资产 (USD): {balance['totalEq']}")
    for coin in balance['details']:
        # 只打印余额大于 0 的币种，过滤掉“碎屑”
        if float(coin['availBal']) > 0.0001:
            logger.info(f"币种: {coin['ccy']}")
            logger.info(f"  可用余额: {coin['availBal']}")
            logger.info(f"  折合人民币: {float(coin['eqUsd'])*6.9}")
            logger.info(f"  冻结金额: {coin['frozenBal']}")
    # 行情轮询（无下单）
    while True:
        try:
            market_service.fetch_prices(config.SYMBOLS)
            time.sleep(5)
        except KeyboardInterrupt:
            logger.warning("Manual stop received. Exiting.")
            break
        except Exception as e:
            logger.error(f"Runtime error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
