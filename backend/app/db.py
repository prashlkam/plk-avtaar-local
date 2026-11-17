"""Tiny SQLite persistence layer for chats, messages and settings."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    model TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    model TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # -- chats -------------------------------------------------------------
    def list_chats(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM chats ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_chat(self, chat_id: str) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if not row:
                return None
            msgs = c.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at, rowid", (chat_id,)
            ).fetchall()
        return {**dict(row), "messages": [dict(m) for m in msgs]}

    def create_chat(self, title: str = "New chat", model: str | None = None) -> dict:
        now = time.time()
        chat = {"id": uuid.uuid4().hex, "title": title, "model": model, "created_at": now, "updated_at": now}
        with self.conn() as c:
            c.execute(
                "INSERT INTO chats (id, title, model, created_at, updated_at) VALUES (:id, :title, :model, :created_at, :updated_at)",
                chat,
            )
        return chat

    def update_chat(self, chat_id: str, **fields) -> None:
        allowed = {k: v for k, v in fields.items() if k in {"title", "model"} and v is not None}
        if not allowed:
            return
        allowed["updated_at"] = time.time()
        sets = ", ".join(f"{k} = :{k}" for k in allowed)
        with self.conn() as c:
            c.execute(f"UPDATE chats SET {sets} WHERE id = :id", {**allowed, "id": chat_id})

    def delete_chat(self, chat_id: str) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0

    # -- messages ----------------------------------------------------------
    def add_message(self, chat_id: str, role: str, content: str, model: str | None = None) -> dict:
        now = time.time()
        msg = {
            "id": uuid.uuid4().hex,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "model": model,
            "created_at": now,
        }
        with self.conn() as c:
            c.execute(
                "INSERT INTO messages (id, chat_id, role, content, model, created_at) "
                "VALUES (:id, :chat_id, :role, :content, :model, :created_at)",
                msg,
            )
            c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        return msg

    def delete_messages_from(self, chat_id: str, message_id: str) -> None:
        """Delete a message and everything after it (used for regenerate / edit)."""
        with self.conn() as c:
            row = c.execute(
                "SELECT created_at, rowid FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)
            ).fetchone()
            if not row:
                return
            c.execute(
                "DELETE FROM messages WHERE chat_id = ? AND (created_at > ? OR (created_at = ? AND rowid >= ?))",
                (chat_id, row["created_at"], row["created_at"], row["rowid"]),
            )

    # -- settings ----------------------------------------------------------
    def get_settings(self) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set_settings(self, values: dict[str, str]) -> None:
        with self.conn() as c:
            c.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(values.items()),
            )
