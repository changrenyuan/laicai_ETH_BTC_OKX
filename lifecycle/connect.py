"""
🔌 Connect Phase
连接交易所 & 初始状态全面拉取（资金/交易账户/持仓/挂单明细打印）
"""

import os
import logging
from exchange.okx_client import OKXClient
from monitor.dashboard import Dashboard
from monitor.notifier import Notifier

logger = logging.getLogger("Connect")

class Connect:
    """Connect 生命周期阶段 - 连接交易所"""

    def __init__(self, config: dict):
        self.config = config
        self.client = None

    async def run(self) -> OKXClient:
        """执行连接及状态初始化"""
        Dashboard.log("【3】连接交易所 & 拉取初始状态...", "INFO")

        # 1. 初始化客户端
        sub_cfg = self.config.get("sub_account", self.config)
        self.client = OKXClient(sub_cfg)
        connected = await self.client.connect()

        if not connected:
            raise ConnectionError("无法连接到 OKX API，请检查 API Key 或网络设置")

        Dashboard.log("交易所 API 连接建立。", "SUCCESS")

        total_usdt = 0.0
        report_lines = []

        try:
            print("\n" + "="*50)
            print("💰 账户明细扫描 (Detailed Account Snapshot)")
            print("="*50)

            # --- A. 资金账户 (Funding) ---
            funding_res = await self.client.get_funding_balances()
            print("\n🏦 [资金账户] (Funding Account):")
            funding_report = "🏦 [资金账户]:"
            if funding_res:
                for item in funding_res:
                    ccy = item.get("ccy")
                    bal = float(item.get("bal", 0))
                    if bal > 0:
                        line = f"   - {ccy}: {bal:.4f}"
                        print(line)
                        funding_report += f"\n{line}"
                        if ccy == "USDT": total_usdt += bal
            else:
                print("   (无余额)")
                funding_report += "\n   (无余额)"
            report_lines.append(funding_report)

            # --- B. 交易账户 (Trading) ---
            trading_res = await self.client.get_trading_balances()
            print("\n📈 [交易账户] (Trading Account):")
            trading_report = "\n📈 [交易账户]:"
            if trading_res and len(trading_res) > 0:
                details = trading_res[0].get("details", [])
                for item in details:
                    ccy = item.get("ccy")
                    avail = float(item.get("availBal", 0))
                    eq = float(item.get("eq", 0))
                    if eq > 0:
                        line = f"   - {ccy}: {eq:.2f} (可用: {avail:.2f})"
                        print(line)
                        trading_report += f"\n{line}"
                        if ccy == "USDT": total_usdt += eq

                # 更新 Dashboard 概览表
                if details:
                    d = details[0]
                    Dashboard.print_account_overview({
                        'totalEq': d.get('eq', 0),
                        'availBal': d.get('availBal', 0),
                        'upl': d.get('upl', 0),
                        'mgnRatio': d.get('mgnRatio', 'N/A')
                    })
            else:
                print("   (无余额)")
                trading_report += "\n   (无余额)"
            report_lines.append(trading_report)

            # --- C. 当前持仓 (Positions) ---
            pos_res = await self.client.get_positions()
            print("\n📦 [当前持仓] (Active Positions):")
            pos_report = "\n📦 [当前持仓]:"
            if pos_res and len(pos_res) > 0:
                for p in pos_res:
                    line = f"   - {p['instId']}: {p['posSide']} {p['pos']}张 (未实现盈亏: {p['upl']})"
                    print(line)
                    pos_report += f"\n{line}"
            else:
                print("   (无持仓)")
                pos_report += "\n   (无持仓)"
            report_lines.append(pos_report)

            # --- D. 汇总打印 ---
            print("\n" + "="*50)
            print(f"💵 预估总资产: {total_usdt:.2f} USDT")
            print("="*50 + "\n")

            # 3. 发送通知
            full_msg = "🚀 系统启动报告\n" + "\n".join(report_lines) + f"\n\n💵 USDT 总权益估算: {total_usdt:.2f}"
            await self._send_startup_notification(full_msg)

        except Exception as e:
            Dashboard.log(f"初始状态拉取异常: {e}", "ERROR")
            import traceback
            logger.error(traceback.format_exc())

        return self.client

    async def _send_startup_notification(self, message: str):
        """发送启动通知"""
        notify_cfg = self.config.get("notifications", {})
        notifier = Notifier({
            "enabled": notify_cfg.get("enabled", True),
            "telegram_enabled": os.getenv("TELEGRAM_BOT_TOKEN") is not None,
            "dingtalk_enabled": os.getenv("DINGTALK_WEBHOOK") is not None,
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
            "dingtalk_webhook": os.getenv("DINGTALK_WEBHOOK"),
        })
        await notifier.send_alert(message, level="info", source="system_startup")