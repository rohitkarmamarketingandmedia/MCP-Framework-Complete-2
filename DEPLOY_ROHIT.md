# 🚀 ROHIT DEPLOY GUIDE - MCP Framework v4.5

## READ THIS FIRST
This is the step-by-step guide. Follow it exactly.

---

## BEFORE YOU START

Run the preflight check to make sure everything is ready:

```bash
cd mcp-framework
python scripts/preflight_check.py
```

You should see: **🚀 READY TO DEPLOY!**

If you see errors, fix them first.

---

## OPTION A: Deploy to Render (Recommended)

### Step 1: Push Code to GitHub

```bash
cd mcp-framework
git add .
git commit -m "Deploy v4.5"
git push origin main
```

### Step 2: Go to Render

1. Open https://render.com
2. Log in (or create account)
3. Click **"New +"** button (top right)
4. Select **"Blueprint"**

### Step 3: Connect GitHub

1. Click "Connect GitHub"
2. Authorize Render
3. Find and select the `mcp-framework` repo
4. Click "Connect"

### Step 4: Set Environment Variables

Render will show you a list of env vars. Set these:

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | `sk-...` (get from OpenAI dashboard) |
| `ADMIN_EMAIL` | `michael@karmamarketing.com` |
| `ADMIN_PASSWORD` | `KarmaAdmin2024!` (or whatever) |
| `CORS_ORIGINS` | `*` for now, change later to actual domain |

**Leave everything else as default.**

### Step 5: Deploy

Click **"Apply"** or **"Create Blueprint"**

Wait 3-5 minutes. Watch the logs.

### Step 6: Verify

1. Go to: `https://mcp-framework.onrender.com/health`
   - Should show: `{"status": "healthy", "version": "4.5.0"}`

2. Go to: `https://mcp-framework.onrender.com/admin`
   - Login with `ADMIN_EMAIL` / `ADMIN_PASSWORD`

**DONE!**

---

## OPTION B: Manual Deploy (Any Host)

### Requirements
- Python 3.11+
- PostgreSQL 14+
- Server with 512MB+ RAM

### Step 1: Clone and Setup

```bash
git clone <repo-url> mcp-framework
cd mcp-framework
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Create PostgreSQL Database

```sql
CREATE DATABASE mcp_framework;
CREATE USER mcp_admin WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE mcp_framework TO mcp_admin;
```

### Step 3: Set Environment Variables

Create `.env` file:

```bash
# COPY THIS EXACTLY - then fill in values
DATABASE_URL=postgresql://mcp_admin:your-password@localhost:5432/mcp_framework
SECRET_KEY=run-this-to-generate-python-c-import-secrets-print-secrets-token-hex-32
JWT_SECRET_KEY=run-this-to-generate-another-one
OPENAI_API_KEY=sk-your-key-here
ADMIN_EMAIL=michael@karmamarketing.com
ADMIN_PASSWORD=YourSecurePassword123!
CORS_ORIGINS=*
FLASK_ENV=production
ENABLE_SCHEDULER=true
```

**To generate secret keys:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Step 4: Initialize Database

```bash
python -c "
from app import create_app
from app.database import db
app = create_app()
with app.app_context():
    db.create_all()
    print('Database tables created')
"
```

### Step 5: Create Admin User

```bash
python scripts/create_admin.py
```

### Step 6: Run Server

**Development:**
```bash
python run.py
```

**Production (with gunicorn):**
```bash
gunicorn run:app --bind 0.0.0.0:8000 --workers 2
```

### Step 7: Verify

Open browser: `http://localhost:8000/admin`

---

## TROUBLESHOOTING

### "ModuleNotFoundError"
```bash
pip install -r requirements.txt
```

### "Database connection refused"
- Check PostgreSQL is running
- Check DATABASE_URL is correct
- Check username/password

### "No admin user"
```bash
python scripts/create_admin.py
```

### "CORS error in browser"
Set `CORS_ORIGINS=*` temporarily, then set to actual domain.

### "OpenAI error"
- Check `OPENAI_API_KEY` is set
- Check you have credits in OpenAI account

### "500 Internal Server Error"
Check logs:
```bash
# Render: Dashboard → Logs
# Local: Check terminal output
```

---

## IMPORTANT URLS

| URL | What It Is |
|-----|------------|
| `/health` | Health check - should return "healthy" |
| `/admin` | Admin panel - login here first |
| `/agency` | Main dashboard - see all clients |
| `/intake` | Create new clients |
| `/api` | API info |

---

## AFTER DEPLOY CHECKLIST

- [ ] Can access `/health` endpoint
- [ ] Can login to `/admin`
- [ ] AI Agents tab shows 7 agents
- [ ] Can create test client in `/intake`
- [ ] Test client appears in `/agency`

---

## NEED HELP?

1. Check the logs first
2. Run validation: `python scripts/validate_production.py`
3. Check DATABASE_URL and OPENAI_API_KEY are set

---

**Version:** 4.5.0
**Last Updated:** November 2024
