#!/bin/bash

# Simple script to run all components of the UBS Hackathon system

echo "🚀 Starting UBS Hackathon System..."

# Function to kill all background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down..."

    # Get all background PIDs
    PIDS=$(jobs -p)

    if [ -n "$PIDS" ]; then
        echo "📡 Stopping background processes..."
        # Try graceful shutdown first
        kill $PIDS 2>/dev/null

        # Wait a moment for processes to exit
        sleep 1

        # Force kill any remaining processes
        REMAINING=$(jobs -p)
        if [ -n "$REMAINING" ]; then
            echo "⚠️  Some processes didn't stop gracefully, forcing shutdown..."
            kill -9 $REMAINING 2>/dev/null
        fi
    fi

    echo "✅ Shutdown complete."
    exit
}

trap cleanup SIGINT SIGTERM

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$PYTHONPATH:$(pwd)/src

# --- 0. Ensure Neo4j is running ---
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

# 1. Start Backend
echo "📡 Starting Backend (REST API) on port 8080..."
python3 -m ubs_hackathon.backend --meta-db data/meta.db --catalog data/catalog.db --host 127.0.0.1 --port 8080 > backend.log 2>&1 &
BACKEND_PID=$!

# 2. Start MCP Server (SSE)
echo "🔌 Starting MCP Server (SSE) on port 8000..."
python3 -m ubs_hackathon.server --config config/config.yaml --transport sse --host 0.0.0.0 --port 8000 > mcp.log 2>&1 &
MCP_PID=$!

# 3. Start Neo4j MCP (SSE)
echo "🌳 Starting Neo4j MCP Server (SSE) on port 8001..."
uvx mcp-neo4j-cypher@0.6.0 \
  --transport sse \
  --server-port 8001 \
  --db-url "${NEO4J_URI:-bolt://localhost:7687}" \
  --username "${NEO4J_USERNAME:-neo4j}" \
  --password "${NEO4J_PASSWORD:-ChangeMe123!}" \
  > neo4j_mcp.log 2>&1 &
NEO4J_MCP_PID=$!

# 4. Start Frontend
echo "💻 Starting Frontend..."
(
    cd frontend
    if command -v pnpm &> /dev/null; then
        exec pnpm run dev > ../frontend.log 2>&1
    else
        exec npm run dev > ../frontend.log 2>&1
    fi
) &
FRONTEND_PID=$!

echo "✅ System is running!"
echo "   - Backend: http://127.0.0.1:8080"
echo "   - Frontend: http://localhost:3000"
echo "   - MCP SSE: http://127.0.0.1:8000/sse"
echo "   - Neo4j endpoint: ${NEO4J_URI:-bolt://localhost:7687}"
echo "   - Neo4j username: ${NEO4J_USERNAME:-neo4j}"
echo "   - Neo4j password: ${NEO4J_PASSWORD:-ChangeMe123!}"
echo "   - Neo4j MCP SSE: http://127.0.0.1:8001/mcp/sse"
echo ""
echo "📝 Logs are being written to: backend.log, mcp.log, frontend.log"
echo "⌨️ Press Ctrl+C to stop all services."

# Wait for background processes
wait
