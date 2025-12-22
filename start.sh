#!/bin/bash

# Navigate to backend and start FastAPI
echo "Starting Backend Server..."
cd backend
source venv/bin/activate
python main.py &
BACKEND_PID=$!

echo "Backend started on http://localhost:8000"
echo "To use the app, open: file://$(pwd)/../frontend/index.html in your browser"
echo "Press Ctrl+C to stop the backend."

# Wait for backend
wait $BACKEND_PID
