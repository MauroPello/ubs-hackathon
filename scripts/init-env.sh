#!/bin/bash
set -e

# Colors for noticeability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Initializing environment..."

# --- 0. Check Prerequisites ---
echo "🔍 Checking mandatory CLI tools..."
MISSING_TOOLS=()

check_tool() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}❌ Missing: $1${NC}"
        MISSING_TOOLS+=("$1")
    else
        echo -e "${GREEN}✅ Found: $1${NC}"
    fi
}

check_tool "python3"
check_tool "node"
check_tool "pnpm"
check_tool "docker"
check_tool "cypher-shell"
check_tool "uv"

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo -e "\n${RED}#################################################${NC}"
    echo -e "${RED}⚠️  ERROR: MANDATORY TOOLS ARE MISSING!${NC}"
    echo -e "${RED}The following tools are required but not found:${NC}"
    for tool in "${MISSING_TOOLS[@]}"; do
        echo -e "${RED}  - $tool${NC}"
    done
    echo -e "${RED}Please install them before proceeding.${NC}"
    echo -e "${RED}Note: Neo4j is now MANDATORY for this system.${NC}"
    echo -e "${RED}#################################################${NC}\n"
    exit 1
fi

# 1. Python Environment
if command -v conda &> /dev/null; then
    echo "📦 Creating Conda environment 'ubs-hackathon'..."
    conda env create -f environment.yml --force
    echo "✅ Conda environment created."
    echo "💡 Run 'conda activate ubs-hackathon' before starting."
else
    echo "⚠️ Conda not found. Creating a standard Python venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    echo "✅ Python venv created and dependencies installed."
fi

# 2. Frontend Dependencies
if [ -d "frontend" ]; then
    echo "🌐 Installing frontend dependencies..."
    cd frontend
    if command -v pnpm &> /dev/null; then
        pnpm install
    else
        npm install
    fi
    cd ..
    echo "✅ Frontend dependencies installed."
fi

echo "✨ Environment initialization complete!"
