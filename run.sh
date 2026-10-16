#!/usr/bin/env bash
set -e

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

if [ "$1" == "api" ]; then
    echo "🚀 Starting AI Surveillance API..."
    pip install fastapi "uvicorn[standard]"
    uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8090}" --reload
else
    echo "Usage: ./run.sh api"
fi
