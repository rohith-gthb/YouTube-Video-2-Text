#!/bin/bash

# Get absolute path to this script's directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "========================================"
echo "    YouTube Video 2 Text System       "
echo "========================================"

# Check if venv exists
if [ ! -d "$DIR/backend/venv" ]; then
    echo "Error: Virtual environment not found in $DIR/backend/venv"
    echo "Please run: cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "Starting Backend Server..."
cd "$DIR/backend"
# Run backend using the venv python directly
./venv/bin/python main.py &
BACKEND_PID=$!

echo "----------------------------------------"
echo "Backend started on http://localhost:8000"
echo "Frontend available at: file://$DIR/frontend/index.html"
echo "----------------------------------------"
echo "Press Ctrl+C to stop the services."

# Trap SIGINT (Ctrl+C) to kill backend
trap "kill $BACKEND_PID; exit" SIGINT

# Wait for backend
wait $BACKEND_PID
