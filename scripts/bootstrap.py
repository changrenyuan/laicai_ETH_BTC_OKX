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

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class BootstrapChecker:
    """启动检查器"""

    def __init__(self, project_root: Optional[Path] = None):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        # 如果传入了 root 就用传入的，否则自动推导
        self.project_root = project_root if project_root else Path(__file__).parent.parent

    def check_python_version(self) -> bool:
        """检查 Python 版本"""
        print("  Checking Python version...")
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 10):
            self.errors.append(f"Python 版本过低: {sys.version.split()[0]} (需 3.10+)")
            print(f"  ❌ Python {sys.version.split()[0]} - 过低")
            return False
        print(f"  ✅ Python {sys.version.split()[0]} - 正常")
        return True

    def check_directories(self) -> bool:
        """检查目录结构 (自动修复)"""
        print("  Checking directories...")
        required_dirs = [
            "config", "core", "risk", "strategy", "execution",
            "exchange", "monitor", "scripts", "data/logs", "data/history"
        ]

        all_ok = True
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    print(f"  ✨ {dir_name}/ - 不存在 (已自动创建)")
                except Exception as e:
                    self.errors.append(f"无法创建目录: {dir_name} ({e})")
                    print(f"  ❌ {dir_name}/ - 创建失败")
                    all_ok = False
            # else:
            #     print(f"  ✅ {dir_name}/ - 正常")
        if all_ok:
            print(f"  ✅ 目录结构完整")
        return all_ok

    def check_config_files(self) -> bool:
        """检查配置文件"""
        print("  Checking config files...")
        config_dir = self.project_root / "config"
        # 根据 main.py 的要求，主要检查这三个
        required_files = ["account.yaml", "strategy.yaml", "risk.yaml"]

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
                    print(f"  ✅ {file_name} - 格式正常")
                except Exception as e:
                    self.errors.append(f"配置文件格式错误: {file_name} ({e})")
                    print(f"  ❌ {file_name} - YAML 格式错误")
                    all_ok = False
        return all_ok

    def check_dependencies(self) -> bool:
        """检查依赖包"""
        print("  Checking dependencies...")

        # 格式: "包名(用于显示)": "import名(用于检测)"
        required_packages = {
            "aiohttp": "aiohttp",
            "PyYAML": "yaml",
            "python-dotenv": "dotenv",
            "pandas": "pandas",
            "numpy": "numpy"
        }

        all_ok = True
        for pkg_name, import_name in required_packages.items():
            try:
                importlib.import_module(import_name)
            except ImportError:
                self.errors.append(f"依赖包未安装: {pkg_name}")
                print(f"  ❌ {pkg_name} - 未安装")
                all_ok = False

        if all_ok:
            print("  ✅ 核心依赖包已安装")
        return all_ok

    def run(self) -> bool:
        """运行所有检查"""
        print("-" * 60)

        results = [
            self.check_python_version(),
            self.check_directories(),
            self.check_config_files(),
            self.check_dependencies()
            # 环境变量检查先跳过，以免未配置 .env 时阻塞启动，
            # 实际的 API Key 检查会在 main.py 连接交易所时进行
        ]

        print("-" * 60)

        if self.errors:
            print(f"❌ 自检发现 {len(self.errors)} 个错误:")
            for error in self.errors:
                print(f"  - {error}")
            return False

        if all(results):
            print("✅ 自检通过，系统环境正常。")
            return True
        else:
            print("❌ 自检未通过。")
            return False


# =========================================================================
# 🔥 核心修复：添加这个对外暴露的函数
# =========================================================================
def run_bootstrap_checks(project_root: Optional[Path] = None) -> bool:
    """
    供 main.py 调用的入口函数
    :param project_root: 项目根目录路径
    :return: Boolean (是否通过)
    """
    checker = BootstrapChecker(project_root)
    return checker.run()


# =========================================================================
# 脚本直接运行入口
# =========================================================================
if __name__ == "__main__":
    success = run_bootstrap_checks()
    sys.exit(0 if success else 1)