"""
turso_db.py — Turso(libsql) 데이터베이스 설정

환경변수:
  TURSO_DATABASE_URL: libsql://your-db.turso.io
  TURSO_AUTH_TOKEN:   eyJ...
"""
from __future__ import annotations

import json
import os
from typing import Generator

import libsql

# ── 연결 설정 ─────────────────────────────────────────────────────────────────
TURSO_URL   = os.getenv("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

if not TURSO_URL:
    print("[DB] WARNING: TURSO_DATABASE_URL 환경변수가 설정되지 않았습니다.")
if not TURSO_TOKEN:
    print("[DB] WARNING: TURSO_AUTH_TOKEN 환경변수가 설정되지 않았습니다.")

def _get_connection():
    """요청마다 새 커넥션 생성 (Thread-Safety 보장)."""
    conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db() -> Generator:
    """FastAPI Depends용 DB 커넥션 (동기, threadpool에서 실행됨)."""
    conn = _get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── 테이블 초기화 ──────────────────────────────────────────────────────────────

def init_db() -> None:
    """앱 시작 시 테이블 생성."""
    conn = _get_connection()
    statements = [
        "PRAGMA foreign_keys = ON",
        """CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id  TEXT UNIQUE NOT NULL,
            email      TEXT NOT NULL,
            name       TEXT DEFAULT '',
            picture    TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS wishlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id TEXT NOT NULL,
            added_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, product_id)
        )""",
        """CREATE TABLE IF NOT EXISTS inventory_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id    TEXT NOT NULL,
            name          TEXT DEFAULT '',
            brand         TEXT DEFAULT '',
            category      TEXT DEFAULT '',
            sub_category  TEXT DEFAULT '',
            style         TEXT DEFAULT '',
            colors        TEXT DEFAULT '[]',
            tags          TEXT DEFAULT '[]',
            image_url     TEXT DEFAULT '',
            price_krw     INTEGER DEFAULT 0,
            source_url    TEXT DEFAULT '',
            obtained_from TEXT DEFAULT 'game',
            obtained_at   TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS game_sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            game_type    TEXT DEFAULT 'fashion_curator',
            started_at   TEXT DEFAULT (datetime('now')),
            ended_at     TEXT NULL,
            is_completed INTEGER DEFAULT 0,
            score        INTEGER DEFAULT 0,
            items_count  INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS game_results (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id          INTEGER NULL REFERENCES game_sessions(id) ON DELETE SET NULL,
            selected_styles     TEXT DEFAULT '[]',
            selected_colors     TEXT DEFAULT '[]',
            selected_categories TEXT DEFAULT '[]',
            selected_keywords   TEXT DEFAULT '[]',
            acquired_item_ids   TEXT DEFAULT '[]',
            style_profile       TEXT DEFAULT '',
            saved_at            TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS products (
            id            TEXT PRIMARY KEY,
            mall          TEXT DEFAULT '',
            brand         TEXT DEFAULT '',
            name          TEXT NOT NULL,
            price_krw     INTEGER DEFAULT 0,
            price_jpy     INTEGER DEFAULT 0,
            main_image    TEXT DEFAULT '',
            detail_images TEXT DEFAULT '[]',
            material      TEXT DEFAULT '',
            care          TEXT DEFAULT '',
            source_url    TEXT DEFAULT '',
            category      TEXT DEFAULT '',
            sub_category  TEXT DEFAULT '',
            colors        TEXT DEFAULT '[]',
            style         TEXT DEFAULT '',
            keyword       TEXT DEFAULT '',
            tags          TEXT DEFAULT '[]',
            is_fashion    INTEGER DEFAULT 1,
            is_clothing   INTEGER DEFAULT 1,
            created_at    TEXT DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)",
        "CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand)",
        "CREATE INDEX IF NOT EXISTS idx_products_price ON products(price_krw)",
    ]
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()
        print("[DB] 테이블 초기화 완료")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────

def row_to_dict(cursor, row) -> dict:
    """커서 description을 이용해 row를 dict로 변환."""
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))

def _safe_json(value, default=None):
    """None 또는 잘못된 JSON 문자열에 대한 방어 파싱."""
    if value is None:
        return default if default is not None else []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


# ── 모델 클래스 ───────────────────────────────────────────────────────────────

class User:
    def __init__(self, row: dict):
        self.id        = row["id"]
        self.google_id = row["google_id"]
        self.email     = row["email"]
        self.name      = row.get("name", "")
        self.picture   = row.get("picture", "")

    @staticmethod
    def get_by_google_id(conn, google_id: str):
        cur = conn.execute(
            "SELECT * FROM users WHERE google_id = ?", (google_id,)
        )
        row = cur.fetchone()
        return User(row_to_dict(cur, row)) if row else None

    @staticmethod
    def get_by_id(conn, user_id: int):
        cur = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        row = cur.fetchone()
        return User(row_to_dict(cur, row)) if row else None

    @staticmethod
    def create(conn, google_id: str, email: str,
               name: str = "", picture: str = "") -> "User":
        cur = conn.execute(
            "INSERT INTO users (google_id, email, name, picture) "
            "VALUES (?, ?, ?, ?) RETURNING *",
            (google_id, email, name, picture),
        )
        row = cur.fetchone()
        conn.commit()
        return User(row_to_dict(cur, row))


class InventoryItem:
    def __init__(self, row: dict):
        self.id            = row["id"]
        self.user_id       = row["user_id"]
        self.product_id    = row["product_id"]
        self.name          = row.get("name", "")
        self.brand         = row.get("brand", "")
        self.category      = row.get("category", "")
        self.sub_category  = row.get("sub_category", "")
        self.style         = row.get("style", "")
        self.colors        = _safe_json(row.get("colors"))
        self.tags          = _safe_json(row.get("tags"))
        self.image_url     = row.get("image_url", "")
        self.price_krw     = row.get("price_krw", 0)
        self.source_url    = row.get("source_url", "")
        self.obtained_from = row.get("obtained_from", "game")
        self.obtained_at   = row.get("obtained_at", "")

    @staticmethod
    def get_by_user(conn, user_id: int, limit: int = 50) -> list:
        cur = conn.execute(
            "SELECT * FROM inventory_items "
            "WHERE user_id = ? ORDER BY obtained_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cur.fetchall()
        return [InventoryItem(row_to_dict(cur, r)) for r in rows]

    @staticmethod
    def exists(conn, user_id: int, product_id: str) -> bool:
        cur = conn.execute(
            "SELECT id FROM inventory_items "
            "WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        return cur.fetchone() is not None

    @staticmethod
    def create(conn, user_id: int, data: dict) -> "InventoryItem":
        cur = conn.execute(
            """INSERT INTO inventory_items
               (user_id, product_id, name, brand, category, sub_category,
                style, colors, tags, image_url, price_krw, source_url,
                obtained_from)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *""",
            (
                user_id,
                data.get("product_id", ""),
                data.get("name", ""),
                data.get("brand", ""),
                data.get("category", ""),
                data.get("sub_category", ""),
                data.get("style", ""),
                json.dumps(data.get("colors", []), ensure_ascii=False),
                json.dumps(data.get("tags", []), ensure_ascii=False),
                data.get("image_url", ""),
                data.get("price_krw", 0),
                data.get("source_url", ""),
                data.get("obtained_from", "game"),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return InventoryItem(row_to_dict(cur, row))


class GameSession:
    def __init__(self, row: dict):
        self.id           = row["id"]
        self.user_id      = row["user_id"]
        self.game_type    = row.get("game_type", "fashion_curator")
        self.started_at   = row.get("started_at", "")
        self.ended_at     = row.get("ended_at")
        self.is_completed = bool(row.get("is_completed", 0))
        self.score        = row.get("score", 0)
        self.items_count  = row.get("items_count", 0)

    @staticmethod
    def create(conn, user_id: int,
               game_type: str = "fashion_curator") -> "GameSession":
        cur = conn.execute(
            "INSERT INTO game_sessions (user_id, game_type) "
            "VALUES (?, ?) RETURNING *",
            (user_id, game_type),
        )
        row = cur.fetchone()
        conn.commit()
        return GameSession(row_to_dict(cur, row))


class GameResult:
    def __init__(self, row: dict):
        self.id                  = row["id"]
        self.user_id             = row["user_id"]
        self.session_id          = row.get("session_id")
        self.selected_styles     = _safe_json(row.get("selected_styles"))
        self.selected_colors     = _safe_json(row.get("selected_colors"))
        self.selected_categories = _safe_json(row.get("selected_categories"))
        self.selected_keywords   = _safe_json(row.get("selected_keywords"))
        self.acquired_item_ids   = _safe_json(row.get("acquired_item_ids"))
        self.style_profile       = row.get("style_profile", "")
        self.saved_at            = row.get("saved_at", "")

    @staticmethod
    def get_by_user(conn, user_id: int, limit: int = 10) -> list:
        cur = conn.execute(
            "SELECT * FROM game_results "
            "WHERE user_id = ? ORDER BY saved_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cur.fetchall()
        return [GameResult(row_to_dict(cur, r)) for r in rows]

    @staticmethod
    def create(conn, user_id: int, session_id: int, data: dict) -> "GameResult":
        cur = conn.execute(
            """INSERT INTO game_results
               (user_id, session_id, selected_styles, selected_colors,
                selected_categories, selected_keywords, acquired_item_ids,
                style_profile)
               VALUES (?,?,?,?,?,?,?,?) RETURNING *""",
            (
                user_id,
                session_id,
                json.dumps(data.get("selected_styles", []), ensure_ascii=False),
                json.dumps(data.get("selected_colors", []), ensure_ascii=False),
                json.dumps(data.get("selected_categories", []), ensure_ascii=False),
                json.dumps(data.get("selected_keywords", []), ensure_ascii=False),
                json.dumps(data.get("acquired_item_ids", []), ensure_ascii=False),
                data.get("style_profile", ""),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return GameResult(row_to_dict(cur, row))


class Wishlist:
    def __init__(self, row: dict):
        self.id         = row["id"]
        self.user_id    = row["user_id"]
        self.product_id = row["product_id"]
        self.added_at   = row.get("added_at", "")

    @staticmethod
    def get_by_user(conn, user_id: int) -> list:
        cur = conn.execute(
            "SELECT * FROM wishlists WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        )
        rows = cur.fetchall()
        return [Wishlist(row_to_dict(cur, r)) for r in rows]

    @staticmethod
    def exists(conn, user_id: int, product_id: str) -> bool:
        cur = conn.execute(
            "SELECT id FROM wishlists WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        return cur.fetchone() is not None

    @staticmethod
    def create(conn, user_id: int, product_id: str) -> "Wishlist":
        cur = conn.execute(
            "INSERT INTO wishlists (user_id, product_id) VALUES (?, ?) RETURNING *",
            (user_id, product_id),
        )
        row = cur.fetchone()
        conn.commit()
        return Wishlist(row_to_dict(cur, row))

    @staticmethod
    def delete(conn, user_id: int, product_id: str) -> bool:
        conn.execute(
            "DELETE FROM wishlists WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        conn.commit()
        return True
