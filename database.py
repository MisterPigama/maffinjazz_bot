# 📄 файл: database.py

import aiosqlite
import logging
from datetime import date, datetime
from typing import Optional

from config import DB_PATH

logger = logging.getLogger(__name__)


# ─────────────────────────── INIT ───────────────────────────

async def init_db() -> None:
    """Создаёт таблицы, если не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id           INTEGER UNIQUE NOT NULL,
                name                  TEXT NOT NULL,
                last_check_time       DATETIME,
                last_edit_request_time DATETIME
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL REFERENCES users(id),
                start_date     DATE NOT NULL,
                end_date       DATE NOT NULL,
                total_lessons  INTEGER NOT NULL DEFAULT 8,
                lessons_left   INTEGER NOT NULL,
                status         TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','expired','used_up'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attendance_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                sub_id          INTEGER NOT NULL REFERENCES subscriptions(id),
                marked_at       DATETIME NOT NULL,
                marked_by_admin_id INTEGER NOT NULL
            )
        """)
        await db.commit()
    logger.info("БД инициализирована.")


# ─────────────────────────── USERS ───────────────────────────

async def get_user_by_telegram_id(telegram_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_user(telegram_id: int, name: str) -> int:
    """Создаёт пользователя. Возвращает его id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO users (telegram_id, name) VALUES (?, ?)",
            (telegram_id, name),
        )
        await db.commit()
        return cur.lastrowid


async def get_all_students() -> list[dict]:
    """Все пользователи, кроме самого себя (без фильтра по admin — фильтр в хендлере)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY name") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def name_exists(name: str, exclude_telegram_id: Optional[int] = None) -> bool:
    """
    Регистронезависимая проверка с игнором пробелов.
    'игорь' == 'Игорь', но 'Игорь' != 'Игорь К.'
    """
    normalized = name.strip().lower().replace(" ", "")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT telegram_id, name FROM users") as cur:
            rows = await cur.fetchall()
    for row in rows:
        if exclude_telegram_id and row["telegram_id"] == exclude_telegram_id:
            continue
        existing = row["name"].strip().lower().replace(" ", "")
        if existing == normalized:
            return True
    return False


async def update_last_check_time(telegram_id: int, dt: datetime) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_check_time = ? WHERE telegram_id = ?",
            (dt.isoformat(), telegram_id),
        )
        await db.commit()


async def update_last_edit_request_time(telegram_id: int, dt: datetime) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_edit_request_time = ? WHERE telegram_id = ?",
            (dt.isoformat(), telegram_id),
        )
        await db.commit()


# ─────────────────────────── SUBSCRIPTIONS ───────────────────────────

async def get_active_subscription(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active' LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_subscription_by_id(sub_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (sub_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_subscription(
    user_id: int,
    start_date: date,
    end_date: date,
    lessons_left: int = 8,
    total_lessons: int = 8,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO subscriptions
                (user_id, start_date, end_date, total_lessons, lessons_left, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (user_id, start_date.isoformat(), end_date.isoformat(), total_lessons, lessons_left),
        )
        await db.commit()
        return cur.lastrowid


async def update_subscription_dates(sub_id: int, start_date: date, end_date: date) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET start_date = ?, end_date = ? WHERE id = ?",
            (start_date.isoformat(), end_date.isoformat(), sub_id),
        )
        await db.commit()


async def update_subscription_lessons(sub_id: int, lessons_left: int) -> None:
    status = "used_up" if lessons_left == 0 else "active"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET lessons_left = ?, status = ? WHERE id = ?",
            (lessons_left, status, sub_id),
        )
        await db.commit()


async def mark_lesson(sub_id: int, admin_id: int) -> int:
    """
    Списывает 1 занятие. Если lessons_left становится 0 — ставит status='used_up'.
    Пишет в attendance_log.
    Возвращает новое значение lessons_left.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT lessons_left FROM subscriptions WHERE id = ?", (sub_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise ValueError(f"Абонемент {sub_id} не найден")
        new_left = max(0, row["lessons_left"] - 1)
        status = "used_up" if new_left == 0 else "active"
        await db.execute(
            "UPDATE subscriptions SET lessons_left = ?, status = ? WHERE id = ?",
            (new_left, status, sub_id),
        )
        await db.execute(
            "INSERT INTO attendance_log (sub_id, marked_at, marked_by_admin_id) VALUES (?, ?, ?)",
            (sub_id, datetime.now().isoformat(), admin_id),
        )
        await db.commit()
    return new_left


async def get_all_active_subscriptions_with_users() -> list[dict]:
    """
    Возвращает все активные абонементы вместе с данными пользователя.
    Сортировка в хендлере.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                s.id          AS sub_id,
                s.user_id,
                s.start_date,
                s.end_date,
                s.total_lessons,
                s.lessons_left,
                s.status,
                u.name,
                u.telegram_id
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE s.status = 'active'
            ORDER BY s.end_date ASC
            """
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def expire_overdue_subscriptions() -> int:
    """
    Помечает просроченные абонементы как expired.
    Вызывается при старте и при каждом просмотре списка.
    Возвращает количество обновлённых записей.
    """
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE subscriptions
            SET status = 'expired'
            WHERE status = 'active' AND end_date < ?
            """,
            (today,),
        )
        await db.commit()
        return cur.rowcount


async def get_attendable_subscriptions() -> list[dict]:
    """
    Абонементы пригодные для отметки: active, lessons_left > 0, end_date >= today.
    """
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                s.id          AS sub_id,
                s.user_id,
                s.end_date,
                s.total_lessons,
                s.lessons_left,
                u.name,
                u.telegram_id
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE s.status = 'active'
              AND s.lessons_left > 0
              AND s.end_date >= ?
            ORDER BY u.name ASC
            """,
            (today,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]