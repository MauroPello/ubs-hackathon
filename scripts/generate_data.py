import json
import random
import sqlite3
from pathlib import Path

TABLE_COUNT = 220
ROWS_PER_TABLE = 500

data_dir = Path("data")
config_dir = Path("config")
data_dir.mkdir(parents=True, exist_ok=True)
config_dir.mkdir(parents=True, exist_ok=True)

db_path = data_dir / "big_demo.db"
docs_path = config_dir / "big_schema_docs.json"
cfg_path = config_dir / "big_config.yaml"

regions = ["EMEA", "AMER", "APAC", "LATAM"]
products = ["FX", "Rates", "Equities", "Credit", "Commodities"]

docs = {"big_demo_sqlite": {"tables": {}}}

with sqlite3.connect(db_path) as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    cur.execute("DROP TABLE IF EXISTS dim_region")
    cur.execute("DROP TABLE IF EXISTS dim_product")
    cur.execute("CREATE TABLE dim_region (region_id INTEGER PRIMARY KEY, region_name TEXT NOT NULL)")
    cur.execute("CREATE TABLE dim_product (product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL)")
    cur.executemany(
        "INSERT INTO dim_region(region_id, region_name) VALUES (?, ?)",
        list(enumerate(regions, start=1)),
    )
    cur.executemany(
        "INSERT INTO dim_product(product_id, product_name) VALUES (?, ?)",
        list(enumerate(products, start=1)),
    )

    docs["big_demo_sqlite"]["tables"]["dim_region"] = {
        "description": "Reference table for reporting regions.",
        "columns": {
            "region_id": "Unique region identifier.",
            "region_name": "Region label used in reporting.",
        },
    }
    docs["big_demo_sqlite"]["tables"]["dim_product"] = {
        "description": "Reference table for product categories.",
        "columns": {
            "product_id": "Unique product identifier.",
            "product_name": "Product family label.",
        },
    }

    for i in range(1, TABLE_COUNT + 1):
        table = f"fact_business_{i:03d}"
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(
            f"""
            CREATE TABLE {table} (
                event_id INTEGER PRIMARY KEY,
                event_date TEXT NOT NULL,
                region_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                customer_segment TEXT NOT NULL,
                revenue REAL NOT NULL,
                trade_count INTEGER NOT NULL,
                FOREIGN KEY(region_id) REFERENCES dim_region(region_id),
                FOREIGN KEY(product_id) REFERENCES dim_product(product_id)
            )
            """
        )
        rows = []
        for event_id in range(1, ROWS_PER_TABLE + 1):
            month = (event_id % 12) + 1
            day = (event_id % 28) + 1
            rows.append(
                (
                    event_id,
                    f"2026-{month:02d}-{day:02d}",
                    random.randint(1, len(regions)),
                    random.randint(1, len(products)),
                    random.choice(["Institutional", "Corporate", "Retail"]),
                    round(random.uniform(5_000, 500_000), 2),
                    random.randint(1, 200),
                )
            )
        cur.executemany(
            f"""
            INSERT INTO {table}
            (event_id, event_date, region_id, product_id, customer_segment, revenue, trade_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        docs["big_demo_sqlite"]["tables"][table] = {
            "description": f"Synthetic business fact table {i:03d} for analytics retrieval testing.",
            "columns": {
                "event_id": "Primary key for each business event.",
                "event_date": "Event booking date in YYYY-MM-DD format.",
                "region_id": "Foreign key to dim_region.",
                "product_id": "Foreign key to dim_product.",
                "customer_segment": "Segment bucket (Institutional, Corporate, Retail).",
                "revenue": "Revenue amount in base currency.",
                "trade_count": "Number of trades aggregated in the event record.",
            },
        }

with docs_path.open("w", encoding="utf-8") as f:
    json.dump(docs, f, indent=2)

cfg_path.write_text(
    "\n".join(
        [
            "catalog:",
            "  db_path: data/big_catalog.db",
            "data_sources:",
            "  - name: big_demo_sqlite",
            "    type: sqlite",
            "    connection: data/big_demo.db",
            "schema_docs_path: config/big_schema_docs.json",
            "",
        ]
    ),
    encoding="utf-8",
)

print(f"Created database: {db_path}")
print(f"Created schema docs: {docs_path}")
print(f"Created config: {cfg_path}")
print(f"Total documented tables: {len(docs['big_demo_sqlite']['tables'])}")