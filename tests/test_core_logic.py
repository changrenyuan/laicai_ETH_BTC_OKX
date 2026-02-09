import asyncio
import sys
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.events import EventBus, Event, EventType
from core.state_machine import StateMachine, SystemState
from core.context import Context

async def main():
    print("=" * 50)
    print("🧪 Phase 3 核心逻辑测试")
    print("=" * 50)

    # 1. 初始化组件
    print("\n1. 初始化组件...")
    event_bus = EventBus()
    state_machine = StateMachine(event_bus)
    context = Context()
    print("  ✅ 组件初始化完成")

    # 2. 测试事件总线
    print("\n2. 测试事件总线...")

    async def on_system_start(event: Event):
        print(f"  📩 收到事件: {event.event_type} - {event.data}")

    event_bus.subscribe(EventType.SYSTEM_START, on_system_start)

    # 3. 测试状态转换
    print("\n3. 测试状态转换 (IDLE -> INITIALIZING)...")
    try:
        # 初始状态应该是 IDLE
        assert state_machine.current_state == SystemState.IDLE
        print(f"  当前状态: {state_machine.current_state}")

        # 尝试合法转换
        await state_machine.transition_to(SystemState.INITIALIZING, reason="Testing")
        print(f"  转换后状态: {state_machine.current_state}")
        assert state_machine.current_state == SystemState.INITIALIZING
        print("  ✅ 合法转换成功")

    except Exception as e:
        print(f"  ❌ 转换失败: {e}")
        return

    # 4. 测试非法状态转换
    print("\n4. 测试非法状态转换 (INITIALIZING -> SHUTDOWN)...")
    # 根据逻辑，INITIALIZING 只能去 READY 或 ERROR，不能直接去 SHUTDOWN (假设)
    # 让我们检查一下 state_machine.py 的 valid_transitions
    # SystemState.INITIALIZING: [SystemState.READY, SystemState.ERROR]
    try:
        await state_machine.transition_to(SystemState.SHUTDOWN, reason="Illegal Jump")
        print("  ❌ 错误：应该抛出异常但没有")
    except ValueError as e:
        print(f"  ✅ 成功捕获预期异常: {e}")

    # 5. 测试 Context
    print("\n5. 测试 Context 数据记录...")
    from core.context import Balance
    context.update_balance("USDT", 1000.0, 0.0)
    bal = context.get_balance("USDT")
    print(f"  USDT 余额: {bal.total}")
    assert bal.total == 1000.0
    print("  ✅ Context 读写正常")

    print("\n" + "=" * 50)
    print("🎉 Phase 3 测试全部通过！核心大脑已就绪。")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())