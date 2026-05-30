#!/bin/bash
set -e

echo "======================================================"
echo "    Fixago RAG - Initial Build & Setup Script       "
echo "======================================================"

echo ""
echo "[1/6] Initializing and updating git submodules..."
git submodule update --init --recursive

echo ""
echo "[2/6] Building cheesebrain..."
make cheesebrain

echo ""
echo "[3/6] Building pomaidb..."
make pomaidb

echo ""
echo "[4/5] Building pomaicache..."
make pomaicache

echo ""
echo "[5/5] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask requests waitress

echo ""
echo "======================================================"
echo "  All components built successfully!                  "
echo "======================================================"
echo "To start the RAG server, you can run:"
echo "  source venv/bin/activate"
echo "  python server.py"
echo "======================================================"
