"""SQLite store — dedupe + telegram message-id map (survives restarts)."""
from __future__ import annotations

import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path: str = "data/state.db"):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS seen(order_no TEXT, status TEXT, qty TEXT, PRIMARY KEY(order_no, status, qty))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS msgmap(group_key TEXT PRIMARY KEY, message_id TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS positions(group_key TEXT PRIMARY KEY, json TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT)"
        )
        self.db.commit()

    def is_duplicate(self, order_no: str, status: str, qty: str) -> bool:
        try:
            self.db.execute("INSERT INTO seen VALUES(?,?,?)", (order_no, status, qty))
            self.db.commit()
            return False
        except sqlite3.IntegrityError:
            return True

    def save_msg(self, group_key: str, message_id) -> None:
        self.db.execute("INSERT OR REPLACE INTO msgmap VALUES(?,?)", (group_key, str(message_id)))
        self.db.commit()

    def save_pos(self, group_key: str, pos_json: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO positions VALUES(?,?)", (group_key, pos_json))
        self.db.commit()

    def load_positions(self) -> dict:
        return {k: j for k, j in self.db.execute("SELECT group_key, json FROM positions").fetchall()}

    def clear_pos(self, group_key: str) -> None:
        self.db.execute("DELETE FROM positions WHERE group_key=?", (group_key,))
        self.db.commit()

    def get_scalar(self, key: str):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_scalar(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, value))
        self.db.commit()

    def get_msg(self, group_key: str):
        row = self.db.execute("SELECT message_id FROM msgmap WHERE group_key=?", (group_key,)).fetchone()
        if not row:
            return None
        try:
            return int(row[0])
        except ValueError:
            return row[0]
