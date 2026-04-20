#!/bin/bash
set -e

echo "📊 Initializing mock data..."

# Ensure we are in the root directory
# (Assumes script is run from project root or via bash scripts/init-data.sh)

# 1. Create data directory if it doesn't exist
mkdir -p data

# 2. Ensure Neo4j is running
NEO4J_CONTAINER="ubs-neo4j"
if [ "$(docker ps -aq -f name=^/${NEO4J_CONTAINER}$)" ]; then
    if [ ! "$(docker ps -q -f name=^/${NEO4J_CONTAINER}$)" ]; then
        echo "🔄 Starting existing Neo4j container..."
        docker start ${NEO4J_CONTAINER}
    fi
else
    echo "🐳 Creating and starting new Neo4j container..."
    docker run --name ${NEO4J_CONTAINER} \
      --detach \
      --publish 7474:7474 \
      --publish 7687:7687 \
      --env NEO4J_AUTH=neo4j/${NEO4J_PASSWORD:-ChangeMe123!} \
      --env NEO4J_PLUGINS='["apoc"]' \
      --volume ubs-neo4j-data:/data \
      neo4j:5.26.1
fi

echo "⏳ Waiting for Neo4j to be ready..."
until cypher-shell -a ${NEO4J_URI:-bolt://localhost:7687} -u ${NEO4J_USERNAME:-neo4j} -p ${NEO4J_PASSWORD:-ChangeMe123!} "RETURN 1" > /dev/null 2>&1; do
    sleep 2
done
echo "✅ Neo4j is ready!"

# 3. Generate demo database
echo "🧬 Seeding demo database..."
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python3 -m ubs_hackathon.demo_seed --db-path data/demo_business.db

# 3. Generate large synthetic dataset
echo "📉 Generating large synthetic dataset..."
python3 scripts/generate_data.py

# 4. Build schema catalog
echo "🏗️ Building schema catalog..."
python3 -m ubs_hackathon.builder --config config/config.yaml

# 5. Load Neo4j data
echo "🌳 Loading graph data into Neo4j..."
cypher-shell \
    -a ${NEO4J_URI:-bolt://localhost:7687} \
    --username ${NEO4J_USERNAME:-neo4j} \
    --password "${NEO4J_PASSWORD:-ChangeMe123!}" \
    --file data/big_demo.cypher
echo "✅ Neo4j data loaded."

echo "✅ Data initialization complete!"
