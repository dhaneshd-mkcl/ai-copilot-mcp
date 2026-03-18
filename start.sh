#!/usr/bin/env bash
set -e

echo "⚡ AI Coding Copilot - Startup"
echo "=============================="

# Backend
echo "📦 Starting backend..."
cd backend
# Assume venv is handled or use system python if preferred, 
# but start.sh usually manages the background process.
source .venv/bin/activate 2>/dev/null || echo "  ⚠️ No .venv found, using system python"
python app.py &
BACKEND_PID=$!
echo "  ✓ Backend started (PID $BACKEND_PID)"
cd ..

# Frontend
echo "🎨 Starting frontend..."
cd frontend

echo ""
echo "🚀 Services initialized:"
echo "  - Backend: http://localhost:8000"
echo "  - Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers"

trap "echo 'Stopping servers...'; kill $BACKEND_PID 2>/dev/null; exit" SIGINT SIGTERM

npm run dev
