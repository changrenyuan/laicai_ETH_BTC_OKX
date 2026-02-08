# -*- coding: utf-8 -*-
"""
来财量化交易系统主程序
"""
import time
import sys
import uuid
from functools import partial

from loguru import logger

import config.config
from config.config import configpara

# 导入自定义模块
from exchange.okx_client import OKXClient
from data.market import MarketService
from data.persistence import PersistenceManager
from data.excel_exporter import export_excel
from scanner.top_gainers import TopGainersScanner
from strategy.short_martingale import ShortMartingaleStrategy
from trade.dry_run import DryRunTrader
from trade.order import RunTrader

# 配置日志
logger.remove()
logger.add("logs/trading_bot.log", rotation="500 MB", level=configpara.LOG_LEVEL)
logger.add(sys.stderr, level=configpara.console_LOG_LEVEL)


def run_trading_cycle(
    client,
    trader,
    scanner,
    strategy,
    balance_info,
    active_symbols,
    leverage,
    persistence
):
    """
    单次交易轮询逻辑

    :param client: OKX 客户端
    :param scanner: 市场扫描器
    :param strategy: 策略实例
    :param balance_info: 账户余额信息
    :param active_symbols: 活跃交易对集合
    :param leverage: 杠杆倍数
    :param persistence: 持久化管理器
    """
    logger.info(f"--- 市场扫描 (当前监控中: {list(active_symbols)}) ---")
    logger.info("--- 开始新一轮市场扫描 ---")

    # 记录扫描行为
    persistence.log_action(
        action_type="SCAN",
        detail=f"开始新一轮市场扫描，监控中: {len(active_symbols)} 个币种",
        extra_data={"active_symbols": list(active_symbols)}
    )

    # 1. 扫描涨幅榜
    top_list = scanner.get_top_gainers(limit=configpara.SCAN_LIMIT)

    if not top_list:
        logger.warning("未发现符合流动性要求的币种")
        return

    # 2. 遍历筛选潜在标的
    for symbol_data in top_list:
        inst_id = symbol_data["instId"]

        # 如果已经在监控名单中，跳过
        if inst_id in active_symbols:
            continue

        try:
            # 价格位置过滤
            if symbol_data["position"] < configpara.ENTRY_POSITION_THRESHOLD:
                continue

            logger.success(
                f"发现高位目标: {inst_id}|当前价格 {symbol_data['last']} | "
                f"当前位置: {symbol_data['position'] * 100:.1f}%"
            )

            # 记录发现目标
            persistence.log_action(
                action_type="TARGET_FOUND",
                inst_id=inst_id,
                detail=f"发现高位目标，价格: {symbol_data['last']}，位置: {symbol_data['position'] * 100:.1f}%"
            )

            # 3. 获取合约规格
            inst_info = client.get_instrument_info(inst_id)
            if not inst_info:
                logger.error(f"{inst_id} 获取合约信息失败")
                continue

            ct_val = float(inst_info["ctVal"])
            lot_sz = float(inst_info["lotSz"])

            # 4. 获取实时账户可用余额
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
                persistence.log_action(
                    action_type="AUDIT_FAILED",
                    inst_id=inst_id,
                    detail="风控审核未通过，放弃下单"
                )
                continue

            # 7. 执行下单
            logger.info(
                f"🚀 {inst_id} 计划执行：均价预估 {audit['avg_price']:.4f}, "
                f"止损位 {audit['sl_price']:.4f}"
            )

            # trader = RunTrader(client)

            # 创建策略记录
            strategy_id = f"{inst_id}_{uuid.uuid4().hex[:8]}"
            persistence.create_strategy(
                strategy_id=strategy_id,
                inst_id=inst_id,
                strategy_type="SHORT_MARTINGALE",
                params={
                    "total_value_usdt": strategy.total_value_usdt,
                    "max_orders": strategy.max_orders,
                    "entry_offset_pct": strategy.entry_offset_pct,
                    "step_pct": strategy.step_pct,
                    "tp_pct": strategy.tp_pct,
                    "sl_pct": strategy.sl_pct,
                    "leverage": strategy.leverage
                },
                audit_result=audit
            )

            # 正式发单
            final_orders = trader.limit_orders(inst_id, orders, leverage)

            if len(final_orders) > 0:
                # 保存订单记录
                for order in final_orders:
                    # 获取订单详情
                    order_data = {
                        "ordId": order.get("ordId"),
                        "instId": inst_id,
                        "side": "sell",
                        "posSide": "short",
                        "ordType": "limit",
                        "px": order.get("price"),
                        "sz": order.get("calc_sz")
                    }
                    persistence.save_order(order_data, strategy_id, source="MARTINGALE")

                    logger.info(
                        f"订单 #{order['index']} 已保存: "
                        f"价格 {order['price']} | 张数 {order['calc_sz']}"
                    )

                # 下单成功，加入监控名单
                active_symbols.add(inst_id)
                logger.success(f"🎯 成功挂出 {len(final_orders)} 笔订单。策略ID: {strategy_id}")

                persistence.log_action(
                    action_type="STRATEGY_STARTED",
                    strategy_id=strategy_id,
                    inst_id=inst_id,
                    detail=f"策略启动，挂出 {len(final_orders)} 笔订单"
                )
            else:
                # 下单失败，标记策略为失败
                persistence.update_strategy_status(
                    strategy_id=strategy_id,
                    status="FAILED",
                    exit_reason="下单失败"
                )

        except Exception as e:
            logger.error(f"处理币种 {inst_id} 时发生错误: {e}")
            persistence.log_action(
                action_type="ERROR",
                inst_id=inst_id,
                detail=f"处理错误: {str(e)}"
            )
            continue

def on_receive_ws_msg(message, trader, strategy):
    """
        WebSocket 消息入口
        :param message: WS 推送的原始字典
        :param trader: 传入的 RunTrader 唯一实例
        :param strategy: 传入的策略逻辑实例
        """
    arg = message.get("arg", {})
    channel = arg.get("channel")
    data = message.get("data", [])

    if channel == "positions":
        # 直接交给 trader 处理，trader 内部会根据 strategy 计算新价格
        trader.handle_ws_position_update(data, strategy)

    elif channel == "orders":
        # 如果需要监听订单状态（例如撤单成功、部分成交）可以在这里扩展
        pass

def main():
    """主函数"""
    logger.info("来财小猪 OKX 量化助手启动中...")
    mode = "🎮 模拟盘（DEMO）" if configpara.OKX_FLAG == "1" else "💰 实盘"
    logger.warning("=" * 70)
    logger.warning(f"⚠️  当前运行模式: {mode}")
    logger.warning(f"⚠️  请确认是否正确！")
    logger.warning("=" * 70 + "\n")

    # 1. 初始化持久化管理器
    try:
        persistence = PersistenceManager()
        logger.success("✅ 数据持久化模块已初始化")
        logger.info(f"   数据库路径: data/trading_history.db")
    except Exception as e:
        logger.error(f"❌ 数据持久化模块初始化失败: {e}")
        sys.exit(1)

    # 2. 初始化客户端
    try:
        logger.info("正在连接交易所...")
        flag = configpara.OKX_FLAG

        if flag == "0":
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

        logger.success("✅ 交易所连接成功")

        # 启动 WebSocket
        client.init_websocket(["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
        logger.success("✅ WebSocket 实时行情已启动")

    except Exception as e:
        logger.error(f"❌ 交易所连接失败: {e}")
        sys.exit(1)

    # 3. 【启动检查】查询并显示账户信息
    logger.info("")
    logger.info("=" * 70)
    logger.info("📊 正在查询账户信息...")
    logger.info("=" * 70)

    try:
        # 3.1 查询账户余额
        balance = client.get_account_balance()
        persistence.save_account_balance(balance)

        total_equity = float(balance.get("totalEq", 0))
        logger.success(f"💰 账户总资产: {total_equity:.2f} USD (约 {total_equity * 6.9:.2f} RMB)")
        logger.info("")

        # 3.2 显示各币种余额
        logger.info("📋 各币种余额明细:")
        has_balance = False
        for coin in balance.get('details', []):
            avail_bal = float(coin.get('availBal', 0))
            frozen_bal = float(coin.get('frozenBal', 0))
            eq_usd = float(coin.get('eqUsd', 0))

            if avail_bal > 0.0001 or frozen_bal > 0.0001:
                has_balance = True
                logger.info(f"  🪙 {coin['ccy']}:")
                logger.info(f"     可用: {avail_bal:.4f} {coin['ccy']}")
                logger.info(f"     冻结: {frozen_bal:.4f} {coin['ccy']}")
                logger.info(f"     折合: {eq_usd:.2f} USD (约 {eq_usd * 6.9:.2f} RMB)")

        if not has_balance:
            logger.warning("  ⚠️  账户中没有可用余额！")
        logger.info("")

        # 3.3 查询当前持仓
        logger.info("📊 当前持仓状态:")
        pos_res = client.account.get_positions()
        all_positions = pos_res.get("data", [])

        # 过滤出有持仓的记录
        active_positions = []
        for pos in all_positions:
            pos_size = float(pos.get("pos", 0))
            if pos_size != 0:
                active_positions.append(pos)

        if active_positions:
            # 保存持仓到数据库
            persistence.save_positions(active_positions)

            for pos in active_positions:
                inst_id = pos.get("instId")
                pos_side = pos.get("posSide")
                pos_size = float(pos.get("pos", 0))
                avg_px = float(pos.get("avgPx", 0))
                last_px = float(pos.get("last", 0))
                upl = float(pos.get("upl", 0))
                upl_ratio = float(pos.get("uplRatio", 0))

                # 计算方向符号
                side_symbol = "📉 做空" if pos_side == "short" else "📈 做多"

                logger.info(f"  {side_symbol} {inst_id}:")
                logger.info(f"     持仓量: {pos_size}")
                logger.info(f"     均价: {avg_px:.6f}")
                logger.info(f"     最新价: {last_px:.6f}")
                logger.info(f"     未实现盈亏: {upl:.2f} USD ({upl_ratio*100:.2f}%)")

            logger.warning(f"  ⚠️  当前共有 {len(active_positions)} 个活跃持仓")
        else:
            logger.success("  ✅ 当前没有持仓，可以放心开始新的策略")

        logger.info("")

        # 3.4 显示历史策略记录
        logger.info("📜 最近的策略记录:")
        recent_strategies = persistence.get_active_strategies()
        if recent_strategies:
            for strat in recent_strategies[:5]:  # 只显示前5个
                inst_id = strat.get("inst_id")
                status = strat.get("status")
                start_time = strat.get("start_time")
                logger.info(f"  🔹 {inst_id} | 状态: {status} | 开始时间: {start_time}")
        else:
            logger.info("  ℹ️  暂无活跃策略")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ 查询账户信息失败: {e}")
        sys.exit(1)

    # 4. 【用户确认】询问是否开始扫描
    logger.warning("=" * 70)
    logger.warning("⚠️  账户信息已加载完成！")
    logger.warning("=" * 70)
    logger.info("")
    logger.info("接下来系统将执行以下操作:")
    logger.info("  1. 扫描涨幅榜，寻找高潜力币种")
    logger.info("  2. 对符合条件的目标执行马丁格尔做空策略")
    logger.info("  3. 自动监控持仓，动态调整止盈止损")
    logger.info("")
    logger.info("所有操作记录将保存到: data/trading_history.db")
    logger.info("")

    # 询问用户确认
    if configpara.OKX_FLAG == "0":
        logger.warning("⚠️  即将进入实盘模式！")
        logger.warning("⚠️  请确认:")
        logger.warning(f"   - 账户余额: {total_equity:.2f} USD")
        logger.warning(f"   - 活跃持仓: {len(active_positions)} 个")
        logger.warning("")
        confirm = input("按回车键继续启动，或输入 'quit' 退出: ")
        if confirm.lower() in ['quit', 'q', 'exit']:
            logger.warning("👋 用户取消启动，程序退出")
            sys.exit(0)
    else:
        # 模拟盘也询问，但更宽松
        logger.info("🎮 模拟盘模式，按回车键开始扫描...")
        input()

    logger.success("🚀 系统启动！开始市场扫描...")
    logger.info("=" * 70)
    logger.info("")

    # 5. 初始化市场服务和扫描器
    try:
        market_service = MarketService(client)
        scanner = TopGainersScanner(client, min_volume_usdt=configpara.MIN_VOLUME)
        logger.success("✅ 市场扫描器已初始化")

        strategy = ShortMartingaleStrategy(
            total_value_usdt=configpara.total_value_usdt,
            max_orders=configpara.MAX_ORDERS,
            entry_offset_pct=configpara.entry_offset_pct,
            step_pct=configpara.STEP_PCT,
            tp_pct=configpara.TP_PCT,
            sl_pct=configpara.SL_PCT,
            leverage=configpara.LEVERAGE,
            step_factor=configpara.step_factor, # float = 1.3,  # 价格间隔的扩大倍数 (越后面间隔越宽)
            size_factor=configpara.size_factor # float = 1.25,  # 加仓倍数 (1.25倍投)
        )
        logger.success("✅ 马丁格尔策略已初始化")



        # 6. 导出 Excel 报表
        logger.info("")
        logger.info("📊 正在导出 Excel 报表...")
        try:
            excel_path = export_excel()
            logger.success(f"✅ Excel 报表已导出: {excel_path}")
            logger.info("   你可以随时打开这个文件查看当前持仓、余额、策略等信息")
        except Exception as e:
            logger.warning(f"⚠️  Excel 导出失败: {e}")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        sys.exit(1)

    # 7. 主循环
    trader = RunTrader(client)
    logger.success("✅ 交易执行器已初始化")
    active_symbols = set()
    bound_callback = partial(on_receive_ws_msg, trader=trader, strategy=strategy)

    # 启动 WebSocket 并传入绑定后的回调
    client.init_websocket(
        inst_ids=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],  # 这里的币种是为了更新价格缓存 (Public)
        callback=bound_callback
    )
    loop_count = 0  # 循环计数器
    excel_export_interval = 5  # 每 5 次循环导出一次 Excel
    logger.info("")

    while True:
        try:
            # 每一轮更新一次余额
            current_balance = client.get_account_balance()

            # 执行交易周期
            run_trading_cycle(
                client=client,
                trader=trader,
                scanner=scanner,
                strategy=strategy,
                balance_info=current_balance,
                active_symbols=active_symbols,
                leverage=configpara.LEVERAGE,
                persistence=persistence
            )

            # 增加循环计数
            loop_count += 1

            # 每隔一定次数导出一次 Excel
            if loop_count % excel_export_interval == 0:
                logger.info(f"📊 正在导出 Excel 报表 (循环次数: {loop_count})...")
                try:
                    excel_path = export_excel()
                    logger.success(f"✅ Excel 报表已更新: {excel_path}")
                except Exception as e:
                    logger.warning(f"⚠️  Excel 导出失败: {e}")

            logger.info(f"轮询结束，休眠 {configpara.LOOP_INTERVAL} 秒...")
            time.sleep(configpara.LOOP_INTERVAL)

            # 每次循环都检查仓位是否有变化
            for inst_id in list(active_symbols):
                # 检查这个币种是否补仓，并更新止盈止损
                trader.monitor_and_sync(inst_id, strategy)

                # 检查这个币种是否已经彻底清仓
                if trader.is_completely_exit(inst_id):
                    logger.warning(f"♻️ {inst_id} 交易已结束，从监控名单移除")

                    # 更新策略状态
                    # TODO: 这里需要根据 inst_id 查找对应的 strategy_id 并更新
                    persistence.log_action(
                        action_type="STRATEGY_EXIT",
                        inst_id=inst_id,
                        detail="交易结束，从监控名单移除"
                    )

                    active_symbols.remove(inst_id)

        except KeyboardInterrupt:
            logger.warning("检测到手动停止指令，正在安全退出...")
            logger.info("正在导出最终的 Excel 报表...")
            try:
                excel_path = export_excel()
                logger.success(f"✅ 最终 Excel 报表已导出: {excel_path}")
            except Exception as e:
                logger.warning(f"⚠️  Excel 导出失败: {e}")
            break
        except Exception as e:
            logger.critical(f"主循环崩溃，5秒后尝试重启: {e}")
            time.sleep(5)

    logger.success("程序已安全退出")


if __name__ == "__main__":
    main()
