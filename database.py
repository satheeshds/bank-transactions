from __future__ import annotations

from datetime import datetime, date as datetime_date
import os
from pathlib import Path
import sqlite3
from typing import Any

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "mail2firefly.db"


def get_db_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite database, enabling row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initializes the SQLite database and creates all required tables."""
    # Ensure the data directory exists
    DB_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Transactions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                transaction_date TEXT,
                merchant TEXT,
                amount REAL,
                currency TEXT,
                status TEXT NOT NULL, -- 'synced', 'pending', 'error'
                error_message TEXT,
                source_name TEXT,
                email_subject TEXT,
                reference_no TEXT
            )
        """)

        # 2. Sync Runs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT NOT NULL, -- 'running', 'success', 'failed'
                unprocessed_emails INTEGER DEFAULT 0,
                parsed_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        """)

        # 3. Sync Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES sync_runs(id) ON DELETE CASCADE
            )
        """)

        conn.commit()


def log_transaction(
    transaction_date: str | None,
    merchant: str | None,
    amount: float | None,
    currency: str | None,
    status: str,
    error_message: str | None = None,
    source_name: str | None = None,
    email_subject: str | None = None,
    reference_no: str | None = None,
) -> int:
    """Logs a parsed transaction attempt to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transactions (
                timestamp, transaction_date, merchant, amount, currency, status, error_message, source_name, email_subject, reference_no
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                transaction_date,
                merchant,
                amount,
                currency,
                status,
                error_message,
                source_name,
                email_subject,
                reference_no,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0


def start_sync_run(unprocessed_emails: int = 0) -> int:
    """Records the start of a synchronization run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sync_runs (start_time, status, unprocessed_emails)
            VALUES (?, 'running', ?)
            """,
            (datetime.now().isoformat(), unprocessed_emails),
        )
        conn.commit()
        return cursor.lastrowid or 0


def end_sync_run(run_id: int, status: str, parsed_count: int = 0, error_count: int = 0) -> None:
    """Records the completion and results of a synchronization run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sync_runs
            SET end_time = ?, status = ?, parsed_count = ?, error_count = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(), status, parsed_count, error_count, run_id),
        )
        conn.commit()


def log_sync_message(run_id: int | None, level: str, message: str) -> None:
    """Logs a detailed execution message associated with a sync run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sync_logs (run_id, timestamp, level, message)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, datetime.now().isoformat(), level.upper(), message),
        )
        conn.commit()


def get_recent_transactions(limit: int = 50) -> list[dict[str, Any]]:
    """Retrieves recent logged transactions."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM transactions ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_recent_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Retrieves recent execution logs."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sync_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        # Return logs in chronological order
        rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


def get_latest_sync_run() -> dict[str, Any] | None:
    """Gets the metadata of the latest sync run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_stats_today() -> dict[str, Any]:
    """Computes daily metrics for the dashboard."""
    today_str = datetime_date.today().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Parsed today (status is 'synced' or 'pending')
        cursor.execute(
            """
            SELECT COUNT(*) FROM transactions 
            WHERE DATE(timestamp) = DATE(?) AND status IN ('synced', 'pending')
            """,
            (today_str,),
        )
        parsed_today = cursor.fetchone()[0]

        # Errors today
        cursor.execute(
            """
            SELECT COUNT(*) FROM transactions 
            WHERE DATE(timestamp) = DATE(?) AND status = 'error'
            """,
            (today_str,),
        )
        errors_today = cursor.fetchone()[0]

        # Total runs today
        cursor.execute(
            """
            SELECT COUNT(*) FROM sync_runs 
            WHERE DATE(start_time) = DATE(?)
            """,
            (today_str,),
        )
        total_runs_today = cursor.fetchone()[0]

        latest_run = get_latest_sync_run()

        return {
            "parsed_today": parsed_today,
            "errors_today": errors_today,
            "total_runs_today": total_runs_today,
            "latest_run": latest_run,
        }
