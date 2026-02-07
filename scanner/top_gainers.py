from loguru import logger


class TopGainersScanner:
    def __init__(self, client, min_volume_usdt=10_000_000, blacklist=None):
        """
        :param client: OKXClient 实例
        :param min_volume_usdt: 最小 24h 成交额 (USDT)，默认 1000 万，过滤流动性差的币
        :param blacklist: 黑名单列表，如 ["USDC-USDT-SWAP", "DAI-USDT-SWAP"]
        """
        self.client = client
        self.min_volume = min_volume_usdt
        self.blacklist = blacklist if blacklist else []

        # 默认黑名单：稳定币对通常不需要扫描
        if not blacklist:
            self.blacklist = ["USDC-USDT-SWAP", "BUSD-USDT-SWAP", "DAI-USDT-SWAP"]

    def get_top_gainers(self, limit=10):
        """
        获取 24h 涨幅榜
        """
        try:
            # 使用 client._request 以获得重试保护，如果没有 _request 则直接调用 SDK
            if hasattr(self.client, '_request'):
                tickers_data = self.client._request(self.client.market.get_tickers, instType="SWAP")
            else:
                # 兼容旧版 client
                response = self.client.market.get_tickers(instType="SWAP")
                if response.get("code") != "0":
                    logger.error("获取 Ticker 失败")
                    return []
                tickers_data = response.get("data", [])

            candidates = []

            for item in tickers_data:
                inst_id = item["instId"]

                # --- 过滤器 1: 必须是 USDT 本位合约 ---
                if not inst_id.endswith("USDT-SWAP"):
                    continue

                # --- 过滤器 2: 黑名单检查 ---
                if inst_id in self.blacklist:
                    continue

                try:
                    # 转换数据类型，使用 get 避免 KeyError
                    # volCcy24h 是以计价货币(USDT)计算的成交额，比 vol24h(张数/币数) 更具参考价值
                    volume_24h = float(item.get("volCcy24h", 0))
                    open_px = float(item.get("open24h", 0))
                    last_px = float(item.get("last", 0))
                    high_px = float(item.get("high24h", 0))
                    low_px = float(item.get("low24h", 0))

                    # --- 过滤器 3: 数据有效性与流动性 ---
                    if open_px <= 0 or last_px <= 0:
                        continue

                    if volume_24h < self.min_volume:
                        # 流动性太差，跳过
                        continue

                    # --- 计算指标 ---
                    # 1. 24h 涨跌幅
                    change_pct = (last_px - open_px) / open_px

                    # 2. 价格位置 (0 = 最低点, 1 = 最高点)
                    # 防止分母为 0
                    range_diff = high_px - low_px
                    position = (last_px - low_px) / range_diff if range_diff > 0 else 0.5

                    # 3. 振幅 (衡量波动剧烈程度)
                    amplitude = range_diff / open_px

                    candidates.append({
                        "instId": inst_id,
                        "change": change_pct,
                        "position": position,
                        "amplitude": amplitude,
                        "last": last_px,
                        "volume": volume_24h
                    })

                except ValueError:
                    continue

            # 按涨幅降序排序
            candidates.sort(key=lambda x: x["change"], reverse=True)
            top_list = candidates[:limit]

            self._log_results(top_list)
            return top_list

        except Exception as e:
            logger.exception(f"扫描市场失败: {e}")
            return []

    def _log_results(self, data):
        """格式化输出日志"""
        logger.info(f"=== 24H 涨幅榜 (成交额 > {self.min_volume / 10000:.0f}万 USDT) ===")
        logger.info(f"{'交易对':<20}| {'最新价格':<6} | {'涨幅':<8} | {'位置':<6} | {'振幅':<6} | {'成交额(亿)RMB':<10}")
        logger.info("-" * 70)
        for r in data:
            # print(r)
            logger.info(
                f"{r['instId']:<20} | "
                f"{r['last']:5.4f} | "
                f"{r['change'] * 100:6.2f}% | "
                f"{r['position'] * 100:5.1f}% | "
                f"{r['amplitude'] * 100:5.1f}% | "
                f"{r['volume'] / 100000000*6.9*r['last']:8.2f}"
            )