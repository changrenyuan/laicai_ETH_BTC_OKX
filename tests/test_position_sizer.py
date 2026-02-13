"""
测试 PositionSizer 功能
"""
import sys
sys.path.insert(0, '/tmp/laicai_ETH_BTC_OKX')

from core.position_sizer import PositionSizer, PositionSizeConfig

def test_position_sizer():
    print("=" * 80)
    print("测试 PositionSizer")
    print("=" * 80)
    
    # 创建 PositionSizer
    sizer = PositionSizer()
    
    # 测试场景1：正常仓位计算
    print("\n【测试1】正常仓位计算（做多）")
    result = sizer.calculate_position(
        total_capital=1000,
        entry_price=50000,
        side="buy",
        stop_loss_pct=0.02,
        leverage=5,
        min_balance=1000
    )
    print(f"仓位大小: {result.position_size} 张")
    print(f"仓位价值: {result.position_value:.2f} USDT")
    print(f"所需保证金: {result.margin_required:.2f} USDT")
    print(f"止损价格: {result.stop_loss_price:.2f}")
    print(f"实际风险: {result.risk_pct:.2%}")
    print(f"是否有效: {result.is_valid}")
    if result.warnings:
        print("警告:")
        for warning in result.warnings:
            print(f"  - {warning}")
    
    # 测试场景2：小资金适配
    print("\n【测试2】小资金适配（不足1张）")
    result = sizer.calculate_position(
        total_capital=40,
        entry_price=50000,
        side="buy",
        stop_loss_pct=0.02,
        leverage=3,
        min_balance=40
    )
    print(f"仓位大小: {result.position_size} 张")
    print(f"仓位价值: {result.position_value:.2f} USDT")
    print(f"所需保证金: {result.margin_required:.2f} USDT")
    print(f"止损价格: {result.stop_loss_price:.2f}")
    print(f"实际风险: {result.risk_pct:.2%}")
    print(f"是否有效: {result.is_valid}")
    if result.warnings:
        print("警告:")
        for warning in result.warnings:
            print(f"  - {warning}")
    
    # 测试场景3：做空
    print("\n【测试3】做空仓位计算")
    result = sizer.calculate_position(
        total_capital=1000,
        entry_price=50000,
        side="sell",
        stop_loss_pct=0.02,
        leverage=5,
        min_balance=1000
    )
    print(f"仓位大小: {result.position_size} 张")
    print(f"仓位价值: {result.position_value:.2f} USDT")
    print(f"所需保证金: {result.margin_required:.2f} USDT")
    print(f"止损价格: {result.stop_loss_price:.2f}")
    print(f"实际风险: {result.risk_pct:.2%}")
    print(f"是否有效: {result.is_valid}")
    
    # 测试场景4：止盈计算
    print("\n【测试4】止盈计算")
    tp_price = sizer.calculate_take_profit(50000, "buy", 0.06)
    print(f"做多止盈价格: {tp_price:.2f}")
    
    tp_price = sizer.calculate_take_profit(50000, "sell", 0.06)
    print(f"做空止盈价格: {tp_price:.2f}")
    
    # 测试场景5：止损计算
    print("\n【测试5】止损计算")
    sl_price = sizer.calculate_stop_loss(50000, "buy", 0.02)
    print(f"做多止损价格: {sl_price:.2f}")
    
    sl_price = sizer.calculate_stop_loss(50000, "sell", 0.02)
    print(f"做空止损价格: {sl_price:.2f}")
    
    # 测试场景6：移动止损
    print("\n【测试6】移动止损")
    stop_price, is_activated = sizer.calculate_trailing_stop(
        entry_price=50000,
        current_price=50500,
        side="buy",
        trailing_pct=0.01,
        activation_pct=0.02
    )
    print(f"当前价格: 50500 (盈利1%)")
    print(f"止损价格: {stop_price:.2f}, 是否激活: {is_activated}")
    
    stop_price, is_activated = sizer.calculate_trailing_stop(
        entry_price=50000,
        current_price=51000,
        side="buy",
        trailing_pct=0.01,
        activation_pct=0.02
    )
    print(f"当前价格: 51000 (盈利2%)")
    print(f"止损价格: {stop_price:.2f}, 是否激活: {is_activated}")
    
    print("\n" + "=" * 80)
    print("✅ PositionSizer 测试完成")
    print("=" * 80)

if __name__ == "__main__":
    test_position_sizer()
