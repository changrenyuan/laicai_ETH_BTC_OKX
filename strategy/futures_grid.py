"""
🕸️ 动态 AI 合约网格策略 (Futures Grid)
"""
import logging
import asyncio
from strategy.base_strategy import BaseStrategy
from strategy.grid_utils import GridUtils

class FuturesGridStrategy(BaseStrategy):
    def __init__(self, config, context, state_machine, order_manager, **kwargs):
        super().__init__(config, context, state_machine, order_manager)
        self.logger = logging.getLogger("DynamicGrid")

        # 读取配置
        self.cfg = config.get("futures_grid", {})
        self.symbol = self.cfg.get("symbol", "ETH-USDT-SWAP")
        self.leverage = self.cfg.get("leverage", 3)
        self.grid_count = int(self.cfg.get("grid_count", 20))
        self.is_dynamic = self.cfg.get("is_dynamic", True)

        # 运行时状态
        self.grids = []       # 价格线
        self.active_orders = []
        self.current_range = (0.0, 0.0) # (lower, upper)

    async def initialize(self):
        """策略启动时的初始化逻辑"""
        self.logger.info(f"🚀 启动动态网格策略: {self.symbol} (Dynamic={self.is_dynamic})")

        # 1. 设置杠杆 (重要！)
        # await self.om.client.set_leverage(self.symbol, self.leverage)

        # 2. 计算网格区间 (核心逻辑)
        if self.is_dynamic:
            await self._calculate_dynamic_params()
        else:
            self.lower = float(self.cfg["lower_price"])
            self.upper = float(self.cfg["upper_price"])
            self.logger.info(f"📌 使用静态区间: [{self.lower} ~ {self.upper}]")

        # 3. 生成网格线
        self.grids = GridUtils.generate_grid_lines(self.lower, self.upper, self.grid_count)
        self.logger.info(f"📐 生成 {len(self.grids)-1} 个格子")

        # 4. 获取当前价格并挂单
        ticker = await self.om.client.get_ticker(self.symbol)
        current_price = float(ticker[0]['last'])

        await self._place_initial_orders(current_price)
        self.is_initialized = True

    async def _calculate_dynamic_params(self):
        """🔥 AI: 根据布林带计算动态区间"""
        self.logger.info("🧠 正在进行 AI 趋势分析...")

        # 获取 K 线
        interval = self.cfg.get("k_line_interval", "1H")
        limit = int(self.cfg.get("lookback_period", 20)) + 5

        klines = await self.om.client.get_candlesticks(self.symbol, bar=interval, limit=limit)
        if not klines:
            self.logger.error("❌ K线获取失败，回退到静态参数")
            self.lower = float(self.cfg["lower_price"])
            self.upper = float(self.cfg["upper_price"])
            return

        # 计算布林带
        upper, lower, curr = GridUtils.calculate_bollinger_bands(klines)

        # 稍微放宽一点区间，防止频繁破网
        padding = (upper - lower) * 0.1
        self.upper = round(upper + padding, 2)
        self.lower = round(lower - padding, 2)

        self.logger.info(f"🔮 AI 预测区间: [{self.lower} ~ {self.upper}] (基于布林带)")

    async def _place_initial_orders(self, current_price: float):
        """初始批量挂单"""
        orders = []

        # 假设投资额 500U，计算每格下单量
        # 简单版：每格 1 张 (0.01 ETH)
        # 进阶版：需要根据 investment / grid_count 计算 sz
        sz = "1"

        for price in self.grids:
            if abs(price - current_price) / current_price < 0.001:
                continue # 距离当前价太近不挂

            side = "sell" if price > current_price else "buy"

            orders.append({
                "instId": self.symbol,
                "tdMode": "cross",
                "side": side,
                "ordType": "limit",
                "px": str(price),
                "sz": sz
            })

        self.logger.info(f"⚡ 准备挂单 {len(orders)} 个...")
        res = await self.om.client.place_batch_orders(orders)
        self.logger.info(f"✅ 成功挂单: {len(res) if res else 0} 个")

    async def run_tick(self):
        if not self.is_initialized:
            await self.initialize()
            return

        # 动态网格的高级功能：
        # 检查当前价格是否跑出了区间 (破网)
        # 如果破网，需要触发 Stop Loss 或 Re-balance (重新计算中枢)

        # 这里暂时只做监控
        # ticker = await self.om.client.get_ticker(self.symbol)
        # curr = float(ticker[0]['last'])
        # if curr > self.upper or curr < self.lower:
        #     self.logger.warning(f"🚨 价格破网! {curr}")
        pass

    async def shutdown(self):
        self.logger.warning("🛑 策略停止，正在撤销所有网格挂单...")
        # 需实现 cancel_all
        # await self.om.client.cancel_all_orders(self.symbol)