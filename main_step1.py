"""
🎯 Phase 1 验收脚本 (修复版：双账户查询)
"""

import asyncio
import sys
import os
import re
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config_with_env(file_path):
    pattern = re.compile(r'\$\{([^}^{]+)\}')
    def replace_env(match):
        env_var = match.group(1)
        return os.environ.get(env_var, f"${{{env_var}}}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(pattern.sub(replace_env, f.read()))

async def main():
    print("=" * 70)
    print("🎯 Phase 1: 基础设施验收 (资金/交易账户双检)")
    print("=" * 70)

    # 1. 配置加载
    try:
        account_config = load_config_with_env("config/account.yaml")
        risk_config = load_config_with_env("config/risk.yaml")
        print("✅ 配置加载成功")
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return

    # 2. 连接交易所
    print("\n🔌 连接交易所...")
    from exchange.okx_client import OKXClient
    okx_client = OKXClient(account_config["sub_account"])
    if not await okx_client.connect():
        print("❌ 无法创建 Session")
        return

    # 3. 核心：查询两个账户
    print("\n💰 正在扫描资金...")
    total_usdt = 0.0
    report_lines = []

    try:
        # --- A. 查询资金账户 (Funding) ---
        funding_res = await okx_client.get_funding_balances()
        report_lines.append("🏦 [资金账户] (Funding Account):")
        has_funding = False
        if funding_res:
            for item in funding_res:
                ccy = item.get("ccy")
                bal = float(item.get("bal", 0))
                if bal > 0:
                    has_funding = True
                    report_lines.append(f"   - {ccy}: {bal:.4f}")
                    if ccy == "USDT": total_usdt += bal
        if not has_funding:
            report_lines.append("   (无余额)")

        # --- B. 查询交易账户 (Trading) ---
        trading_res = await okx_client.get_trading_balances()
        report_lines.append("\n📈 [交易账户] (Trading Account):")
        has_trading = False
        if trading_res and len(trading_res) > 0:
            for item in trading_res[0].get("details", []):
                ccy = item.get("ccy")
                avail = float(item.get("availBal", 0))
                eq = float(item.get("eq", 0)) # 权益
                if eq > 0:
                    has_trading = True
                    report_lines.append(f"   - {ccy}: {eq:.4f} (可用: {avail:.4f})")
                    if ccy == "USDT": total_usdt += eq
        if not has_trading:
            report_lines.append("   (无余额)")

        # 打印报告
        print("-" * 50)
        for line in report_lines:
            print(line)
        print("-" * 50)
        print(f"💵 USDT 总权益估算: {total_usdt:.4f}")

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        await okx_client.disconnect()
        return

    # 4. 发送通知
    print("\n📱 推送通知测试...")
    from monitor.notifier import Notifier
    notify_cfg = {
        "enabled": True,
        "telegram_enabled": os.getenv("TELEGRAM_BOT_TOKEN") is not None,
        "dingtalk_enabled": os.getenv("DINGTALK_WEBHOOK") is not None,
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "dingtalk_webhook": os.getenv("DINGTALK_WEBHOOK"),
    }
    notifier = Notifier(notify_cfg)
    msg = f"✅ Phase 1 验收\nUSDT总额: {total_usdt:.2f}"
    await notifier.send_alert(msg, level="info", source="phase1")

    await okx_client.disconnect()
    print("\n🎉 验收结束")

if __name__ == "__main__":
    asyncio.run(main())