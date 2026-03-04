#!/usr/bin/env bash
# ===================================================================
#  ServiceNow Ops Analyzer — Unix/macOS Quick Setup
# ===================================================================
set -e

echo ""
echo "=== ServiceNow Ops Analyzer Setup ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install via:"
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-venv"
    exit 1
fi

python3 --version

# Virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt -q

echo ""
echo "=== Running demo analysis ==="
echo ""
python main.py demo --tickets 300 --format all --output demo_report

echo ""
echo "=== Done! ==="
echo "  Open demo_report.html in your browser to see the report."
echo ""
