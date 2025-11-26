#!/bin/bash

# ============================================
# MCP Framework - Start Server
# ============================================

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${PURPLE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    MCP Framework 3.0                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    echo "Virtual environment not found. Run: bash setup.sh"
    exit 1
fi

# Load environment
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo -e "${GREEN}Starting server...${NC}"
echo ""
echo -e "  Dashboard: ${BLUE}http://localhost:5000${NC}"
echo -e "  API:       ${BLUE}http://localhost:5000/api${NC}"
echo -e "  Health:    ${BLUE}http://localhost:5000/health${NC}"
echo ""
echo -e "  Press Ctrl+C to stop"
echo ""

python run.py
