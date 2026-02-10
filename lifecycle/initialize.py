"""
📋 Initialize Phase
加载配置 & 初始化组件
"""

import yaml
from pathlib import Path
from typing import Dict
from monitor.dashboard import Dashboard

ROOT_DIR = Path(__file__).parent.parent


class Initialize:
    """Initialize 生命周期阶段 - 加载配置"""
    
    def __init__(self):
        self.config_dir = ROOT_DIR / "config"
    
    def run(self) -> Dict:
        """加载配置"""
        Dashboard.log("【2】加载配置 & 初始化组件...", "INFO")
        
        try:
            with open(self.config_dir / "account.yaml", "r", encoding="utf-8") as f:
                ac = yaml.safe_load(f)
            with open(self.config_dir / "risk.yaml", "r", encoding="utf-8") as f:
                ri = yaml.safe_load(f)
            with open(self.config_dir / "strategy.yaml", "r", encoding="utf-8") as f:
                st = yaml.safe_load(f)
            
            config = {**ac, **ri, **st}
            
            Dashboard.log(
                f"配置加载完成 | 激活策略: [{config.get('active_strategy', 'N/A').upper()}]",
                "SUCCESS"
            )
            
            return config
            
        except Exception as e:
            Dashboard.log(f"配置文件解析失败: {e}", "ERROR")
            raise e
