"""
✅ 状态机测试
测试状态机的状态转换逻辑
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.state_machine import StateMachine, SystemState
from core.events import EventBus


async def test_state_transitions():
    """测试状态转换"""
    print("=" * 60)
    print("🧪 状态机测试")
    print("=" * 60)

    event_bus = EventBus()
    state_machine = StateMachine(event_bus)

    # 测试初始状态
    print("\n1️⃣  测试初始状态...")
    assert state_machine.get_current_state() == SystemState.IDLE
    print("  ✅ 初始状态: IDLE")

    # 测试状态转换
    print("\n2️⃣  测试状态转换...")

    # IDLE -> INITIALIZING
    await state_machine.transition_to(
        SystemState.INITIALIZING,
        reason="系统启动"
    )
    assert state_machine.get_current_state() == SystemState.INITIALIZING
    print("  ✅ IDLE -> INITIALIZING")

    # INITIALIZING -> READY
    await state_machine.transition_to(
        SystemState.READY,
        reason="初始化完成"
    )
    assert state_machine.get_current_state() == SystemState.READY
    print("  ✅ INITIALIZING -> READY")

    # READY -> MONITORING
    await state_machine.transition_to(
        SystemState.MONITORING,
        reason="开始监控"
    )
    assert state_machine.get_current_state() == SystemState.MONITORING
    print("  ✅ READY -> MONITORING")

    # MONITORING -> OPENING_POSITION
    await state_machine.transition_to(
        SystemState.OPENING_POSITION,
        reason="开仓信号"
    )
    assert state_machine.get_current_state() == SystemState.OPENING_POSITION
    print("  ✅ MONITORING -> OPENING_POSITION")

    # OPENING_POSITION -> MONITORING
    await state_machine.transition_to(
        SystemState.MONITORING,
        reason="开仓完成"
    )
    assert state_machine.get_current_state() == SystemState.MONITORING
    print("  ✅ OPENING_POSITION -> MONITORING")

    # 测试非法转换
    print("\n3️⃣  测试非法转换...")
    try:
        await state_machine.transition_to(
            SystemState.IDLE,
            reason="非法转换"
        )
        print("  ❌ 应该抛出异常但没有")
        return False
    except ValueError as e:
        print(f"  ✅ 正确抛出异常: {e}")

    # 测试状态历史
    print("\n4️⃣  测试状态历史...")
    history = state_machine.get_state_history()
    print(f"  转换次数: {len(history)}")
    for transition in history:
        print(f"    {transition.from_state.value} -> {transition.to_state.value}: {transition.reason}")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过")
    print("=" * 60)

    return True


async def main():
    """主函数"""
    success = await test_state_transitions()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
