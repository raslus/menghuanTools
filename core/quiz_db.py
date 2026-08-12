"""答题器题库数据库

SQLite 存储，支持：
- CRUD 操作
- 模糊匹配（优先 rapidfuzz，回退到编辑距离）
- CSV 导入/导出
"""

import csv
import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from utils.logger_setup import logger

# 可选依赖：rapidfuzz（高性能模糊匹配）
try:
    from rapidfuzz import fuzz, process as rf_process
    _rapidfuzz_available = True
except ImportError:
    _rapidfuzz_available = False


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """编辑距离相似度（0~1），rapidfuzz 不可用时的回退方案"""
    if not s1 or not s2:
        return 0.0
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    distance = dp[m][n]
    return 1.0 - distance / max(m, n)


class QuizDB:
    """答题器题库"""

    def __init__(self, db_file: str = "quiz_bank.db"):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                category TEXT DEFAULT '',
                hit_count INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_question ON quiz_bank(question)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON quiz_bank(category)')
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def add_question(self, question: str, answer: str, category: str = "") -> Dict:
        """添加题目"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO quiz_bank (question, answer, category, hit_count, created_at, updated_at) '
            'VALUES (?, ?, ?, 0, ?, ?)',
            (question, answer, category, now, now)
        )
        question_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.debug(f"添加题目: id={question_id}, question={question[:30]}...")
        return {"id": question_id, "question": question, "answer": answer,
                "category": category, "hit_count": 0}

    def update_question(self, question_id: int, question: str = None,
                        answer: str = None, category: str = None) -> bool:
        """更新题目"""
        updates, params = [], []
        if question is not None:
            updates.append("question = ?")
            params.append(question)
        if answer is not None:
            updates.append("answer = ?")
            params.append(answer)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(question_id)

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(f'UPDATE quiz_bank SET {", ".join(updates)} WHERE id = ?', params)
        affected = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return affected

    def delete_question(self, question_id: int) -> bool:
        """删除题目"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM quiz_bank WHERE id = ?', (question_id,))
        affected = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return affected

    def get_all_questions(self, category: str = None) -> List[Dict]:
        """获取所有题目（可按分类筛选）"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        if category:
            cursor.execute(
                'SELECT id, question, answer, category, hit_count FROM quiz_bank '
                'WHERE category = ? ORDER BY hit_count DESC, id DESC',
                (category,)
            )
        else:
            cursor.execute(
                'SELECT id, question, answer, category, hit_count FROM quiz_bank '
                'ORDER BY hit_count DESC, id DESC'
            )
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "question": r[1], "answer": r[2],
                 "category": r[3], "hit_count": r[4]} for r in rows]

    def search_questions(self, keyword: str, limit: int = 50) -> List[Dict]:
        """关键词搜索题目"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, question, answer, category, hit_count FROM quiz_bank '
            'WHERE question LIKE ? OR answer LIKE ? '
            'ORDER BY hit_count DESC, id DESC LIMIT ?',
            (f"%{keyword}%", f"%{keyword}%", limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "question": r[1], "answer": r[2],
                 "category": r[3], "hit_count": r[4]} for r in rows]

    def get_categories(self) -> List[str]:
        """获取所有分类"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT DISTINCT category FROM quiz_bank WHERE category != "" ORDER BY category'
        )
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM quiz_bank')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(DISTINCT category) FROM quiz_bank WHERE category != ""')
        categories = cursor.fetchone()[0]
        cursor.execute('SELECT SUM(hit_count) FROM quiz_bank')
        total_hits = cursor.fetchone()[0] or 0
        conn.close()
        return {"total": total, "categories": categories, "total_hits": total_hits}

    # ------------------------------------------------------------------
    # 模糊匹配
    # ------------------------------------------------------------------
    def fuzzy_match(self, query: str, limit: int = 5,
                    min_score: float = 0.5) -> List[Tuple[Dict, float]]:
        """模糊匹配题目

        Args:
            query: 待匹配的文本（OCR 识别结果）
            limit: 返回的最大匹配数
            min_score: 最低相似度阈值（0~1）

        Returns:
            [(question_dict, score), ...] 按相似度降序排列
        """
        if not query or not query.strip():
            return []

        all_questions = self.get_all_questions()
        if not all_questions:
            return []

        query_clean = query.strip()
        results = []

        if _rapidfuzz_available:
            # rapidfuzz 高性能匹配：综合 partial_ratio 和 token_sort_ratio
            questions_text = [q["question"] for q in all_questions]
            matches = rf_process.extract(
                query_clean, questions_text,
                scorer=fuzz.partial_ratio,
                limit=limit * 2,
                score_cutoff=min_score * 100
            )
            for match in matches:
                idx, score = match[1], match[2]
                results.append((all_questions[idx], score / 100.0))
        else:
            # 回退：编辑距离相似度
            for q in all_questions:
                score = _levenshtein_ratio(query_clean, q["question"])
                if score >= min_score:
                    results.append((q, score))
            results.sort(key=lambda x: x[1], reverse=True)
            results = results[:limit * 2]

        results = results[:limit]

        # 记录命中（仅对最佳匹配）
        if results:
            best_id = results[0][0]["id"]
            self._increment_hit_count(best_id)

        return results

    def _increment_hit_count(self, question_id: int):
        """增加题目命中次数"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('UPDATE quiz_bank SET hit_count = hit_count + 1 WHERE id = ?', (question_id,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 导入/导出
    # ------------------------------------------------------------------
    def export_to_csv(self, filepath: str) -> int:
        """导出题库到 CSV 文件

        Returns:
            导出的题目数量
        """
        questions = self.get_all_questions()
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['问题', '答案', '分类', '命中次数'])
                for q in questions:
                    writer.writerow([q["question"], q["answer"], q["category"], q["hit_count"]])
            logger.info(f"题库导出完成: {filepath}，共 {len(questions)} 条")
            return len(questions)
        except Exception as e:
            logger.error(f"题库导出失败: {e}")
            return 0

    def import_from_csv(self, filepath: str, merge: bool = True) -> Tuple[bool, int]:
        """从 CSV 文件导入题库

        Args:
            filepath: CSV 文件路径
            merge: True=合并（去重），False=覆盖

        Returns:
            (成功, 导入数量)
        """
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                # 跳过表头
                if header and '问题' in str(header):
                    pass

                existing = set()
                if merge:
                    for q in self.get_all_questions():
                        existing.add(q["question"])

                imported = 0
                for row in reader:
                    if len(row) < 2:
                        continue
                    question, answer = row[0].strip(), row[1].strip()
                    category = row[2].strip() if len(row) > 2 else ""
                    if not question or not answer:
                        continue
                    if merge and question in existing:
                        continue
                    self.add_question(question, answer, category)
                    existing.add(question)
                    imported += 1

                logger.info(f"题库导入完成: {filepath}，共 {imported} 条")
                return True, imported
        except Exception as e:
            logger.error(f"题库导入失败: {e}")
            return False, 0
