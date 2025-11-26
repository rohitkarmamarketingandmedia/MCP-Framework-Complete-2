# 🚀 DEPLOY v3.5 - FOR ROHIT

## STEP 1: Replace files in your repo

Copy ALL files from this zip into your existing `mcp-framework` GitHub repo folder, replacing everything.

## STEP 2: Push to GitHub

```bash
cd your-mcp-framework-folder
git add .
git commit -m "v3.5 - Client dashboard + internal linking"
git push
```

That's it. Render auto-deploys from GitHub.

---

## STEP 3: Add Environment Variable (ONE TIME ONLY)

If you haven't already, go to Render Dashboard:

1. Click your `mcp-framework` service
2. Go to **Environment** tab
3. Add these if missing:

| Key | Value |
|-----|-------|
| `OPENAI_API_KEY` | `sk-...` (your OpenAI key) |
| `SEMRUSH_API_KEY` | `be25762c17edc78b7a5aabda2b41e43f` |

4. Click **Save Changes**

---

## STEP 4: Wait for Deploy

Watch the Render dashboard. Deploy takes ~2-3 minutes.

Build log should show:
```
✓ Database tables created/verified
✓ service_pages column already exists (or "Added service_pages column")
✓ Admin user exists (or "Default admin created")
=== Build Complete ===
```

---

## STEP 5: Test

Visit these URLs (replace with your actual Render URL):

- `https://mcp-framework.onrender.com/health` → Should show `{"status": "healthy"}`
- `https://mcp-framework.onrender.com/intake` → Intake dashboard
- `https://mcp-framework.onrender.com/client-dashboard` → Client demo view

---

## Login Credentials

```
Email: admin@mcp.local
Password: admin123
```

---

## What's New in v3.5

1. **Client Dashboard** (`/client-dashboard`) - Show clients their content
2. **Internal Linking** - Auto-injects service page links into blogs
3. **Service Pages API** - Manage internal link targets per client

---

## If Something Breaks

1. Check Render logs for errors
2. Make sure OPENAI_API_KEY and SEMRUSH_API_KEY are set
3. Try "Manual Deploy" → "Clear build cache & deploy"

---

## Quick Test After Deploy

```bash
# Get token
curl -X POST https://YOUR-URL.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@mcp.local","password":"admin123"}'

# Should return: {"token": "eyJ..."}
```
