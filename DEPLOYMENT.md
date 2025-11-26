# MCP Framework - Complete Deployment Guide

**For Rohit (and anyone not deeply familiar with Python)**

**Estimated Time: 30-45 minutes** for basic setup, 1-2 hours with all integrations configured.

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Create First Admin User](#4-create-first-admin-user)
5. [Test the API](#5-test-the-api)
6. [Create Your First Client](#6-create-your-first-client)
7. [Generate Content](#7-generate-content)
8. [Production Deployment](#8-production-deployment)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

### Install Python 3.10+

**Check if Python is installed:**
```bash
python3 --version
```

If not installed or version is below 3.10:

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

**macOS:**
```bash
brew install python@3.11
```

**Windows:**
Download from https://www.python.org/downloads/ and run installer.
**IMPORTANT:** Check "Add Python to PATH" during installation.

### Verify Installation
```bash
python3 --version   # Should show 3.10 or higher
pip3 --version      # Should show pip 21+
```

---

## 2. Installation

### Step 2.1: Get the Files

Put the `mcp-framework` folder on your server. If you received it as a zip:
```bash
unzip mcp-framework.zip
cd mcp-framework
```

### Step 2.2: Create Virtual Environment

This keeps dependencies isolated (recommended):
```bash
python3 -m venv venv
```

### Step 2.3: Activate Virtual Environment

**Linux/macOS:**
```bash
source venv/bin/activate
```

**Windows (Command Prompt):**
```bash
venv\Scripts\activate
```

**Windows (PowerShell):**
```bash
.\venv\Scripts\Activate.ps1
```

You should see `(venv)` at the start of your command prompt now.

### Step 2.4: Install Dependencies

```bash
pip install -r requirements.txt
```

**Expected output:** A bunch of "Successfully installed..." messages. Should take 1-2 minutes.

### Step 2.5: Verify Installation

```bash
python -c "from app import create_app; print('✅ Installation successful!')"
```

If you see `✅ Installation successful!` - move to the next step.

---

## 3. Configuration

### Step 3.1: Create Environment File

```bash
cp .env.example .env
```

### Step 3.2: Edit .env File

Open `.env` in any text editor (nano, vim, VS Code, Notepad++):

```bash
nano .env   # Linux/macOS
notepad .env   # Windows
```

### Step 3.3: Required Settings (Minimum to Run)

These are the **only required** settings to get started:

```env
# Generate a random secret key (or make up a long random string)
SECRET_KEY=your-random-string-at-least-32-characters-long

# OpenAI API key for content generation
OPENAI_API_KEY=sk-your-openai-api-key-here
```

**How to get OpenAI API Key:**
1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy and paste into .env

### Step 3.4: Optional Settings (Add Later)

These enable additional features but aren't required to start:

| Setting | What It Does | How to Get |
|---------|--------------|------------|
| `SEMRUSH_API_KEY` | Keyword rankings | SEMrush dashboard → API |
| `WP_BASE_URL` | WordPress publishing | Your client's site URL |
| `WP_APP_PASSWORD` | WordPress auth | WP Admin → Users → App Passwords |
| `GA4_PROPERTY_ID` | Analytics | Google Analytics → Admin → Property Settings |

Save and close the file.

---

## 4. Create First Admin User

**This is critical** - you need an admin user to access the API.

### Step 4.1: Run the Setup Script

```bash
python setup_admin.py
```

**Wait - that file doesn't exist!** Let me create it for you:

### Step 4.1 (Alternative): Create Admin Manually

Run this in your terminal:

```bash
python -c "
from app.services.data_service import DataService
from app.models.user import create_admin_user

# Create admin user
admin = create_admin_user(
    email='admin@karmamarketing.com',
    name='Admin User', 
    password='ChangeMe123!'
)

# Save to database
ds = DataService()
ds.save_user(admin)

print('✅ Admin user created!')
print(f'   Email: {admin.email}')
print(f'   Password: ChangeMe123!')
print(f'   User ID: {admin.id}')
print('')
print('⚠️  CHANGE THIS PASSWORD after first login!')
"
```

**Expected output:**
```
✅ Admin user created!
   Email: admin@karmamarketing.com
   Password: ChangeMe123!
   User ID: user_abc123def456
```

---

## 5. Test the API

### Step 5.1: Start the Server

```bash
python run.py
```

**Expected output:**
```
╔══════════════════════════════════════════════════════════════╗
║                    MCP Framework v3.0                        ║
║              Marketing Control Platform                      ║
║                  by Karma Marketing                          ║
╠══════════════════════════════════════════════════════════════╣
║  Server: http://localhost:5000                               ║
║  Health: http://localhost:5000/health                        ║
║  API:    http://localhost:5000/api                           ║
╚══════════════════════════════════════════════════════════════╝
```

**Leave this terminal running.** Open a NEW terminal for the next steps.

### Step 5.2: Test Health Endpoint

Open new terminal and run:
```bash
curl http://localhost:5000/health
```

**Expected output:**
```json
{"status": "healthy", "version": "3.0.0"}
```

### Step 5.3: Login and Get Token

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@karmamarketing.com", "password": "ChangeMe123!"}'
```

**Expected output:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...(long string)",
  "user": {
    "id": "user_abc123",
    "email": "admin@karmamarketing.com",
    "name": "Admin User",
    "role": "admin"
  }
}
```

**Copy that token** - you'll need it for all API calls.

### Step 5.4: Save Token as Variable (Makes Life Easier)

```bash
export TOKEN="eyJhbGciOiJIUzI1NiIs...(paste your full token here)"
```

Now you can use `$TOKEN` in commands instead of pasting the whole thing.

---

## 6. Create Your First Client

```bash
curl -X POST http://localhost:5000/api/clients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "ABC Roofing",
    "industry": "roofing",
    "geo": "Sarasota, FL",
    "website_url": "https://abcroofing.com",
    "phone": "(941) 555-1234",
    "primary_keywords": ["roof repair sarasota", "roofing company sarasota"],
    "service_areas": ["Sarasota", "Bradenton", "Venice"],
    "tone": "professional"
  }'
```

**Expected output:**
```json
{
  "message": "Client created successfully",
  "client": {
    "id": "client_abc123def456",
    "business_name": "ABC Roofing",
    ...
  }
}
```

**Save that client_id** - you need it for content generation.

---

## 7. Generate Content

### Generate a Blog Post

```bash
curl -X POST http://localhost:5000/api/content/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_abc123def456",
    "keyword": "roof repair sarasota",
    "geo": "Sarasota, FL",
    "industry": "roofing",
    "word_count": 1200,
    "include_faq": true
  }'
```

**This takes 30-60 seconds** (AI is generating content).

**Expected output:**
```json
{
  "success": true,
  "content": {
    "id": "content_xyz789",
    "title": "Expert Roof Repair in Sarasota, FL...",
    "body": "<h1>Professional Roof Repair Services in Sarasota, FL</h1>...",
    "meta_title": "Roof Repair Sarasota FL | Expert Roofing Services",
    "meta_description": "Need roof repair in Sarasota? Our expert team provides...",
    ...
  },
  "seo_score": {
    "total": 85,
    "checks": {...}
  }
}
```

**🎉 Congratulations!** The framework is working.

---

## 8. Production Deployment

### Option A: Simple (Direct Python)

For a small/medium traffic site:

```bash
# Install production server
pip install gunicorn

# Run with 4 workers
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app
```

### Option B: Docker (Recommended)

```bash
# Build and start
docker-compose up -d

# Check it's running
docker-compose ps

# View logs
docker-compose logs -f
```

### Option C: Docker + Nginx (Production)

```bash
docker-compose --profile with-nginx up -d
```

This gives you:
- SSL/HTTPS support
- Rate limiting
- Static file caching
- Reverse proxy

---

## 9. Troubleshooting

### "ModuleNotFoundError: No module named 'xyz'"

**Fix:** You forgot to activate the virtual environment or install dependencies.
```bash
source venv/bin/activate  # Activate venv
pip install -r requirements.txt  # Install deps
```

### "Connection refused" when calling API

**Fix:** The server isn't running. Start it:
```bash
python run.py
```

### "401 Unauthorized" on API calls

**Fix:** Your token is missing or expired.
1. Login again to get a new token
2. Make sure you're including `Authorization: Bearer YOUR_TOKEN` header

### "OpenAI API error" when generating content

**Fix:** Check your OpenAI API key in `.env`:
1. Make sure there are no extra spaces
2. Make sure the key starts with `sk-`
3. Check you have credits at https://platform.openai.com/usage

### "Permission denied" errors

**Fix:** File permission issues. Run:
```bash
chmod -R 755 .
mkdir -p data
chmod 777 data
```

### Server crashes after a while

**Fix:** You're running out of memory. Use gunicorn with fewer workers:
```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 run:app
```

### Content generation is slow (>60 seconds)

**Normal.** AI content generation takes time. If it's timing out, increase timeout:
```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 300 run:app
```

---

## Quick Reference

### API Base URL
```
http://localhost:5000/api
```

### Common Endpoints

| Action | Method | Endpoint |
|--------|--------|----------|
| Login | POST | `/api/auth/login` |
| Create Client | POST | `/api/clients` |
| Generate Blog | POST | `/api/content/generate` |
| Generate Social | POST | `/api/social/kit` |
| Publish to WP | POST | `/api/publish/wordpress` |

### Required Headers

```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

---

## Getting Help

1. Check this guide's troubleshooting section
2. Review the server logs: `docker-compose logs -f` or check terminal output
3. Contact Michael at Karma Marketing

---

## Summary Checklist

- [ ] Python 3.10+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with at least `SECRET_KEY` and `OPENAI_API_KEY`
- [ ] Admin user created
- [ ] Server starts without errors
- [ ] Health check returns `{"status": "healthy"}`
- [ ] Can login and get JWT token
- [ ] Can create a client
- [ ] Can generate content

**Once all boxes are checked, you're deployed!** 🚀
