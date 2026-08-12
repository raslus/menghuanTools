"""答题器题库的 SQLite 数据访问层。"""

import csv
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from utils.logger_setup import logger

try:
    from rapidfuzz import fuzz, process as rf_process

    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False


def _normalize_text(value: str) -> str:
    """生成用于去重和模糊匹配的稳定文本。"""
    return re.sub(r"[\W_]+", "", (value or "").strip().lower(), flags=re.UNICODE)


def _levenshtein_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return 1.0 - previous[-1] / max(len(left), len(right))


class QuizDB:
    """提供题库迁移、增删改查、搜索、匹配和 CSV 交换。"""

    SELECT_FIELDS = (
        "id, question, answer, category, hit_count, created_at, updated_at"
    )

    def __init__(self, db_file: str = "quiz_bank.db", seed_file: Optional[str] = None):
        self.db_file = db_file
        self.seed_file = seed_file
        os.makedirs(os.path.dirname(os.path.abspath(db_file)), exist_ok=True)
        self._init_db()
        self._seed_if_empty()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_file, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _init_db(self) -> None:
        """创建数据库，并为旧版题库无损增加规范化字段和索引。"""
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    hit_count INTEGER NOT NULL DEFAULT 0 CHECK (hit_count >= 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    normalized_question TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(quiz_bank)")
            }
            if "normalized_question" not in columns:
                connection.execute(
                    "ALTER TABLE quiz_bank ADD COLUMN normalized_question TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_quiz_question ON quiz_bank(question)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_quiz_category ON quiz_bank(category)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_quiz_normalized ON quiz_bank(normalized_question)"
            )
            rows = connection.execute(
                "SELECT id, question FROM quiz_bank WHERE normalized_question = ''"
            ).fetchall()
            connection.executemany(
                "UPDATE quiz_bank SET normalized_question = ? WHERE id = ?",
                [(_normalize_text(row["question"]), row["id"]) for row in rows],
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict:
        return dict(row)

    @staticmethod
    def _clean_values(question: str, answer: str, category: str = "") -> Tuple[str, str, str]:
        question = (question or "").strip()
        answer = (answer or "").strip()
        category = (category or "").strip()
        if not question or not answer:
            raise ValueError("问题和答案不能为空")
        return question, answer, category

    def add_question(self, question: str, answer: str, category: str = "") -> Dict:
        question, answer, category = self._clean_values(question, answer, category)
        normalized = _normalize_text(question)
        with closing(self._connect()) as connection, connection:
            duplicate = connection.execute(
                "SELECT id FROM quiz_bank WHERE normalized_question = ? LIMIT 1",
                (normalized,),
            ).fetchone()
            if duplicate:
                raise ValueError("题库中已存在相同题目")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor = connection.execute(
                """
                INSERT INTO quiz_bank
                    (question, answer, category, hit_count, created_at, updated_at,
                     normalized_question)
                VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (question, answer, category, now, now, normalized),
            )
            question_id = cursor.lastrowid
        logger.debug("添加题目: id=%s, question=%s", question_id, question[:30])
        return self.get_question(question_id)

    def get_question(self, question_id: int) -> Optional[Dict]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT {self.SELECT_FIELDS} FROM quiz_bank WHERE id = ?",
                (question_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update_question(
        self,
        question_id: int,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        existing = self.get_question(question_id)
        if not existing:
            return False
        new_question, new_answer, new_category = self._clean_values(
            question if question is not None else existing["question"],
            answer if answer is not None else existing["answer"],
            category if category is not None else existing["category"],
        )
        normalized = _normalize_text(new_question)
        with closing(self._connect()) as connection, connection:
            duplicate = connection.execute(
                "SELECT id FROM quiz_bank WHERE normalized_question = ? AND id != ? LIMIT 1",
                (normalized, question_id),
            ).fetchone()
            if duplicate:
                raise ValueError("题库中已存在相同题目")
            cursor = connection.execute(
                """
                UPDATE quiz_bank
                SET question = ?, answer = ?, category = ?, normalized_question = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_question,
                    new_answer,
                    new_category,
                    normalized,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    question_id,
                ),
            )
        return cursor.rowcount > 0

    def delete_question(self, question_id: int) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM quiz_bank WHERE id = ?", (question_id,))
        return cursor.rowcount > 0

    def query_questions(
        self,
        keyword: str = "",
        category: str = "",
        limit: Optional[int] = 200,
        offset: int = 0,
    ) -> List[Dict]:
        conditions, params = [], []
        if keyword.strip():
            pattern = f"%{keyword.strip()}%"
            conditions.append("(question LIKE ? OR answer LIKE ? OR category LIKE ?)")
            params.extend([pattern, pattern, pattern])
        if category.strip():
            conditions.append("category = ?")
            params.append(category.strip())
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT {self.SELECT_FIELDS} FROM quiz_bank{where} ORDER BY hit_count DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([max(1, limit), max(0, offset)])
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_all_questions(self, category: Optional[str] = None) -> List[Dict]:
        return self.query_questions(category=category or "", limit=None)

    def search_questions(self, keyword: str, limit: int = 50) -> List[Dict]:
        return self.query_questions(keyword=keyword, limit=limit)

    def count_questions(self, keyword: str = "", category: str = "") -> int:
        conditions, params = [], []
        if keyword.strip():
            pattern = f"%{keyword.strip()}%"
            conditions.append("(question LIKE ? OR answer LIKE ? OR category LIKE ?)")
            params.extend([pattern, pattern, pattern])
        if category.strip():
            conditions.append("category = ?")
            params.append(category.strip())
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        with closing(self._connect()) as connection:
            return connection.execute(
                f"SELECT COUNT(*) FROM quiz_bank{where}", params
            ).fetchone()[0]

    def get_categories(self) -> List[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT category FROM quiz_bank WHERE category != '' ORDER BY category"
            ).fetchall()
        return [row[0] for row in rows]

    def get_stats(self) -> Dict:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(DISTINCT CASE WHEN category != '' THEN category END) AS categories,
                       COALESCE(SUM(hit_count), 0) AS total_hits
                FROM quiz_bank
                """
            ).fetchone()
        return dict(row)

    def fuzzy_match(
        self, query: str, limit: int = 5, min_score: float = 0.5
    ) -> List[Tuple[Dict, float]]:
        normalized_query = _normalize_text(query)
        questions = self.get_all_questions()
        if not normalized_query or not questions:
            return []
        candidates = [_normalize_text(item["question"]) for item in questions]
        if _RAPIDFUZZ_AVAILABLE:
            raw_matches = rf_process.extract(
                normalized_query,
                candidates,
                scorer=fuzz.WRatio,
                limit=limit,
                score_cutoff=min_score * 100,
            )
            results = [(questions[index], score / 100.0) for _, score, index in raw_matches]
        else:
            results = [
                (item, _levenshtein_ratio(normalized_query, candidate))
                for item, candidate in zip(questions, candidates)
            ]
            results = sorted(
                (result for result in results if result[1] >= min_score),
                key=lambda result: result[1],
                reverse=True,
            )[:limit]
        if results:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    "UPDATE quiz_bank SET hit_count = hit_count + 1 WHERE id = ?",
                    (results[0][0]["id"],),
                )
            results[0][0]["hit_count"] += 1
        return results

    def export_to_csv(self, filepath: str) -> int:
        questions = self.get_all_questions()
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["问题", "答案", "分类", "命中次数"])
                writer.writerows(
                    (q["question"], q["answer"], q["category"], q["hit_count"])
                    for q in questions
                )
            return len(questions)
        except OSError as exc:
            logger.error("题库导出失败: %s", exc)
            return 0

    def import_from_csv(self, filepath: str, merge: bool = True) -> Tuple[bool, int]:
        """事务化导入；合并模式按规范化问题去重，覆盖模式原子替换。"""
        try:
            with open(filepath, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.reader(file))
            if rows and rows[0] and rows[0][0].strip() in {"问题", "question"}:
                rows = rows[1:]
            cleaned = []
            seen = set()
            for row in rows:
                if len(row) < 2:
                    continue
                try:
                    question, answer, category = self._clean_values(
                        row[0], row[1], row[2] if len(row) > 2 else ""
                    )
                except ValueError:
                    continue
                normalized = _normalize_text(question)
                if normalized in seen:
                    continue
                seen.add(normalized)
                cleaned.append((question, answer, category, normalized))
            with closing(self._connect()) as connection, connection:
                if not merge:
                    connection.execute("DELETE FROM quiz_bank")
                    existing = set()
                else:
                    existing = {
                        row[0]
                        for row in connection.execute(
                            "SELECT normalized_question FROM quiz_bank"
                        )
                    }
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_rows = [row for row in cleaned if row[3] not in existing]
                connection.executemany(
                    """
                    INSERT INTO quiz_bank
                        (question, answer, category, hit_count, created_at, updated_at,
                         normalized_question)
                    VALUES (?, ?, ?, 0, ?, ?, ?)
                    """,
                    [(q, a, c, now, now, n) for q, a, c, n in new_rows],
                )
            logger.info("题库导入完成: %s，共 %s 条", filepath, len(new_rows))
            return True, len(new_rows)
        except (OSError, csv.Error, sqlite3.Error) as exc:
            logger.error("题库导入失败: %s", exc)
            return False, 0

    def _seed_if_empty(self) -> None:
        if self.seed_file and os.path.isfile(self.seed_file) and self.count_questions() == 0:
            success, count = self.import_from_csv(self.seed_file)
            if success:
                logger.info("已初始化答题器内置题库，共 %s 条", count)
