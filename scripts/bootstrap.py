"""
🛠 启动前自检
在启动系统前进行必要的检查
"""

import sys
import os
import asyncio
import yaml
from pathlib import Path
from typing import Dict, List


# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class BootstrapChecker:
    """启动检查器"""

    def __init__(self):
        self.checks: List[Dict] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def check_config_files(self) -> bool:
        """检查配置文件"""
        print("\n🔍 检查配置文件...")

        config_dir = Path(__file__).parent.parent / "config"

        required_files = [
            "account.yaml",
            "instruments.yaml",
            "strategy.yaml",
            "risk.yaml",
        ]

        all_ok = True

        for file_name in required_files:
            file_path = config_dir / file_name

            if not file_path.exists():
                self.errors.append(f"配置文件不存在: {file_name}")
                all_ok = False
                print(f"  ❌ {file_name} - 不存在")
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        yaml.safe_load(f)
                    print(f"  ✅ {file_name} - 正常")
                except Exception as e:
                    self.errors.append(f"配置文件格式错误: {file_name} - {e}")
                    all_ok = False
                    print(f"  ❌ {file_name} - 格式错误: {e}")

        self.checks.append({
            "name": "config_files",
            "passed": all_ok,
            "errors": self.errors,
        })

        return all_ok

    def check_directories(self) -> bool:
        """检查目录结构"""
        print("\n🔍 检查目录结构...")

        project_root = Path(__file__).parent.parent

        required_dirs = [
            "config",
            "core",
            "risk",
            "strategy",
            "execution",
            "exchange",
            "monitor",
            "scripts",
            "data",
            "logs",
            "tests",
        ]

        all_ok = True

        for dir_name in required_dirs:
            dir_path = project_root / dir_name

            if not dir_path.exists():
                self.errors.append(f"目录不存在: {dir_name}")
                all_ok = False
                print(f"  ❌ {dir_name}/ - 不存在")
            else:
                print(f"  ✅ {dir_name}/ - 正常")

        self.checks.append({
            "name": "directories",
            "passed": all_ok,
        })

        return all_ok

    def check_environment_variables(self) -> bool:
        """检查环境变量"""
        print("\n🔍 检查环境变量...")

        required_vars = [
            "OKX_API_KEY",
            "OKX_API_SECRET",
            "OKX_API_PASSPHRASE",
        ]

        all_ok = True

        for var_name in required_vars:
            value = os.getenv(var_name)

            if not value:
                self.warnings.append(f"环境变量未设置: {var_name}")
                print(f"  ⚠️  {var_name} - 未设置")
            else:
                print(f"  ✅ {var_name} - 已设置")

        if not os.getenv("OKX_API_KEY"):
            print("\n  💡 提示: 请设置环境变量后再启动系统")
            all_ok = False

        self.checks.append({
            "name": "environment_variables",
            "passed": all_ok,
        })

        return all_ok

    def check_python_version(self) -> bool:
        """检查 Python 版本"""
        print("\n🔍 检查 Python 版本...")

        version = sys.version_info
        min_version = (3, 9)

        if version >= min_version:
            print(f"  ✅ Python {version.major}.{version.minor}.{version.micro} - 正常")
            return True
        else:
            self.errors.append(f"Python 版本过低: {version} < {min_version}")
            print(f"  ❌ Python {version.major}.{version.minor}.{version.micro} - 版本过低 (需要 >= 3.9)")
            return False

    def check_dependencies(self) -> bool:
        """检查依赖包"""
        print("\n🔍 检查依赖包...")

        required_packages = [
            "aiohttp",
            "pyyaml",
            "asyncio",
        ]

        all_ok = True

        for package in required_packages:
            try:
                __import__(package)
                print(f"  ✅ {package} - 已安装")
            except ImportError:
                self.errors.append(f"依赖包未安装: {package}")
                all_ok = False
                print(f"  ❌ {package} - 未安装")

        self.checks.append({
            "name": "dependencies",
            "passed": all_ok,
        })

        return all_ok

    def run_all_checks(self) -> bool:
        """运行所有检查"""
        print("=" * 60)
        print("🚀 系统启动前自检")
        print("=" * 60)

        results = []

        # 检查 Python 版本
        results.append(self.check_python_version())

        # 检查目录结构
        results.append(self.check_directories())

        # 检查配置文件
        results.append(self.check_config_files())

        # 检查依赖包
        results.append(self.check_dependencies())

        # 检查环境变量
        results.append(self.check_environment_variables())

        # 汇总结果
        print("\n" + "=" * 60)
        print("📋 检查结果汇总")
        print("=" * 60)

        total = len(results)
        passed = sum(results)

        print(f"\n总计: {passed}/{total} 项通过")

        if self.errors:
            print(f"\n❌ 错误 ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print(f"\n⚠️  警告 ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        all_passed = all(results)

        if all_passed:
            print("\n✅ 所有检查通过，可以启动系统！")
            return True
        else:
            print("\n❌ 检查失败，请修复问题后再启动！")
            return False


async def main():
    """主函数"""
    checker = BootstrapChecker()

    all_ok = checker.run_all_checks()

    if all_ok:
        print("\n" + "=" * 60)
        print("✅ 自检完成，系统准备就绪")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ 自检失败，请修复问题后重试")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
