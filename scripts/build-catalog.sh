#!/bin/bash
set -e

echo "🏗️ Building schema catalog from config..."

# Ensure we are in the root directory
# (Assumes script is run from project root or via bash scripts/build-catalog.sh)

# 1. Ensure data directory exists
mkdir -p data

# 2. Build schema catalog
# This script now also syncs the data_sources and docs from config.yaml into meta.db
export PYTHONPATH=$PYTHONPATH:$(pwd)/src

PYTHON_EXEC="python3"
if [ -f "./.venv/bin/python" ]; then
    PYTHON_EXEC="./.venv/bin/python"
fi

$PYTHON_EXEC -m ubs_hackathon.builder --config config/config.yaml

echo "✅ Catalog build and config sync complete!"
