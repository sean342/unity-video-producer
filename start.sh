#!/bin/bash
# Unity Video Producer — Start Script
# Run this on the Cloudways server to start the app

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Install backend dependencies
echo "Installing backend dependencies..."
cd backend
pip3 install -r requirements.txt
cd ..

# Build frontend (if Node.js is available)
if command -v node &> /dev/null; then
    echo "Building frontend..."
    cd frontend
    npm install
    npm run build
    cd ..
fi

# Create outputs directory
mkdir -p backend/outputs

# Start the FastAPI server
echo "Starting Unity Video Producer on port ${APP_PORT:-8000}..."
cd backend
uvicorn main:app \
    --host "${APP_HOST:-0.0.0.0}" \
    --port "${APP_PORT:-8000}" \
    --workers 2 \
    --log-level info
