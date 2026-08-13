import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, Optional


class GrowthDB:
    def __init__(self, db_file="growth.db"):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_growth (
                role_name TEXT PRIMARY KEY,
                cur_level INTEGER DEFAULT 0,
                cur_hp INTEGER DEFAULT 0,
                cur_mp INTEGER DEFAULT 0,
                cur_damage INTEGER DEFAULT 0,
                cur_magic_damage INTEGER DEFAULT 0,
                cur_defense INTEGER DEFAULT 0,
                cur_magic_defense INTEGER DEFAULT 0,
                cur_speed INTEGER DEFAULT 0,
                cur_atk_cult INTEGER DEFAULT 0,
                cur_def_cult INTEGER DEFAULT 0,
                cur_magic_atk_cult INTEGER DEFAULT 0,
                cur_magic_def_cult INTEGER DEFAULT 0,
                cur_main_skill INTEGER DEFAULT 0,
                tar_level INTEGER DEFAULT 0,
                tar_hp INTEGER DEFAULT 0,
                tar_mp INTEGER DEFAULT 0,
                tar_damage INTEGER DEFAULT 0,
                tar_magic_damage INTEGER DEFAULT 0,
                tar_defense INTEGER DEFAULT 0,
                tar_magic_defense INTEGER DEFAULT 0,
                tar_speed INTEGER DEFAULT 0,
                tar_atk_cult INTEGER DEFAULT 0,
                tar_def_cult INTEGER DEFAULT 0,
                tar_magic_atk_cult INTEGER DEFAULT 0,
                tar_magic_def_cult INTEGER DEFAULT 0,
                tar_main_skill INTEGER DEFAULT 0,
                equip_weapon TEXT,
                equip_head TEXT,
                equip_body TEXT,
                equip_belt TEXT,
                equip_shoes TEXT,
                equip_necklace TEXT,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_equipment (
                role_name TEXT NOT NULL,
                slot TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (role_name, slot)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_growth_system (
                role_name TEXT PRIMARY KEY,
                data_json TEXT NOT NULL DEFAULT '{}',
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_role_growth(self, role_name: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM role_growth WHERE role_name = ?', (role_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return self._row_to_dict(row)
        return None

    def upsert_role_growth(self, data: Dict) -> bool:
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO role_growth (
                role_name, cur_level, cur_hp, cur_mp, cur_damage, cur_magic_damage,
                cur_defense, cur_magic_defense, cur_speed, cur_atk_cult, cur_def_cult,
                cur_magic_atk_cult, cur_magic_def_cult, cur_main_skill,
                tar_level, tar_hp, tar_mp, tar_damage, tar_magic_damage,
                tar_defense, tar_magic_defense, tar_speed, tar_atk_cult, tar_def_cult,
                tar_magic_atk_cult, tar_magic_def_cult, tar_main_skill,
                equip_weapon, equip_head, equip_body, equip_belt, equip_shoes, equip_necklace,
                update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('role_name'),
            data.get('cur_level', 0),
            data.get('cur_hp', 0),
            data.get('cur_mp', 0),
            data.get('cur_damage', 0),
            data.get('cur_magic_damage', 0),
            data.get('cur_defense', 0),
            data.get('cur_magic_defense', 0),
            data.get('cur_speed', 0),
            data.get('cur_atk_cult', 0),
            data.get('cur_def_cult', 0),
            data.get('cur_magic_atk_cult', 0),
            data.get('cur_magic_def_cult', 0),
            data.get('cur_main_skill', 0),
            data.get('tar_level', 0),
            data.get('tar_hp', 0),
            data.get('tar_mp', 0),
            data.get('tar_damage', 0),
            data.get('tar_magic_damage', 0),
            data.get('tar_defense', 0),
            data.get('tar_magic_defense', 0),
            data.get('tar_speed', 0),
            data.get('tar_atk_cult', 0),
            data.get('tar_def_cult', 0),
            data.get('tar_magic_atk_cult', 0),
            data.get('tar_magic_def_cult', 0),
            data.get('tar_main_skill', 0),
            data.get('equip_weapon', ''),
            data.get('equip_head', ''),
            data.get('equip_body', ''),
            data.get('equip_belt', ''),
            data.get('equip_shoes', ''),
            data.get('equip_necklace', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        
        conn.commit()
        conn.close()
        return True

    def delete_role_growth(self, role_name: str) -> bool:
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM role_growth WHERE role_name = ?', (role_name,))
        affected = cursor.rowcount
        cursor.execute('DELETE FROM role_equipment WHERE role_name = ?', (role_name,))
        cursor.execute('DELETE FROM role_growth_system WHERE role_name = ?', (role_name,))
        conn.commit()
        conn.close()
        return affected > 0

    def get_role_equipment(self, role_name: str) -> Dict:
        """Return structured equipment keyed by slot; invalid rows are ignored."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT slot, data_json FROM role_equipment WHERE role_name = ?',
            (role_name,),
        )
        result = {}
        for slot, raw_data in cursor.fetchall():
            try:
                value = json.loads(raw_data)
                if isinstance(value, dict):
                    result[slot] = value
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        conn.close()
        return result

    def save_role_equipment(self, role_name: str, equipment: Dict) -> bool:
        """Atomically replace all structured equipment for one role."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM role_equipment WHERE role_name = ?', (role_name,))
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            rows = [
                (role_name, slot, json.dumps(data, ensure_ascii=False), now)
                for slot, data in equipment.items()
                if isinstance(data, dict) and data
            ]
            if rows:
                cursor.executemany('''
                    INSERT INTO role_equipment (role_name, slot, data_json, update_time)
                    VALUES (?, ?, ?, ?)
                ''', rows)
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_role_growth_system(self, role_name: str) -> Dict:
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT data_json FROM role_growth_system WHERE role_name = ?', (role_name,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {}
        try:
            value = json.loads(row[0])
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def save_role_growth_system(self, role_name: str, data: Dict) -> bool:
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO role_growth_system (role_name, data_json, update_time)
            VALUES (?, ?, ?)
            ON CONFLICT(role_name) DO UPDATE SET
                data_json = excluded.data_json,
                update_time = excluded.update_time
        ''', (
            role_name,
            json.dumps(data, ensure_ascii=False),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        conn.commit()
        conn.close()
        return True

    def rename_role(self, old_name: str, new_name: str) -> bool:
        """同步角色在养成相关表中的名称。"""
        if not old_name or old_name == new_name:
            return True
        conn = sqlite3.connect(self.db_file)
        try:
            cursor = conn.cursor()
            for table in ("role_growth", "role_equipment", "role_growth_system"):
                cursor.execute(
                    f"UPDATE {table} SET role_name=? WHERE role_name=?",
                    (new_name, old_name),
                )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            conn.rollback()
            return False
        finally:
            conn.close()

    def _row_to_dict(self, row) -> Dict:
        columns = [
            'role_name', 'cur_level', 'cur_hp', 'cur_mp', 'cur_damage', 'cur_magic_damage',
            'cur_defense', 'cur_magic_defense', 'cur_speed', 'cur_atk_cult', 'cur_def_cult',
            'cur_magic_atk_cult', 'cur_magic_def_cult', 'cur_main_skill',
            'tar_level', 'tar_hp', 'tar_mp', 'tar_damage', 'tar_magic_damage',
            'tar_defense', 'tar_magic_defense', 'tar_speed', 'tar_atk_cult', 'tar_def_cult',
            'tar_magic_atk_cult', 'tar_magic_def_cult', 'tar_main_skill',
            'equip_weapon', 'equip_head', 'equip_body', 'equip_belt', 'equip_shoes', 'equip_necklace',
            'update_time'
        ]
        return dict(zip(columns, row))
