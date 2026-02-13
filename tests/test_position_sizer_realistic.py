"""
测试 PositionSizer 功能（使用合理的参数）
"""
import sys
sys.path.insert(0, '/tmp/laicai_ETH_BTC_OKX')

from core.position_sizer import PositionSizer

def test_position_sizer_realistic():
    print("=" * 80)
    print("测试 PositionSizer（合理参数）")
    print("=" * 80)
    
    # 创建 PositionSizer
    sizer = PositionSizer()
    
    # 测试场景1：正常仓位计算（使用低价格币种，如 DOGE）
    print("\n【测试1】正常仓位计算（低价格币种）")
    result = sizer.calculate_position(
        total_capital=1000,
        entry_price=0.1,  # 0.1 USDT 的币种
        side="buy",
        stop_loss_pct=0.02,
        leverage=5,
        min_balance=1000
    )
    print(f"仓位大小: {result.position_size} 张")
    print(f"仓位价值: {result.position_value:.2f} USDT")
    print(f"所需保证金: {result.margin_required:.2f} USDT")
    print(f"止损价格: {result.stop_loss_price:.6f}")
    print(f"实际风险: {result.risk_pct:.2%}")
    print(f"是否有效: {result.is_valid}")
    if result.warnings:
        print("警告:")
        for warning in result.warnings:
            print(f"  - {warning}")
    
    # 测试场景2：小资金适配（DOGE）
    print("\n【测试2】小资金适配（DOGE）")
    result = sizer.calculate_position(
        total_capital=40,
        entry_price=0.1,
        side="buy",
        stop_loss_pct=0.02,
        leverage=3,
        min_balance=40
    )
    print(f"仓位大小: {result.position_size} 张")
    print(f"仓位价值: {result.position_value:.2f} USDT")
    print(f"所需保证金: {result.margin_required:.2f} USDT")
    print(f"止损价格: {result.stop_loss_price:.6f}")
    print(f"实际风险: {result.risk_pct:.2%}")
    print(f"是否有效: {result.is_valid}")
    if result.warnings:
        print("警告:")
        for warning in result.warnings:
            print(f"  - {warning}")
    
    # 测试场景3：中等价格币种（ETH）
    print("\n【测试3】中等价格币种（ETH）")
    result = sizer.calculate_position(
        total_capital=1000,
        entry_price=2000,
        side="buy",
        stop_loss_pct=0.02,
        leverage=10,  # 使用更高杠杆
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
    
    # 测试场景4：做空
    print("\n【测试4】做空（低价格币种）")
    result = sizer.calculate_position(
        total_capital=1000,
        entry_price=0.1,
        side="sell",
        stop_loss_pct=0.02,
        leverage=5,
        min_balance=1000
    )
    print(f"仓位大小: {result.position_size} 张")
    print(f"仓位价值: {result.position_value:.2f} USDT")
    print(f"所需保证金: {result.margin_required:.2f} USDT")
    print(f"止损价格: {result.stop_loss_price:.6f}")
    print(f"实际风险: {result.risk_pct:.2%}")
    print(f"是否有效: {result.is_valid}")
    
    # 测试场景5：止盈计算
    print("\n【测试5】止盈计算")
    tp_price = sizer.calculate_take_profit(0.1, "buy", 0.06)
    print(f"做多止盈价格: {tp_price:.6f}")
    
    tp_price = sizer.calculate_take_profit(2000, "buy", 0.06)
    print(f"ETH做多止盈价格: {tp_price:.2f}")
    
    tp_price = sizer.calculate_take_profit(0.1, "sell", 0.06)
    print(f"做空止盈价格: {tp_price:.6f}")
    
    # 测试场景6：止损计算
    print("\n【测试6】止损计算")
    sl_price = sizer.calculate_stop_loss(0.1, "buy", 0.02)
    print(f"做多止损价格: {sl_price:.6f}")
    
    sl_price = sizer.calculate_stop_loss(2000, "buy", 0.02)
    print(f"ETH做多止损价格: {sl_price:.2f}")
    
    sl_price = sizer.calculate_stop_loss(0.1, "sell", 0.02)
    print(f"做空止损价格: {sl_price:.6f}")
    
    # 测试场景7：移动止损
    print("\n【测试7】移动止损")
    stop_price, is_activated = sizer.calculate_trailing_stop(
        entry_price=0.1,
        current_price=0.101,  # 盈利1%
        side="buy",
        trailing_pct=0.01,
        activation_pct=0.015
    )
    print(f"当前价格: 0.101 (盈利1%), 激活阈值: 1.5%")
    print(f"止损价格: {stop_price:.6f}, 是否激活: {is_activated}")
    
    stop_price, is_activated = sizer.calculate_trailing_stop(
        entry_price=0.1,
        current_price=0.102,  # 盈利2%
        side="buy",
        trailing_pct=0.01,
        activation_pct=0.015
    )
    print(f"当前价格: 0.102 (盈利2%), 激活阈值: 1.5%")
    print(f"止损价格: {stop_price:.6f}, 是否激活: {is_activated}")
    
    stop_price, is_activated = sizer.calculate_trailing_stop(
        entry_price=0.1,
        current_price=0.105,  # 盈利5%
        side="buy",
        trailing_pct=0.01,
        activation_pct=0.015
    )
    print(f"当前价格: 0.105 (盈利5%), 激活阈值: 1.5%")
    print(f"止损价格: {stop_price:.6f}, 是否激活: {is_activated}")
    
    print("\n" + "=" * 80)
    print("✅ PositionSizer 测试完成")
    print("=" * 80)

if __name__ == "__main__":
    test_position_sizer_realistic()
