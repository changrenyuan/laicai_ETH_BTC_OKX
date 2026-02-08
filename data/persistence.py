# -*- coding: utf-8 -*-
"""
数据持久化模块
用于保存所有策略执行记录、账户信息、持仓信息等
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger


class PersistenceManager:
    """数据持久化管理器"""

    def __init__(self, db_path: str = "data/trading_history.db"):
        """
        初始化持久化管理器

        :param db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 返回字典格式
        self._create_tables()

    def _create_tables(self):
        """创建所有数据表"""
        cursor = self.conn.cursor()

        # 1. 账户余额历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_balance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_equity_usd REAL,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. 持仓记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                inst_id TEXT,
                pos_side TEXT,
                pos REAL,
                avg_px REAL,
                unrealized_pnl REAL,
                unrealized_pnl_ratio REAL,
                leverage TEXT,
                margin REAL,
                last TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. 策略记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT UNIQUE,
                inst_id TEXT,
                strategy_type TEXT,
                status TEXT,
                params TEXT,
                start_time DATETIME,
                end_time DATETIME,
                total_margin_usd REAL,
                total_contracts INTEGER,
                avg_entry_price REAL,
                tp_price REAL,
                sl_price REAL,
                liq_price REAL,
                final_pnl_usd REAL,
                final_pnl_ratio REAL,
                exit_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. 订单记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                strategy_id TEXT,
                inst_id TEXT,
                side TEXT,
                pos_side TEXT,
                ord_type TEXT,
                px REAL,
                sz REAL,
                sz_currency TEXT,
                filled_sz REAL,
                avg_px REAL,
                state TEXT,
                ccy TEXT,
                fee REAL,
                fee_ccy TEXT,
                source TEXT,
                created_time DATETIME,
                update_time DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. 止盈止损记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tp_sl_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                inst_id TEXT,
                tp_trigger_px REAL,
                sl_trigger_px REAL,
                sz REAL,
                status TEXT,
                created_time DATETIME,
                triggered_time DATETIME,
                trigger_type TEXT,
                exit_price REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 6. 行为日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                strategy_id TEXT,
                inst_id TEXT,
                action_type TEXT,
                action_detail TEXT,
                extra_data TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 7. 资产快照表（每日汇总）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asset_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                total_equity_usd REAL,
                available_usdt REAL,
                total_pnl_usd REAL,
                positions_count INTEGER,
                active_strategies INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        logger.info(f"✅ 数据库表创建完成: {self.db_path}")

    # =========================
    # 账户余额相关
    # =========================

    def save_account_balance(self, balance_data: dict):
        """
        保存账户余额

        :param balance_data: 余额数据，格式如 OKX 返回的格式
        """
        cursor = self.conn.cursor()

        # 解析余额数据
        total_equity = float(balance_data.get("totalEq", 0))
        details_json = json.dumps(balance_data.get("details", []), ensure_ascii=False)

        cursor.execute("""
            INSERT INTO account_balance (timestamp, total_equity_usd, details)
            VALUES (?, ?, ?)
        """, (
            datetime.now(),
            total_equity,
            details_json
        ))

        self.conn.commit()
        logger.debug(f"保存账户余额: {total_equity} USD")

    def get_latest_balance(self) -> Optional[dict]:
        """获取最新账户余额"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM account_balance
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_balance_history(self, limit: int = 100) -> List[dict]:
        """获取余额历史"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM account_balance
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # 持仓相关
    # =========================

    def save_positions(self, positions: List[dict]):
        """
        保存当前持仓

        :param positions: 持仓列表
        """
        cursor = self.conn.cursor()
        timestamp = datetime.now()

        for pos in positions:
            cursor.execute("""
                INSERT INTO positions (
                    timestamp, inst_id, pos_side, pos, avg_px,
                    unrealized_pnl, unrealized_pnl_ratio, leverage,
                    margin, last
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                pos.get("instId"),
                pos.get("posSide"),
                float(pos.get("pos", 0)),
                float(pos.get("avgPx", 0)),
                float(pos.get("upl", 0)),
                float(pos.get("uplRatio", 0)),
                pos.get("lever"),
                float(pos.get("margin", 0)),
                pos.get("last")
            ))

        self.conn.commit()
        logger.debug(f"保存持仓记录: {len(positions)} 条")

    def get_current_positions(self, inst_id: Optional[str] = None) -> List[dict]:
        """
        获取当前持仓

        :param inst_id: 交易对ID，None 表示查询所有
        """
        cursor = self.conn.cursor()

        if inst_id:
            cursor.execute("""
                SELECT * FROM positions
                WHERE inst_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (inst_id,))
        else:
            cursor.execute("""
                SELECT * FROM positions
                ORDER BY timestamp DESC
                LIMIT 20
            """)

        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # 策略相关
    # =========================

    def create_strategy(
        self,
        strategy_id: str,
        inst_id: str,
        strategy_type: str,
        params: dict,
        audit_result: dict
    ) -> bool:
        """
        创建策略记录

        :param strategy_id: 策略唯一ID
        :param inst_id: 交易对ID
        :param strategy_type: 策略类型
        :param params: 策略参数
        :param audit_result: 审核结果
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO strategies (
                    strategy_id, inst_id, strategy_type, status,
                    params, start_time, total_margin_usd, total_contracts,
                    avg_entry_price, tp_price, sl_price, liq_price
                )
                VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy_id,
                inst_id,
                strategy_type,
                json.dumps(params, ensure_ascii=False),
                datetime.now(),
                audit_result.get("margin_used", 0),
                audit_result.get("total_contracts", 0),
                audit_result.get("avg_price", 0),
                audit_result.get("tp_price", 0),
                audit_result.get("sl_price", 0),
                audit_result.get("liq_price", 0)
            ))

            self.conn.commit()
            logger.success(f"✅ 创建策略记录: {strategy_id}")
            return True

        except sqlite3.IntegrityError:
            logger.error(f"策略 ID 已存在: {strategy_id}")
            return False

    def update_strategy_status(
        self,
        strategy_id: str,
        status: str,
        pnl_usd: Optional[float] = None,
        pnl_ratio: Optional[float] = None,
        exit_reason: Optional[str] = None
    ):
        """
        更新策略状态

        :param strategy_id: 策略ID
        :param status: 状态 (RUNNING, COMPLETED, STOPPED, STOPPED)
        :param pnl_usd: 最终盈亏
        :param pnl_ratio: 最终收益率
        :param exit_reason: 退出原因
        """
        cursor = self.conn.cursor()

        update_fields = {
            "status": status,
            "updated_at": datetime.now()
        }

        if pnl_usd is not None:
            update_fields["final_pnl_usd"] = pnl_usd
        if pnl_ratio is not None:
            update_fields["final_pnl_ratio"] = pnl_ratio
        if exit_reason is not None:
            update_fields["exit_reason"] = exit_reason
        if status in ["COMPLETED", "STOPPED", "STOPPED"]:
            update_fields["end_time"] = datetime.now()

        # 构建更新语句
        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        values = list(update_fields.values()) + [strategy_id]

        cursor.execute(f"""
            UPDATE strategies
            SET {set_clause}
            WHERE strategy_id = ?
        """, values)

        self.conn.commit()
        logger.info(f"更新策略状态: {strategy_id} -> {status}")

    def get_active_strategies(self) -> List[dict]:
        """获取所有运行中的策略"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM strategies
            WHERE status = 'RUNNING'
            ORDER BY start_time DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_strategy_history(self, limit: int = 50) -> List[dict]:
        """获取策略历史"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM strategies
            ORDER BY start_time DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # 订单相关
    # =========================

    def save_order(self, order_data: dict, strategy_id: str, source: str = "MARTINGALE"):
        """
        保存订单记录

        :param order_data: 订单数据
        :param strategy_id: 策略ID
        :param source: 订单来源 (MARTINGALE, TP, SL, MANUAL)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO orders (
                order_id, strategy_id, inst_id, side, pos_side, ord_type,
                px, sz, sz_currency, filled_sz, avg_px, state,
                ccy, fee, fee_ccy, source, created_time, update_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_data.get("ordId"),
            strategy_id,
            order_data.get("instId"),
            order_data.get("side"),
            order_data.get("posSide"),
            order_data.get("ordType"),
            float(order_data.get("px", 0)),
            float(order_data.get("sz", 0)),
            order_data.get("szCcy"),
            float(order_data.get("fillSz", 0)),
            float(order_data.get("avgPx", 0)),
            order_data.get("state"),
            order_data.get("ccy"),
            float(order_data.get("fee", 0)),
            order_data.get("feeCcy"),
            source,
            order_data.get("cTime"),
            order_data.get("uTime")
        ))

        self.conn.commit()
        logger.debug(f"保存订单: {order_data.get('ordId')}")

    def get_orders_by_strategy(self, strategy_id: str) -> List[dict]:
        """获取策略的所有订单"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM orders
            WHERE strategy_id = ?
            ORDER BY created_time DESC
        """, (strategy_id,))
        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # 止盈止损相关
    # =========================

    def save_tp_sl_order(
        self,
        strategy_id: str,
        inst_id: str,
        tp_px: float,
        sl_px: float,
        sz: int
    ):
        """
        保存止盈止损单记录

        :param strategy_id: 策略ID
        :param inst_id: 交易对ID
        :param tp_px: 止盈价格
        :param sl_px: 止损价格
        :param sz: 数量
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO tp_sl_orders (
                strategy_id, inst_id, tp_trigger_px, sl_trigger_px,
                sz, status, created_time
            )
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?)
        """, (
            strategy_id,
            inst_id,
            tp_px,
            sl_px,
            sz,
            datetime.now()
        ))

        self.conn.commit()
        logger.debug(f"保存止盈止损单: {strategy_id}")

    def update_tp_sl_triggered(
        self,
        strategy_id: str,
        trigger_type: str,  # TP or SL
        exit_price: float
    ):
        """
        更新止盈止损触发状态

        :param strategy_id: 策略ID
        :param trigger_type: 触发类型 (TP/SL)
        :param exit_price: 退出价格
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE tp_sl_orders
            SET status = 'TRIGGERED',
                triggered_time = ?,
                trigger_type = ?,
                exit_price = ?
            WHERE strategy_id = ?
            AND status = 'ACTIVE'
        """, (
            datetime.now(),
            trigger_type,
            exit_price,
            strategy_id
        ))

        self.conn.commit()
        logger.info(f"止盈止损触发: {strategy_id} - {trigger_type}")

    # =========================
    # 行为日志相关
    # =========================

    def log_action(
        self,
        action_type: str,
        strategy_id: Optional[str] = None,
        inst_id: Optional[str] = None,
        detail: str = "",
        extra_data: Optional[dict] = None
    ):
        """
        记录行为日志

        :param action_type: 行为类型 (SCAN, ORDER, FILL, TP_SL, EXIT, etc.)
        :param strategy_id: 策略ID
        :param inst_id: 交易对ID
        :param detail: 详细描述
        :param extra_data: 额外数据
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO action_logs (
                timestamp, strategy_id, inst_id, action_type,
                action_detail, extra_data
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(),
            strategy_id,
            inst_id,
            action_type,
            detail,
            json.dumps(extra_data, ensure_ascii=False) if extra_data else None
        ))

        self.conn.commit()
        logger.debug(f"记录行为日志: {action_type} - {detail}")

    def get_action_logs(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """
        获取行为日志

        :param strategy_id: 策略ID，None 表示查询所有
        :param limit: 限制数量
        """
        cursor = self.conn.cursor()

        if strategy_id:
            cursor.execute("""
                SELECT * FROM action_logs
                WHERE strategy_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (strategy_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM action_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # 快照相关
    # =========================

    def save_daily_snapshot(
        self,
        total_equity: float,
        available_usdt: float,
        positions_count: int,
        active_strategies: int
    ):
        """
        保存每日资产快照

        :param total_equity: 总权益
        :param available_usdt: 可用USDT
        :param positions_count: 持仓数量
        :param active_strategies: 活跃策略数
        """
        cursor = self.conn.cursor()
        today = datetime.now().date()

        try:
            cursor.execute("""
                INSERT INTO asset_snapshots (
                    date, total_equity_usd, available_usdt,
                    positions_count, active_strategies
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                today,
                total_equity,
                available_usdt,
                positions_count,
                active_strategies
            ))

            self.conn.commit()
            logger.info(f"保存每日快照: {today}")

        except sqlite3.IntegrityError:
            # 今天已经有快照，更新
            cursor.execute("""
                UPDATE asset_snapshots
                SET total_equity_usd = ?, available_usdt = ?,
                    positions_count = ?, active_strategies = ?
                WHERE date = ?
            """, (
                total_equity,
                available_usdt,
                positions_count,
                active_strategies,
                today
            ))
            self.conn.commit()

    def get_daily_snapshots(self, days: int = 30) -> List[dict]:
        """获取每日快照"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM asset_snapshots
            ORDER BY date DESC
            LIMIT ?
        """, (days,))
        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # 工具方法
    # =========================

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def __del__(self):
        """析构函数"""
        self.close()
