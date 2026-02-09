"""
🔥 资金防护 (Phase 5 实战版)
资金再平衡 / 自动补保证金 / 利润提取
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import logging

from core.context import Context
from exchange.okx_client import OKXClient

@dataclass
class TransferRecord:
    """资金划转记录"""
    timestamp: datetime
    from_account: str
    to_account: str
    amount: float
    currency: str
    reason: str

class FundGuard:
    """
    资金防护类
    核心功能：监控保证金率，自动在 资金账户 <-> 交易账户 之间划转 USDT
    """

    def __init__(self, config: dict, client: Optional[OKXClient] = None):
        self.config = config
        self.client = client # 需要持有 client 进行划转操作
        self.logger = logging.getLogger(__name__)

        # 阈值配置
        guard_cfg = config.get("fund_guard", {}) # 注意 yaml 里的层级
        margin_cfg = config.get("margin_guard", {})

        # 1. 补仓阈值 (例如 300%)
        self.min_margin = float(margin_cfg.get("margin_ratio_warning", 3.0))
        # 2. 止盈阈值 (例如 1000%，合约赚了很多钱)
        self.profit_margin = float(margin_cfg.get("margin_ratio_profit", 10.0))

        # 限制
        self.transfer_threshold = float(guard_cfg.get("transfer_threshold", 50.0)) # 最小划转金额
        self.max_transfer_per_day = float(guard_cfg.get("max_transfer_per_day", 10000.0))

        # 状态
        self.transfers: List[TransferRecord] = []
        self.last_check_time: Optional[datetime] = None

    def set_client(self, client: OKXClient):
        """依赖注入"""
        self.client = client

    async def check_and_transfer(self, context: Context):
        """
        [自动化核心] 检查并执行资金划转
        """
        if not self.client:
            return

        # 1. 获取当前保证金率
        # 注意：Context 里的 margin_ratio 需要在 Main Loop 或 Scheduler 里更新
        ratio = context.margin_ratio
        if ratio <= 0:
            return # 数据未就绪

        self.last_check_time = datetime.now()

        # 获取账户总权益 (用于计算金额)
        # 假设我们只关心 USDT
        usdt_balance = context.balances.get("USDT")
        if not usdt_balance:
            return

        # 简单估算：合约账户权益。实际应从 API 获取 details.eq
        equity = usdt_balance.total

        # 2. 场景A: 🚨 危险！补仓 (资金 -> 交易)
        if ratio < self.min_margin:
            self.logger.warning(f"🚨 保证金不足 ({ratio:.2f} < {self.min_margin})，准备补仓...")

            # 计算需要补充多少才能回到安全线 (例如 5.0)
            target_ratio = 5.0
            # 当前占用保证金 = 权益 / ratio
            used_margin = equity / ratio if ratio > 0 else 0
            needed_equity = used_margin * target_ratio
            transfer_amount = needed_equity - equity

            if transfer_amount < self.transfer_threshold:
                transfer_amount = self.transfer_threshold

            # 检查资金账户余额
            funding_bals = await self.client.get_funding_balances("USDT")
            avail_funding = 0.0
            if funding_bals:
                for b in funding_bals:
                    if b['ccy'] == 'USDT':
                        avail_funding = float(b['availBal'])

            # 执行划转
            real_transfer = min(transfer_amount, avail_funding)
            if real_transfer > 1.0: # 至少转1块钱
                success = await self.client.transfer_funds("USDT", real_transfer, "6", "18") # 6->18
                if success:
                    self._record_transfer("funding", "trading", real_transfer, "Margin Top-up")
                else:
                    self.logger.error("❌ 补仓划转失败")
            else:
                self.logger.critical("😱 资金账户没钱了，无法补仓！")

        # 3. 场景B: 💰 止盈！提现 (交易 -> 资金)
        elif ratio > self.profit_margin:
            self.logger.info(f"💰 保证金过高 ({ratio:.2f} > {self.profit_margin})，执行利润提取...")

            # 提取多余资金，保留到安全线 (例如 8.0)
            target_ratio = 8.0
            used_margin = equity / ratio
            target_equity = used_margin * target_ratio
            transfer_amount = equity - target_equity

            if transfer_amount > self.transfer_threshold:
                # 检查交易账户可用余额 (availBal)
                # 注意：equity 包含未实现盈亏，不能全转，只能转 availBal
                avail_trading = usdt_balance.available

                real_transfer = min(transfer_amount, avail_trading)
                if real_transfer > 1.0:
                    success = await self.client.transfer_funds("USDT", real_transfer, "18", "6") # 18->6
                    if success:
                        self._record_transfer("trading", "funding", real_transfer, "Profit Take")

    def _record_transfer(self, from_acc, to_acc, amount, reason):
        rec = TransferRecord(datetime.now(), from_acc, to_acc, amount, "USDT", reason)
        self.transfers.append(rec)
        self.logger.info(f"✅ 资金划转成功: {amount} USDT ({from_acc}->{to_acc}) Reason: {reason}")