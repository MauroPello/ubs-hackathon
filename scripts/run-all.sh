#!/bin/bash

# Simple script to run all components of the UBS Hackathon system

echo "🚀 Starting UBS Hackathon System..."

# Function to kill all background processes on exit
cleanup() {
    echo "🛑 Shutting down..."
    kill $(jobs -p)
    exit
}

trap cleanup SIGINT SIGTERM

# 1. Start Backend
echo "📡 Starting Backend (REST API) on port 8080..."
ubs-backend --meta-db data/meta.db --catalog data/catalog.db --host 127.0.0.1 --port 8080 > backend.log 2>&1 &

# 2. Start MCP Server (SSE)
echo "🔌 Starting MCP Server (SSE) on port 8000..."
ubs-mcp-server --config config/config.yaml --transport sse --host 0.0.0.0 --port 8000 > mcp.log 2>&1 &

# 3. Start Neo4j MCP (if environment variables are set)
if [ ! -z "$NEO4J_URI" ]; then
    echo "🌳 Starting Neo4j MCP Server..."
    uvx mcp-neo4j-cypher@0.6.0 --transport stdio > neo4j_mcp.log 2>&1 &
else
    echo "ℹ️ Neo4j environment variables not set. Skipping Neo4j MCP."
fi

# 4. Start Frontend
echo "💻 Starting Frontend..."
cd frontend
if command -v pnpm &> /dev/null; then
    pnpm run dev > ../frontend.log 2>&1 &
else
    npm run dev > ../frontend.log 2>&1 &
fi
cd ..

echo "✅ System is running!"
echo "   - Backend: http://127.0.0.1:8080"
echo "   - Frontend: http://localhost:3000 (usually)"
echo "   - MCP SSE: http://127.0.0.1:8000/sse"
echo ""
echo "📝 Logs are being written to: backend.log, mcp.log, frontend.log"
echo "⌨️ Press Ctrl+C to stop all services."

# Wait for background processes
wait
