"""
🛠 一键平仓脚本 (Phase 2 独立版)
紧急情况下平掉所有持仓，撤销所有挂单。
不依赖高级模块，直接调用 API，确保最高可靠性。
"""

import sys
import asyncio
import logging
from pathlib import Path
import yaml
import os
from dotenv import load_dotenv

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from exchange.okx_client import OKXClient

# 配置简单的日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

async def close_position(client: OKXClient, symbol: str, direction: str):
    """平掉单个仓位"""
    try:
        inst_id = f"{symbol}-SWAP"
        # 构造平仓请求
        data = {
            "instId": inst_id,
            "mgnMode": "cross", # 假设全仓，如果你的策略是逐仓需改为 isolated
        }
        if direction != "net":
            data["posSide"] = direction # long/short

        logger.info(f"正在平仓 {inst_id} ({direction})...")

        # 直接调用 API，不走 OrderManager
        result = await client._request("POST", "/api/v5/trade/close-position", data=data)

        if result is not None:
            logger.info(f"✅ {inst_id} 平仓请求已发送")
            return True
        else:
            logger.error(f"❌ {inst_id} 平仓失败 (API返回空)")
            return False

    except Exception as e:
        logger.error(f"❌ {symbol} 平仓异常: {e}")
        return False

async def cancel_all_orders(client: OKXClient):
    """撤销所有挂单"""
    logger.info("正在撤销所有挂单...")
    try:
        # 获取所有未成交订单
        pending = await client._request("GET", "/api/v5/trade/orders-pending", params={"instType": "SWAP"})
        if not pending:
            logger.info("✅ 当前无挂单")
            return

        for order in pending:
            inst_id = order.get("instId")
            ord_id = order.get("ordId")
            logger.info(f"撤销订单: {inst_id} (ID: {ord_id})")

            await client._request("POST", "/api/v5/trade/cancel-order", data={
                "instId": inst_id,
                "ordId": ord_id
            })

    except Exception as e:
        logger.error(f"❌ 撤单异常: {e}")

async def main():
    print("=" * 60)
    print("🔥 一键平仓脚本 (Panic Button - 独立版)")
    print("=" * 60)

    # 1. 确认
    confirm = input("\n⚠️  警告：此操作将市价平掉所有合约持仓并撤单！\n确定要继续吗？(输入 yes 确认): ")
    if confirm.lower() != "yes":
        print("操作已取消")
        return

    # 2. 加载配置
    try:
        load_dotenv() # 加载 .env
        config_path = Path(__file__).parent.parent / "config" / "account.yaml"

        # 简单读取 yaml 用于获取子账户名（其实 api key 主要靠 env）
        with open(config_path, "r", encoding="utf-8") as f:
            account_config = yaml.safe_load(f)

        print("✅ 配置加载成功")
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return

    # 3. 连接交易所
    client = OKXClient(account_config.get("sub_account", {}))
    if not await client.connect():
        print("❌ 无法连接交易所，请检查网络或代理")
        return

    try:
        # 4. 撤销所有挂单
        await cancel_all_orders(client)

        # 5. 获取持仓
        print("\n📊 获取当前持仓...")
        positions_data = await client.get_positions()

        active_positions = []
        if positions_data:
            active_positions = [p for p in positions_data if float(p.get("pos", 0)) != 0]

        if not active_positions:
            print("✅ 当前无活跃持仓")
            return

        print(f"发现 {len(active_positions)} 个持仓，准备平仓...")

        # 6. 执行平仓
        tasks = []
        for pos in active_positions:
            inst_id = pos.get("instId")
            symbol = inst_id.replace("-SWAP", "")
            pos_side = pos.get("posSide", "net")

            tasks.append(close_position(client, symbol, pos_side))

        if tasks:
            await asyncio.gather(*tasks)

        print("\n✅ 所有操作执行完毕。请务必登录 OKX APP 确认最终状态！")

    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())