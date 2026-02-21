#!/bin/bash
# System Lock Guard - Launcher (macOS / Linux)

echo "================================================"
echo "         System Lock Guard - Launcher"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo "Install it via: sudo apt install python3  OR  brew install python3"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet 2>/dev/null || \
    python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo ""

# Parse arguments
if [ "$1" == "--test" ]; then
    echo "[TEST MODE] Keyboard will be blocked immediately!"
    echo ""
    python3 "$SCRIPT_DIR/lock_guard.py" --test
elif [ "$1" == "--status" ]; then
    python3 "$SCRIPT_DIR/lock_guard.py" --status
else
    echo "Starting Lock Guard..."
    echo "To stop: Press Ctrl+C"
    echo ""
    python3 "$SCRIPT_DIR/lock_guard.py"
fi
