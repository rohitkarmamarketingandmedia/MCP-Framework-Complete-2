# MCP Framework - Render Deployment Guide

## One-Click Deploy

1. **Fork/Clone this repo to your GitHub**

2. **Go to Render Dashboard**
   - https://dashboard.render.com
   - Click "New" → "Blueprint"

3. **Connect your GitHub repo**
   - Select the repo
   - Render will detect the `render.yaml`

4. **Set Environment Variables**
   - `OPENAI_API_KEY` - Your OpenAI API key (required)
   - All other vars are auto-configured

5. **Deploy**
   - Click "Apply"
   - Wait ~5 minutes for first deploy

6. **Create Admin User**
   - Go to your service in Render dashboard
   - Click "Shell" tab
   - Run:
   ```bash
   python create_admin.py
   ```

7. **Done!**
   - Your app is live at `https://mcp-framework.onrender.com`

---

## Manual Deploy Steps

If you prefer not to use the Blueprint:

### 1. Create PostgreSQL Database

- Render Dashboard → New → PostgreSQL
- Name: `mcp-db`
- Plan: Starter (free)
- Save the Internal Database URL

### 2. Create Web Service

- Render Dashboard → New → Web Service
- Connect your repo
- Settings:
  - **Name:** mcp-framework
  - **Runtime:** Python 3
  - **Build Command:** `chmod +x build.sh && ./build.sh`
  - **Start Command:** `gunicorn run:app --bind 0.0.0.0:$PORT --workers 2`

### 3. Set Environment Variables

| Variable | Value |
|----------|-------|
| `FLASK_ENV` | production |
| `SECRET_KEY` | (click Generate) |
| `DATABASE_URL` | (paste from step 1) |
| `OPENAI_API_KEY` | sk-your-key-here |

### 4. Deploy

Click "Create Web Service"

---

## After Deployment

### Create Admin User

1. Go to Render Dashboard → Your Service → Shell
2. Run:
```bash
python create_admin.py
```
3. Enter email, name, and password when prompted

### Test the Deployment

```bash
# Health check
curl https://your-app.onrender.com/health

# Should return:
# {"status": "healthy", "version": "3.0.0"}
```

### Access the Dashboard

Open `https://your-app.onrender.com` in your browser.

---

## Costs

| Resource | Plan | Cost |
|----------|------|------|
| Web Service | Starter | Free (750 hrs/mo) |
| PostgreSQL | Starter | Free |
| **Total** | | **$0/month** |

Note: Free tier services spin down after 15 minutes of inactivity. First request after spin-down takes ~30 seconds.

For always-on service, upgrade to paid plan (~$7/month).

---

## Troubleshooting

### "Application failed to respond"
- Check logs in Render dashboard
- Ensure `DATABASE_URL` is set correctly
- Ensure `OPENAI_API_KEY` is valid

### "ModuleNotFoundError"
- Check build logs for pip install errors
- Ensure `requirements.txt` is in repo root

### Database connection errors
- Verify DATABASE_URL is set
- Check that PostgreSQL service is running
- Note: Render uses `postgres://` prefix, which we auto-convert to `postgresql://`

### OpenAI errors
- Verify API key is correct
- Check OpenAI account has credits
- Check API key has correct permissions

---

## Updating

To update your deployment:

1. Push changes to GitHub
2. Render auto-deploys (if autoDeploy is enabled)
3. Or manually trigger deploy from Render dashboard

---

## Custom Domain

1. Render Dashboard → Your Service → Settings
2. Scroll to "Custom Domains"
3. Add your domain
4. Update DNS as instructed
