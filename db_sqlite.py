"""SQLite backend for trips, people and expenses."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date

from errors import DuplicateError

DB_PATH = os.environ.get("SPLITWISE_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "splitwise.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    currency   TEXT NOT NULL DEFAULT '₹',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS people (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    name    TEXT NOT NULL COLLATE NOCASE,
    UNIQUE (trip_id, name)
);
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id     INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    payer_id    INTEGER NOT NULL REFERENCES people(id),
    split_mode  TEXT NOT NULL,
    spent_on    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS expense_shares (
    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES people(id),
    share      INTEGER NOT NULL,
    PRIMARY KEY (expense_id, person_id)
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DuplicateError(str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------- trips ----------

def list_trips() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT t.*, (SELECT COUNT(*) FROM expenses e WHERE e.trip_id = t.id) AS expense_count,
                      (SELECT COALESCE(SUM(amount), 0) FROM expenses e WHERE e.trip_id = t.id) AS total
               FROM trips t ORDER BY t.created_at DESC, t.id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def create_trip(name: str, currency: str) -> int:
    with connect() as conn:
        cur = conn.execute("INSERT INTO trips (name, currency) VALUES (?, ?)", (name, currency))
        return cur.lastrowid


def rename_trip(trip_id: int, name: str, currency: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE trips SET name = ?, currency = ? WHERE id = ?", (name, currency, trip_id))


def delete_trip(trip_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))


# ---------- people ----------

def list_people(trip_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM people WHERE trip_id = ? ORDER BY id", (trip_id,)).fetchall()
    return [dict(r) for r in rows]


def add_person(trip_id: int, name: str) -> int:
    with connect() as conn:
        cur = conn.execute("INSERT INTO people (trip_id, name) VALUES (?, ?)", (trip_id, name))
        return cur.lastrowid


def person_in_use(person_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            """SELECT 1 FROM expenses WHERE payer_id = ?
               UNION SELECT 1 FROM expense_shares WHERE person_id = ? LIMIT 1""",
            (person_id, person_id),
        ).fetchone()
    return row is not None


def delete_person(person_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))


# ---------- expenses ----------

def list_expenses(trip_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE trip_id = ? ORDER BY spent_on DESC, id DESC", (trip_id,)
        ).fetchall()
        expenses = [dict(r) for r in rows]
        shares = conn.execute(
            """SELECT s.* FROM expense_shares s JOIN expenses e ON e.id = s.expense_id
               WHERE e.trip_id = ?""",
            (trip_id,),
        ).fetchall()
    by_expense: dict[int, dict[int, int]] = {}
    for s in shares:
        by_expense.setdefault(s["expense_id"], {})[s["person_id"]] = s["share"]
    for e in expenses:
        e["shares"] = by_expense.get(e["id"], {})
    return expenses


def add_expense(
    trip_id: int,
    description: str,
    amount: int,
    payer_id: int,
    split_mode: str,
    shares: dict[int, int],
    spent_on: date,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO expenses (trip_id, description, amount, payer_id, split_mode, spent_on)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (trip_id, description, amount, payer_id, split_mode, spent_on.isoformat()),
        )
        expense_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO expense_shares (expense_id, person_id, share) VALUES (?, ?, ?)",
            [(expense_id, pid, share) for pid, share in shares.items() if share > 0],
        )
        return expense_id


def delete_expense(expense_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
