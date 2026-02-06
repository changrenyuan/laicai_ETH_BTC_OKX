from loguru import logger
import time


class DryRunTrader:
    def __init__(self, client):
        self.client = client

    def test_limit_orders(self, inst_id: str, orders: list[dict]):
        """
        挂限价单 → 立即撤单（验证参数）
        """
        for o in orders:
            logger.info(
                f"[DRY-RUN] {inst_id} | "
                f"#{o['index']} price={o['price']} size={o['size']}"
            )

            result = self.client.trade.place_order(
                instId=inst_id,
                tdMode="isolated",
                side="sell",
                ordType="limit",
                px=str(o["price"]),
                sz=str(o["size"]), # sz张
                # lever="7"
            )

            if result.get("code") == "0":
                ord_id = result["data"][0]["ordId"]
                logger.info(f"Order placed: {ord_id}, canceling...")
                self.client.client.cancel_order(instId=inst_id, ordId=ord_id)
            else:
                logger.error(f"Order error: {result}")

            time.sleep(0.3)
