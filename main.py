import time
import sys
from loguru import logger

import config.config
from config.config import configpara

# 导入自定义模块
from exchange.okx_client import OKXClient
from data.market import MarketService
from scanner.top_gainers import TopGainersScanner
from strategy.short_martingale import ShortMartingaleStrategy
from trade.dry_run import DryRunTrader
from trade.order import RunTrader

logger.remove()
# 配置日志输出到文件
logger.add("logs/trading_bot.log", rotation="500 MB", level=configpara.LOG_LEVEL)
# 配置日志输出到文件
logger.add(sys.stderr, level=configpara.console_LOG_LEVEL)



def run_trading_cycle(client, scanner, strategy, balance_info, active_symbols,leverage):
    """
    单次交易轮询逻辑
    """
    logger.info(f"--- 市场扫描 (当前监控中: {list(active_symbols)}) ---")
    logger.info("--- 开始新一轮市场扫描 ---")

    # 1. 扫描涨幅榜 (成交额过滤已在 scanner 内实现)
    top_list = scanner.get_top_gainers(limit=configpara.SCAN_LIMIT)

    if not top_list:
        logger.warning("未发现符合流动性要求的币种")
        return

    # 2. 遍历筛选潜在标的
    for symbol_data in top_list:
        inst_id = symbol_data["instId"]
        # --- 【关键拦截】如果在名单里，说明已经下过单了，直接跳过 ---
        if inst_id in active_symbols:
            continue
        try:
            # 价格位置过滤 (从 config 读取参数，例如 0.9)
            if symbol_data["position"] < configpara.ENTRY_POSITION_THRESHOLD:
                continue

            logger.success(f"发现高位目标: {inst_id}|当前价格{symbol_data['last']} | 当前位置: {symbol_data['position'] * 100:.1f}%")

            # 3. 获取合约规格
            inst_info = client.get_instrument_info(inst_id)
            if not inst_info:
                logger.error(f"{inst_id} 获取合约信息失败")
                continue

            ct_val = float(inst_info["ctVal"])
            lot_sz = float(inst_info["lotSz"])

            # 4. 获取实时账户可用余额 (这里假设余额列表第一个是USDT，实战建议通过'ccy'查找)
            usdt_bal = 0.0
            for details in balance_info.get('details', []):
                if details['ccy'] == 'USDT':
                    usdt_bal = float(details['availBal'])
                    break

            # 5. 构建马丁格尔计划
            current_price = symbol_data["last"]
            orders = strategy.build_orders(current_price)

            # 6. 风险审核
            audit = strategy.audit_orders(
                orders=orders,
                current_price=current_price,
                ct_val=ct_val,
                lot_sz=lot_sz,
                avail_usdt=usdt_bal
            )

            if not audit:
                logger.warning(f"{inst_id} | 风控审核未通过，放弃下单")
                continue

            # 7. 执行层 (这里可以切换 DryRun 或 真实交易)
            logger.info(f"🚀 {inst_id} 计划执行：均价预估 {audit['avg_price']:.4f}, 止损位 {audit['sl_price']:.4f}")
            trader = RunTrader(client)
            # 【正式发单】
            final_orders = trader.limit_orders(inst_id, orders,leverage)
            if len(final_orders) > 0:
                # --- 【关键记录】下单成功，加入全局名单 ---
                active_symbols.add(inst_id)
                logger.success(f"🎯 成功挂出 {len(final_orders)} 笔订单。现在只需等待行情拉升触发补仓。")
                # 这里你可以把这些 order_id 存到本地数据库或 JSON 文件，方便后续监控

        except Exception as e:
            logger.error(f"处理币种 {inst_id} 时发生错误: {e}")
            continue  # 继续处理下一个币种



def main():
    logger.info("来财小猪 OKX 量化助手启动中...")
    mode = "🎮 模拟盘（DEMO）" if configpara.OKX_FLAG == "1" else "💰 实盘"
    logger.warning("=" * 70)
    logger.warning(f"⚠️  当前运行模式: {mode}")
    logger.warning(f"⚠️  请确认是否正确！")
    logger.warning("=" * 70 + "\n")
    # 如果是实盘，再次确认
    if configpara.OKX_FLAG == "0":
        logger.warning("⚠️  即将进入实盘模式！按回车键继续，或 Ctrl+C 取消...")
        input()

    logger.info(f"来财小猪 OKX 量化助手 {mode}启动中...")
    # 1. 初始化客户端
    try:
        flag = configpara.OKX_FLAG
        if flag=="0" :
            client = OKXClient(
                api_key=configpara.OKX_API_KEY,
                secret_key=configpara.OKX_SECRET_KEY,
                passphrase=configpara.OKX_PASSPHRASE,
                flag=configpara.OKX_FLAG
            )
        else:
            client = OKXClient(
                api_key=configpara.OKX_M_API_KEY,
                secret_key=configpara.OKX_M_SECRET_KEY,
                passphrase=configpara.OKX_M_PASSPHRASE,
                flag=configpara.OKX_FLAG
            )
        # 2. 启动 WebSocket 实时行情 (提高响应速度)
        # 预加载一些主流币种监控，或者由扫描器动态订阅
        client.init_websocket(["BTC-USDT-SWAP", "ETH-USDT-SWAP"])

        market_service = MarketService(client)
        # 启动时打印账户余额（只读）
        balance = client.get_account_balance()
        # logger.info(f"小主的账户信息: {balance}")
        logger.info(f"小主的账户总资产 : {balance['totalEq']}(USD)")
        for coin in balance['details']:
            # 只打印余额大于 0 的币种，过滤掉“碎屑”
            if float(coin['availBal']) > 0.0001:
                logger.info(f"币种: {coin['ccy']}")
                logger.info(f"  可用余额: {coin['availBal']} {coin['ccy']}")
                logger.info(f"  折合人民币: {float(coin['eqUsd']) * 6.9} RMB")
                logger.info(f"  冻结金额: {coin['frozenBal']}")
        scanner = TopGainersScanner(client, min_volume_usdt=configpara.MIN_VOLUME)

        strategy = ShortMartingaleStrategy(
            total_value_usdt=configpara.total_value_usdt,
            max_orders=configpara.MAX_ORDERS,
            entry_offset_pct=configpara.entry_offset_pct,
            step_pct=configpara.STEP_PCT,
            tp_pct=configpara.TP_PCT,
            sl_pct=configpara.SL_PCT,
            leverage=configpara.LEVERAGE
        )

        # 3. 初始资产检查
        balance = client.get_account_balance()
        logger.info(f"账户初始总资产: {balance['totalEq']} USD")
        active_symbols = set()
        trader = RunTrader(client)
        # 4. 主循环
        while True:
            try:
                # 每一轮更新一次余额
                current_balance = client.get_account_balance()

                run_trading_cycle(client, scanner, strategy, current_balance, active_symbols,leverage=config.config.configpara.LEVERAGE)

                logger.info(f"轮询结束，休眠 {configpara.LOOP_INTERVAL} 秒...")
                time.sleep(configpara.LOOP_INTERVAL)
                # 每次循环都检查一下仓位是否有变化
                # 3. 【核心监控逻辑】对已经下单的币种进行成交检查和止盈止损维护
                # 使用 list() 是为了在遍历时可以安全地从 set 中 remove 元素
                for inst_id in list(active_symbols):
                # 检查这个币种是否补仓，并更新止盈止损
                    trader.monitor_and_sync(inst_id, strategy)
                    # 检查这个币种是否已经彻底清仓（止盈或止损离场了）
                    # 这里假设你的 trader 类里有一个判断是否完全结束的方法
                    if trader.is_completely_exit(inst_id):
                        logger.warning(f"♻️ {inst_id} 交易已结束，从监控名单移除")
                        active_symbols.remove(inst_id)
            except KeyboardInterrupt:
                logger.warning("检测到手动停止指令，正在安全退出...")
                break
            except Exception as e:
                logger.critical(f"主循环崩溃，5秒后尝试重启: {e}")
                time.sleep(5)
    except Exception as e:
        logger.error(f"系统初始化失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()