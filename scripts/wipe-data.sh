#!/bin/bash
set -e

echo "⚠️ Wiping all local data..."

# 1. Clean data directory
if [ -d "data" ]; then
    echo "🗑️ Removing SQLite databases and Cypher scripts in data/..."
    rm -f data/*.db
    rm -f data/*.cypher
    # Optional: remove meta.db if it exists
    rm -f data/meta.db
else
    mkdir -p data
fi

# 2. Clean generated configs/docs
echo "🗑️ Removing generated schema docs..."
rm -f config/schema_docs.json

# 3. Clean logs
echo "🗑️ Removing log files..."
rm -f *.log

# 4. Ensure Neo4j is running for wipe
NEO4J_CONTAINER="ubs-neo4j"
if [ "$(docker ps -aq -f name=^/${NEO4J_CONTAINER}$)" ]; then
    if [ ! "$(docker ps -q -f name=^/${NEO4J_CONTAINER}$)" ]; then
        echo "🔄 Starting Neo4j container for cleanup..."
        docker start ${NEO4J_CONTAINER}
    fi
    echo "⏳ Waiting for Neo4j to be ready..."
    until cypher-shell -a ${NEO4J_URI:-bolt://localhost:7687} -u ${NEO4J_USERNAME:-neo4j} -p ${NEO4J_PASSWORD:-ChangeMe123!} "RETURN 1" > /dev/null 2>&1; do
        sleep 2
    done
    
    echo "🌳 Attempting to wipe Neo4j database..."
    cypher-shell \
        -a ${NEO4J_URI:-bolt://localhost:7687} \
        --username ${NEO4J_USERNAME:-neo4j} \
        --password "${NEO4J_PASSWORD:-ChangeMe123!}" \
        "MATCH (n) DETACH DELETE n;"
    echo "✅ Neo4j database cleared."
else
    echo "ℹ️ Neo4j container not found. Skipping graph wipe."
fi

echo "✨ All local data wiped! Run 'bash scripts/init-data.sh' to start fresh."
