#!/bin/bash

# ============================================
# MCP Framework - Docker Setup
# Run: bash docker-setup.sh
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${PURPLE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MCP Framework - Docker Setup                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not found. Install from: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker found${NC}"

# Check docker-compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo -e "${RED}Docker Compose not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker Compose found${NC}"

# Create .env if needed
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env file${NC}"
    
    # Generate secret key
    NEW_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
    else
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
    fi
    echo -e "${GREEN}✓ Generated SECRET_KEY${NC}"
fi

# Check for OpenAI key
source .env 2>/dev/null || true

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-your-openai-key" ]; then
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  OpenAI API Key Required${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Get your key at: https://platform.openai.com/api-keys"
    echo ""
    read -p "  Paste your OpenAI API key: " OPENAI_KEY
    
    if [ -n "$OPENAI_KEY" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$OPENAI_KEY/" .env
        else
            sed -i "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$OPENAI_KEY/" .env
        fi
        echo -e "${GREEN}✓ OpenAI API key saved${NC}"
    fi
fi

# Build and run
echo ""
echo -e "${BLUE}Building Docker image...${NC}"
$COMPOSE_CMD build

echo ""
echo -e "${BLUE}Starting containers...${NC}"
$COMPOSE_CMD up -d

# Wait for health
echo ""
echo -e "${BLUE}Waiting for server to be ready...${NC}"
sleep 5

# Check health
for i in {1..10}; do
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    ✓ MCP IS RUNNING!                         ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Dashboard: ${BLUE}http://localhost:5000${NC}"
    echo ""
    echo -e "  Create admin user:"
    echo -e "    ${YELLOW}docker exec -it mcp-framework python setup_admin.py${NC}"
    echo ""
    echo -e "  View logs:"
    echo -e "    ${YELLOW}$COMPOSE_CMD logs -f${NC}"
    echo ""
    echo -e "  Stop:"
    echo -e "    ${YELLOW}$COMPOSE_CMD down${NC}"
    echo ""
else
    echo -e "${RED}Server failed to start. Check logs:${NC}"
    echo "  $COMPOSE_CMD logs"
    exit 1
fi
