"""
🕸️ 动态 AI 合约网格策略 (纯信号生成版)
"""
import logging
from typing import Dict, Optional, List
import math

from strategy.base_strategy import BaseStrategy

class FuturesGridStrategy(BaseStrategy):
    def __init__(self, config, context, state_machine, order_manager, **kwargs):
        super().__init__(config, context, state_machine, order_manager)
        self.logger = logging.getLogger("GridStrategy")
        self.cfg = config.get("futures_grid", {})

        # 配置参数
        self.symbol = self.cfg.get("symbol", "ETH-USDT-SWAP")
        self.investment = float(self.cfg.get("investment", 20))
        self.leverage = int(self.cfg.get("leverage", 5))
        self.grid_count = int(self.cfg.get("grid_count", 23))

        # 状态标记
        self.is_initialized = False

    async def initialize(self):
        """
        初始化：仅做状态标记，不进行任何交易动作
        注意：具体的杠杆设置建议移交至 OrderManager 或 execution 层统一处理，
        此处策略只负责汇报它需要的杠杆倍数。
        """
        self.logger.info(f"✅ 网格策略 ({self.symbol}) 已就绪，等待扫描信号...")
        self.is_initialized = True

    async def analyze_signal(self) -> Optional[Dict]:
        """
        🧠 核心大脑：计算网格，生成所有待执行订单，但不执行。
        """
        if not self.is_initialized:
            await self.initialize()

        try:
            # 1. 检查是否已有持仓 (如果有持仓，暂不生成开仓信号，防止重复开单)
            current_pos = self.context.get_position(self.symbol)
            if current_pos and float(current_pos.quantity) != 0:
                # 这里可以扩展：计算是否需要补单，如果需要，返回“补单”信号
                return None

            # 2. 获取市场价格
            ticker = await self.om.client.get_ticker(self.symbol)
            if not ticker:
                return None
            current_price = float(ticker['last'])

            # 3. 计算网格参数 (示例逻辑：上下 10% 区间，等差网格)
            # 实际应用中建议结合 ATR 或布林带计算 dynamic range
            range_pct = 0.10
            lower_price = current_price * (1 - range_pct)
            upper_price = current_price * (1 + range_pct)

            # 计算每格价格间隔
            price_step = (upper_price - lower_price) / self.grid_count

            # 4. 生成所有网格挂单明细 (Plan Orders)
            pending_orders = []

            # 计算单格下单数量 (假设做多网格，资金均分)
            # 注意：实际需考虑合约面值(contract_val)和最小下单单位
            # 这里简化为按 USDT 价值估算张数，实际需调用 instrument info
            total_margin = self.investment * self.leverage
            amount_per_grid = total_margin / self.grid_count
            # 假设 1张 = 10 USDT (需根据币种调整，这里仅做演示)
            size_per_grid = max(1, int(amount_per_grid / 10))

            self.logger.info(f"📊 [网格计算] 价格:{current_price} | 区间:[{lower_price:.2f}, {upper_price:.2f}] | 格数:{self.grid_count}")

            # 循环生成 Limit Orders
            for i in range(self.grid_count):
                grid_price = lower_price + (i * price_step)

                # 简单逻辑：
                # 低于当前价 -> 挂买单 (做多接货)
                # 高于当前价 -> 挂卖单 (平仓获利)
                if grid_price < current_price:
                    side = "buy"
                else:
                    side = "sell"

                # 构造标准订单结构
                order_plan = {
                    "symbol": self.symbol,
                    "price": f"{grid_price:.4f}", # 格式化价格
                    "size": str(size_per_grid),
                    "side": side,
                    "type": "limit",              # 限价单
                    "reduce_only": False          # 网格单通常非只减仓
                }
                pending_orders.append(order_plan)

            # 5. 打包信号并返回给 Runtime/Audit
            if pending_orders:
                signal = {
                    "symbol": self.symbol,
                    "action": "grid_start",       # 动作类型
                    "strategy": "futures_grid",
                    "leverage": self.leverage,    # 告知 execution 层需要设置的杠杆
                    "orders": pending_orders,     # 🔥 核心：包含 20-30 个待执行订单的列表
                    "reason": f"Grid Init: {lower_price:.2f}-{upper_price:.2f}"
                }
                self.logger.info(f"🚀 [策略产出] 生成 {len(pending_orders)} 个网格挂单计划，发送至审计...")
                return signal

            return None

        except Exception as e:
            self.logger.error(f"策略分析异常: {e}")
            return None

    async def shutdown(self):
        """
        策略停止时的逻辑
        注意：策略不直接撤单，而是发出'停止'信号请求 Runtime 撤单
        """
        self.logger.info("🛑 策略停止，建议 Runtime 撤销相关挂单。")
        # 这里不需要 await self.om.cancel...
        # 实际的撤单动作应由 Runtime 在监测到状态变化时触发
        pass