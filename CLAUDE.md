# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

MCP Framework is an AI-powered SEO content automation platform (Marketing Control Platform) for agencies. It generates SEO-optimized content, manages multi-tenant clients, publishes to WordPress/GBP/social, tracks rankings, and monitors competitors — all through a Flask REST API with 7 vanilla-JS dashboard UIs.

**Current version:** 5.5.191 (tracked in `app/__init__.py`)

## Commands

```bash
# Development setup
bash setup.sh                        # Automated: creates venv, installs deps, configures .env
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # Then fill in API keys

# Run development server (auto-selects port 5000–8080)
python run.py

# Docker (local dev stack with PostgreSQL)
docker-compose up -d

# Tests
python -m pytest tests/ -v           # Unit tests (21 tests in tests/test_models.py)
python test_all.py                   # Full test suite
python test_smoke.py                 # Smoke tests

# Validation / preflight
python scripts/validate_production.py
python scripts/preflight_check.py

# Bootstrap first admin user
python scripts/create_admin.py
```

## Architecture

### App Factory & Startup (`app/__init__.py`)
`create_app()` is the single entry point that wires everything together:
1. Configures Flask, CORS, rate limiting, proxy fix
2. Initializes SQLAlchemy and runs `db.create_all()` plus **inline column migrations** (no Alembic — new columns are added directly in this file)
3. Registers all 34 route blueprints
4. Starts APScheduler with 9 background jobs

When adding new database columns, add them to the inline migration block in `create_app()` (see existing pattern with `try: db.session.execute(text("ALTER TABLE..."))` blocks).

### Request Flow
All API routes require JWT bearer tokens (RS256, stored in localStorage on the frontend). Role hierarchy: `ADMIN > MANAGER > CLIENT > VIEWER`.

```
Frontend HTML/JS → POST /api/auth/login → JWT token
                 → All other /api/* endpoints with Authorization: Bearer <token>
```

### Route Blueprints (`app/routes/`)
34 blueprint files, each registered with an `/api/<name>` prefix. Key ones:
- `auth.py` — login, bootstrap admin, `/health`
- `content.py` — blog post generation (`POST /api/content/generate`)
- `clients.py` — multi-tenant client CRUD
- `publish.py` — WordPress REST API + GBP publishing
- `analytics.py` — GA4 data, rank tracking, competitor analysis
- `agents.py` — AI agent configuration (editable prompts, model, temperature)
- `scheduler.py` — job management
- `indexing.py` — Google Search Console indexing (new, unregistered — check `app/routes/__init__.py`)

### Service Layer (`app/services/`)
40+ services encapsulate all business logic. Key services:
- `ai_service.py` — content generation via Claude (primary) with OpenAI fallback; uses `litellm` for abstraction
- `seo_scoring_engine.py` — 100-point SEO scoring (keyword density, readability, structure)
- `scheduler_service.py` — APScheduler job definitions
- `gsc_service.py`, `indexing_service.py`, `indexnow_service.py` — new GSC/indexing services (currently unregistered)
- `semrush_service.py` — keyword research
- `gbp_service.py` — Google Business Profile integration

### Database (`app/models/db_models.py`)
SQLAlchemy models, SQLite in dev / PostgreSQL in production. Render auto-converts `postgres://` → `postgresql+psycopg://`. Core models: `DBUser`, `DBClient`, `DBBlogPost`, `DBSocialPost`, `DBCampaign`, `DBLead`, `DBReview`, `DBSchedule`, `DBClientInsight`.

### AI Agent System
7 configurable agents stored in the database (initialized in `build.sh`): `content_writer`, `review_responder`, `social_writer`, `seo_analyzer`, `competitor_analyzer`, `service_page_writer`, `intake_analyzer`. Each has an editable system prompt, model choice, and temperature setting — loaded dynamically at runtime from DB.

### Frontend Dashboards
7 standalone HTML files (Tailwind CSS + vanilla JS, no build step):
- `admin-dashboard.html` → `/admin`
- `agency-dashboard.html` → `/agency`
- `client-dashboard.html` → `/client/<id>`
- `intake-dashboard.html` → `/intake`
- `portal-dashboard.html` → `/portal`
- `elite-dashboard.html` → `/elite`

These make direct `fetch()` calls to the `/api/*` endpoints with JWT tokens stored in `localStorage`.

### Background Scheduler
9 APScheduler jobs defined in `app/services/scheduler_service.py`: content publishing, rank tracking, email digests, social auto-post, competitor monitoring, review checking, analytics sync, lead notifications. Job schedules are configurable via the admin UI.

## Key Environment Variables

See `.env.example` for the full list. Minimum required to run:
- `SECRET_KEY`, `JWT_SECRET_KEY` — Flask/JWT secrets
- `DATABASE_URL` — auto-linked on Render; SQLite used as fallback
- `ANTHROPIC_API_KEY` — primary AI provider
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — bootstrapped on first deploy via `build.sh`

## Deployment

- **Render.com:** `render.yaml` blueprint handles everything. `build.sh` runs on each deploy (installs fonts for PDF generation, runs column migrations, initializes AI agents and admin).
- **Docker:** `docker-compose.yml` for local dev; `Dockerfile` for production container (Python 3.11, Gunicorn + Gevent workers).
- **No Alembic** — migrations are raw SQL in `app/__init__.py` and `build.sh`.

## Current Uncommitted Work

The git status shows several new untracked files for a GSC/indexing autopilot feature:
- `app/routes/indexing.py` — new blueprint (needs registration in `app/routes/__init__.py`)
- `app/services/gsc_service.py`, `indexing_service.py`, `indexnow_service.py` — new services
- `docs/INDEXING_AUTOPILOT_SETUP.md` — setup documentation

And modifications to: `app/database.py`, `app/models/db_models.py`, `app/routes/__init__.py`, `app/services/scheduler_service.py`, `client-dashboard.html`.
