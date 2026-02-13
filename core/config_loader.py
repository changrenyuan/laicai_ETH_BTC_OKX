"""
🔧 Config Loader - 配置加载器
==============================
从 YAML 文件加载配置，支持环境变量替换
"""

import os
import yaml
from typing import Dict, Any
from pathlib import Path


class ConfigLoader:
    """
    配置加载器
    
    功能：
    - 从 YAML 文件加载配置
    - 支持环境变量替换 (${VAR_NAME})
    - 提供配置访问接口
    """

    def __init__(self, config_dir: str = None):
        """
        初始化配置加载器
        
        Args:
            config_dir: 配置文件目录路径
        """
        if config_dir is None:
            # 默认路径：项目根目录/config
            project_root = Path(__file__).parent.parent
            config_dir = project_root / "config"
        
        self.config_dir = Path(config_dir)
        self._configs: Dict[str, Dict] = {}
        
        self.logger = None  # 延迟初始化

    def load_all(self) -> Dict[str, Dict]:
        """
        加载所有配置文件
        
        Returns:
            Dict: 所有配置的字典
        """
        config_files = {
            "account": "account.yaml",
            "instruments": "instruments.yaml",
            "risk": "risk.yaml",
            "strategy": "strategy.yaml",
            "exchange": "exchange.yaml",  # 新增交易所配置
        }
        
        for name, filename in config_files.items():
            file_path = self.config_dir / filename
            if file_path.exists():
                self._configs[name] = self._load_yaml(file_path)
                print(f"✅ 加载配置: {name}")
            else:
                print(f"⚠️ 配置文件不存在: {filename}")
                self._configs[name] = {}
        
        return self._configs

    def _load_yaml(self, file_path: Path) -> Dict:
        """
        加载 YAML 文件
        
        Args:
            file_path: YAML 文件路径
            
        Returns:
            Dict: 配置字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 替换环境变量
                content = self._replace_env_vars(content)
                return yaml.safe_load(content)
        except Exception as e:
            print(f"❌ 加载配置文件失败 {file_path}: {e}")
            return {}

    def _replace_env_vars(self, text: str) -> str:
        """
        替换环境变量
        
        Args:
            text: 包含环境变量占位符的文本
            
        Returns:
            str: 替换后的文本
        """
        import re
        
        def replacer(match):
            var_name = match.group(1)
            return os.getenv(var_name, "")
        
        # 匹配 ${VAR_NAME} 格式
        return re.sub(r'\$\{([^}]+)\}', replacer, text)

    def get(self, config_name: str, key_path: str = None, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            config_name: 配置名称（如 "account", "strategy"）
            key_path: 配置键路径（如 "sub_account.api_key"）
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        if config_name not in self._configs:
            return default
        
        config = self._configs[config_name]
        
        if key_path is None:
            return config
        
        # 解析键路径（如 "sub_account.api_key"）
        keys = key_path.split('.')
        value = config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value

    def get_account_config(self) -> Dict:
        """获取账户配置"""
        if "account" not in self._configs:
            self.load_all()
        return self._configs.get("account", {})

    def get_strategy_config(self) -> Dict:
        """获取策略配置"""
        if "strategy" not in self._configs:
            self.load_all()
        return self._configs.get("strategy", {})

    def get_risk_config(self) -> Dict:
        """获取风险配置"""
        if "risk" not in self._configs:
            self.load_all()
        return self._configs.get("risk", {})

    def get_instruments_config(self) -> Dict:
        """获取交易品种配置"""
        if "instruments" not in self._configs:
            self.load_all()
        return self._configs.get("instruments", {})

    def get_exchange_config(self) -> Dict:
        """获取交易所配置"""
        if "exchange" not in self._configs:
            self.load_all()
        return self._configs.get("exchange", {})


# 全局配置加载器实例
_config_loader = None


def get_config_loader() -> ConfigLoader:
    """
    获取全局配置加载器实例
    
    Returns:
        ConfigLoader: 配置加载器实例
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
        _config_loader.load_all()
    return _config_loader


# 导出
__all__ = ["ConfigLoader", "get_config_loader"]
