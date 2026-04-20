#!/bin/bash
set -e

echo "📊 Initializing mock data..."

# Ensure we are in the root directory
# (Assumes script is run from project root or via bash scripts/init-data.sh)

# 1. Create data directory if it doesn't exist
mkdir -p data

# 2. Generate demo database
echo "🧬 Seeding demo database..."
ubs-seed-demo --db-path data/demo_business.db

# 3. Generate large synthetic dataset
echo "📉 Generating large synthetic dataset..."
python3 scripts/generate_data.py

# 4. Build schema catalogs
echo "🏗️ Building schema catalogs..."
ubs-build-catalog --config config/config.yaml
ubs-build-catalog --config config/big_config.yaml

echo "✅ Data initialization complete!"
