# MCP Framework - Quick Start

## 🚀 Deploy to Render (Recommended for Production)

1. Push code to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect repo → Render auto-detects `render.yaml`
4. Set `OPENAI_API_KEY` environment variable
5. Deploy!

**Time: ~5 minutes | Cost: Free tier available**

See `RENDER.md` for detailed instructions.

---

## 💻 Local Development

### Mac/Linux

```bash
bash setup.sh
bash start.sh
```

### Windows

```cmd
setup.bat
start.bat
```

### Docker

```bash
bash docker-setup.sh
```

Open **http://localhost:5000** in your browser.

---

## What Happens During Setup

1. ✅ Checks your Python version
2. ✅ Creates virtual environment  
3. ✅ Installs all dependencies
4. ✅ Asks for your OpenAI API key
5. ✅ Creates your admin account
6. ✅ Verifies everything works

**Total time: ~5-10 minutes**

---

## After Setup

1. Login with the admin account you created
2. Paste a client interview transcript
3. Watch AI extract everything
4. Select topics to generate
5. Publish to WordPress

---

## Troubleshooting

**"Port 5000 already in use" (Mac)**
→ macOS uses port 5000 for AirPlay. The server will automatically use 5001 instead.

**"command not found: python3"**
→ Install Python: https://www.python.org/downloads/

**"ModuleNotFoundError"**
→ Run setup again: `bash setup.sh` (or `setup.bat` on Windows)

**"OpenAI API error"**
→ Check your API key in `.env` file. Make sure it starts with `sk-`

**"Cannot connect to server"**
→ Make sure you ran `bash start.sh` first

**"Database error"**
→ For local dev, SQLite is used by default. For production, set `DATABASE_URL`.

**Need more help?**
→ See `DEPLOYMENT.md` for local setup or `RENDER.md` for cloud deployment.

---

## Files You Might Need to Edit

| File | What It's For |
|------|---------------|
| `.env` | API keys (OpenAI, WordPress, etc.) |
| `render.yaml` | Render deployment config |

---

## Commands Reference

| What | Mac/Linux | Windows |
|------|-----------|---------|
| Setup | `bash setup.sh` | `setup.bat` |
| Start server | `bash start.sh` | `start.bat` |
| Run tests | `python test_smoke.py` | `python test_smoke.py` |
| Create admin | `python setup_admin.py` | `python setup_admin.py` |
| Docker | `bash docker-setup.sh` | (use Git Bash) |
