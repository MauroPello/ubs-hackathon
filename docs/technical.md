# Technical Documentation

This document provides in-depth technical details about the system architecture and configuration.

## System Architecture

- **MCP Server** (`src/ubs_hackathon/server.py`): Core logic and tool definitions.
- **Catalog Builder** (`src/ubs_hackathon/builder.py`): Indexing pipeline for schema introspection.
- **Data Source Abstraction** (`src/ubs_hackathon/datasource.py`): Unified interface for SQL and Graph sources.
- **Semantic Search** (`src/ubs_hackathon/catalog.py`): Persistence and retrieval using embeddings.

## Supported Data Sources

Powered by **SQLAlchemy**, supporting any database with a compatible dialect.

| Database | URL scheme | Extra install |
|---|---|---|
| SQLite (default) | `sqlite:///path/to/file.db` | *(stdlib)* |
| PostgreSQL | `postgresql+psycopg2://user:pw@host/db` | `pip install "ubs-hackathon[postgres]"` |
| MySQL / MariaDB | `mysql+pymysql://user:pw@host/db` | `pip install "ubs-hackathon[mysql]"` |
| Snowflake | `snowflake://user:pw@account/db/schema` | `pip install "ubs-hackathon[snowflake]"` |
| DuckDB | `duckdb:///path/to/file.duckdb` | `pip install "ubs-hackathon[duckdb]"` |

## Embeddings Configuration

The system uses an `auto` mode for embeddings:
1. **OpenAI**: Used if `OPENAI_API_KEY` is present.
2. **Hugging Face**: Free online inference as a fallback.
3. **Local**: Automatic local model fallback if online calls fail.

### Environment Variables
- `UBS_EMBEDDINGS_PROVIDER`: `auto`, `openai`, `huggingface`, or `local`.
- `OPENAI_API_KEY`: Required for OpenAI.
- `UBS_EMBEDDINGS_MODEL`: Defaults to `text-embedding-3-small`.
- `UBS_HF_EMBEDDINGS_MODEL`: Defaults to `sentence-transformers/all-MiniLM-L6-v2`.

## Datasets

For large-scale testing, we recommend:
- **NYC TLC Trip Record Data**: Real-world open dataset.
- **Synthetic Generator** (`scripts/generate_data.py`): Customizable, high-volume local data.

### Large Dataset Generation
```bash
python scripts/generate_data.py --table-count 320 --rows-per-table 3000 --day-span 1095 --seed 42
```
This produces a complex schema with hundreds of interconnected fact and dimension tables.
