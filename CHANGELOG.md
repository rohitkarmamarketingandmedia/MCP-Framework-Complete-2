# Changelog

## v3.1.0 - PostgreSQL + Render Deployment (November 2024)

### Breaking Changes

**Database**: Migrated from JSON file storage to PostgreSQL database.
- All data models rewritten as SQLAlchemy ORM classes
- Data persists across deployments
- Required for Render and other PaaS deployment

### New Files

| File | Purpose |
|------|---------|
| `render.yaml` | Render Blueprint - auto-configures web service + PostgreSQL |
| `build.sh` | Build script that creates database tables |
| `RENDER.md` | Step-by-step Render deployment guide |
| `test_all.py` | Comprehensive 19-test verification suite |
| `app/database.py` | SQLAlchemy database initialization |
| `app/models/db_models.py` | All ORM models (User, Client, BlogPost, SocialPost, Campaign, Schema) |
| `app/services/db_service.py` | Database-backed DataService |

### Updated Files

| File | Changes |
|------|---------|
| `requirements.txt` | Added Flask-SQLAlchemy, SQLAlchemy, psycopg2-binary |
| `app/config.py` | Added SQLALCHEMY_DATABASE_URI with postgres:// conversion |
| `app/__init__.py` | Added database initialization |
| `app/routes/auth.py` | Updated to use DBUser, db_service |
| `app/routes/clients.py` | Updated to use DBClient, db_service |
| `app/routes/content.py` | Updated to use DBBlogPost, db_service |
| `app/routes/social.py` | Updated to use DBSocialPost, db_service |
| `app/routes/campaigns.py` | Updated to use DBCampaign, db_service |
| `app/routes/schema.py` | Updated to use DBSchemaMarkup, db_service |
| `app/routes/publish.py` | Updated to use db_service |
| `app/routes/analytics.py` | Updated to use db_service |
| `app/routes/intake.py` | Updated to use DBClient, db_service |
| `setup_admin.py` | Updated to use DB models with app context |
| `QUICKSTART.md` | Added Render deployment option |

### Database Schema

```
users
├── id (PK)
├── email (unique, indexed)
├── name
├── password_hash
├── password_salt
├── role
├── api_key (unique)
├── client_ids (JSON)
├── is_active
├── created_at
└── last_login

clients
├── id (PK)
├── business_name
├── industry
├── geo
├── website_url
├── phone
├── email
├── primary_keywords (JSON)
├── secondary_keywords (JSON)
├── competitors (JSON)
├── service_areas (JSON)
├── unique_selling_points (JSON)
├── tone
├── integrations (JSON)
├── subscription_tier
├── monthly_content_limit
├── is_active
├── created_at
└── updated_at

blog_posts
├── id (PK)
├── client_id (indexed)
├── title
├── slug
├── meta_title
├── meta_description
├── body
├── excerpt
├── primary_keyword
├── secondary_keywords (JSON)
├── word_count
├── seo_score
├── internal_links (JSON)
├── external_links (JSON)
├── schema_markup (JSON)
├── faq_content (JSON)
├── featured_image_url
├── status
├── published_url
├── published_at
├── created_at
└── updated_at

social_posts
├── id (PK)
├── client_id (indexed)
├── platform
├── content
├── hashtags (JSON)
├── media_urls (JSON)
├── link_url
├── cta_type
├── status
├── scheduled_for
├── published_at
├── published_id
└── created_at

campaigns
├── id (PK)
├── client_id (indexed)
├── name
├── campaign_type
├── description
├── start_date
├── end_date
├── budget
├── spent
├── status
├── content_ids (JSON)
├── metrics (JSON)
├── created_at
└── updated_at

schema_markups
├── id (PK)
├── client_id (indexed)
├── schema_type
├── name
├── json_ld (JSON)
├── is_active
└── created_at
```

### Render Deployment

One-click deployment to Render:

1. Push to GitHub
2. Render Dashboard → New → Blueprint
3. Connect repo (auto-detects `render.yaml`)
4. Set `OPENAI_API_KEY` environment variable
5. Deploy

**Cost**: Free tier (750 hrs/mo web + free PostgreSQL)

### Testing

Run the test suite to verify installation:

```bash
python test_all.py
```

Tests 19 items:
- All module imports
- App creation
- User/Client/BlogPost/SocialPost/Campaign/Schema CRUD
- API endpoints (health, auth, clients)
- Render postgres:// URL conversion

### Migration from v3.0

If upgrading from file-based storage:

1. Export existing data from `data/` folder
2. Deploy new version with PostgreSQL
3. Create admin user: `python setup_admin.py`
4. Re-create clients via API or dashboard

Note: Automatic migration script not included - manual data transfer required.
