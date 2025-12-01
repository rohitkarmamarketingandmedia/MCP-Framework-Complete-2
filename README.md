# MCP Framework v5.5.1

**Marketing Control Platform** - AI-powered SEO content automation engine by Karma Marketing + Media.

## 🚀 DEPLOY NOW

| Guide | For |
|-------|-----|
| **`QUICKSTART.md`** | Deploy in 10 minutes (one page) |
| `DEPLOY_ROHIT.md` | Detailed step-by-step guide |
| `N8N_SETUP.md` | Add automation workflows |

## Overview

MCP Framework is a complete marketing automation platform that generates SEO-optimized content, manages social media, publishes to WordPress, tracks analytics, and provides AI-powered agents for content generation - all with a beautiful dashboard UI.

## 🎯 Client Value Focus (v5.5)

**Goal:** Make clients feel ABSOLUTE VALUE, build TRUST, and want to PAY MORE.

### Customer Intelligence Engine (NEW!)
**Turn every customer interaction into SEO content:**

```
📞 Calls + 💬 Chats + 📝 Forms  →  🧠 AI Analysis  →  📝 Auto-Content
```

- **Analyze** CallRail transcripts, chatbot conversations, lead forms
- **Extract** questions, pain points, keywords customers actually use
- **Generate** FAQ pages, blog posts, service page Q&A automatically
- **Schedule** content calendars based on real customer demand

### Client Experience
- **Health Score Report Card** - 100-point score clients instantly understand
- **3-Day Snapshot Reports** - Automated emails showing wins, activity, pipeline
- **CallRail Integration** - Call tracking, recordings, transcripts, hot leads
- **Activity Feed** - Show clients we're WORKING for them
- **Wins Celebration** - Highlight successes to build confidence

## Features

### Core
- **AI Content Generation** - Blog posts, landing pages with proper SEO structure (1800+ words)
- **AI Agent System** - 7 configurable AI agents with prompt editing via admin UI
- **Schema Markup** - JSON-LD generation for LocalBusiness, FAQ, Article, etc.
- **SEO Scoring** - 100-point scoring system with keyword density, internal linking, headings
- **Multi-tenant** - Client management with role-based access control
- **PostgreSQL Database** - Production-ready with full ORM models

### Publishing & Social
- **WordPress Publishing** - Direct REST API integration with Yoast SEO support
- **Social Auto-Post** - Multi-platform publishing (Facebook, Instagram, LinkedIn, GBP)
- **OAuth2 Integration** - Secure connection to all social platforms
- **AI Image Generation** - DALL-E, Stability AI, Replicate, Unsplash

### Analytics & Monitoring
- **Google Analytics 4** - Traffic and performance integration
- **Rank Tracking** - Daily keyword position monitoring with history
- **Competitor Monitoring** - Content changes, ranking battles, gap analysis
- **SEMRush Integration** - Keyword rankings and competitor data

### Client Experience
- **Client Portal** - Self-service dashboard for clients
- **Approval Workflow** - Content review, approve, request changes
- **Notification System** - 14 types with email digests and quiet hours
- **Lead Capture** - Forms, tracking, and GBP integration

### Operations
- **Background Scheduler** - 8 automated jobs (publishing, monitoring, digests)
- **Webhooks** - 12 event types for integrations
- **Audit Logging** - Full trail of all system changes
- **Review Management** - AI-powered review response generation

## Quick Start

### Option 1: Deploy to Render (Recommended)

See `DEPLOY_ROHIT.md` for step-by-step instructions.

```bash
# 1. Push to GitHub
git add . && git commit -m "Deploy" && git push

# 2. Go to render.com → New Blueprint → Connect repo

# 3. Set environment variables:
#    - OPENAI_API_KEY
#    - ADMIN_EMAIL
#    - ADMIN_PASSWORD

# 4. Click Deploy
```

### Option 2: Local Development

```bash
# Clone and setup
git clone <repo-url>
cd mcp-framework
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.production.example .env
# Edit .env with your values

# Run
python run.py
```

Server starts at `http://localhost:5000`

## Dashboards

| URL | Purpose |
|-----|---------|
| `/admin` | Admin panel - users, agents, settings, audit log |
| `/agency` | Agency command center - all clients overview |
| `/intake` | New client onboarding wizard |
| `/elite` | SEO monitoring dashboard |
| `/portal` | Client self-service portal |
| `/client` | Client content dashboard |

## AI Agents

The framework includes 7 configurable AI agents:

| Agent | Purpose |
|-------|---------|
| `content_writer` | SEO-optimized blog posts |
| `review_responder` | Professional review responses |
| `social_writer` | Platform-specific social posts |
| `seo_analyzer` | Keyword opportunity analysis |
| `competitor_analyzer` | Competitive intelligence |
| `service_page_writer` | Location/service landing pages |
| `intake_analyzer` | Client discovery analysis |

Edit prompts, models, and settings via `/admin` → AI Agents tab.

## API Endpoints (204 total)

### Core APIs

| Category | Endpoints |
|----------|-----------|
| Auth | `/api/auth/*` - Login, register, users |
| Content | `/api/content/*` - Blog generation |
| Clients | `/api/clients/*` - Client management |
| Social | `/api/social/*` - Social media |
| Schema | `/api/schema/*` - JSON-LD markup |
| Publish | `/api/publish/*` - WordPress, GBP |
| Analytics | `/api/analytics/*` - Traffic, rankings |
| Agents | `/api/agents/*` - AI agent config |
| Settings | `/api/settings/*` - System settings |
| Webhooks | `/api/webhooks/*` - Event triggers |

### Quick Examples

```bash
# Health check
curl https://your-app.onrender.com/health

# Login
curl -X POST https://your-app.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"yourpass"}'

# Generate blog post
curl -X POST https://your-app.onrender.com/api/content/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_123",
    "keyword": "roof repair sarasota",
    "geo": "Sarasota, FL",
    "industry": "roofing"
  }'
```

## Environment Variables

### Required

```env
DATABASE_URL=postgresql://...
SECRET_KEY=<generate-secure-key>
JWT_SECRET_KEY=<generate-secure-key>
OPENAI_API_KEY=sk-...
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=SecurePassword123!
```

### Optional

```env
ANTHROPIC_API_KEY=sk-ant-...
SEMRUSH_API_KEY=...
SENDGRID_API_KEY=SG....
CORS_ORIGINS=https://yourdomain.com
```

See `.env.production.example` for full list.

## Project Structure

```
mcp-framework/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Configuration
│   ├── database.py          # SQLAlchemy setup
│   ├── models/              # Database models (19 tables)
│   ├── routes/              # API endpoints (19 blueprints)
│   └── services/            # Business logic (23 services)
├── scripts/
│   ├── create_admin.py      # Create admin user
│   └── validate_production.py # Verify deployment
├── tests/                   # Test suite (21 tests)
├── *.html                   # Dashboard UIs (7 dashboards)
├── run.py                   # Development server
├── build.sh                 # Render build script
├── render.yaml              # Render blueprint
├── requirements.txt         # Python dependencies
├── DEPLOY_ROHIT.md          # Deployment guide
├── PRODUCTION.md            # Production docs
└── README.md                # This file
```

## System Stats

- **Version:** 5.5.1
- **Python Code:** 25,000+ lines
- **API Routes:** 319
- **Database Tables:** 21
- **AI Agents:** 7
- **Dashboards:** 7
- **Scheduler Jobs:** 9
- **Tests:** 21 passing

## Deployment

### Render (Recommended)

The `render.yaml` blueprint handles everything:
- PostgreSQL database
- Auto-generated secrets
- Health checks
- Auto-deploy from GitHub

### Docker

```bash
docker-compose up -d
```

### Manual

```bash
pip install -r requirements.txt
gunicorn run:app --bind 0.0.0.0:8000 --workers 2
```

## Scripts

```bash
# Create admin user
python scripts/create_admin.py

# Validate production deployment
python scripts/validate_production.py

# Run tests
python -m pytest tests/ -v
```

## License

Proprietary - Karma Marketing + Media

## Support

- **Quick Start:** `QUICKSTART.md` (10 min deploy)
- Deployment Guide: `DEPLOY_ROHIT.md`
- N8N Automation: `N8N_SETUP.md`
- Production Docs: `PRODUCTION.md`
