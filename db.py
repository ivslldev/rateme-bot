"""SQLite data layer. rater_id / ratee_id / photos.user_id store telegram_id."""
import random
import sqlite3
from typing import List, Optional

import config


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create all tables on first launch."""
    con = _connect()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            name TEXT,
            gender TEXT,
            target_gender TEXT,
            avg_rating REAL DEFAULT 0,
            ratings_to_unlock INTEGER DEFAULT 3,
            is_rateable INTEGER DEFAULT 0,
            reports INTEGER DEFAULT 0,
            is_test INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rater_id INTEGER NOT NULL,
            ratee_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rater_id, ratee_id)
        );
        CREATE TABLE IF NOT EXISTS test_sessions (
            admin_id INTEGER PRIMARY KEY,
            acting_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exchanges (
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            PRIMARY KEY(sender_id, receiver_id)
        );
    """)
    con.commit()
    con.close()


# ---------- users ----------

def create_user(telegram_id: int, is_test: int = 0) -> None:
    con = _connect()
    con.execute(
        "INSERT OR IGNORE INTO users (telegram_id, is_test) VALUES (?, ?)",
        (telegram_id, is_test),
    )
    con.commit()
    con.close()


def get_user(telegram_id: int):
    con = _connect()
    row = con.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    con.close()
    return row


def set_name(telegram_id: int, name: str) -> None:
    _update("UPDATE users SET name = ? WHERE telegram_id = ?", (name, telegram_id))


def set_gender(telegram_id: int, gender: str) -> None:
    _update("UPDATE users SET gender = ? WHERE telegram_id = ?", (gender, telegram_id))


def set_target_gender(telegram_id: int, target: str) -> None:
    _update("UPDATE users SET target_gender = ? WHERE telegram_id = ?", (target, telegram_id))


def set_unlocked(telegram_id: int) -> None:
    """Force-unlock a profile (used for test profiles)."""
    _update("UPDATE users SET ratings_to_unlock = 0, is_rateable = 1 WHERE telegram_id = ?",
            (telegram_id,))


def _update(sql: str, params: tuple) -> None:
    con = _connect()
    con.execute(sql, params)
    con.commit()
    con.close()


# ---------- photos ----------

def add_photo(telegram_id: int, file_id: str) -> None:
    con = _connect()
    con.execute("INSERT INTO photos (user_id, file_id) VALUES (?, ?)", (telegram_id, file_id))
    con.commit()
    con.close()


def get_photos(telegram_id: int) -> List[str]:
    con = _connect()
    rows = con.execute("SELECT file_id FROM photos WHERE user_id = ? LIMIT 3",
                       (telegram_id,)).fetchall()
    con.close()
    return [r["file_id"] for r in rows]


# ---------- ratings & balance ----------

def has_rated(rater_id: int, ratee_id: int) -> bool:
    con = _connect()
    row = con.execute("SELECT 1 FROM ratings WHERE rater_id = ? AND ratee_id = ?",
                      (rater_id, ratee_id)).fetchone()
    con.close()
    return row is not None


def add_rating(rater_id: int, ratee_id: int, score: int) -> bool:
    """Insert rating, recompute average, decrement rater's unlock counter."""
    con = _connect()
    cur = con.execute(
        "INSERT OR IGNORE INTO ratings (rater_id, ratee_id, score) VALUES (?, ?, ?)",
        (rater_id, ratee_id, score),
    )
    inserted = cur.rowcount > 0
    if inserted:
        avg = con.execute("SELECT AVG(score) AS a FROM ratings WHERE ratee_id = ?",
                          (ratee_id,)).fetchone()["a"]
        con.execute("UPDATE users SET avg_rating = ? WHERE telegram_id = ?",
                    (round(avg, 2), ratee_id))
        # Balance system: rating someone brings you closer to being rateable.
        row = con.execute("SELECT ratings_to_unlock, is_rateable FROM users WHERE telegram_id = ?",
                          (rater_id,)).fetchone()
        if row and row["is_rateable"] == 0 and row["ratings_to_unlock"] > 0:
            left = row["ratings_to_unlock"] - 1
            con.execute(
                "UPDATE users SET ratings_to_unlock = ?, is_rateable = ? WHERE telegram_id = ?",
                (left, 1 if left == 0 else 0, rater_id),
            )
    con.commit()
    con.close()
    return inserted


def count_received(telegram_id: int) -> int:
    con = _connect()
    n = con.execute("SELECT COUNT(*) AS c FROM ratings WHERE ratee_id = ?",
                    (telegram_id,)).fetchone()["c"]
    con.close()
    return n


def get_next_rateable(rater_id: int, target_gender: str):
    """Random profile of target gender: rateable, with photos, not yet rated by us."""
    con = _connect()
    row = con.execute(
        """
        SELECT * FROM users
        WHERE gender = ? AND telegram_id != ? AND is_rateable = 1
          AND telegram_id IN (SELECT user_id FROM photos)
          AND telegram_id NOT IN (SELECT ratee_id FROM ratings WHERE rater_id = ?)
        ORDER BY RANDOM() LIMIT 1
        """,
        (target_gender, rater_id, rater_id),
    ).fetchone()
    con.close()
    return row


def increment_reports(telegram_id: int) -> int:
    con = _connect()
    con.execute("UPDATE users SET reports = reports + 1 WHERE telegram_id = ?", (telegram_id,))
    n = con.execute("SELECT reports FROM users WHERE telegram_id = ?",
                    (telegram_id,)).fetchone()["reports"]
    con.commit()
    con.close()
    return n


# ---------- test tooling ----------

def list_test_users():
    con = _connect()
    rows = con.execute("SELECT * FROM users WHERE is_test = 1").fetchall()
    con.close()
    return rows


def unique_fake_id() -> int:
    """Generate a telegram_id that does not exist in DB (for fake profiles)."""
    while True:
        tid = random.randint(900_000_001, 999_999_999)
        if get_user(tid) is None:
            return tid


def set_session(admin_id: int, acting_id: int) -> None:
    con = _connect()
    con.execute("INSERT OR REPLACE INTO test_sessions (admin_id, acting_id) VALUES (?, ?)",
                (admin_id, acting_id))
    con.commit()
    con.close()


def get_session(admin_id: int) -> Optional[int]:
    con = _connect()
    row = con.execute("SELECT acting_id FROM test_sessions WHERE admin_id = ?",
                      (admin_id,)).fetchone()
    con.close()
    return row["acting_id"] if row else None


def clear_session(admin_id: int) -> None:
    con = _connect()
    con.execute("DELETE FROM test_sessions WHERE admin_id = ?", (admin_id,))
    con.commit()
    con.close()


# ---------- one-message exchange limit ----------

def exchange_exists(sender: int, receiver: int) -> bool:
    con = _connect()
    row = con.execute("SELECT 1 FROM exchanges WHERE sender_id = ? AND receiver_id = ?",
                      (sender, receiver)).fetchone()
    con.close()
    return row is not None


def exchange_start(sender: int, receiver: int) -> None:
    con = _connect()
    con.execute("INSERT OR IGNORE INTO exchanges (sender_id, receiver_id) VALUES (?, ?)",
                (sender, receiver))
    con.commit()
    con.close()


def exchange_delete(sender: int, receiver: int) -> None:
    con = _connect()
    con.execute("DELETE FROM exchanges WHERE sender_id = ? AND receiver_id = ?",
                (sender, receiver))
    con.commit()
    con.close()