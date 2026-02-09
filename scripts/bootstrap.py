"""
🛠 启动前自检 (修复版)
在启动系统前进行必要的检查：自动修复目录、加载环境变量、映射包名
"""

import sys
import os
import importlib
import yaml
from pathlib import Path
from typing import Dict, List, Optional

# 🔥 核心修复1：加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ 警告: 未安装 python-dotenv，无法加载 .env 文件")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class BootstrapChecker:
    """启动检查器"""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.project_root = Path(__file__).parent.parent

    def check_python_version(self) -> bool:
        """检查 Python 版本"""
        print("\n🔍 检查 Python 版本...")
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 10):
            self.errors.append(f"Python 版本过低: {sys.version.split()[0]} (需 3.10+)")
            print(f"  ❌ Python {sys.version.split()[0]} - 过低")
            return False
        print(f"  ✅ Python {sys.version.split()[0]} - 正常")
        return True

    def check_directories(self) -> bool:
        """检查目录结构 (自动修复)"""
        print("\n🔍 检查目录结构...")
        required_dirs = [
            "config", "core", "risk", "strategy", "execution",
            "exchange", "monitor", "scripts", "data", "logs", "tests"
        ]

        all_ok = True
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                # 🔥 核心修复3：自动创建缺失目录
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    print(f"  ✨ {dir_name}/ - 不存在 (已自动创建)")
                except Exception as e:
                    self.errors.append(f"无法创建目录: {dir_name} ({e})")
                    print(f"  ❌ {dir_name}/ - 创建失败")
                    all_ok = False
            else:
                print(f"  ✅ {dir_name}/ - 正常")
        return all_ok

    def check_config_files(self) -> bool:
        """检查配置文件"""
        print("\n🔍 检查配置文件...")
        config_dir = self.project_root / "config"
        required_files = ["account.yaml", "instruments.yaml", "strategy.yaml", "risk.yaml"]

        all_ok = True
        for file_name in required_files:
            file_path = config_dir / file_name
            if not file_path.exists():
                self.errors.append(f"配置文件不存在: {file_name}")
                print(f"  ❌ {file_name} - 不存在")
                all_ok = False
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        yaml.safe_load(f)
                    print(f"  ✅ {file_name} - 正常")
                except Exception as e:
                    self.errors.append(f"配置文件格式错误: {file_name} ({e})")
                    print(f"  ❌ {file_name} - 格式错误")
                    all_ok = False
        return all_ok

    def check_dependencies(self) -> bool:
        """检查依赖包"""
        print("\n🔍 检查依赖包...")

        # 🔥 核心修复2：包名 -> 导入名 映射
        # pip install name : import name
        required_packages = {
            "aiohttp": "aiohttp",
            "pyyaml": "yaml",        # 关键修正
            "asyncio": "asyncio",
            "python-dotenv": "dotenv" # 关键修正
        }

        all_ok = True
        for pkg_name, import_name in required_packages.items():
            try:
                importlib.import_module(import_name)
                print(f"  ✅ {pkg_name} - 已安装")
            except ImportError:
                self.errors.append(f"依赖包未安装: {pkg_name}")
                print(f"  ❌ {pkg_name} - 未安装")
                all_ok = False
        return all_ok

    def check_environment_variables(self) -> bool:
        """检查环境变量"""
        print("\n🔍 检查环境变量...")
        required_vars = ["OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"]

        all_ok = True
        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
                print(f"  ⚠️  {var} - 未设置")
                all_ok = False
            else:
                # 简单的掩码显示
                masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
                print(f"  ✅ {var} - 已设置 ({masked})")

        if missing_vars:
            self.warnings.append(f"环境变量未设置: {', '.join(missing_vars)}")
            print("\n  💡 提示: 请确保根目录下有 .env 文件，并且安装了 python-dotenv")

        return all_ok

    def run(self) -> bool:
        """运行所有检查"""
        print("=" * 60)
        print("🚀 系统启动前自检")
        print("=" * 60)

        results = [
            self.check_python_version(),
            self.check_directories(),
            self.check_config_files(),
            self.check_dependencies(),
            self.check_environment_variables()
        ]

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

        if all(results):
            print("\n✅ 所有检查通过，系统准备就绪！")
            return True
        else:
            print("\n❌ 自检失败，请修复上述错误。")
            return False

if __name__ == "__main__":
    checker = BootstrapChecker()
    success = checker.run()
    sys.exit(0 if success else 1)