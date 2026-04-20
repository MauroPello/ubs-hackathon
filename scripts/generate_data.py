from __future__ import annotations

import argparse
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DEFAULT_TABLE_COUNT = 260
DEFAULT_ROWS_PER_TABLE = 2000
DEFAULT_SEED = 42
DATA_SOURCE_NAME = "big_demo_sqlite"
MAX_SETTLEMENT_LAG_DAYS = 5


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a large, interconnected SQLite dataset plus schema docs."
    )
    parser.add_argument("--table-count", type=int, default=DEFAULT_TABLE_COUNT)
    parser.add_argument("--rows-per-table", type=int, default=DEFAULT_ROWS_PER_TABLE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--day-span", type=int, default=730)
    parser.add_argument("--db-path", default="data/big_demo.db")
    parser.add_argument("--docs-path", default="config/schema_docs.json")
    parser.add_argument("--config-path", default="config/config.yaml")
    parser.add_argument("--cypher-path", default="data/big_demo.cypher")
    return parser


def _drop_existing_tables(cur: sqlite3.Cursor) -> None:
    table_rows = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    names = [row[0] for row in table_rows]
    cur.execute("PRAGMA foreign_keys = OFF")
    for name in names:
        cur.execute(f'DROP TABLE IF EXISTS "{name}"')
    cur.execute("PRAGMA foreign_keys = ON")


def _create_dimension_tables(cur: sqlite3.Cursor) -> None:
    cur.executescript("""
        CREATE TABLE dim_region (
            region_id INTEGER PRIMARY KEY,
            region_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE dim_country (
            country_id INTEGER PRIMARY KEY,
            region_id INTEGER NOT NULL,
            iso_code TEXT NOT NULL UNIQUE,
            country_name TEXT NOT NULL,
            FOREIGN KEY(region_id) REFERENCES dim_region(region_id)
        );

        CREATE TABLE dim_desk (
            desk_id INTEGER PRIMARY KEY,
            country_id INTEGER NOT NULL,
            desk_name TEXT NOT NULL UNIQUE,
            desk_tier TEXT NOT NULL,
            FOREIGN KEY(country_id) REFERENCES dim_country(country_id)
        );

        CREATE TABLE dim_product_family (
            family_id INTEGER PRIMARY KEY,
            family_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE dim_product (
            product_id INTEGER PRIMARY KEY,
            family_id INTEGER NOT NULL,
            product_name TEXT NOT NULL UNIQUE,
            risk_class TEXT NOT NULL,
            liquidity_tier TEXT NOT NULL,
            FOREIGN KEY(family_id) REFERENCES dim_product_family(family_id)
        );

        CREATE TABLE dim_channel (
            channel_id INTEGER PRIMARY KEY,
            channel_name TEXT NOT NULL UNIQUE,
            automation_level TEXT NOT NULL
        );

        CREATE TABLE dim_customer (
            customer_id INTEGER PRIMARY KEY,
            country_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL UNIQUE,
            customer_segment TEXT NOT NULL,
            credit_bucket TEXT NOT NULL,
            inception_date TEXT NOT NULL,
            FOREIGN KEY(country_id) REFERENCES dim_country(country_id)
        );

        CREATE TABLE dim_counterparty (
            counterparty_id INTEGER PRIMARY KEY,
            country_id INTEGER NOT NULL,
            counterparty_name TEXT NOT NULL UNIQUE,
            counterparty_type TEXT NOT NULL,
            systemic_flag INTEGER NOT NULL,
            FOREIGN KEY(country_id) REFERENCES dim_country(country_id)
        );

        CREATE TABLE dim_trader (
            trader_id INTEGER PRIMARY KEY,
            desk_id INTEGER NOT NULL,
            trader_name TEXT NOT NULL UNIQUE,
            seniority TEXT NOT NULL,
            location TEXT NOT NULL,
            FOREIGN KEY(desk_id) REFERENCES dim_desk(desk_id)
        );

        CREATE TABLE dim_calendar (
            date_key INTEGER PRIMARY KEY,
            trade_date TEXT NOT NULL UNIQUE,
            year INTEGER NOT NULL,
            quarter TEXT NOT NULL,
            month INTEGER NOT NULL,
            month_name TEXT NOT NULL,
            week_of_year INTEGER NOT NULL,
            is_month_end INTEGER NOT NULL
        );

        CREATE TABLE bridge_customer_counterparty (
            bridge_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            counterparty_id INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            relationship_since TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES dim_customer(customer_id),
            FOREIGN KEY(counterparty_id) REFERENCES dim_counterparty(counterparty_id)
        );

        CREATE TABLE market_daily_signal (
            signal_id INTEGER PRIMARY KEY,
            date_key INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,
            volatility_index REAL NOT NULL,
            spread_bps REAL NOT NULL,
            stress_level TEXT NOT NULL,
            macro_regime TEXT NOT NULL,
            FOREIGN KEY(date_key) REFERENCES dim_calendar(date_key),
            FOREIGN KEY(product_id) REFERENCES dim_product(product_id),
            FOREIGN KEY(country_id) REFERENCES dim_country(country_id)
        );
        """)


def _create_fact_table(cur: sqlite3.Cursor, table_name: str) -> None:
    cur.execute(f"""
        CREATE TABLE "{table_name}" (
            event_id INTEGER PRIMARY KEY,
            date_key INTEGER NOT NULL,
            settlement_date_key INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            counterparty_id INTEGER NOT NULL,
            trader_id INTEGER NOT NULL,
            desk_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            scenario TEXT NOT NULL,
            notional_usd REAL NOT NULL,
            revenue_usd REAL NOT NULL,
            cost_usd REAL NOT NULL,
            pnl_usd REAL NOT NULL,
            trade_count INTEGER NOT NULL,
            latency_ms REAL NOT NULL,
            slippage_bps REAL NOT NULL,
            fail_flag INTEGER NOT NULL,
            FOREIGN KEY(date_key) REFERENCES dim_calendar(date_key),
            FOREIGN KEY(settlement_date_key) REFERENCES dim_calendar(date_key),
            FOREIGN KEY(customer_id) REFERENCES dim_customer(customer_id),
            FOREIGN KEY(counterparty_id) REFERENCES dim_counterparty(counterparty_id),
            FOREIGN KEY(trader_id) REFERENCES dim_trader(trader_id),
            FOREIGN KEY(desk_id) REFERENCES dim_desk(desk_id),
            FOREIGN KEY(product_id) REFERENCES dim_product(product_id),
            FOREIGN KEY(country_id) REFERENCES dim_country(country_id),
            FOREIGN KEY(channel_id) REFERENCES dim_channel(channel_id)
        )
        """)
    cur.executescript(f"""
        CREATE INDEX idx_{table_name}_date_key ON "{table_name}" (date_key);
        CREATE INDEX idx_{table_name}_product_id ON "{table_name}" (product_id);
        CREATE INDEX idx_{table_name}_country_id ON "{table_name}" (country_id);
        CREATE INDEX idx_{table_name}_customer_id ON "{table_name}" (customer_id);
        CREATE INDEX idx_{table_name}_counterparty_id ON "{table_name}" (counterparty_id);
        """)


def _table_docs() -> dict[str, dict[str, Any]]:
    return {
        "dim_region": {
            "description": "Top-level reporting region dimension.",
            "columns": {
                "region_id": "Surrogate key for region.",
                "region_name": "Business reporting region label.",
            },
        },
        "dim_country": {
            "description": "Country dimension mapped to reporting regions.",
            "columns": {
                "country_id": "Surrogate key for country.",
                "region_id": "Foreign key to dim_region.",
                "iso_code": "ISO 3166-1 alpha-2 country code (two-letter format).",
                "country_name": "Full country name.",
            },
        },
        "dim_desk": {
            "description": "Trading/sales desk structure linked to home country.",
            "columns": {
                "desk_id": "Desk identifier.",
                "country_id": "Foreign key to dim_country.",
                "desk_name": "Business desk label.",
                "desk_tier": "Desk criticality tier.",
            },
        },
        "dim_product_family": {
            "description": "Product family hierarchy root.",
            "columns": {
                "family_id": "Product family identifier.",
                "family_name": "Product family name.",
            },
        },
        "dim_product": {
            "description": "Tradable product reference linked to product family.",
            "columns": {
                "product_id": "Product identifier.",
                "family_id": "Foreign key to dim_product_family.",
                "product_name": "Product label.",
                "risk_class": "Risk class category for controls.",
                "liquidity_tier": "Relative market liquidity bucket.",
            },
        },
        "dim_channel": {
            "description": "Execution channel dimension.",
            "columns": {
                "channel_id": "Execution channel key.",
                "channel_name": "Channel label (voice/electronic/etc).",
                "automation_level": "Automation maturity bucket.",
            },
        },
        "dim_customer": {
            "description": "Customer master data used by fact tables.",
            "columns": {
                "customer_id": "Customer identifier.",
                "country_id": "Foreign key to dim_country.",
                "customer_name": "Synthetic customer legal name.",
                "customer_segment": "Client segment classification.",
                "credit_bucket": "Internal credit quality bucket.",
                "inception_date": "Customer onboarding date.",
            },
        },
        "dim_counterparty": {
            "description": "Counterparty reference data.",
            "columns": {
                "counterparty_id": "Counterparty identifier.",
                "country_id": "Foreign key to dim_country.",
                "counterparty_name": "Synthetic counterparty name.",
                "counterparty_type": "Counterparty archetype (bank/broker/etc).",
                "systemic_flag": "1 when counterparty is systemically important.",
            },
        },
        "dim_trader": {
            "description": "Trader workforce roster linked to desks.",
            "columns": {
                "trader_id": "Trader identifier.",
                "desk_id": "Foreign key to dim_desk.",
                "trader_name": "Synthetic trader name.",
                "seniority": "Trader seniority level.",
                "location": "Primary operating location.",
            },
        },
        "dim_calendar": {
            "description": "Date dimension used for both trade and settlement dates.",
            "columns": {
                "date_key": "Integer date key (YYYYMMDD).",
                "trade_date": "Calendar date in ISO format.",
                "year": "Calendar year.",
                "quarter": "Calendar quarter.",
                "month": "Calendar month number.",
                "month_name": "Calendar month label.",
                "week_of_year": "ISO week number.",
                "is_month_end": "1 if date is month-end.",
            },
        },
        "bridge_customer_counterparty": {
            "description": "Many-to-many relationship table for customer and counterparty networks.",
            "columns": {
                "bridge_id": "Relationship record identifier.",
                "customer_id": "Foreign key to dim_customer.",
                "counterparty_id": "Foreign key to dim_counterparty.",
                "relationship_type": "Type of relationship between entities.",
                "relationship_since": "Date relationship became active.",
            },
        },
        "market_daily_signal": {
            "description": "Synthetic daily market conditions at product-country level.",
            "columns": {
                "signal_id": "Market signal record identifier.",
                "date_key": "Foreign key to dim_calendar.",
                "product_id": "Foreign key to dim_product.",
                "country_id": "Foreign key to dim_country.",
                "volatility_index": "Synthetic implied volatility indicator.",
                "spread_bps": "Average market spread in basis points.",
                "stress_level": "Market stress bucket.",
                "macro_regime": "Macro environment classification.",
            },
        },
    }


def _seed_dimensions(
    cur: sqlite3.Cursor, rng: random.Random, start_dt: date, day_span: int
) -> None:
    regions = ["EMEA", "AMER", "APAC", "LATAM"]
    country_rows = [
        (1, 1, "GB", "United Kingdom"),
        (2, 1, "DE", "Germany"),
        (3, 1, "CH", "Switzerland"),
        (4, 2, "US", "United States"),
        (5, 2, "CA", "Canada"),
        (6, 2, "BR", "Brazil"),
        (7, 3, "JP", "Japan"),
        (8, 3, "SG", "Singapore"),
        (9, 3, "AU", "Australia"),
        (10, 4, "MX", "Mexico"),
        (11, 4, "CL", "Chile"),
        (12, 4, "CO", "Colombia"),
    ]
    family_rows = [
        (1, "FX"),
        (2, "Rates"),
        (3, "Equities"),
        (4, "Credit"),
        (5, "Commodities"),
    ]
    product_rows = [
        (1, 1, "Spot FX", "Market", "Tier-1"),
        (2, 1, "FX Options", "Market", "Tier-2"),
        (3, 2, "IRS", "Market", "Tier-1"),
        (4, 2, "Gov Bonds", "Market", "Tier-1"),
        (5, 3, "Cash Equity", "Market", "Tier-1"),
        (6, 3, "Equity Derivatives", "Model", "Tier-2"),
        (7, 4, "IG Credit", "Credit", "Tier-2"),
        (8, 4, "HY Credit", "Credit", "Tier-3"),
        (9, 5, "Energy", "Commodity", "Tier-2"),
        (10, 5, "Metals", "Commodity", "Tier-2"),
    ]
    channel_rows = [
        (1, "voice", "low"),
        (2, "electronic", "high"),
        (3, "algo", "very_high"),
        (4, "rfq", "medium"),
    ]
    desk_rows = [
        (
            desk_id,
            country_id,
            f"{country_name} Desk",
            rng.choice(["Tier-1", "Tier-2", "Tier-3"]),
        )
        for desk_id, (_, country_id, _, country_name) in enumerate(
            country_rows, start=1
        )
    ]
    customer_rows = []
    counterparty_rows = []
    trader_rows = []
    bridge_rows = []
    customer_segments = [
        "Institutional",
        "Corporate",
        "Retail",
        "Sovereign",
        "Hedge Fund",
    ]
    credit_buckets = ["AAA", "AA", "A", "BBB", "BB"]
    cpty_types = ["Bank", "Broker", "Asset Manager", "Corporate"]
    seniority = ["Junior", "Associate", "VP", "Director", "Managing Director"]

    for customer_id in range(1, 601):
        country_id = rng.randint(1, len(country_rows))
        start_offset = rng.randint(0, max(day_span - 1, 1))
        inception = (start_dt + timedelta(days=start_offset)).isoformat()
        customer_rows.append(
            (
                customer_id,
                country_id,
                f"Customer_{customer_id:04d}",
                rng.choice(customer_segments),
                rng.choice(credit_buckets),
                inception,
            )
        )

    for counterparty_id in range(1, 301):
        country_id = rng.randint(1, len(country_rows))
        counterparty_rows.append(
            (
                counterparty_id,
                country_id,
                f"Counterparty_{counterparty_id:04d}",
                rng.choice(cpty_types),
                1 if rng.random() < 0.12 else 0,
            )
        )

    for trader_id in range(1, 241):
        desk_id = rng.randint(1, len(desk_rows))
        country_name = desk_rows[desk_id - 1][2].replace(" Desk", "")
        trader_rows.append(
            (
                trader_id,
                desk_id,
                f"Trader_{trader_id:04d}",
                rng.choice(seniority),
                country_name,
            )
        )

    bridge_id = 1
    relationship_types = ["Prime", "Clearing", "Execution", "Collateral", "Custody"]
    for customer_id in range(1, len(customer_rows) + 1):
        for counterparty_id in rng.sample(
            range(1, len(counterparty_rows) + 1), k=rng.randint(2, 6)
        ):
            since_offset = rng.randint(0, max(day_span - 1, 1))
            bridge_rows.append(
                (
                    bridge_id,
                    customer_id,
                    counterparty_id,
                    rng.choice(relationship_types),
                    (start_dt + timedelta(days=since_offset)).isoformat(),
                )
            )
            bridge_id += 1

    calendar_rows = []
    # +1 keeps the upper bound inclusive for trade dates near the last day plus max settlement lag.
    for offset in range(day_span + MAX_SETTLEMENT_LAG_DAYS + 1):
        current = start_dt + timedelta(days=offset)
        next_day = current + timedelta(days=1)
        calendar_rows.append(
            (
                int(current.strftime("%Y%m%d")),
                current.isoformat(),
                current.year,
                f"Q{((current.month - 1) // 3) + 1}",
                current.month,
                current.strftime("%B"),
                int(current.strftime("%V")),
                1 if next_day.month != current.month else 0,
            )
        )

    market_rows = []
    signal_id = 1
    stress_levels = ["calm", "normal", "elevated", "stressed"]
    macro_regimes = ["risk_on", "risk_off", "stagflation", "disinflation", "transition"]
    date_keys = [row[0] for row in calendar_rows]
    for date_key in date_keys:
        for product_id in range(1, len(product_rows) + 1):
            for country_id in range(1, len(country_rows) + 1):
                volatility = round(max(4.0, rng.gauss(18, 6)), 2)
                spread = round(max(1.0, volatility * rng.uniform(0.7, 1.8)), 2)
                stress = stress_levels[
                    min(int(volatility // 10), len(stress_levels) - 1)
                ]
                market_rows.append(
                    (
                        signal_id,
                        date_key,
                        product_id,
                        country_id,
                        volatility,
                        spread,
                        stress,
                        rng.choice(macro_regimes),
                    )
                )
                signal_id += 1

    cur.executemany(
        "INSERT INTO dim_region(region_id, region_name) VALUES (?, ?)",
        list(enumerate(regions, start=1)),
    )
    cur.executemany(
        "INSERT INTO dim_country(country_id, region_id, iso_code, country_name) VALUES (?, ?, ?, ?)",
        country_rows,
    )
    cur.executemany(
        "INSERT INTO dim_desk(desk_id, country_id, desk_name, desk_tier) VALUES (?, ?, ?, ?)",
        desk_rows,
    )
    cur.executemany(
        "INSERT INTO dim_product_family(family_id, family_name) VALUES (?, ?)",
        family_rows,
    )
    cur.executemany(
        "INSERT INTO dim_product(product_id, family_id, product_name, risk_class, liquidity_tier) VALUES (?, ?, ?, ?, ?)",
        product_rows,
    )
    cur.executemany(
        "INSERT INTO dim_channel(channel_id, channel_name, automation_level) VALUES (?, ?, ?)",
        channel_rows,
    )
    cur.executemany(
        "INSERT INTO dim_customer(customer_id, country_id, customer_name, customer_segment, credit_bucket, inception_date) VALUES (?, ?, ?, ?, ?, ?)",
        customer_rows,
    )
    cur.executemany(
        "INSERT INTO dim_counterparty(counterparty_id, country_id, counterparty_name, counterparty_type, systemic_flag) VALUES (?, ?, ?, ?, ?)",
        counterparty_rows,
    )
    cur.executemany(
        "INSERT INTO dim_trader(trader_id, desk_id, trader_name, seniority, location) VALUES (?, ?, ?, ?, ?)",
        trader_rows,
    )
    cur.executemany(
        "INSERT INTO dim_calendar(date_key, trade_date, year, quarter, month, month_name, week_of_year, is_month_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        calendar_rows,
    )
    cur.executemany(
        "INSERT INTO bridge_customer_counterparty(bridge_id, customer_id, counterparty_id, relationship_type, relationship_since) VALUES (?, ?, ?, ?, ?)",
        bridge_rows,
    )
    cur.executemany(
        "INSERT INTO market_daily_signal(signal_id, date_key, product_id, country_id, volatility_index, spread_bps, stress_level, macro_regime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        market_rows,
    )


def _fact_table_docs(table_name: str) -> dict[str, Any]:
    return {
        "description": (
            f"Synthetic event fact table {table_name} with multi-dimensional keys and "
            "financial + operational performance metrics."
        ),
        "columns": {
            "event_id": "Primary key for each synthetic event row.",
            "date_key": "Foreign key to dim_calendar for trade date.",
            "settlement_date_key": "Foreign key to dim_calendar for settlement date.",
            "customer_id": "Foreign key to dim_customer.",
            "counterparty_id": "Foreign key to dim_counterparty.",
            "trader_id": "Foreign key to dim_trader.",
            "desk_id": "Foreign key to dim_desk.",
            "product_id": "Foreign key to dim_product.",
            "country_id": "Foreign key to dim_country.",
            "channel_id": "Foreign key to dim_channel.",
            "scenario": "Scenario bucket representing market context.",
            "notional_usd": "Nominal traded amount in USD.",
            "revenue_usd": "Generated revenue in USD.",
            "cost_usd": "Attributed operational and funding costs in USD.",
            "pnl_usd": "Profit and loss in USD (revenue - cost).",
            "trade_count": "Number of child trades represented by this record.",
            "latency_ms": "Execution latency in milliseconds.",
            "slippage_bps": "Execution slippage in basis points.",
            "fail_flag": "1 if execution breached quality threshold; otherwise 0.",
        },
    }


def _seed_fact_tables(
    cur: sqlite3.Cursor,
    rng: random.Random,
    table_count: int,
    rows_per_table: int,
    day_span: int,
    start_dt: date,
) -> list[str]:
    scenarios = ["baseline", "stressed", "risk_on", "risk_off", "flash_event"]
    trade_dates = [start_dt + timedelta(days=d) for d in range(day_span)]
    created_tables: list[str] = []

    for i in range(1, table_count + 1):
        table_name = f"fact_business_{i:03d}"
        _create_fact_table(cur, table_name)
        created_tables.append(table_name)

        rows = []
        for event_id in range(1, rows_per_table + 1):
            trade_date = rng.choice(trade_dates)
            date_key = int(trade_date.strftime("%Y%m%d"))
            settle_shift = rng.randint(0, MAX_SETTLEMENT_LAG_DAYS)
            settle_date = trade_date + timedelta(days=settle_shift)
            settlement_date_key = int(settle_date.strftime("%Y%m%d"))

            product_id = rng.randint(1, 10)
            customer_id = rng.randint(1, 600)
            counterparty_id = rng.randint(1, 300)
            desk_id = rng.randint(1, 12)
            trader_id = rng.randint(1, 240)
            country_id = rng.randint(1, 12)
            channel_id = rng.randint(1, 4)
            scenario = rng.choice(scenarios)

            scenario_mult = {
                "baseline": 1.0,
                "stressed": 1.4,
                "risk_on": 1.2,
                "risk_off": 0.9,
                "flash_event": 1.8,
            }[scenario]
            notional = max(50_000.0, rng.lognormvariate(11.5, 0.7) * scenario_mult)
            revenue = max(500.0, notional * rng.uniform(0.0006, 0.0032))
            cost = max(100.0, revenue * rng.uniform(0.35, 0.92))
            pnl = revenue - cost
            trade_count = max(1, int(rng.gauss(18, 8)))
            latency = max(1.0, rng.gauss(14.0 * scenario_mult, 5.0))
            slippage = max(0.1, rng.gauss(1.4 * scenario_mult, 0.9))
            fail_flag = (
                1 if (latency > 26.0 or slippage > 4.0) and rng.random() < 0.7 else 0
            )

            rows.append(
                (
                    event_id,
                    date_key,
                    settlement_date_key,
                    customer_id,
                    counterparty_id,
                    trader_id,
                    desk_id,
                    product_id,
                    country_id,
                    channel_id,
                    scenario,
                    round(notional, 2),
                    round(revenue, 2),
                    round(cost, 2),
                    round(pnl, 2),
                    trade_count,
                    round(latency, 2),
                    round(slippage, 2),
                    fail_flag,
                )
            )

        cur.executemany(
            f"""
            INSERT INTO "{table_name}" (
                event_id, date_key, settlement_date_key, customer_id, counterparty_id,
                trader_id, desk_id, product_id, country_id, channel_id, scenario,
                notional_usd, revenue_usd, cost_usd, pnl_usd, trade_count,
                latency_ms, slippage_bps, fail_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    return created_tables


def _generate_cypher(
    path: Path,
    regions: list[tuple],
    countries: list[tuple],
    desks: list[tuple],
    product_families: list[tuple],
    products: list[tuple],
    customers: list[tuple],
    counterparties: list[tuple],
    traders: list[tuple],
    bridge: list[tuple],
) -> None:
    """Generates a Cypher script to load the dimension data into Neo4j."""
    lines = [
        "// Auto-generated Cypher script for big_demo dataset",
        "// Constraints",
        "CREATE CONSTRAINT region_id_unique IF NOT EXISTS FOR (r:Region) REQUIRE r.region_id IS UNIQUE;",
        "CREATE CONSTRAINT country_id_unique IF NOT EXISTS FOR (c:Country) REQUIRE c.country_id IS UNIQUE;",
        "CREATE CONSTRAINT desk_id_unique IF NOT EXISTS FOR (d:Desk) REQUIRE d.desk_id IS UNIQUE;",
        "CREATE CONSTRAINT family_id_unique IF NOT EXISTS FOR (f:ProductFamily) REQUIRE f.family_id IS UNIQUE;",
        "CREATE CONSTRAINT product_id_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE;",
        "CREATE CONSTRAINT customer_id_unique IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE;",
        "CREATE CONSTRAINT counterparty_id_unique IF NOT EXISTS FOR (cp:Counterparty) REQUIRE cp.counterparty_id IS UNIQUE;",
        "CREATE CONSTRAINT trader_id_unique IF NOT EXISTS FOR (t:Trader) REQUIRE t.trader_id IS UNIQUE;",
        "",
    ]

    # Regions
    for r_id, r_name in regions:
        lines.append(f'MERGE (:Region {{region_id: {r_id}, name: "{r_name}"}});')
    lines.append("")

    # Countries
    for c_id, r_id, iso, c_name in countries:
        lines.append(
            f'MERGE (c:Country {{country_id: {c_id}, iso_code: "{iso}", name: "{c_name}"}});'
        )
        lines.append(
            f"MATCH (c:Country {{country_id: {c_id}}}), (r:Region {{region_id: {r_id}}}) "
            f"MERGE (c)-[:IN_REGION]->(r);"
        )
    lines.append("")

    # Desks
    for d_id, c_id, d_name, tier in desks:
        lines.append(
            f'MERGE (d:Desk {{desk_id: {d_id}, name: "{d_name}", tier: "{tier}"}});'
        )
        lines.append(
            f"MATCH (d:Desk {{desk_id: {d_id}}}), (c:Country {{country_id: {c_id}}}) "
            f"MERGE (d)-[:LOCATED_IN]->(c);"
        )
    lines.append("")

    # Product Families
    for f_id, f_name in product_families:
        lines.append(f'MERGE (:ProductFamily {{family_id: {f_id}, name: "{f_name}"}});')
    lines.append("")

    # Products
    for p_id, f_id, p_name, risk, liq in products:
        lines.append(
            f'MERGE (p:Product {{product_id: {p_id}, name: "{p_name}", risk_class: "{risk}", liquidity_tier: "{liq}"}});'
        )
        lines.append(
            f"MATCH (p:Product {{product_id: {p_id}}}), (f:ProductFamily {{family_id: {f_id}}}) "
            f"MERGE (p)-[:PART_OF_FAMILY]->(f);"
        )
    lines.append("")

    # Customers
    for c_id, co_id, name, seg, credit, inc in customers:
        lines.append(
            f'MERGE (c:Customer {{customer_id: {c_id}, name: "{name}", segment: "{seg}", credit_bucket: "{credit}", inception_date: "{inc}"}});'
        )
        lines.append(
            f"MATCH (c:Customer {{customer_id: {c_id}}}), (co:Country {{country_id: {co_id}}}) "
            f"MERGE (c)-[:BASED_IN]->(co);"
        )
    lines.append("")

    # Counterparties
    for cp_id, co_id, name, c_type, sys_flag in counterparties:
        lines.append(
            f'MERGE (cp:Counterparty {{counterparty_id: {cp_id}, name: "{name}", type: "{c_type}", systemic_flag: {sys_flag}}});'
        )
        lines.append(
            f"MATCH (cp:Counterparty {{counterparty_id: {cp_id}}}), (co:Country {{country_id: {co_id}}}) "
            f"MERGE (cp)-[:BASED_IN]->(co);"
        )
    lines.append("")

    # Traders
    for t_id, d_id, name, seniority, location in traders:
        lines.append(
            f'MERGE (t:Trader {{trader_id: {t_id}, name: "{name}", seniority: "{seniority}", location: "{location}"}});'
        )
        lines.append(
            f"MATCH (t:Trader {{trader_id: {t_id}}}), (d:Desk {{desk_id: {d_id}}}) "
            f"MERGE (t)-[:WORKS_AT]->(d);"
        )
    lines.append("")

    # Bridge (Relationships)
    for _, c_id, cp_id, rel_type, since in bridge:
        lines.append(
            f"MATCH (c:Customer {{customer_id: {c_id}}}), (cp:Counterparty {{counterparty_id: {cp_id}}}) "
            f'MERGE (c)-[:HAS_RELATIONSHIP {{type: "{rel_type}", since: "{since}"}}]->(cp);'
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = _build_parser().parse_args()
    if args.table_count < 1:
        raise ValueError("table-count must be >= 1")
    if args.rows_per_table < 1:
        raise ValueError("rows-per-table must be >= 1")
    if args.day_span < 30:
        raise ValueError("day-span must be >= 30")

    db_path = Path(args.db_path)
    docs_path = Path(args.docs_path)
    cfg_path = Path(args.config_path)
    cypher_path = Path(args.cypher_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cypher_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    start_dt = date.fromisoformat(args.start_date)

    # Initial docs with standard demo sources
    docs = {
        "demo_sqlite": {
            "tables": {
                "regions": {
                    "description": "Region reference dimension for customer geography.",
                    "columns": {
                        "region_id": "Unique region identifier.",
                        "region_name": "Business reporting region label.",
                    },
                },
                "customers": {
                    "description": "Customer master with regional assignment.",
                    "columns": {
                        "customer_id": "Unique customer identifier.",
                        "customer_name": "Legal customer name.",
                        "region_id": "Foreign key to regions.",
                    },
                },
                "orders": {
                    "description": "Order facts with booked revenue and reporting quarter.",
                    "columns": {
                        "order_id": "Unique order identifier.",
                        "customer_id": "Foreign key to customers.",
                        "order_date": "Order booking date.",
                        "revenue": "Booked revenue amount for the order.",
                        "quarter": "Reporting quarter (for example Q1, Q2.",
                    },
                },
            }
        },
        DATA_SOURCE_NAME: {"tables": _table_docs()},
    }

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        _drop_existing_tables(cur)
        _create_dimension_tables(cur)
        _seed_dimensions(cur, rng, start_dt, args.day_span)
        created_fact_tables = _seed_fact_tables(
            cur,
            rng,
            table_count=args.table_count,
            rows_per_table=args.rows_per_table,
            day_span=args.day_span,
            start_dt=start_dt,
        )
        for table_name in created_fact_tables:
            docs[DATA_SOURCE_NAME]["tables"][table_name] = _fact_table_docs(table_name)
        conn.commit()

    with docs_path.open("w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)

    # Note: _seed_dimensions fills the database but doesn't return the lists.
    # For simplicity, we could modify _seed_dimensions or just re-read the DB if needed.
    # Better: let's wrap the logic to capture the data lists.
    # Since we already ran the seeding, we can just extract from the DB for Cypher.

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        regions = cur.execute(
            "SELECT region_id, region_name FROM dim_region"
        ).fetchall()
        countries = cur.execute(
            "SELECT country_id, region_id, iso_code, country_name FROM dim_country"
        ).fetchall()
        desks = cur.execute(
            "SELECT desk_id, country_id, desk_name, desk_tier FROM dim_desk"
        ).fetchall()
        families = cur.execute(
            "SELECT family_id, family_name FROM dim_product_family"
        ).fetchall()
        products = cur.execute(
            "SELECT product_id, family_id, product_name, risk_class, liquidity_tier FROM dim_product"
        ).fetchall()
        customers = cur.execute(
            "SELECT customer_id, country_id, customer_name, customer_segment, credit_bucket, inception_date FROM dim_customer"
        ).fetchall()
        counterparties = cur.execute(
            "SELECT counterparty_id, country_id, counterparty_name, counterparty_type, systemic_flag FROM dim_counterparty"
        ).fetchall()
        traders = cur.execute(
            "SELECT trader_id, desk_id, trader_name, seniority, location FROM dim_trader"
        ).fetchall()
        bridge = cur.execute(
            "SELECT bridge_id, customer_id, counterparty_id, relationship_type, relationship_since FROM bridge_customer_counterparty"
        ).fetchall()

    _generate_cypher(
        cypher_path,
        regions,
        countries,
        desks,
        families,
        products,
        customers,
        counterparties,
        traders,
        bridge,
    )

    total_tables = len(docs[DATA_SOURCE_NAME]["tables"])
    print(f"Created database: {db_path}")
    print(f"Created schema docs: {docs_path}")
    print(f"Created Cypher script: {cypher_path}")
    print(f"Fact tables: {args.table_count}")
    print(f"Rows per fact table: {args.rows_per_table}")
    print(f"Total documented tables: {total_tables}")


if __name__ == "__main__":
    main()
