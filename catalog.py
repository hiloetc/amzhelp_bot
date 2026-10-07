import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = "builds.db"


def init_db():
    """Создаёт таблицы, если их нет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            author TEXT,
            link TEXT,
            sha256 TEXT,
            vt_status TEXT,
            rating REAL DEFAULT 0,
            votes INTEGER DEFAULT 0,
            created_at TEXT,
            added_by INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT,
            UNIQUE(build_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


def add_build(title: str, category: str, description: str = "",
              author: str = "", link: str = "", sha256: str = "",
              vt_status: str = "", added_by: int = 0) -> int:
    """Добавляет сборку в каталог. Возвращает ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO builds (title, description, category, author, link, sha256, vt_status, created_at, added_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, description, category, author, link, sha256, vt_status,
          datetime.now().isoformat(), added_by))
    build_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return build_id


def get_builds(category: Optional[str] = None, limit: int = 10, offset: int = 0):
    """Возвращает список сборок, опционально с фильтром по категории."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if category:
        cursor.execute("""
            SELECT * FROM builds WHERE category = ?
            ORDER BY rating DESC, votes DESC, created_at DESC
            LIMIT ? OFFSET ?
        """, (category, limit, offset))
    else:
        cursor.execute("""
            SELECT * FROM builds
            ORDER BY rating DESC, votes DESC, created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_build(build_id: int):
    """Возвращает одну сборку по ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM builds WHERE id = ?", (build_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def rate_build(build_id: int, user_id: int, score: int):
    """Ставит оценку (1–5). Если пользователь уже голосовал — обновляет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ratings (build_id, user_id, score, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(build_id, user_id) DO UPDATE SET score = excluded.score
    """, (build_id, user_id, score, datetime.now().isoformat()))

    # Пересчёт рейтинга
    cursor.execute("""
        UPDATE builds
        SET rating = (SELECT AVG(score) FROM ratings WHERE build_id = ?),
            votes  = (SELECT COUNT(*) FROM ratings WHERE build_id = ?)
        WHERE id = ?
    """, (build_id, build_id, build_id))

    conn.commit()
    conn.close()


def delete_build(build_id: int):
    """Удаляет сборку (для админов)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM builds WHERE id = ?", (build_id,))
    cursor.execute("DELETE FROM ratings WHERE build_id = ?", (build_id,))
    conn.commit()
    conn.close()


def count_builds(category: Optional[str] = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if category:
        cursor.execute("SELECT COUNT(*) FROM builds WHERE category = ?", (category,))
    else:
        cursor.execute("SELECT COUNT(*) FROM builds")
    count = cursor.fetchone()[0]
    conn.close()
    return count