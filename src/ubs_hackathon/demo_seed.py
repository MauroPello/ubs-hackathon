from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


DDL = """
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS regions;

CREATE TABLE regions (
    region_id INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region_id INTEGER NOT NULL,
    FOREIGN KEY(region_id) REFERENCES regions(region_id)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    revenue REAL NOT NULL,
    quarter TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
);
"""


def seed_demo_db(path: str | Path) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL)
        conn.executemany(
            "INSERT INTO regions(region_id, region_name) VALUES (?, ?)",
            [(1, "EMEA"), (2, "AMER"), (3, "APAC")],
        )
        conn.executemany(
            "INSERT INTO customers(customer_id, customer_name, region_id) VALUES (?, ?, ?)",
            [
                (1, "Acme AG", 1),
                (2, "Blue Corp", 2),
                (3, "Zenith KK", 3),
                (4, "Nordic AB", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO orders(order_id, customer_id, order_date, revenue, quarter) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 1, "2026-01-15", 125000.0, "Q1"),
                (2, 2, "2026-02-02", 210500.0, "Q1"),
                (3, 3, "2026-02-14", 180300.0, "Q1"),
                (4, 4, "2026-03-01", 99000.0, "Q1"),
                (5, 1, "2026-04-01", 150000.0, "Q2"),
            ],
        )

    print(f"Seeded demo database at {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a demo SQLite business database")
    parser.add_argument("--db-path", default="data/demo_business.db")
    args = parser.parse_args()
    seed_demo_db(args.db_path)


if __name__ == "__main__":
    main()
