import math
import time
from loguru import logger


class DryRunTrader:
    def __init__(self, client):
        self.client = client
        self._inst_cache = {}  # instId -> instrument info

    # =========================
    # 合约规格（按需拉取）
    # =========================
    def get_inst_info(self, inst_id: str):
        if inst_id not in self._inst_cache:
            info = self.client.get_instrument_info(inst_id)
            self._inst_cache[inst_id] = info
        return self._inst_cache[inst_id]

    # =========================
    # 币数量 → 合约张数
    # =========================
    def coin_to_contract(self, inst_id: str, coin_size: float):
        info = self.get_inst_info(inst_id)

        ctVal = float(info["ctVal"])
        lotSz = float(info["lotSz"])

        contracts = coin_size / ctVal
        contracts = math.floor(contracts / lotSz) * lotSz

        return int(contracts)

    # =========================
    # 干跑限价单（下 → 立刻撤）
    # =========================
    def test_limit_orders(self, inst_id: str, orders: list[dict]):
        """
        只验证参数是否合法，不承担成交风险
        """
        for o in orders:
            contracts = self.coin_to_contract(
                inst_id,
                o["coin_size"]
            )

            if contracts <= 0:
                logger.warning(
                    f"[SKIP] {inst_id} "
                    f"#{o['index']} 张数不足，跳过"
                )
                continue

            logger.info(
                f"[DRY-RUN] {inst_id} | "
                f"#{o['index']} "
                f"price={o['price']} "
                f"contracts={contracts}"
            )

            result = self.client.trade.place_order(
                instId=inst_id,
                tdMode="isolated",
                side="sell",
                posSide="short",  # 🔥 关键修复
                ordType="limit",
                px=str(o["price"]),
                sz=str(contracts),  # ✅ 张数
            )

            if result.get("code") == "0":
                ord_id = result["data"][0]["ordId"]
                logger.info(f"Order placed: {ord_id}, canceling...")
                self.client.trade.cancel_order(
                    instId=inst_id,
                    ordId=ord_id
                )
            else:
                logger.error(f"Order error: {result}")

            time.sleep(0.3)
