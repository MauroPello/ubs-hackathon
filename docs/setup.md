# Setup Guide

This guide covers the installation and environment setup for the UBS Hackathon project.

## Prerequisites

- **Python 3.10+**
- **Conda** (recommended) or **pip**
- **Node.js 18+** and **pnpm** (for the frontend)
- **Docker** (optional, for Neo4j)

## Quickstart

We provide a script to initialize the environment automatically:

```bash
bash scripts/init-env.sh
```

### 1) Manual Conda Environment Setup

```bash
conda env create -f environment.yml
conda activate ubs-hackathon
```

### 2) Manual pip Installation

If you prefer not to use Conda:

```bash
pip install -e .
```

### 3) Frontend Setup

The frontend is a Nuxt application located in the `frontend` directory.

```bash
cd frontend
pnpm install
```

## Data Initialization

To initialize the demo database and build the schema catalog:

```bash
bash scripts/init-data.sh
```

### Manual Steps

1. **Create demo database**:
   ```bash
   ubs-seed-demo --db-path data/demo_business.db
   ```

2. **Build schema catalog**:
   ```bash
   ubs-build-catalog --config config/config.yaml
   ```

3. **Generate large synthetic dataset (Optional)**:
   ```bash
   python scripts/generate_data.py
   ubs-build-catalog --config config/big_config.yaml
   ```

## Neo4j Setup

For a complete Neo4j walkthrough, including how to start a local Neo4j database, run the Neo4j MCP server, and load demo data, see [docs/neo4j.md](neo4j.md).

## VS Code / Copilot Chat Integration

To connect the local MCP server to GitHub Copilot Chat in VS Code:

1. Open the workspace in VS Code.
2. Open Chat and make sure Copilot Chat is available in your account.
3. VS Code will discover the `ubs-hackathon` MCP server from `.vscode/mcp.json`.
4. The default config points at the Conda environment: `/home/mpello/.conda/envs/ubs-hackathon/bin/python`. Update this in `.vscode/mcp.json` if your path is different.
