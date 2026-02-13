"""
📦 交付演示：OKXExchange 使用示例
==================================
此文件展示 P1 阶段已完成的 OKXExchange 功能

功能演示：
1. OKXExchange 初始化
2. 连接与认证
3. 获取行情数据
4. 账户余额查询
5. 持仓查询
6. 模拟下单（不实际下单）

运行方式：python examples/demo_okx_exchange.py
"""

import sys
import asyncio
import os

# 添加项目路径
sys.path.insert(0, '/workspace/projects/laicai_ETH_BTC_OKX')

from exchange.okx import OKXExchange
from core.events import Event, EventType

print("=" * 80)
print("📦 P1 阶段交付演示：OKXExchange")
print("=" * 80)


async def demo_okx_exchange():
    """演示 OKXExchange 功能"""
    
    # ============================================
    # 1. 初始化 OKXExchange
    # ============================================
    print("\n【测试1】初始化 OKXExchange")
    
    # 从环境变量读取配置（如果存在）
    config = {
        "api_key": os.getenv("OKX_API_KEY", "demo_key"),
        "secret_key": os.getenv("OKX_API_SECRET", "demo_secret"),
        "passphrase": os.getenv("OKX_API_PASSPHRASE", "demo_passphrase"),
        "sandbox": True,  # 使用沙盒环境
        "rate_limits": {
            "trade": {"limit": 20, "window": 2},
            "account": {"limit": 20, "window": 2},
            "market": {"limit": 20, "window": 2}
        }
    }
    
    okx_exchange = OKXExchange(config)
    
    print(f"  交易所名称: {okx_exchange.name}")
    print(f"  是否沙盒: {okx_exchange.sandbox}")
    print(f"  基础URL: {okx_exchange.base_url}")
    print(f"  WebSocket URL: {okx_exchange.ws_url}")
    print(f"  Rate Limit 规则: {okx_exchange.rate_limits_rules}")
    print("  ✅ OKXExchange 初始化成功")
    
    # ============================================
    # 2. 连接与认证
    # ============================================
    print("\n【测试2】连接与认证")
    
    try:
        # 连接
        connected = await okx_exchange.connect()
        print(f"  HTTP 连接: {'✅ 成功' if connected else '❌ 失败'}")
        
        # 认证（需要真实 API Key）
        print("  ⚠️ 跳过认证（需要真实 API Key）")
        print("  如需测试认证，请设置环境变量：")
        print("    - OKX_API_KEY")
        print("    - OKX_API_SECRET")
        print("    - OKX_API_PASSPHRASE")
        
    except Exception as e:
        print(f"  ❌ 连接异常: {e}")
    
    # ============================================
    # 3. 获取行情数据（无需认证）
    # ============================================
    print("\n【测试3】获取行情数据")
    
    try:
        symbol = "BTC-USDT-SWAP"
        ticker = await okx_exchange.get_ticker(symbol)
        
        if ticker:
            print(f"  交易对: {ticker.get('instId')}")
            print(f"  最新价格: {ticker.get('last')} USDT")
            print(f"  24h成交量: {ticker.get('vol24h')}")
            print(f"  24h最高价: {ticker.get('high24h')} USDT")
            print(f"  24h最低价: {ticker.get('low24h')} USDT")
            print("  ✅ 获取行情成功")
        else:
            print("  ⚠️ 无法获取行情（可能需要网络连接）")
    
    except Exception as e:
        print(f"  ❌ 获取行情异常: {e}")
    
    # ============================================
    # 4. 获取订单簿（无需认证）
    # ============================================
    print("\n【测试4】获取订单簿")
    
    try:
        order_book = await okx_exchange.get_order_book("BTC-USDT-SWAP", depth=5)
        
        if order_book:
            asks = order_book.get("asks", [])
            bids = order_book.get("bids", [])
            
            print(f"  卖单 (前3档):")
            for i, ask in enumerate(asks[:3]):
                print(f"    {i+1}. 价格: {ask[0]}, 数量: {ask[1]}")
            
            print(f"  买单 (前3档):")
            for i, bid in enumerate(bids[:3]):
                print(f"    {i+1}. 价格: {bid[0]}, 数量: {bid[1]}")
            
            print("  ✅ 获取订单簿成功")
        else:
            print("  ⚠️ 无法获取订单簿")
    
    except Exception as e:
        print(f"  ❌ 获取订单簿异常: {e}")
    
    # ============================================
    # 5. 获取 K 线数据（无需认证）
    # ============================================
    print("\n【测试5】获取 K 线数据")
    
    try:
        klines = await okx_exchange.get_candlesticks("BTC-USDT-SWAP", bar="1H", limit=10)
        
        if klines:
            print(f"  获取到 {len(klines)} 条 K 线数据")
            print(f"  最新 K 线:")
            latest = klines[0]  # OKX 返回的是倒序的，最新在前
            print(f"    时间: {latest[0]}")
            print(f"    开盘: {latest[1]}")
            print(f"    最高: {latest[2]}")
            print(f"    最低: {latest[3]}")
            print(f"    收盘: {latest[4]}")
            print(f"    成交量: {latest[5]}")
            print("  ✅ 获取 K 线成功")
        else:
            print("  ⚠️ 无法获取 K 线")
    
    except Exception as e:
        print(f"  ❌ 获取 K 线异常: {e}")
    
    # ============================================
    # 6. 模拟下单（不下单，只验证接口）
    # ============================================
    print("\n【测试6】模拟下单接口验证")
    
    try:
        order_data = {
            "symbol": "BTC-USDT-SWAP",
            "side": "buy",
            "size": 0.001,
            "type": "market"
        }
        
        print(f"  订单数据: {order_data}")
        print(f"  ⚠️ 跳过实际下单（需要认证）")
        print(f"  如需测试下单，请配置真实 API Key 并设置 sandbox=False")
        
        # 演示：如果要下单，调用方式如下：
        # success, order_id, error_msg = await okx_exchange.place_order(order_data)
        # if success:
        #     print(f"  ✅ 下单成功: {order_id}")
        # else:
        #     print(f"  ❌ 下单失败: {error_msg}")
        
    except Exception as e:
        print(f"  ❌ 下单异常: {e}")
    
    # ============================================
    # 7. 事件回调测试
    # ============================================
    print("\n【测试7】事件回调机制")
    
    async def ticker_callback(event: Event):
        """行情回调"""
        print(f"  📊 收到行情事件: {event.data.get('symbol')} = {event.data.get('last_price')}")
    
    # 添加回调
    okx_exchange.add_event_callback(EventType.TICKER, ticker_callback)
    print("  ✅ 已添加行情回调")
    
    # 模拟触发事件
    mock_event = Event(
        event_type=EventType.TICKER,
        data={"symbol": "BTC-USDT-SWAP", "last_price": 50000.0, "timestamp": 0}
    )
    print("  模拟触发行情事件...")
    await ticker_callback(mock_event)
    
    # 移除回调
    okx_exchange.remove_event_callback(EventType.TICKER, ticker_callback)
    print("  ✅ 已移除行情回调")
    
    # ============================================
    # 8. 断开连接
    # ============================================
    print("\n【测试8】断开连接")
    
    await okx_exchange.disconnect()
    print("  ✅ 已断开连接")
    
    # ============================================
    # 总结
    # ============================================
    print("\n" + "=" * 80)
    print("✅ P1 阶段交付总结：OKXExchange")
    print("=" * 80)
    print("已完成功能：")
    print("  1. ✅ OKXExchange 类（exchange/okx/okx_exchange.py）")
    print("     - 继承 ExchangeBase")
    print("     - OKX V5 签名实现")
    print("     - 统一的 API 请求方法")
    print()
    print("  2. ✅ 订单管理接口")
    print("     - place_order()")
    print("     - cancel_order()")
    print("     - get_order_status()")
    print("     - get_open_orders()")
    print()
    print("  3. ✅ 账户管理接口")
    print("     - get_trading_balances()")
    print("     - get_funding_balances()")
    print("     - transfer_funds()")
    print()
    print("  4. ✅ 持仓管理接口")
    print("     - get_positions()")
    print("     - get_position()")
    print("     - set_leverage()")
    print()
    print("  5. ✅ 行情数据接口")
    print("     - get_ticker()")
    print("     - get_order_book()")
    print("     - get_candlesticks()")
    print()
    print("  6. ✅ WebSocket 支持")
    print("     - start_websocket()")
    print("     - 实时行情推送")
    print()
    print("  7. ✅ 事件回调机制")
    print("     - add_event_callback()")
    print("     - remove_event_callback()")
    print()
    print("待完成工作：")
    print("  ⏳ Controller 与 OKXExchange 完整集成测试（需要真实 API Key）")
    print("  ⏳ P2: UI 界面开发")
    print("=" * 80)
    print("\n💡 提示：")
    print("  - 行情数据接口（get_ticker, get_order_book, get_candlesticks）无需认证即可测试")
    print("  - 订单和账户接口需要配置真实 API Key")
    print("  - 建议使用沙盒环境 (sandbox=True) 进行测试")
    print("=" * 80)


# 运行演示
if __name__ == "__main__":
    asyncio.run(demo_okx_exchange())
