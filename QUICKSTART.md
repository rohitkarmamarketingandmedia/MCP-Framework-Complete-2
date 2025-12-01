# 🚀 ROHIT: Deploy MCP in 10 Minutes

## YOU NEED:
- GitHub account
- Render account (free to start)
- OpenAI API key

---

## DO THIS:

### 1. PUSH TO GITHUB
```bash
cd mcp-framework
git init
git add .
git commit -m "Initial"
git remote add origin https://github.com/YOUR_USERNAME/mcp-framework.git
git push -u origin main
```

### 2. GO TO RENDER
- https://render.com → Sign up/Login
- Click **"New +"** → **"Blueprint"**
- Connect GitHub → Select `mcp-framework` repo

### 3. SET THESE 4 VARIABLES
| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | `sk-...` from OpenAI |
| `ADMIN_EMAIL` | `michael@karmamarketing.com` |
| `ADMIN_PASSWORD` | `KarmaAdmin2024!` |
| `CORS_ORIGINS` | `*` |

### 4. CLICK DEPLOY
Wait 3-5 minutes.

### 5. TEST IT
- Go to: `https://YOUR-APP.onrender.com/health`
- Should see: `{"status": "healthy"}`
- Go to: `https://YOUR-APP.onrender.com/admin`
- Login with the email/password you set

---

## ✅ DONE!

---

## IF SOMETHING BREAKS:

**"Application error"**
→ Check Render logs (Dashboard → Logs)

**"Invalid credentials"**
→ Check ADMIN_EMAIL and ADMIN_PASSWORD are set in Render env vars

**"OpenAI error"**
→ Check OPENAI_API_KEY is correct and has credits

**Can't connect to database**
→ Render creates the database automatically via render.yaml. If it didn't, create a PostgreSQL database manually and set DATABASE_URL.

---

## URLS AFTER DEPLOY:

| URL | What |
|-----|------|
| `/health` | Check if running |
| `/admin` | Login here first |
| `/agency` | Main dashboard |
| `/intake` | Add new clients |
| `/portal` | Client portal |

---

## OPTIONAL LATER:

Add these env vars for extra features:

```
# CallRail (call tracking)
CALLRAIL_API_KEY=xxx
CALLRAIL_ACCOUNT_ID=xxx

# N8N (automation - see N8N_SETUP.md)
WEBHOOK_URL_DEFAULT=https://your-n8n.com/webhook/mcp-events
```

---

## QUESTIONS?

1. Check Render logs first
2. Run: `python scripts/validate_production.py`
3. Text Michael

---

**v5.5.1** | Takes 10 minutes | You got this 💪
