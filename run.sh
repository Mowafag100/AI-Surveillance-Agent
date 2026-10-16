#!/usr/bin/env bash
set -e

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

if [ "$1" == "web" ]; then
    echo "🚀 Starting AI Surveillance Agent..."
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "Usage: ./run.sh web"
fi
