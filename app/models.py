"""Database models for SnowDrive."""

import os
import sqlite3
import threading
from contextlib import contextmanager

from app.config import Config

_local = threading.local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
        _local.conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def db_transaction():
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            avatar_path TEXT DEFAULT NULL,
            totp_required_reset INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_2fa_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            method_type TEXT NOT NULL,
            method_name TEXT NOT NULL DEFAULT '',
            is_enabled INTEGER DEFAULT 1,
            totp_secret TEXT,
            credential_id TEXT,
            credential_public_key BLOB,
            sign_count INTEGER DEFAULT 0,
            rp_id TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS download_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            filename TEXT DEFAULT '',
            dest_path TEXT NOT NULL,
            total_size INTEGER DEFAULT 0,
            downloaded INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            error_message TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_2fa_user ON user_2fa_methods(user_id);
        CREATE INDEX IF NOT EXISTS idx_download_user ON download_tasks(user_id);
    """)
    db.commit()
    migrate_old_2fa(db)


def migrate_old_2fa(db):
    try:
        cols = db.execute("PRAGMA table_info(users)").fetchall()
        col_names = [c["name"] for c in cols]
        if "totp_secret" in col_names and "totp_enabled" in col_names:
            users_with_totp = db.execute(
                "SELECT id, totp_secret FROM users WHERE totp_enabled = 1 AND totp_secret IS NOT NULL"
            ).fetchall()
            for u in users_with_totp:
                existing = db.execute(
                    "SELECT id FROM user_2fa_methods WHERE user_id = ? AND method_type = 'totp'",
                    (u["id"],),
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT INTO user_2fa_methods (user_id, method_type, method_name, totp_secret) VALUES (?, 'totp', 'Authenticator', ?)",
                        (u["id"], u["totp_secret"]),
                    )
            db.commit()
    except Exception:
        pass


# ─── User CRUD ────────────────────────────────────────────────────

def get_user_count() -> int:
    db = get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
    return row["cnt"]

def get_user_by_id(user_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None

def get_user_by_username(username: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None

def create_user(username: str, password_hash: str) -> int:
    db = get_db()
    cursor = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
    db.commit()
    return cursor.lastrowid

def update_user_password(user_id: int, password_hash: str):
    db = get_db()
    db.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (password_hash, user_id))
    db.commit()

def update_user_avatar(user_id: int, avatar_path: str | None):
    db = get_db()
    db.execute("UPDATE users SET avatar_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (avatar_path, user_id))
    db.commit()

def require_totp_reset(user_id: int):
    db = get_db()
    db.execute("UPDATE users SET totp_required_reset = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    db.execute("DELETE FROM user_2fa_methods WHERE user_id = ?", (user_id,))
    db.commit()

def clear_totp_reset(user_id: int):
    db = get_db()
    db.execute("UPDATE users SET totp_required_reset = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    db.commit()

# ─── Sessions ─────────────────────────────────────────────────────

def create_session(user_id: int, token_hash: str, expires_at: str) -> int:
    db = get_db()
    cursor = db.execute("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)", (user_id, token_hash, expires_at))
    db.commit()
    return cursor.lastrowid

def get_session(token_hash: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE token_hash = ? AND expires_at > datetime('now')", (token_hash,)).fetchone()
    return dict(row) if row else None

def delete_session(token_hash: str):
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    db.commit()

def delete_user_sessions(user_id: int):
    db = get_db()
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.commit()

def cleanup_expired_sessions():
    db = get_db()
    db.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
    db.commit()

# ─── 2FA Methods ──────────────────────────────────────────────────

def get_user_2fa_methods(user_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM user_2fa_methods WHERE user_id = ? AND is_enabled = 1 ORDER BY created_at", (user_id,)).fetchall()
    return [dict(r) for r in rows]

def get_2fa_method(method_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM user_2fa_methods WHERE id = ?", (method_id,)).fetchone()
    return dict(row) if row else None

def count_2fa_methods(user_id: int) -> int:
    db = get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM user_2fa_methods WHERE user_id = ? AND is_enabled = 1", (user_id,)).fetchone()
    return row["cnt"]

def add_totp_method(user_id: int, secret: str, name: str = "Authenticator") -> int:
    db = get_db()
    cursor = db.execute("INSERT INTO user_2fa_methods (user_id, method_type, method_name, totp_secret) VALUES (?, 'totp', ?, ?)", (user_id, name, secret))
    db.commit()
    return cursor.lastrowid

def add_webauthn_method(user_id: int, credential_id: str, public_key: bytes, sign_count: int, rp_id: str, name: str = "Passkey") -> int:
    db = get_db()
    cursor = db.execute("INSERT INTO user_2fa_methods (user_id, method_type, method_name, credential_id, credential_public_key, sign_count, rp_id) VALUES (?, 'webauthn', ?, ?, ?, ?, ?)", (user_id, name, credential_id, public_key, sign_count, rp_id))
    db.commit()
    return cursor.lastrowid

def get_webauthn_credential(credential_id: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM user_2fa_methods WHERE credential_id = ? AND method_type = 'webauthn' AND is_enabled = 1", (credential_id,)).fetchone()
    return dict(row) if row else None

def update_webauthn_sign_count(method_id: int, sign_count: int):
    db = get_db()
    db.execute("UPDATE user_2fa_methods SET sign_count = ?, last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (sign_count, method_id))
    db.commit()

def update_2fa_last_used(method_id: int):
    db = get_db()
    db.execute("UPDATE user_2fa_methods SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (method_id,))
    db.commit()

def delete_2fa_method(method_id: int):
    db = get_db()
    db.execute("DELETE FROM user_2fa_methods WHERE id = ?", (method_id,))
    db.commit()

def rename_2fa_method(method_id: int, name: str):
    db = get_db()
    db.execute("UPDATE user_2fa_methods SET method_name = ? WHERE id = ?", (name, method_id))
    db.commit()

# ─── Site Settings ────────────────────────────────────────────────

def get_site_setting(key: str) -> str | None:
    db = get_db()
    row = db.execute("SELECT value FROM site_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None

def set_site_setting(key: str, value: str):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO site_settings (key, value) VALUES (?, ?)", (key, value))
    db.commit()

def delete_site_setting(key: str):
    db = get_db()
    db.execute("DELETE FROM site_settings WHERE key = ?", (key,))
    db.commit()

# ─── Download Tasks ───────────────────────────────────────────────

def create_download_task(user_id: int, url: str, dest_path: str, filename: str = "") -> int:
    db = get_db()
    cursor = db.execute("INSERT INTO download_tasks (user_id, url, filename, dest_path, status) VALUES (?, ?, ?, ?, 'pending')", (user_id, url, filename, dest_path))
    db.commit()
    return cursor.lastrowid

def get_download_tasks(user_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM download_tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()
    return [dict(r) for r in rows]

def get_download_task(task_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM download_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None

def update_download_progress(task_id: int, downloaded: int, total_size: int = 0, status: str = "downloading"):
    db = get_db()
    if total_size > 0:
        db.execute("UPDATE download_tasks SET downloaded = ?, total_size = ?, status = ? WHERE id = ?", (downloaded, total_size, status, task_id))
    else:
        db.execute("UPDATE download_tasks SET downloaded = ?, status = ? WHERE id = ?", (downloaded, status, task_id))
    db.commit()

def complete_download(task_id: int, success: bool, error_msg: str = ""):
    db = get_db()
    status = "completed" if success else "failed"
    db.execute("UPDATE download_tasks SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?", (status, error_msg, task_id))
    db.commit()

def delete_download_task(task_id: int):
    db = get_db()
    db.execute("DELETE FROM download_tasks WHERE id = ?", (task_id,))
    db.commit()
