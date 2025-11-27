#!/bin/bash

# ============================================
# MCP Framework - One-Command Setup
# Run: bash setup.sh
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Banner
echo -e "${PURPLE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║               MCP Framework 3.0 Setup                        ║"
echo "║            Marketing Control Platform                        ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ============================================
# Step 1: Check Python
# ============================================
echo -e "${CYAN}[1/7] Checking Python...${NC}"

if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
    PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
    
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        echo -e "${GREEN}✓ Python $PY_VERSION found${NC}"
        
        # Warn about bleeding edge Python versions
        if [ "$PY_MINOR" -ge 14 ]; then
            echo ""
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}  ⚠️  WARNING: Python $PY_VERSION is bleeding edge${NC}"
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo ""
            echo -e "  Some packages may not have pre-built wheels for Python $PY_VERSION."
            echo -e "  If installation fails, use Python 3.12 (stable) instead:"
            echo ""
            echo -e "  ${CYAN}macOS:${NC}"
            echo -e "    brew install python@3.12"
            echo -e "    /opt/homebrew/bin/python3.12 -m venv venv"
            echo ""
            echo -e "  ${CYAN}Linux:${NC}"
            echo -e "    sudo apt install python3.12 python3.12-venv"
            echo -e "    python3.12 -m venv venv"
            echo ""
            read -p "  Continue with Python $PY_VERSION anyway? (y/N): " CONTINUE_BETA
            if [[ ! "$CONTINUE_BETA" =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Aborted. Install Python 3.12 and try again.${NC}"
                exit 0
            fi
            echo ""
        fi
    else
        echo -e "${RED}✗ Python 3.10+ required (found $PY_VERSION)${NC}"
        echo "  Install: https://www.python.org/downloads/"
        exit 1
    fi
else
    echo -e "${RED}✗ Python 3 not found${NC}"
    echo "  Install: https://www.python.org/downloads/"
    exit 1
fi

# ============================================
# Step 2: Create Virtual Environment
# ============================================
echo -e "${CYAN}[2/7] Setting up virtual environment...${NC}"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${YELLOW}• Virtual environment already exists${NC}"
fi

# Activate
source venv/bin/activate 2>/dev/null || . venv/bin/activate

# ============================================
# Step 3: Install Dependencies
# ============================================
echo -e "${CYAN}[3/7] Installing dependencies...${NC}"

pip install --upgrade pip --quiet

# Try to install dependencies
if pip install -r requirements.txt; then
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo ""
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  ✗ Dependency installation failed${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  This often happens with Python 3.14+ (bleeding edge)."
    echo ""
    echo -e "  ${CYAN}Fix: Use Python 3.12 instead${NC}"
    echo ""
    echo -e "  ${YELLOW}macOS:${NC}"
    echo -e "    brew install python@3.12"
    echo -e "    rm -rf venv"
    echo -e "    /opt/homebrew/bin/python3.12 -m venv venv"
    echo -e "    source venv/bin/activate"
    echo -e "    pip install -r requirements.txt"
    echo ""
    echo -e "  ${YELLOW}Linux:${NC}"
    echo -e "    sudo apt install python3.12 python3.12-venv"
    echo -e "    rm -rf venv"
    echo -e "    python3.12 -m venv venv"
    echo -e "    source venv/bin/activate"
    echo -e "    pip install -r requirements.txt"
    echo ""
    exit 1
fi

# ============================================
# Step 4: Configure Environment
# ============================================
echo -e "${CYAN}[4/7] Configuring environment...${NC}"

if [ -f ".env" ]; then
    echo -e "${YELLOW}• .env file exists, checking configuration...${NC}"
    source .env 2>/dev/null || true
else
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env file${NC}"
fi

# Generate secret key if not set
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "your-secret-key-change-in-production" ]; then
    NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
    else
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
    fi
    echo -e "${GREEN}✓ Generated secure SECRET_KEY${NC}"
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
    read -p "  Paste your OpenAI API key (starts with sk-): " OPENAI_KEY
    
    if [ -n "$OPENAI_KEY" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$OPENAI_KEY/" .env
        else
            sed -i "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$OPENAI_KEY/" .env
        fi
        echo -e "${GREEN}✓ OpenAI API key saved${NC}"
    else
        echo -e "${YELLOW}⚠ Skipped - you'll need to add this to .env later${NC}"
    fi
fi

# ============================================
# Step 5: Create Data Directories
# ============================================
echo -e "${CYAN}[5/7] Creating data directories...${NC}"

mkdir -p data/{users,clients,content,social,schemas,campaigns}
echo -e "${GREEN}✓ Data directories ready${NC}"

# ============================================
# Step 6: Create Admin User
# ============================================
echo -e "${CYAN}[6/7] Setting up admin user...${NC}"

# Check if admin exists
ADMIN_EXISTS=$(python3 -c "
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///mcp_framework.db')
from app import create_app
from app.database import db
from app.models.db_models import DBUser, UserRole
from app.services.db_service import DataService

app = create_app('development')
with app.app_context():
    db.create_all()
    ds = DataService()
    users = ds.get_all_users()
    admins = [u for u in users if u.role == UserRole.ADMIN]
    print('yes' if admins else 'no')
" 2>/dev/null || echo "no")

if [ "$ADMIN_EXISTS" = "yes" ]; then
    echo -e "${YELLOW}• Admin user already exists${NC}"
else
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  Create Admin Account${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    read -p "  Admin email: " ADMIN_EMAIL
    read -p "  Admin name: " ADMIN_NAME
    read -s -p "  Admin password: " ADMIN_PASS
    echo ""
    
    python3 -c "
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///mcp_framework.db')
from app import create_app
from app.database import db
from app.models.db_models import DBUser, UserRole
from app.services.db_service import DataService

app = create_app('development')
with app.app_context():
    db.create_all()
    admin = DBUser(
        email='$ADMIN_EMAIL',
        name='$ADMIN_NAME',
        password='$ADMIN_PASS',
        role=UserRole.ADMIN
    )
    ds = DataService()
    ds.save_user(admin)
    print('SUCCESS')
" && echo -e "${GREEN}✓ Admin user created${NC}" || echo -e "${RED}✗ Failed to create admin${NC}"
fi

# ============================================
# Step 7: Verify Installation
# ============================================
echo -e "${CYAN}[7/7] Verifying installation...${NC}"

python3 -c "
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///mcp_framework.db')
from app import create_app
from app.models.db_models import DBUser, DBClient, DBBlogPost
from app.services.db_service import DataService
app = create_app('development')
with app.app_context():
    print('SUCCESS')
" && echo -e "${GREEN}✓ All systems operational${NC}" || {
    echo -e "${RED}✗ Verification failed${NC}"
    exit 1
}

# ============================================
# Done!
# ============================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}║                    ✓ SETUP COMPLETE!                         ║${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}To start the server:${NC}"
echo ""
echo -e "    ${YELLOW}bash start.sh${NC}"
echo ""
echo -e "  Or manually:"
echo ""
echo -e "    source venv/bin/activate"
echo -e "    python run.py"
echo ""
echo -e "  Then open: ${BLUE}http://localhost:5000${NC}"
echo ""
