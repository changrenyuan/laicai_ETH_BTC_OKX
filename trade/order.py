import math
import time
from loguru import logger


class RunTrader:
    def __init__(self, client):
        self.client = client
        self._inst_cache = {}  # instId -> instrument info
        self.last_pos_sz = 0  # 记录上次持仓张数，用于判断是否成交补仓
        self.planned_orders = []  # 🔥 必须在这里初始化：存储计划补仓订单列表
    # =========================
    # 合约规格（按需拉取）
    # =========================
    def get_inst_info(self, inst_id: str):
        if inst_id not in self._inst_cache:
            info = self.client.get_instrument_info(inst_id)
            self._inst_cache[inst_id] = info
        return self._inst_cache[inst_id]

    # =========================
    # 获取算法订单列表（止盈止损单）
    # =========================
    def get_algo_orders(self, inst_id: str):
        """
        获取指定交易对的算法订单列表（止盈止损单等）

        :param inst_id: 交易对ID
        :return: 算法订单列表
        """
        try:
            # OKX V5 标准方法名
            result = self.client.trade.get_order_algo_list(
                instType="SWAP",
                instId=inst_id
            )
            return result.get("data", [])
        except AttributeError:
            # 如果方法名不同，尝试其他可能的命名
            logger.warning("get_order_algo_list 方法不存在，尝试其他方法名")
            try:
                result = self.client.trade.get_algo_order_list(
                    instType="SWAP",
                    instId=inst_id
                )
                return result.get("data", [])
            except AttributeError:
                logger.error("无法获取算法订单列表，SDK 方法名不匹配")
                return []
        except Exception as e:
            logger.error(f"获取算法订单列表失败: {e}")
            return []

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
    # 设置计划补仓订单
    # =========================
    def set_planned_orders(self, orders: list):
        """
        设置计划补仓订单列表

        :param orders: 计划订单列表，每个订单应包含 index, price, coin_size 等字段
        """
        self.planned_orders = orders
        logger.debug(f"📝 已设置计划订单列表，共 {len(orders)} 个订单")

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
        检查仓位变化并同步止盈止损。建议在外部循环中调用。
        """
        try:
            # 获取当前持仓
            pos_res = self.client.account.get_positions(instId=inst_id)
            positions = pos_res.get("data", [])

            if not positions:
                if self.last_pos_sz > 0:
                    logger.success(f"🎊 {inst_id} 持仓已清空（止盈或止损成交）")
                    self.last_pos_sz = 0
                return

            pos = positions[0]
            current_sz = int(pos["pos"])
            avg_px = float(pos["avgPx"])

            # 只有当持仓张数增加（补仓成功）时，才重新计算
            if current_sz != self.last_pos_sz:
                logger.info(f"🔔 检测到仓位变动: {self.last_pos_sz} -> {current_sz} (成交补仓)")

                # 从 strategy 对象获取基于最新均价的新止盈止损位
                targets = strategy.get_exit_targets(avg_px)

                # 执行更新
                self.set_exit_orders(
                    inst_id,
                    current_sz,
                    targets["tp_price"],
                    targets["sl_price"]
                )

                # 更新本地记录的状态
                self.last_pos_sz = current_sz
            else:
                # 🔥 新增：如果没有仓位变动，检查订单一致性
                # 如果有计划订单，进行对账检查
                if self.planned_orders:
                    self.reconcile_orders(inst_id, self.planned_orders)

        except Exception as e:
            logger.error(f"监控轮询发生异常: {e}")

    def reconcile_orders(self, inst_id: str, planned_orders: list):
        """
        对账逻辑：确认交易所挂单是否符合 strategy 的计划
        """
        try:
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

        except Exception as e:
            logger.error(f"对账 {inst_id} 时发生异常: {e}")

    def is_completely_exit(self, inst_id: str) -> bool:
        """
        判断是否已经完全平仓（止盈或止损离场）

        :param inst_id: 交易对ID，如 'BTC-USDT-SWAP'
        :return: True 表示已平仓，False 表示仍有持仓
        """
        try:
            # 获取当前空头持仓
            pos_res = self.client.account.get_positions(instId=inst_id)
            positions = pos_res.get("data", [])

            # 🔥 改进：更严格的筛选，只计算 short 且持仓张数 > 0 的仓位
            has_pos = any(
                p.get("posSide") == "short" and int(p.get("pos", 0)) > 0
                for p in positions
            )

            if not has_pos:
                # 确保最后记录的持仓张数也归零
                if self.last_pos_sz > 0:
                    logger.info(f"✅ {inst_id} 确认已完全平仓")
                    self.last_pos_sz = 0
                return True

            # 还有 short 持仓，未平仓
            logger.debug(f"📊 {inst_id} 仍有持仓，继续监控")
            return False

        except Exception as e:
            logger.error(f"检查 {inst_id} 持仓状态时出错: {e}")
            # 出错时保守处理，返回 True，从监控名单移除，避免无限循环
            return True

    def handle_ws_position_update(self, data, strategy):
        """
        ⚡ WebSocket 回调处理器
        当监听到持仓变动推送时，立即触发此函数
        """
        try:
            if not data:
                return

            # 找到我们关心的 short 仓位数据
            short_pos = None
            for p in data:
                if p.get("posSide") == "short":
                    short_pos = p
                    break

            if not short_pos:
                # 如果推送里没有 short 仓位，且本地记录有持仓，说明可能平仓了
                if self.last_pos_sz > 0:
                    logger.success("🎊 WebSocket 消息：持仓已清空")
                    self.last_pos_sz = 0
                return

            current_sz = int(short_pos["pos"])
            avg_px = float(short_pos["avgPx"])
            inst_id = short_pos["instId"]

            # 关键判断：张数增加了才重挂止盈止损（马丁格尔补仓）
            if current_sz > self.last_pos_sz:
                logger.info(f"🚀 WS 捕获成交！仓位由 {self.last_pos_sz} 增至 {current_sz}")

                # 计算并设置新的止盈止损
                targets = strategy.get_exit_targets(avg_px)
                self.set_exit_orders(
                    inst_id,
                    current_sz,
                    targets["tp_price"],
                    targets["sl_price"]
                )

                # 更新本地状态
                self.last_pos_sz = current_sz
                logger.success(f"✅ 止盈止损同步完成 (均价: {avg_px})| 止盈: {targets['tp_price']}| 止损: {targets['sl_price']}")

            elif current_sz < self.last_pos_sz:
                # 减仓逻辑（如果你的策略涉及减仓）
                self.last_pos_sz = current_sz

        except Exception as e:
            logger.error(f"处理 WS 持仓推送失败: {e}")