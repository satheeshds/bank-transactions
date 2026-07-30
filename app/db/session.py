from __future__ import annotations

from datetime import datetime, date as datetime_date
import os
from pathlib import Path
from typing import Any

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DB_DIR / "mail2firefly.db"


def _using_mysql() -> bool:
    return True


def get_db_connection():
    """Return a DB connection. Uses SQLite by default or MariaDB when configured.

    For MariaDB we use `pymysql` with `DictCursor` so rows are accessible by column name.
    """
    if _using_mysql():
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except Exception as e:
            raise RuntimeError("pymysql is required for MySQL/MariaDB connections") from e

        raw_conn = pymysql.connect(
            host=os.environ.get("DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("DB_PORT", 3306)),
            user=os.environ.get("WEB_DB_USER", ""),
            password=os.environ.get("WEB_DB_PASSWORD", ""),
            database=os.environ.get("WEB_DB_NAME", ""),
            cursorclass=DictCursor,
            autocommit=False,
        )

        # Provide a thin wrapper that adapts qmark-style '?' to MySQL '%s' and
        # exposes a context-manager-compatible connection interface.
        class _WrappedCursor:
            def __init__(self, cur):
                self._cur = cur

            def execute(self, q, params=None):
                if params is None:
                    return self._cur.execute(q.replace('?', '%s'))
                return self._cur.execute(q.replace('?', '%s'), params)

            def executemany(self, q, seq):
                return self._cur.executemany(q.replace('?', '%s'), seq)

            def fetchone(self):
                return self._cur.fetchone()

            def fetchall(self):
                return self._cur.fetchall()

            def __getattr__(self, name):
                return getattr(self._cur, name)

        class _ConnWrapper:
            def __init__(self, raw):
                self._raw = raw

            def cursor(self):
                return _WrappedCursor(self._raw.cursor())

            def commit(self):
                return self._raw.commit()

            def close(self):
                return self._raw.close()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                try:
                    if exc_type is None:
                        self._raw.commit()
                    else:
                        self._raw.rollback()
                finally:
                    self._raw.close()

        return _ConnWrapper(raw_conn)

    # Only MySQL/MariaDB supported in this application.


def init_db() -> None:
    """Initialize MySQL/MariaDB tables required by the application."""

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Create tables using MySQL-compatible types
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INT PRIMARY KEY AUTO_INCREMENT,
                timestamp TEXT NOT NULL,
                transaction_date TEXT,
                merchant TEXT,
                amount DOUBLE,
                currency TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                rule_name TEXT,
                rule_id INT,
                source_name TEXT,
                email_subject TEXT,
                reference_no TEXT,
                raw_email LONGTEXT,
                firefly_payload LONGTEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INT PRIMARY KEY AUTO_INCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT NOT NULL,
                unprocessed_emails INT DEFAULT 0,
                parsed_count INT DEFAULT 0,
                error_count INT DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_logs (
                id INT PRIMARY KEY AUTO_INCREMENT,
                run_id INT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mailboxes (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name TEXT NOT NULL UNIQUE,
                host TEXT,
                port INT,
                username TEXT,
                password TEXT,
                encryption TEXT,
                smtp_host TEXT,
                smtp_port INT,
                processed_tag TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                `key` VARCHAR(255) PRIMARY KEY,
                value TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parsing_rules (
                id INT PRIMARY KEY AUTO_INCREMENT,
                source_name TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                regex TEXT NOT NULL,
                description TEXT,
                transaction_type TEXT NOT NULL DEFAULT 'withdrawal',
                card_last4 TEXT,
                conditions_json TEXT,
                mappings_json TEXT,
                condition_mode TEXT
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
    rule_name: str | None = None,
    rule_id: int | None = None,
    raw_email: str | None = None,
    firefly_payload: str | None = None,
) -> int:
    """Logs a parsed transaction attempt to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # adapt paramstyle for mysql (pymysql uses %s while sqlite uses ?)
        def _exec(q, params=None):
            if _using_mysql():
                q = q.replace('?', '%s')
            if params is None:
                return cursor.execute(q)
            return cursor.execute(q, params)

        _exec(
            """
            INSERT INTO transactions (
                timestamp, transaction_date, merchant, amount, currency, status, error_message, rule_name, rule_id, source_name, email_subject, reference_no, raw_email, firefly_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                transaction_date,
                merchant,
                amount,
                currency,
                status,
                error_message,
                rule_name,
                rule_id,
                source_name,
                email_subject,
                reference_no,
                raw_email,
                firefly_payload,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0


def start_sync_run(unprocessed_emails: int = 0) -> int:
    """Records the start of a synchronization run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if _using_mysql():
            cursor.execute("INSERT INTO sync_runs (start_time, status, unprocessed_emails) VALUES (%s, 'running', %s)", (datetime.now().isoformat(), unprocessed_emails))
        else:
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
        if _using_mysql():
            cursor.execute(
                "UPDATE sync_runs SET end_time = %s, status = %s, parsed_count = %s, error_count = %s WHERE id = %s",
                (datetime.now().isoformat(), status, parsed_count, error_count, run_id),
            )
        else:
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
        if _using_mysql():
            cursor.execute(
                "INSERT INTO sync_logs (run_id, timestamp, level, message) VALUES (%s, %s, %s, %s)",
                (run_id, datetime.now().isoformat(), level.upper(), message),
            )
        else:
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
        if _using_mysql():
            cursor.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT %s", (limit,))
        else:
            cursor.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_transaction_by_id(tx_id: int) -> dict[str, Any] | None:
    """Retrieve a single transaction row by id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if _using_mysql():
            cursor.execute("SELECT * FROM transactions WHERE id = %s", (tx_id,))
        else:
            cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_parsing_rules() -> list[dict[str, Any]]:
    """Return parsing rules stored in the DB."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, source_name, rule_name, regex, description, transaction_type, card_last4, conditions_json, mappings_json, condition_mode FROM parsing_rules ORDER BY id")
        rows = cursor.fetchall()
        rules = []
        for row in rows:
            # row is a mapping in both sqlite row objects and pymysql DictCursor
            rules.append(
                {
                    "id": row["id"],
                    "source_name": row["source_name"],
                    "rule_name": row["rule_name"],
                    "regex": row["regex"],
                    "description": row["description"],
                    "transaction_type": row["transaction_type"],
                    "card_last4": row["card_last4"],
                    "conditions": __import__('json').loads(row["conditions_json"]) if row.get("conditions_json") else None,
                    "mappings": __import__('json').loads(row["mappings_json"]) if row.get("mappings_json") else None,
                    "condition_mode": row.get("condition_mode"),
                }
            )
        return rules


def get_setting(key: str) -> str | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE `key` = %s", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str | None) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if value is None:
            cursor.execute("DELETE FROM settings WHERE `key` = %s", (key,))
        else:
            cursor.execute("REPLACE INTO settings (`key`, value) VALUES (%s, %s)", (key, value))
        conn.commit()


def get_recent_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Retrieves recent execution logs."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if _using_mysql():
            cursor.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT %s", (limit,))
        else:
            cursor.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT ?", (limit,))
        # Return logs in chronological order
        rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


def get_latest_sync_run() -> dict[str, Any] | None:
    """Gets the metadata of the latest sync run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Use LIMIT placeholder style appropriate for the backend
        if _using_mysql():
            cursor.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
        else:
            cursor.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None


def get_stats_today() -> dict[str, Any]:
    """Computes daily metrics for the dashboard."""
    today_str = datetime_date.today().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Parsed today (status is 'synced' or 'pending')
        if _using_mysql():
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM transactions WHERE DATE(timestamp) = DATE(%s) AND status IN ('synced', 'pending')",
                (today_str,),
            )
            parsed_today = cursor.fetchone()["cnt"]
        else:
            cursor.execute(
                """
                SELECT COUNT(*) FROM transactions 
                WHERE DATE(timestamp) = DATE(?) AND status IN ('synced', 'pending')
                """,
                (today_str,),
            )
            parsed_today = cursor.fetchone()[0]

        # Errors today
        if _using_mysql():
            cursor.execute("SELECT COUNT(*) AS cnt FROM transactions WHERE DATE(timestamp) = DATE(%s) AND status = 'error'", (today_str,))
            errors_today = cursor.fetchone()["cnt"]
        else:
            cursor.execute(
                """
                SELECT COUNT(*) FROM transactions 
                WHERE DATE(timestamp) = DATE(?) AND status = 'error'
                """,
                (today_str,),
            )
            errors_today = cursor.fetchone()[0]

        # Total runs today
        if _using_mysql():
            cursor.execute("SELECT COUNT(*) AS cnt FROM sync_runs WHERE DATE(start_time) = DATE(%s)", (today_str,))
            total_runs_today = cursor.fetchone()["cnt"]
        else:
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


def list_mailboxes() -> list[dict[str, Any]]:
    """Return stored mailboxes from the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, host, port, username, encryption, smtp_host, smtp_port, processed_tag FROM mailboxes ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]


def get_mailbox_by_id(mailbox_id: int) -> dict[str, Any] | None:
    """Return mailbox row including sensitive fields (password) for internal use."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, host, port, username, password, encryption, smtp_host, smtp_port, processed_tag FROM mailboxes WHERE id = ?",
            (mailbox_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def add_mailbox(
    name: str,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    encryption: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    processed_tag: str | None = None,
    firefly_account_id: str | None = None,
) -> int:
    """Insert a new mailbox definition and return its id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO mailboxes (
                name, host, port, username, password, encryption, smtp_host, smtp_port, processed_tag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, host, port, username, password, encryption, smtp_host, smtp_port, processed_tag),
        )
        conn.commit()
        return cursor.lastrowid or 0


def update_mailbox(
    mailbox_id: int,
    name: str | None = None,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    encryption: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
) -> None:
    """Update mailbox fields by id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Build dynamic update
        fields = []
        values = []
        if name is not None:
            fields.append('name = ?')
            values.append(name)
        if host is not None:
            fields.append('host = ?')
            values.append(host)
        if port is not None:
            fields.append('port = ?')
            values.append(port)
        if username is not None:
            fields.append('username = ?')
            values.append(username)
        if password is not None:
            fields.append('password = ?')
            values.append(password)
        if encryption is not None:
            fields.append('encryption = ?')
            values.append(encryption)
        if smtp_host is not None:
            fields.append('smtp_host = ?')
            values.append(smtp_host)
        if smtp_port is not None:
            fields.append('smtp_port = ?')
            values.append(smtp_port)

        if not fields:
            return

        sql = f"UPDATE mailboxes SET {', '.join(fields)} WHERE id = ?"
        values.append(mailbox_id)
        cursor.execute(sql, tuple(values))
        conn.commit()


def delete_mailbox(mailbox_id: int) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mailboxes WHERE id = ?", (mailbox_id,))
        conn.commit()
