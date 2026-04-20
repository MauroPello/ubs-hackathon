#!/bin/bash
set -e

echo "🚀 Initializing environment..."

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
