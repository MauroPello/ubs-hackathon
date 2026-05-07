import argparse
import csv
import json
import random
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DEFAULT_ROWS_PER_TABLE = 100
DEFAULT_SEED = 42
DATA_SOURCE_NAME = "big_demo_sqlite"
NEO4J_DATA_SOURCE_NAME = "big_demo_neo4j"

def get_sqlite_type(t):
    t = t.upper()
    if 'DECIMAL' in t or 'DOUBLE' in t: return 'REAL'
    if 'INTEGER' in t or 'BOOLEAN' in t: return 'INTEGER'
    return 'TEXT'

def generate_random_value(col, row_index):
    # Base generation on data type and example value
    dt = col['Data Type'].upper()
    ex = col['Synthetic Example Value']
    if col['Key'] == 'PK':
        # Ensure uniqueness by appending row_index
        prefix = ex.split('_')[0] if '_' in ex else 'ID'
        return f"{prefix}_{row_index}"
    if dt == 'BOOLEAN':
        return random.choice([0, 1])
    if 'INTEGER' in dt:
        try: return int(ex) + random.randint(-10, 10)
        except: return random.randint(1, 100)
    if 'DECIMAL' in dt or 'DOUBLE' in dt:
        try: return float(ex) * random.uniform(0.5, 1.5)
        except: return random.uniform(10.0, 1000.0)
    if dt == 'DATE':
        # Excel date offset -> YYYY-MM-DD
        try:
            offset = int(ex) + random.randint(-100, 100)
        except:
            offset = 46000 + random.randint(-100, 100)
        return (date(1899, 12, 30) + timedelta(days=offset)).strftime("%Y-%m-%d")
    # STRING
    if ex: return f"{ex}_{row_index}"
    return f"str_{row_index}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows-per-table", type=int, default=DEFAULT_ROWS_PER_TABLE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--db-path", default="data/big_demo.db")
    parser.add_argument("--docs-path", default="config/schema_docs.json")
    parser.add_argument("--config-path", default="config/config.yaml")
    parser.add_argument("--cypher-path", default="data/big_demo.cypher")
    # Ignored args to keep compatibility
    parser.add_argument("--table-count", type=int, default=10)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--day-span", type=int, default=30)
    args = parser.parse_args()

    random.seed(args.seed)

    # 1. Parse CSV
    schema = defaultdict(list)
    with open('data/official_synthetic_schema.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            schema[row['Table Name']].append(row)

    # 2. Prepare PKs
    pks = {}
    for table, cols in schema.items():
        pk_col = next((c for c in cols if c['Key'] == 'PK'), None)
        if pk_col:
            pks[table] = [generate_random_value(pk_col, i) for i in range(1, args.rows_per_table + 1)]

    # 3. Generate Data
    all_data = {}
    for table, cols in schema.items():
        table_data = []
        pk_col = next((c for c in cols if c['Key'] == 'PK'), None)
        for i in range(1, args.rows_per_table + 1):
            row_data = {}
            for col in cols:
                cname = col['Column Name']
                if col['Key'] == 'PK':
                    row_data[cname] = pks[table][i-1]
                elif col['Key'] == 'FK':
                    ref = col['References']
                    if ref:
                        ref_table = ref.split('.')[0]
                        if ref_table in pks:
                            # Randomly pick from target table's PKs
                            row_data[cname] = random.choice(pks[ref_table])
                        else:
                            row_data[cname] = None
                    else:
                        row_data[cname] = None
                else:
                    if col['Nullable'] == 'Y' and random.random() < 0.2:
                        row_data[cname] = None
                    else:
                        row_data[cname] = generate_random_value(col, i)
            table_data.append(row_data)
        all_data[table] = table_data

    # 4. Save to SQLite
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF")
        for table, cols in schema.items():
            col_defs = []
            for col in cols:
                col_type = get_sqlite_type(col['Data Type'])
                # Just base types
                col_defs.append(f"\"{col['Column Name']}\" {col_type}")
            cur.execute(f"CREATE TABLE \"{table}\" ({', '.join(col_defs)})")
            
            if not all_data[table]: continue
            
            cnames = [f"\"{c['Column Name']}\"" for c in cols]
            placeholders = ", ".join(["?"] * len(cols))
            
            insert_data = []
            for row in all_data[table]:
                insert_data.append([row[c['Column Name']] for c in cols])
                
            cur.executemany(f"INSERT INTO \"{table}\" ({', '.join(cnames)}) VALUES ({placeholders})", insert_data)
        conn.commit()

    # 5. Generate Schema Docs
    docs = {
        DATA_SOURCE_NAME: {"tables": {}},
        NEO4J_DATA_SOURCE_NAME: {"graph_entities": {}}
    }
    for table, cols in schema.items():
        desc_parts = [f"{c['Column Name']} ({c['Column Description']})" for c in cols]
        docs[DATA_SOURCE_NAME]["tables"][table] = {
            "description": f"Synthetic table {table}. Attributes: " + ", ".join(desc_parts)
        }
        docs[NEO4J_DATA_SOURCE_NAME]["graph_entities"][table] = {
            "description": f"Graph node {table}. Attributes: " + ", ".join(desc_parts)
        }
        
    docs_path = Path(args.docs_path)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    with docs_path.open("w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)

    # 6. Generate Cypher
    cypher_path = Path(args.cypher_path)
    cypher_path.parent.mkdir(parents=True, exist_ok=True)
    with cypher_path.open("w", encoding="utf-8") as f:
        f.write("// Auto-generated Cypher script\n")
        f.write("MATCH (n) DETACH DELETE n;\n\n")
        
        # Nodes
        for table, cols in schema.items():
            # Create a label (CamelCase from snake_case)
            label = "".join(word.capitalize() for word in table.split("_"))
            for row in all_data[table]:
                props = []
                for col in cols:
                    if col['Key'] == 'FK': continue
                    val = row[col['Column Name']]
                    if val is None: continue
                    if isinstance(val, (int, float)):
                        props.append(f"{col['Column Name']}: {val}")
                    else:
                        safe_val = str(val).replace('"', '\\"')
                        props.append(f"{col['Column Name']}: \"{safe_val}\"")
                f.write(f"CREATE (:{label} {{{', '.join(props)}}});\n")
                
        # Indexes for fast relationship creation
        f.write("\n// Constraints and Indexes\n")
        for table, cols in schema.items():
            label = "".join(word.capitalize() for word in table.split("_"))
            pk_col = next((c for c in cols if c['Key'] == 'PK'), None)
            if pk_col:
                f.write(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{pk_col['Column Name']} IS UNIQUE;\n")

        # Edges
        f.write("\n// Relationships\n")
        for table, cols in schema.items():
            label = "".join(word.capitalize() for word in table.split("_"))
            fks = [c for c in cols if c['Key'] == 'FK' and c['References']]
            for fk in fks:
                ref = fk['References'].split('.')
                if len(ref) != 2: continue
                ref_table, ref_col = ref
                ref_label = "".join(word.capitalize() for word in ref_table.split("_"))
                rel_type = fk['Column Name'].upper()
                
                for row in all_data[table]:
                    if row[fk['Column Name']] is None: continue
                    pk_col = next((c for c in cols if c['Key'] == 'PK'), None)
                    if not pk_col: continue
                    
                    src_pk = row[pk_col['Column Name']]
                    dst_pk = row[fk['Column Name']]
                    f.write(f"MATCH (a:{label} {{{pk_col['Column Name']}: \"{src_pk}\"}}), (b:{ref_label} {{{ref_col}: \"{dst_pk}\"}}) CREATE (a)-[:{rel_type}]->(b);\n")

    print(f"Generated data with {len(schema)} tables.")

if __name__ == "__main__":
    main()
