"""SQLite boundary for DataPilot's read-only analytics tool."""

import csv
import re
import sqlite3
from pathlib import Path
from typing import Any


class QueryRejected(ValueError):
    """Raised when a query violates the read-only tool contract."""


class SQLiteAnalyticsRepository:
    """Initialise demo data and execute validated read-only SQL."""

    _BLOCKED = re.compile(
        r"\b(insert|update|delete|drop|alter|attach|detach|pragma|vacuum|replace|create)\b",
        re.IGNORECASE,
    )

    def __init__(self, db_path: Path, csv_path: Path) -> None:
        self.db_path = db_path
        self.csv_path = csv_path

    def initialize(self) -> None:
        """Create the local database once and load the tracked demo dataset."""

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    order_date TEXT NOT NULL,
                    region TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            if count == 0:
                with self.csv_path.open(encoding="utf-8-sig", newline="") as source:
                    records = [
                        (
                            row["order_id"],
                            row["order_date"],
                            row["region"],
                            row["category"],
                            float(row["amount"]),
                            row["status"],
                        )
                        for row in csv.DictReader(source)
                    ]
                connection.executemany(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                    records,
                )

    def schema_summary(self) -> str:
        """Return the schema surfaced to the planning step."""

        return (
            "orders(order_id TEXT, order_date YYYY-MM-DD, region TEXT, "
            "category TEXT, amount REAL, status TEXT)"
        )

    def execute(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        """Execute one SELECT statement after enforcing a strict allow-list."""

        normalized = " ".join(sql.strip().split())
        if not normalized.lower().startswith("select "):
            raise QueryRejected("Only SELECT statements are allowed.")
        if ";" in normalized or self._BLOCKED.search(normalized):
            raise QueryRejected("The query contains a forbidden statement or token.")
        if " from orders" not in normalized.lower():
            raise QueryRejected("Queries may only read the demo orders table.")

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(normalized)
            rows = [dict(row) for row in cursor.fetchall()]
            columns = [description[0] for description in cursor.description or []]
        return columns, rows

    def scalar(self, sql: str) -> float:
        """Return a numeric scalar through the same validated query boundary."""

        _, rows = self.execute(sql)
        if not rows:
            return 0.0
        return float(next(iter(rows[0].values())))
