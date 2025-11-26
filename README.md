# MCP Framework v3.0

**Marketing Control Platform** - AI-powered SEO content automation engine by Karma Marketing + Media.

## Overview

MCP Framework is a complete marketing automation API that generates SEO-optimized content, manages social media, publishes to WordPress, and tracks analytics - all powered by AI.

## Features

- **AI Content Generation** - Blog posts, landing pages with proper SEO structure
- **Schema Markup** - JSON-LD generation for LocalBusiness, FAQ, Article, etc.
- **Social Media** - Multi-platform post generation (GBP, Facebook, Instagram, LinkedIn)
- **WordPress Publishing** - Direct REST API integration with Yoast SEO support
- **Analytics** - Google Analytics 4 integration for traffic and performance
- **SEO Tools** - SEMrush integration for keyword rankings and competitor analysis
- **Multi-tenant** - Client management with role-based access control

## Quick Start

### 1. Clone and Setup

```bash
git clone <repo-url>
cd mcp-framework

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run Development Server

```bash
python run.py
```

Server starts at `http://localhost:5000`

### 3. Test the API

```bash
# Health check
curl http://localhost:5000/health

# Create admin user (first time)
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","name":"Admin","password":"secure123","role":"admin"}'
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login, get JWT token |
| POST | `/api/auth/register` | Register user (admin only) |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/change-password` | Change password |

### Content Generation
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/content/generate` | Generate SEO blog post |
| POST | `/api/content/bulk-generate` | Generate multiple posts |
| GET | `/api/content/{id}` | Get content by ID |
| PUT | `/api/content/{id}` | Update content |
| GET | `/api/content/client/{client_id}` | List client content |
| POST | `/api/content/seo-check` | Check SEO score |

### Schema Markup
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/schema/generate` | Generate JSON-LD schema |
| POST | `/api/schema/validate` | Validate schema |
| GET | `/api/schema/{id}` | Get schema by ID |
| GET | `/api/schema/client/{client_id}` | List client schemas |

### Social Media
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/social/generate` | Generate social post |
| POST | `/api/social/kit` | Generate all platforms |
| GET | `/api/social/{id}` | Get post by ID |
| PUT | `/api/social/{id}` | Update post |
| POST | `/api/social/schedule` | Schedule posts |

### Publishing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/publish/wordpress` | Publish to WordPress |
| POST | `/api/publish/gbp` | Publish to Google Business |
| POST | `/api/publish/facebook` | Publish to Facebook |
| POST | `/api/publish/bulk` | Bulk publish |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/overview/{client_id}` | Overview metrics |
| GET | `/api/analytics/traffic/{client_id}` | Traffic details |
| GET | `/api/analytics/rankings/{client_id}` | Keyword rankings |
| GET | `/api/analytics/competitors/{client_id}` | Competitor analysis |
| GET | `/api/analytics/report/{client_id}` | Full report |

### Clients
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/clients` | List clients |
| POST | `/api/clients` | Create client |
| GET | `/api/clients/{id}` | Get client |
| PUT | `/api/clients/{id}` | Update client |
| PUT | `/api/clients/{id}/keywords` | Update keywords |
| PUT | `/api/clients/{id}/integrations` | Update integrations |

### Campaigns
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/campaigns` | List campaigns |
| POST | `/api/campaigns` | Create campaign |
| GET | `/api/campaigns/{id}` | Get campaign |
| PUT | `/api/campaigns/{id}` | Update campaign |
| POST | `/api/campaigns/{id}/activate` | Activate |
| POST | `/api/campaigns/{id}/pause` | Pause |
| POST | `/api/campaigns/{id}/complete` | Complete |

## Usage Examples

### Generate Blog Post

```bash
curl -X POST http://localhost:5000/api/content/generate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_abc123",
    "keyword": "roof repair sarasota",
    "geo": "Sarasota, FL",
    "industry": "roofing",
    "word_count": 1200,
    "include_faq": true,
    "internal_links": [
      {"url": "/services/roof-repair", "anchor": "roof repair services"}
    ]
  }'
```

### Generate Social Kit

```bash
curl -X POST http://localhost:5000/api/social/kit \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_abc123",
    "custom_topic": "Spring roof maintenance tips",
    "platforms": ["gbp", "facebook", "instagram", "linkedin"]
  }'
```

### Publish to WordPress

```bash
curl -X POST http://localhost:5000/api/publish/wordpress \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content_id": "content_xyz789",
    "status": "publish",
    "categories": ["Roofing", "Tips"]
  }'
```

## Project Structure

```
mcp-framework/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Configuration
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User authentication
│   │   ├── client.py        # Client/business data
│   │   ├── content.py       # Blog, schema, social posts
│   │   └── campaign.py      # Campaign tracking
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── content.py       # Content generation
│   │   ├── schema.py        # Schema markup
│   │   ├── social.py        # Social media
│   │   ├── publish.py       # Publishing
│   │   ├── analytics.py     # Analytics
│   │   ├── clients.py       # Client management
│   │   └── campaigns.py     # Campaign management
│   └── services/
│       ├── __init__.py
│       ├── ai_service.py    # OpenAI/Anthropic
│       ├── seo_service.py   # SEMrush/Ahrefs
│       ├── cms_service.py   # WordPress
│       ├── social_service.py # Social platforms
│       ├── analytics_service.py # GA4
│       └── data_service.py  # Data persistence
├── data/                    # JSON data storage
├── tests/
├── run.py                   # Entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── .env.example
└── README.md
```

## Deployment

### Docker

```bash
# Build and run
docker-compose up -d

# With nginx reverse proxy
docker-compose --profile with-nginx up -d

# View logs
docker-compose logs -f
```

### Manual (Production)

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app
```

## Configuration

All configuration via environment variables. See `.env.example` for full list.

**Required:**
- `SECRET_KEY` - Flask secret key
- `OPENAI_API_KEY` - For content generation

**Optional integrations:**
- `SEMRUSH_API_KEY` - Keyword rankings
- `WP_BASE_URL`, `WP_USERNAME`, `WP_APP_PASSWORD` - WordPress
- `GA4_PROPERTY_ID`, `GA4_CREDENTIALS_JSON` - Google Analytics
- `GBP_LOCATION_ID`, `GBP_API_KEY` - Google Business Profile
- `FACEBOOK_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID` - Facebook

## SEO Content Strategy

The framework enforces SEO best practices:

1. **H1** - Contains primary keyword + location
2. **All H2s** - Include location reference
3. **H3s** - Keyword variations
4. **Meta title** - 50-60 chars, keyword at start
5. **Meta description** - 150-160 chars with CTA
6. **Keyword density** - 1-2% natural distribution
7. **Internal links** - 3+ per article minimum
8. **FAQs** - Schema-ready Q&A sections

## License

Proprietary - Karma Marketing + Media

## Support

Contact: Karma Marketing + Media
