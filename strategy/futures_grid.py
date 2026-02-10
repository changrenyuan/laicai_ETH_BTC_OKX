"""
🕸️ 动态 AI 合约网格策略 (修复版)
"""
import logging
import asyncio
import pandas as pd
from strategy.base_strategy import BaseStrategy
from strategy.grid_utils import GridUtils
# 注意：这里不再需要导入 Dashboard，策略只负责干活，不负责画图

class FuturesGridStrategy(BaseStrategy):
    def __init__(self, config, context, state_machine, order_manager, **kwargs):
        super().__init__(config, context, state_machine, order_manager)
        self.logger = logging.getLogger("GridStrategy")
        self.cfg = config.get("futures_grid", {})

        self.symbol = self.cfg.get("symbol", "ETH-USDT-SWAP")
        self.investment = self.cfg.get("investment", 500)
        self.leverage = self.cfg.get("leverage", 3)
        self.grid_count = int(self.cfg.get("grid_count", 20))

        # 状态
        self.account_info = {}
        self.trends = {}
        self.plan = {}
        self.grids = []

    async def initialize(self):
        self.logger.info("正在初始化网格策略逻辑...")

        # 1. 获取账户信息 (仅用于内部计算，不打印)
        bal = await self.om.client.get_trading_balances()
        if bal and len(bal) > 0:
            details = bal[0]['details'][0]
            self.account_info = {
                'totalEq': float(details.get('eq', 0)),
                'availBal': float(details.get('availBal', 0))
            }

        # 2. 多周期趋势分析
        await self._analyze_market_trends()

        # 3. 生成网格计划
        await self._generate_grid_plan()

        # 4. 执行挂单
        await self._execute_grid()

        self.is_initialized = True
        self.logger.info("✅ 网格策略初始化完成")

    async def _analyze_market_trends(self):
        """分析 1D, 4H, 15m 趋势"""
        periods = {"1D": "1D", "4H": "4H", "15m": "15m"}
        results = {}

        for name, bar in periods.items():
            # 这里调用 client 获取 K 线
            # 注意：需确保 client 有 get_candlesticks 方法
            # 如果没有，请在 exchange/okx_client.py 中添加 (参考之前提供的代码)
            klines = []
            if hasattr(self.om.client, 'get_candlesticks'):
                klines = await self.om.client.get_candlesticks(self.symbol, bar=bar, limit=50)

            if klines:
                df = pd.DataFrame(klines, columns=["ts", "o", "h", "l", "c", "vol", "vc", "vq", "cf"])
                df["c"] = df["c"].astype(float)
                ma20 = df["c"].rolling(20).mean().iloc[-1]
                curr = df["c"].iloc[-1]

                if curr > ma20 * 1.01: results[name] = "Bullish"
                elif curr < ma20 * 0.99: results[name] = "Bearish"
                else: results[name] = "Neutral"

                if name == "15m":
                    results['ATR'] = GridUtils.calculate_atr(klines)

        self.trends = results
        # 策略层不直接打印 Dashboard，数据会通过 Context 或日志体现
        self.logger.info(f"市场趋势分析结果: {self.trends}")

    async def _generate_grid_plan(self):
        """生成网格参数"""
        ticker = await self.om.client.get_ticker(self.symbol)
        if not ticker: return
        curr_price = float(ticker[0]['last'])

        atr = self.trends.get('ATR', curr_price * 0.01)
        range_pct = (atr * 10) / curr_price

        lower = curr_price * (1 - range_pct)
        upper = curr_price * (1 + range_pct)

        self.grids = GridUtils.generate_grid_lines(lower, upper, self.grid_count)

        profit_pct = (upper - lower) / self.grid_count / curr_price

        self.plan = {
            'lower': round(lower, 2),
            'upper': round(upper, 2),
            'grid_count': self.grid_count,
            'investment': self.investment,
            'profit_per_grid': profit_pct
        }
        self.logger.info(f"网格计划生成: {self.plan}")

    async def _execute_grid(self):
        """执行挂单"""
        ticker = await self.om.client.get_ticker(self.symbol)
        if not ticker: return
        curr_price = float(ticker[0]['last'])

        orders = []
        sz = "1"

        for price in self.grids:
            if abs(price - curr_price) / curr_price < 0.002: continue
            side = "sell" if price > curr_price else "buy"

            orders.append({
                "instId": self.symbol,
                "tdMode": "cross",
                "side": side,
                "ordType": "limit",
                "px": str(price),
                "sz": sz
            })

        if orders:
            self.logger.info(f"准备批量挂单 {len(orders)} 个...")
            if hasattr(self.om.client, 'place_batch_orders'):
                res = await self.om.client.place_batch_orders(orders)
                self.logger.info(f"批量挂单响应: {len(res) if res else 0} 条")
            else:
                self.logger.warning("Client 缺少 place_batch_orders 方法，跳过挂单")

    async def run_tick(self):
        if not self.is_initialized:
            await self.initialize()
        # 可以在这里添加心跳日志
        # self.logger.debug("Grid strategy tick...")

    async def shutdown(self):
        self.logger.warning("🛑 撤销所有网格挂单...")