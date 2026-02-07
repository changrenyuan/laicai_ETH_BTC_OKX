from dotenv import load_dotenv
from loguru import logger
import time

from config import config
from exchange.okx_client import OKXClient
from data.market import MarketService
from scanner.top_gainers import TopGainersScanner
from strategy.short_martingale import ShortMartingaleStrategy
from trade.dry_run import DryRunTrader
from risk.liquidation import estimate_short_liquidation


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
    logger.info(f"小主的账户总资产 : {balance['totalEq']}(USD)")
    for coin in balance['details']:
        # 只打印余额大于 0 的币种，过滤掉“碎屑”
        if float(coin['availBal']) > 0.0001:
            logger.info(f"币种: {coin['ccy']}")
            logger.info(f"  可用余额: {coin['availBal']} {coin['ccy']}")
            logger.info(f"  折合人民币: {float(coin['eqUsd'])*6.9} RMB")
            logger.info(f"  冻结金额: {coin['frozenBal']}")
    # 行情轮询（无下单）
    # while True:
    #     try:
    #         market_service.fetch_prices(config.SYMBOLS)
    #         time.sleep(5)
    #     except KeyboardInterrupt:
    #         logger.warning("Manual stop received. Exiting.")
    #         break
    #     except Exception as e:
    #         logger.error(f"Runtime error: {e}")
    #         time.sleep(5)
    scanner = TopGainersScanner(client)
    top = scanner.get_top_gainers()

    strategy = ShortMartingaleStrategy(base_size=5,
                                       max_orders=4,
                                       step_pct=0.0085
                                       )
    trader = DryRunTrader(client)
    for symbol in top:
        # print(symbol)
        pos = symbol["position"]
        if pos>0.9:
            print(symbol["instId"])
            inst_id = symbol["instId"]
            current_price = symbol["last"]

            # === ① 查询合约规格 ===
            inst_info = client.get_instrument_info(inst_id)
            ct_val = float(inst_info["ctVal"])
            lot_sz = float(inst_info["lotSz"])

            # === ② 账户可用 USDT ===
            avail_usdt = float(balance["details"][0]["availBal"])

            orders = strategy.build_orders(entry_price=current_price)
            audit = strategy.aaudit = strategy.audit_orders(orders=orders,
                                                            entry_price=current_price,
                                                            ct_val=ct_val,
                                                            lot_sz=lot_sz,
                                                            avail_usdt=avail_usdt,
                                                        )
            if audit is None:
                logger.warning(f"{inst_id} | 审核失败，跳过")
                continue
            liq = estimate_short_liquidation(
                avg_price=audit["avg_price"],
                leverage=7
            )
            print(
                f"Liquidation price (est): {liq:.4f} | "
                f"From avg: {(liq - audit['avg_price']) / audit['avg_price'] * 100:.2f}%"
            )
            trader.test_limit_orders(symbol["instId"], orders)



if __name__ == "__main__":
    main()
