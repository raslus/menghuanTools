import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class AccountingDB:
    def __init__(self, db_file="accounting.db"):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS income_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_name TEXT NOT NULL,
                record_date TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                cash_income REAL DEFAULT 0,
                item_income REAL DEFAULT 0,
                cost REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                remark TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_all_records(self) -> List[Dict]:
        """获取所有记录"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM income_records ORDER BY record_date DESC, id DESC')
        rows = cursor.fetchall()
        conn.close()
        return self._rows_to_dict(rows)

    def get_records_by_filter(self, start_date: str, end_date: str, 
                            role_name: str = None, activity_type: str = None) -> List[Dict]:
        """按条件筛选记录"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        query = 'SELECT * FROM income_records WHERE record_date BETWEEN ? AND ?'
        params = [start_date, end_date]
        
        if role_name and role_name != "全部角色":
            query += ' AND role_name = ?'
            params.append(role_name)
        
        if activity_type and activity_type != "全部":
            query += ' AND activity_type = ?'
            params.append(activity_type)
        
        query += ' ORDER BY record_date DESC, id DESC'
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return self._rows_to_dict(rows)

    def get_distinct_roles(self) -> List[str]:
        """获取所有不同的角色名"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT role_name FROM income_records ORDER BY role_name')
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def get_yesterday_records(self) -> List[Dict]:
        """获取昨天的所有记录"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM income_records WHERE record_date = ?', (yesterday,))
        rows = cursor.fetchall()
        conn.close()
        return self._rows_to_dict(rows)

    def insert_record(self, role_name: str, record_date: str, activity_type: str,
                    cash_income: float, item_income: float, cost: float, 
                    net_profit: float, remark: str = None) -> int:
        """插入新记录"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO income_records 
            (role_name, record_date, activity_type, cash_income, item_income, cost, net_profit, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (role_name, record_date, activity_type, cash_income, item_income, cost, net_profit, remark))
        conn.commit()
        record_id = cursor.lastrowid
        conn.close()
        return record_id

    def update_record(self, record_id: int, role_name: str, record_date: str, 
                    activity_type: str, cash_income: float, item_income: float, 
                    cost: float, net_profit: float, remark: str = None) -> bool:
        """更新记录"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE income_records 
            SET role_name=?, record_date=?, activity_type=?, cash_income=?, 
                item_income=?, cost=?, net_profit=?, remark=?
            WHERE id=?
        ''', (role_name, record_date, activity_type, cash_income, item_income, cost, net_profit, remark, record_id))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def delete_record(self, record_id: int) -> bool:
        """删除记录"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM income_records WHERE id=?', (record_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def rename_role(self, old_name: str, new_name: str) -> int:
        """角色改名时同步历史收益，避免统计被拆分。"""
        if not old_name or old_name == new_name:
            return 0
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE income_records SET role_name=? WHERE role_name=?',
            (new_name, old_name),
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected

    def delete_role_records(self, role_name: str) -> int:
        """删除指定角色的全部历史收益记录。"""
        if not role_name:
            return 0
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM income_records WHERE role_name=?', (role_name,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected

    def get_daily_summary(self, records: List[Dict]) -> List[Dict]:
        """按日期汇总"""
        daily = {}
        for r in records:
            date = r['record_date']
            if date not in daily:
                daily[date] = {'record_date': date, 'total_cash': 0, 'total_item': 0, 'total_cost': 0, 'total_net': 0}
            daily[date]['total_cash'] += r['cash_income']
            daily[date]['total_item'] += r['item_income']
            daily[date]['total_cost'] += r['cost']
            daily[date]['total_net'] += r['net_profit']
        return sorted(daily.values(), key=lambda x: x['record_date'])

    def get_role_summary(self, records: List[Dict]) -> List[Dict]:
        """按角色汇总"""
        roles = {}
        for r in records:
            name = r['role_name']
            if name not in roles:
                roles[name] = {'role_name': name, 'days': set(), 'total_net': 0}
            roles[name]['days'].add(r['record_date'])
            roles[name]['total_net'] += r['net_profit']
        result = []
        for name, data in roles.items():
            result.append({
                'role_name': name,
                'days': len(data['days']),
                'total_net': data['total_net'],
                'avg_daily': data['total_net'] / len(data['days']) if data['days'] else 0
            })
        return sorted(result, key=lambda x: x['total_net'], reverse=True)

    def get_activity_summary(self, records: List[Dict]) -> List[Dict]:
        """按活动汇总"""
        activities = {}
        for r in records:
            act = r['activity_type']
            if act not in activities:
                activities[act] = {'activity_type': act, 'count': 0, 'total_net': 0}
            activities[act]['count'] += 1
            activities[act]['total_net'] += r['net_profit']
        result = []
        for act, data in activities.items():
            result.append({
                'activity_type': act,
                'count': data['count'],
                'total_net': data['total_net'],
                'avg_per_time': data['total_net'] / data['count'] if data['count'] else 0
            })
        return sorted(result, key=lambda x: x['total_net'], reverse=True)

    def _rows_to_dict(self, rows) -> List[Dict]:
        """将SQLite行转换为字典列表"""
        result = []
        columns = ['id', 'role_name', 'record_date', 'activity_type', 
                    'cash_income', 'item_income', 'cost', 'net_profit', 'remark']
        for row in rows:
            result.append(dict(zip(columns, row)))
        return result


ACTIVITY_TYPES = ["抓鬼", "副本", "神器", "周末活动", "摆摊卖货", "其他"]


def format_number(value: float) -> str:
    """格式化以“万”为输入单位的金额。"""
    if abs(value) >= 10000:
        return f"{value / 10000:.2f}亿"
    return f"{value:.2f}万"
