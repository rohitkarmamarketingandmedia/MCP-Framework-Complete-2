# MCP Framework Deployment Guide

## Prerequisites

- Python 3.11+
- PostgreSQL 14+ (production)
- Node.js 18+ (for optional build tools)
- Render.com account (or similar PaaS)

## Environment Variables

```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=your-secret-key-here
FLASK_ENV=production

# AI Services
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# SEO Data (optional)
SEMRUSH_API_KEY=...

# Email (optional)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
```

## Local Development

```bash
# Clone and setup
git clone <repo>
cd mcp-framework

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your values

# Initialize database
flask db upgrade

# Run development server
python run.py
# or
flask run --debug
```

## Render.com Deployment

### 1. Create Web Service
- Connect GitHub repo
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn run:app`
- Environment: Python 3

### 2. Create PostgreSQL Database
- Plan: Starter or higher
- Copy Internal Database URL

### 3. Set Environment Variables
- Add all required variables from above
- Set `DATABASE_URL` to internal database URL

### 4. Deploy
- Push to main branch triggers auto-deploy
- Or manual deploy from dashboard

## Database Migrations

```bash
# Create new migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Rollback one migration
flask db downgrade
```

## Deployment Checklist

- [ ] All tests passing
- [ ] Version bumped in `app/__init__.py`
- [ ] CHANGELOG.md updated
- [ ] Environment variables set
- [ ] Database migrations applied
- [ ] Static files collected
- [ ] Health check endpoint responding

## Health Check

```bash
curl https://your-app.onrender.com/api/auth/health
# Expected: {"status": "healthy", "version": "5.5.41"}
```

## Rollback Procedure

1. In Render dashboard, go to Events
2. Find last working deployment
3. Click "Rollback to this deploy"
4. Verify health check
5. If database changes, run `flask db downgrade`

## Monitoring

- Render provides basic metrics (CPU, memory, requests)
- Add Sentry for error tracking (optional)
- Add Datadog/New Relic for APM (optional)

## Scaling

- Render auto-scales based on plan
- For high traffic:
  - Upgrade to Pro plan
  - Add Redis for caching
  - Consider CDN for static assets
