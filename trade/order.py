import math
import time
from loguru import logger


class RunTrader:
    def __init__(self, client):
        self.client = client
        self._inst_cache = {}  # instId -> instrument info
        self.last_pos_sz = 0  # 记录上次持仓张数，用于判断是否成交补仓
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
    def limit_orders(self, inst_id: str, orders: list[dict], leverage: int):
        """
        真实发单逻辑：将审计通过的所有订单一次性挂向交易所
        """
        res = self.client.account.set_leverage(
            instId=inst_id,
            lever=str(leverage),
            mgnMode="isolated",  # 必须与你下单的 tdMode 一致
            posSide = "short"  # 🔥 关键修复：指定空头方向
        )
        if res.get("code") == "0":
            logger.info(f"✅ {inst_id} 杠杆已成功设置为 {leverage}x")
        else:
            logger.warning(f"⚠️ {inst_id} 杠杆设置反馈: {res.get('msg')}")
        placed_orders = []
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
                f"[order] {inst_id} | "
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
                logger.success(f"✅ 订单已在交易所挂出! ID: {ord_id}")
                o["ordId"] = ord_id
                placed_orders.append(o)
                # logger.info(f"Order placed: {ord_id}, canceling...")
                # self.client.trade.cancel_order(
                #     instId=inst_id,
                #     ordId=ord_id
                # )
            else:
                logger.error(f"Order error: {result}")

            time.sleep(0.1)
        return placed_orders

    # =========================
    # 核心：止盈止损管理 (TP/SL)
    # =========================
    def set_exit_orders(self, inst_id: str, sz: int, tp_px: float, sl_px: float):
        """
        设置或覆盖当前的止盈止损单 (策略委托)
        """
        # 1. 先撤销该币种现有的止盈止损单，防止冲突
        try:
            self.client.trade.cancel_algo_order_all(instId=inst_id, ordType="conditional")
        except Exception as e:
            logger.debug(f"尝试撤销旧止盈单时出错（可能原本就没有）: {e}")

        # 2. 挂出新的止盈止损
        # 使用 conditional 类型，一次性带上 TP 和 SL
        logger.info(f"📐 正在为 {sz} 张仓位重置止盈({tp_px})和止损({sl_px})")

        result = self.client.trade.place_algo_order(
            instId=inst_id,
            tdMode="isolated",  # 需与你开仓模式一致
            side="buy",  # 做空平仓用买入
            posSide="short",  # 平掉空头仓位
            ordType="conditional",
            sz=str(sz),
            tpTriggerPx=str(round(tp_px, 6)),
            tpOrdPx="-1",  # -1 表示市价止盈，确保成交
            slTriggerPx=str(round(sl_px, 6)),
            slOrdPx="-1"  # -1 表示市价止损
        )
        return result

    # =========================
    # 核心：仓位监控更新逻辑
    # =========================
    def monitor_and_sync(self, inst_id: str, strategy):
        """
        修正参数报错后的监控逻辑
        """
        try:
            # 1. 获取该币种下所有持仓 (不传 posSide)
            pos_res = self.client.account.get_positions(instId=inst_id)
            # 筛选 short 仓位且张数大于 0 的
            positions = [p for p in pos_res.get("data", [])
                         if p.get("posSide") == "short" and int(p.get("pos", 0)) > 0]

            current_sz = 0
            if positions:
                pos = positions[0]
                current_sz = int(pos["pos"])
                avg_px = float(pos["avgPx"])

                # 检查成交补仓
                if current_sz != self.last_pos_sz:
                    logger.info(f"🔔 {inst_id} 仓位变化: {self.last_pos_sz} -> {current_sz}")
                    targets = strategy.get_exit_targets(avg_px)
                    self.set_exit_orders(inst_id, current_sz, targets["tp_price"], targets["sl_price"])
                    self.last_pos_sz = current_sz
            else:
                # 处理清仓逻辑
                if self.last_pos_sz > 0:
                    logger.success(f"🎊 {inst_id} 持仓已平仓")
                    self.last_pos_sz = 0
                    self.planned_orders = []

            # 2. 只有在还有计划单且未清仓的情况下才对账
            if self.planned_orders:
                self.reconcile_orders(inst_id)

        except Exception as e:
            logger.error(f"❌ 监控轮询发生异常: {e}")
            # 这里不要 raise，让主循环继续，防止因为一次网络抖动导致整个机器人挂掉
    def reconcile_orders(self, inst_id: str, planned_orders: list):
        """
        对账逻辑：确认交易所挂单是否符合 strategy 的计划
        """
        # 获取交易所真实挂单
        remote_orders = self.client.trade.get_order_list(instId=inst_id).get("data", [])
        # 提取真实挂单的价格集合（保留6位精度）
        remote_prices = {round(float(o['px']), 6) for o in remote_orders}

        # 提取本地计划中尚未成交的价格
        # 注意：你需要记录哪些 index 已经成交了，只检查还没成交的
        for plan in planned_orders:
            plan_px = round(float(plan['price']), 6)
            if plan_px not in remote_prices:
                # 检查该价格是否已经变成了持仓（通过成交均价和张数推算）
                # 如果没变成持仓，也没在挂单里，说明一致性被破坏了！
                logger.error(f"🚨 一致性错误：计划挂单 {plan_px} 在交易所消失了！")
                # 这里可以执行补单逻辑 trader.place_single_order(...)

    def is_completely_exit(self, inst_id):
        """
        判断一个币种是否已经彻底退出了这轮马丁格尔
        """
        # 1. 检查仓位
        pos = self.client.account.get_positions(instId=inst_id, posSide="short")
        has_pos = len(pos.get("data", [])) > 0

        # 2. 检查挂单 (包括限价单和策略单)
        orders = self.client.trade.get_order_list(instId=inst_id)
        algos = self.client.trade.get_algo_order_list(instId=inst_id)
        has_orders = len(orders.get("data", [])) > 0 or len(algos.get("data", [])) > 0

        # 如果既没持仓也没挂单，说明这轮结束了
        return (not has_pos) and (not has_orders)