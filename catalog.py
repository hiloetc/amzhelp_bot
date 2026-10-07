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

    # Добавь эту функцию в catalog.py

def init_authors_table():
    """Создаёт таблицу авторов сборок."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            telegram TEXT,
            description TEXT,
            verified INTEGER DEFAULT 0,
            trust_score REAL DEFAULT 0,
            builds_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_author(name: str, telegram: str = "", description: str = "", verified: int = 0) -> int:
    """Добавляет автора. Если существует — обновляет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO authors (name, telegram, description, verified, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            telegram = excluded.telegram,
            description = excluded.description,
            verified = excluded.verified
    """, (name, telegram, description, verified, datetime.now().isoformat()))
    conn.commit()

    cursor.execute("SELECT id FROM authors WHERE name = ?", (name,))
    author_id = cursor.fetchone()[0]
    conn.close()
    return author_id


def get_author(author_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM authors WHERE id = ?", (author_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_author_by_name(name: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM authors WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_authors(limit: int = 20, offset: int = 0):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM authors
        ORDER BY verified DESC, trust_score DESC, builds_count DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_author_stats(author_name: str):
    """Пересчитывает количество сборок и средний рейтинг автора."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE authors
        SET builds_count = (
                SELECT COUNT(*) FROM builds WHERE author = ?
            ),
            trust_score = COALESCE((
                SELECT AVG(rating) FROM builds
                WHERE author = ? AND votes > 0
            ), 0)
        WHERE name = ?
    """, (author_name, author_name, author_name))

    conn.commit()
    conn.close()


# ========== КОНСТРУКТОР СБОРОК ==========

def init_components_table():
    """Создаёт таблицу компонентов для конструктора."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            link TEXT,
            sha256 TEXT,
            size_kb INTEGER,
            author TEXT,
            created_at TEXT,
            UNIQUE(name, category)
        )
    """)
    conn.commit()
    conn.close()


def add_component(name: str, category: str, description: str = "",
                  link: str = "", sha256: str = "", size_kb: int = 0,
                  author: str = "") -> int:
    """Добавляет компонент в конструктор."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO components (name, category, description, link, sha256, size_kb, author, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name, category) DO UPDATE SET
            description = excluded.description,
            link = excluded.link,
            sha256 = excluded.sha256,
            size_kb = excluded.size_kb,
            author = excluded.author
    """, (name, category, description, link, sha256, size_kb, author, datetime.now().isoformat()))
    conn.commit()
    cursor.execute("SELECT id FROM components WHERE name = ? AND category = ?", (name, category))
    comp_id = cursor.fetchone()[0]
    conn.close()
    return comp_id


def get_components(category: str = None, limit: int = 50):
    """Список компонентов по категории или все."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if category:
        cursor.execute("""
            SELECT * FROM components WHERE category = ?
            ORDER BY name LIMIT ?
        """, (category, limit))
    else:
        cursor.execute("""
            SELECT * FROM components ORDER BY category, name LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_component(comp_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM components WHERE id = ?", (comp_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_component(comp_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM components WHERE id = ?", (comp_id,))
    conn.commit()
    conn.close()


# Категории компонентов для конструктора
COMPONENT_CATEGORIES = {
    "fps_boost": "🚀 FPS-буст",
    "textures": "🖼 Сжатые текстуры",
    "lights": "🚨 Мигалки / спецсигналы",
    "masks": "🎭 Маски / скины",
    "weapons": "🔫 Оружие / звуки",
    "ui": "🎨 Интерфейс / HUD",
    "sounds": "🔊 Звуки / музыка",
    "other": "📦 Другое",
}