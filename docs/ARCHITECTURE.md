# MCP Framework Architecture

## Overview

The MCP (Marketing Control Platform) Framework is a comprehensive AI-powered content generation system for SEO blogs, social media, and client onboarding. Built with Flask backend and vanilla JavaScript frontend.

## Technology Stack

### Backend
- **Framework**: Flask (Python 3.11+)
- **Database**: PostgreSQL (production) / SQLite (development)
- **AI Integration**: OpenAI GPT-4, Anthropic Claude
- **SEO Data**: SEMRush API integration
- **Deployment**: Render.com compatible

### Frontend
- **CSS Framework**: Tailwind CSS (via CDN)
- **Icons**: Font Awesome
- **JavaScript**: Vanilla ES6+ (no framework)
- **Storage**: localStorage for drafts/state

## Directory Structure

```
mcp-framework/
├── app/
│   ├── __init__.py          # App factory, version info
│   ├── models/              # SQLAlchemy models
│   │   ├── client.py
│   │   ├── blog.py
│   │   ├── social_post.py
│   │   ├── lead.py
│   │   ├── review.py
│   │   └── ...
│   ├── routes/              # Flask blueprints
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── intake.py        # Client onboarding
│   │   ├── clients.py       # Client management
│   │   ├── blogs.py         # Blog generation
│   │   ├── social.py        # Social media
│   │   ├── leads.py         # Lead management
│   │   ├── reviews.py       # Review management
│   │   ├── seo.py           # SEO tools
│   │   ├── competitors.py   # Competitor analysis
│   │   └── ...
│   ├── services/            # Business logic
│   │   ├── ai_service.py    # AI content generation
│   │   ├── seo_service.py   # SEO analysis
│   │   ├── semrush_service.py
│   │   └── ...
│   └── templates/           # Jinja2 templates (minimal)
├── static/                  # Static assets
├── docs/                    # Documentation
├── tests/                   # Test suite
├── config.py               # Configuration
├── run.py                  # Entry point
└── requirements.txt        # Python dependencies
```

## Key HTML Dashboards

| File | Route | Purpose |
|------|-------|---------|
| `intake-dashboard.html` | `/intake` | Client onboarding wizard (4 steps) |
| `client-dashboard.html` | `/client/<id>` | Individual client management |
| `agency-dashboard.html` | `/agency` | Agency-wide overview |
| `admin-dashboard.html` | `/admin` | System administration |

## Authentication Flow

1. User enters email/password on login screen
2. POST to `/api/auth/login`
3. Server validates, returns JWT token
4. Token stored in `localStorage` as `mcp_token`
5. All API calls include `Authorization: Bearer ${token}` header
6. Token validated on each request via `@token_required` decorator

## Client Onboarding Flow (intake-dashboard.html)

### Step 1: Business Profile
- Business name, industry, location (required)
- Website, phone, email (optional)
- Service areas (tag input)
- USPs (checkboxes + custom)
- Competitor auto-discovery

### Step 2: Keyword Discovery
- Auto-generated keywords based on industry/location
- SEMRush integration for volume/difficulty data
- Manual keyword addition
- Competitor URL analysis
- Primary (blue) / Secondary (green) selection

### Step 3: Review & Launch
- Summary of selections
- Generation options (blogs, social, monitoring)
- Quick setup toggle (skip content generation)

### Step 4: Success
- Delivery summary
- Quick stats
- Next steps (review content, service pages, WordPress, lead forms)

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/bootstrap` | Create admin account |
| GET | `/api/auth/me` | Get current user |
| GET | `/api/auth/health` | Health check |

### Intake/Onboarding
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/intake/analyze` | Analyze business info with AI |
| POST | `/api/intake/research` | Research keywords with SEMRush |
| POST | `/api/intake/pipeline` | Complete intake-to-content pipeline |
| POST | `/api/intake/quick` | Quick client setup without content |

### Clients
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/clients` | List all clients |
| GET | `/api/clients/<id>` | Get client details |
| POST | `/api/clients` | Create client |
| PUT | `/api/clients/<id>` | Update client |
| DELETE | `/api/clients/<id>` | Delete client |

### Content
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/blogs` | List blogs |
| POST | `/api/blogs/generate` | Generate blog |
| POST | `/api/blogs/bulk` | Bulk generate blogs |
| GET | `/api/social` | List social posts |
| POST | `/api/social/generate` | Generate social posts |

### SEO & Competitors
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/seo/analyze` | Analyze content SEO |
| POST | `/api/seo/serp-preview` | Generate SERP preview |
| POST | `/api/competitors/analyze` | Analyze competitor content |
| POST | `/api/competitors/beat` | Generate "beat this" content |

## State Management

### Global JavaScript Variables
```javascript
let currentStep = 1;           // Current wizard step
let clientData = {};           // Business profile data
let keywords = [];             // Selected keywords
let serviceAreas = [];         // Service area tags
let selectedUSPs = [];         // Selected USPs
let discoveredCompetitors = []; // Found competitors
let token = '';                // JWT auth token
let headers = {};              // API request headers
```

### localStorage Keys
| Key | Purpose |
|-----|---------|
| `mcp_token` | JWT authentication token |
| `intake_draft` | Saved draft of Step 1 form |
| `intake_state` | Full wizard state for resume |

## Security Considerations

1. **XSS Prevention**: `escapeHtml()` function for all user/API data
2. **CSRF**: Token-based authentication (no cookies)
3. **Input Validation**: Server-side validation on all endpoints
4. **SQL Injection**: SQLAlchemy ORM prevents injection
5. **Rate Limiting**: Configurable per endpoint
