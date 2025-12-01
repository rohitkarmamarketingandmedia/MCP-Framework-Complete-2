# MCP Framework Changelog

## v5.5.0 - Client Value Experience + Customer Intelligence Engine

### 🎯 Goal: Make Clients Feel ABSOLUTE VALUE, Build TRUST, and Want to PAY MORE

### New Features

#### 1. Customer Interaction Intelligence Engine
**Files:**
- `app/services/interaction_intelligence_service.py`
- `app/services/content_from_interactions_service.py`

**The GOLDMINE:** Turn every customer interaction into content:

| Source | What We Extract |
|--------|-----------------|
| CallRail Calls | Questions, pain points, keywords, services mentioned |
| Chatbot Convos | Questions asked, topics, keywords |
| Lead Forms | Service requests, questions in notes |

**Intelligence Outputs:**
- Top questions customers ask (ranked by frequency)
- Common pain points and concerns
- Keywords customers actually use (for SEO)
- Service demand analysis
- Content opportunities identified

#### 2. Auto-Generate Content from Interactions
**Automatically create:**

| Content Type | What It Does |
|--------------|--------------|
| **FAQ Pages** | Real Q&A from calls/chats with Schema markup |
| **Blog Posts** | Answer question clusters in 1800+ word articles |
| **Service Page Q&A** | "What Customers Ask" sections to embed |
| **Content Calendars** | Weekly blog schedule based on real demand |
| **Full Content Package** | FAQ + 3 blogs + calendar in one click |

**API Endpoints (13 new):**

| Endpoint | Description |
|----------|-------------|
| `POST /api/intelligence/analyze-call` | Analyze single transcript |
| `POST /api/intelligence/analyze-calls/{id}` | Analyze multiple calls |
| `POST /api/intelligence/fetch-callrail/{id}` | Fetch & analyze from CallRail |
| `GET /api/intelligence/report/{id}` | Full intelligence report |
| `GET /api/intelligence/questions/{id}` | Top questions extracted |
| `GET /api/intelligence/opportunities/{id}` | Content opportunities |
| `GET /api/intelligence/chatbot/{id}` | Chatbot conversation analysis |
| `GET /api/intelligence/forms/{id}` | Lead form analysis |
| `POST /api/intelligence/generate/faq/{id}` | Generate FAQ page |
| `POST /api/intelligence/generate/blog/{id}` | Generate blog from questions |
| `POST /api/intelligence/generate/service-qa/{id}` | Generate service page Q&A |
| `POST /api/intelligence/generate/calendar/{id}` | Generate content calendar |
| `POST /api/intelligence/generate/package/{id}` | Generate complete content package |

#### 3. Client Health Score System
**File:** `app/services/client_health_service.py`

100-point "Report Card" score that clients understand instantly:
- **Rankings** (25 pts): Keywords improving vs dropping
- **Content** (20 pts): Publishing on schedule
- **Leads** (25 pts): Lead generation vs target
- **Reviews** (15 pts): New reviews coming in
- **Engagement** (15 pts): Social/GMB activity

Grades: A+ (90+), A (80+), B+ (70+), B (60+), C+ (50+), C (40+), D (30+), F (<30)

#### 4. CallRail Integration
**File:** `app/services/callrail_service.py`

Full call tracking integration:
- Call metrics (total, answered, missed, voicemails)
- Answer rate with visual progress
- Hot leads (calls > 2 min)
- Call recordings (MP3 URLs)
- Call transcripts (requires CI plan)
- Lead quality scoring (hot/warm/cold)

#### 5. 3-Day Client Snapshot Reports
**File:** `app/services/client_report_service.py`

Automated email reports (Mon/Thu 9 AM):
- 🏆 **The Wins** - Ranking improvements, content published
- ⚠️ **Needs Attention** - Issues we're fixing
- 🔧 **What We're Doing** - Activity feed
- 📅 **Coming Up** - Content pipeline
- 📞 **Lead Summary** - Calls + forms + trends

#### 6. Portal Dashboard Upgrade
Enhanced Performance tab:
- Health Score Circle (animated)
- Score Breakdown bars
- Recent Wins section
- Activity Feed
- Coming Up pipeline
- Call Metrics (if CallRail configured)

### Database Updates
**DBClient** added fields:
- `callrail_company_id` - Link to CallRail company
- `monthly_lead_target` - For health score calculation

### Scheduler Updates
- New job: `client_3day_reports` - Runs Mon/Thu at 9 AM

### Environment Variables
```bash
# CallRail (for call tracking + intelligence)
CALLRAIL_API_KEY=your-api-key
CALLRAIL_ACCOUNT_ID=your-account-id
```

### Route Summary
- **319 total routes** (+38 from v5.4)
- **9 scheduler jobs** (+1)

### Webhook/N8N Integration (NEW!)

**The Bridge:** MCP fires events → N8N handles distribution

**Outbound Events (MCP → N8N):**
| Event | Description |
|-------|-------------|
| `content.approved` | Content approved, ready to publish |
| `content.published` | Content published to WordPress |
| `lead.created` | New lead from any source |
| `lead.qualified` | Lead marked qualified |
| `call.received` | Call received (from CallRail) |
| `call.transcribed` | Transcript ready |
| `client.onboarded` | New client setup complete |
| `report.generated` | Client report ready |
| `alert.triggered` | Something needs attention |

**Inbound Webhooks (External → MCP):**
| Endpoint | Source |
|----------|--------|
| `/api/webhooks/inbound/callrail` | CallRail call events |
| `/api/webhooks/inbound/form` | Form submissions |
| `/api/webhooks/inbound/chatbot` | Chatbot lead capture |

**Management Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `GET /api/webhooks/endpoints` | List configured endpoints |
| `POST /api/webhooks/endpoints` | Create new endpoint |
| `POST /api/webhooks/endpoints/{id}/test` | Test endpoint |
| `GET /api/webhooks/logs` | View webhook history |
| `POST /api/webhooks/fire` | Manually fire event |
| `GET /api/webhooks/events` | List available events |

**Environment Variables:**
```bash
WEBHOOK_URL_DEFAULT=https://your-n8n.com/webhook/mcp-events
WEBHOOK_URL_CONTENT=https://your-n8n.com/webhook/content
WEBHOOK_URL_LEADS=https://your-n8n.com/webhook/leads
WEBHOOK_URL_CALLS=https://your-n8n.com/webhook/calls
WEBHOOK_SECRET=your-signing-secret
```

### The Big Picture: Interaction → Intelligence → Content

```
📞 Customer Calls ──┐
                    │
💬 Chatbot Chats ───┼──→ 🧠 AI Analysis ──→ 📊 Insights ──→ 📝 Auto-Content
                    │     • Questions        • Top 25 Q's    • FAQ Pages
📝 Lead Forms ──────┘     • Pain Points      • Keywords      • Blog Posts
                          • Keywords         • Opportunities  • Service Q&A
                          • Services                          • Content Calendar
```

---

## v5.4.0 - Unified Header + Portal Approval Workflow

### New Features

#### 1. Unified Header Component
**File:** `/static/js/unified-header.js`
- Smart navigation based on user role (admin, agency, client)
- Notification bell with real-time unread count and dropdown panel
- User menu with profile, settings, and logout
- Global search with Ctrl/Cmd+K shortcut
- Auto-poll for new notifications every 60 seconds
- Consistent branding across all dashboards

**Usage:**
```html
<script src="/static/js/unified-header.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', () => initUnifiedHeader());
</script>
```

#### 2. Content Approval Workflow
**New Routes:** `/api/approval/*`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pending?client_id=xxx` | GET | Get all content pending approval |
| `/approve/{type}/{id}` | POST | Approve content |
| `/request-changes/{type}/{id}` | POST | Request revisions with feedback |
| `/feedback/{type}/{id}` | GET | Get feedback history |
| `/feedback/{type}/{id}` | POST | Add new feedback |
| `/submit/{type}/{id}` | POST | Submit for client approval (agency) |
| `/bulk-approve` | POST | Approve multiple items at once |

#### 3. Portal Dashboard Approvals Tab
- Summary cards: Pending, Revisions Requested, Approved, Published
- Approval badge on tab showing pending count
- "Approve All" button for bulk approval
- Filter buttons: All / Pending / Needs Revision
- Rich content cards with status badges, type icons, dates
- Full content review modal
- Feedback modal with priority selection (low/normal/high)
- Toast notifications for all actions

### Database Updates
**DBBlogPost** added fields:
- `scheduled_for` - DateTime for scheduling
- `wordpress_post_id` - WordPress integration
- `revision_notes` - Client feedback text
- `approved_at` / `approved_by` - Approval tracking

**DBSocialPost** added fields:
- `revision_notes` - Client feedback text
- `approved_at` / `approved_by` - Approval tracking

### Route Summary
- **281 total API routes** (+7 approval routes)

---

## v5.3.1 - OAuth + Image Generation Debugging

### Bug Fixes
- OAuth callback URL encoding (special characters)
- OAuth client context restoration after redirect
- Image service import cleanup
- Auto-publish notification integration fixes
- Proper error handling in OAuth flows

### Testing Validated
- All 274 routes tested
- OAuth callback flow validated end-to-end
- Image generation tested with all providers
- Auto-publish with notifications confirmed working

---

## v5.3.0 - OAuth Flows + AI Image Generation (Tier 3)

### New Features

#### 1. OAuth2 Service
**File:** `app/services/oauth_service.py` (450+ lines)

Supported platforms:
- **Facebook** - Pages, posts, insights
- **Instagram** - Business accounts via Facebook
- **LinkedIn** - Organization posting
- **Google Business Profile** - Location management

Features:
- Secure state token generation with 10-minute expiry
- Token exchange and refresh
- Account discovery (Pages, Organizations, Locations)
- Token validation

#### 2. OAuth Routes
**File:** `app/routes/oauth.py` (589 lines)

| Endpoint | Description |
|----------|-------------|
| `GET /api/oauth/config` | Get configured providers |
| `POST /api/oauth/authorize/{platform}` | Start OAuth flow |
| `GET /api/oauth/callback/{platform}` | Handle OAuth callback |
| `POST /api/oauth/accounts/{platform}` | List available accounts |
| `POST /api/oauth/connect` | Finalize connection |
| `GET /api/oauth/validate/{platform}/{client_id}` | Validate connection |
| `POST /api/oauth/refresh/{platform}/{client_id}` | Refresh token |
| `POST /api/oauth/disconnect/{platform}/{client_id}` | Remove connection |

#### 3. AI Image Generation Service
**File:** `app/services/image_service.py` (700 lines)

Providers (priority order):
1. **DALL-E 3** - Best quality, $0.04-0.12/image
2. **Stability AI** - Stable Diffusion XL
3. **Replicate** - SDXL via API
4. **Unsplash** - Free stock photos fallback

Style presets:
- photorealistic, social_media, corporate, illustration
- minimal, lifestyle, product, blog_header, abstract, vintage

Features:
- Automatic prompt enhancement
- Platform-optimized sizes (FB, IG, LinkedIn, Twitter, GBP)
- Batch generation for all platforms
- Local image storage

#### 4. Image Generation Routes
**File:** `app/routes/images.py` (357 lines)

| Endpoint | Description |
|----------|-------------|
| `POST /api/images/generate` | Generate single image |
| `POST /api/images/generate-for-social` | Generate for multiple platforms |
| `POST /api/images/generate-prompt` | Generate optimized prompt |
| `GET /api/images/config` | Get available providers/styles |
| `GET /api/images/list` | List generated images |
| `GET /api/images/view/{filename}` | Serve image file |
| `DELETE /api/images/delete/{filename}` | Delete image |

### Dashboard Updates
- OAuth integration with account selection modal
- AI Image Generator card with style/size dropdowns
- Generate for all platforms button
- Image preview with download and copy URL

### Environment Variables
```bash
# OAuth (configure at least one)
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
APP_URL=https://your-domain.com

# Image Generation (configure at least one)
OPENAI_API_KEY=         # DALL-E 3 (recommended)
STABILITY_API_KEY=      # Stability AI
REPLICATE_API_TOKEN=    # Replicate/SDXL
UNSPLASH_ACCESS_KEY=    # Stock photos fallback
```

### Route Summary
- **274 total routes** (+15 from v5.2)

---

## v5.2.0 - Email Notifications + Digest System (Tier 2 Complete)

### New Features

#### 1. Notification Service
**File:** `app/services/notification_service.py` (700+ lines)

14 notification types:
- Content lifecycle: scheduled, due_today, published, approval_needed, approved, feedback
- WordPress: published, failed
- Social: published, failed
- SEO: ranking_improved, ranking_dropped
- Competitor: new_content, ranking_change

Delivery methods:
- In-app notifications with badge counts
- Email notifications (immediate or digest)
- Digest modes: immediate, daily, weekly

#### 2. User Notification Preferences
- Per-type enable/disable
- Delivery method selection
- Quiet hours (e.g., 10pm-7am)
- Digest scheduling

#### 3. Scheduled Digest Jobs
- Daily digest at 8 AM
- Weekly digest on Mondays at 8 AM
- Respects user quiet hours

### Route Summary
- **260+ total routes**
- 8 scheduler jobs

---

## v5.1.0 - Competitor Dashboard + Social Auto-Post (Tier 2)

### Features
- Competitor monitoring dashboard
- Social media auto-posting
- Enhanced rank tracking
- Alert system for ranking changes

---

## v5.0.0 - PostgreSQL Migration + Render Deployment

### Major Changes
- Migrated from JSON file storage to PostgreSQL
- Full database models with SQLAlchemy ORM
- Render.com deployment configuration
- Production-ready with gunicorn
- Background scheduler with APScheduler

### Database Models (25+)
- DBClient, DBUser, DBBlogPost, DBSocialPost
- DBCampaign, DBCompetitor, DBRankHistory
- DBNotificationLog, DBNotificationPreferences
- DBContentFeedback, and more

---

## v4.4.0 - Lead Generation & Conversion Suite

### New Features

#### 1. Lead Capture System
- **Lead Capture Forms**: Embeddable forms with customizable fields
- **Instant Notifications**: Email (SendGrid) + SMS (Twilio) alerts for new leads
- **Lead Database**: Full CRM-style lead tracking with status workflow
- **Auto-Response**: Automatic thank-you emails to leads
- **UTM Tracking**: Source, medium, campaign attribution
- **Lead Analytics**: Conversion rates, trends, source breakdown

**API Endpoints:**
- `POST /api/leads/capture` - Public lead capture (no auth)
- `GET /api/leads` - Get leads with filters
- `PUT /api/leads/{id}/status` - Update lead status
- `GET /api/leads/stats` - Lead statistics
- `POST /api/leads/form-embed` - Generate embed code

#### 2. Service/Location Page Generator
- **Service Pages**: High-converting landing pages for each service
- **Location Pages**: Geo-targeted pages for service areas
- **AI-Powered Content**: GPT-generated headlines, body, CTAs
- **SEO Optimized**: Schema markup, meta tags, keywords
- **Lead Form Integration**: Built-in forms on every page
- **HTML Export**: Download ready-to-deploy pages

**API Endpoints:**
- `POST /api/pages/generate/service` - Generate service page
- `POST /api/pages/generate/location` - Generate location page
- `POST /api/pages/generate/bulk` - Generate multiple pages
- `GET /api/pages/{id}/export` - Export as HTML

#### 3. Client Portal Dashboard
- **Lead Tracking**: Real-time lead counts and trends
- **Conversion Metrics**: Conversion rate, revenue from leads
- **Ranking Display**: Keyword position tracking
- **Source Analysis**: Lead source breakdown charts
- **Self-Service**: Clients can view their own performance

**File:** `portal-dashboard.html`

#### 4. Google Business Profile Integration
- **OAuth Flow**: Secure GBP account connection
- **Post Publishing**: Push content directly to GBP
- **Review Management**: View and respond to reviews
- **Q&A Management**: Answer customer questions
- **Photo Upload**: Add photos to listing
- **Insights**: GBP performance metrics

**API Endpoints:**
- `GET /api/gbp/auth/url` - Get OAuth URL
- `POST /api/gbp/posts` - Create GBP post
- `GET /api/gbp/reviews` - Get reviews
- `POST /api/gbp/reviews/{name}/reply` - Reply to review
- `GET /api/gbp/insights` - Get performance data

#### 5. Review Management System
- **Multi-Platform**: Google, Yelp, Facebook reviews
- **AI Responses**: GPT-generated review responses
- **Review Requests**: Email/SMS requests to customers
- **Bulk Requests**: Auto-request from converted leads
- **Review Widget**: Embeddable testimonials widget
- **Analytics**: Rating trends, sentiment analysis

**API Endpoints:**
- `GET /api/reviews` - Get reviews with filters
- `POST /api/reviews/{id}/generate-response` - AI response
- `POST /api/reviews/request/send` - Send review request
- `POST /api/reviews/request/bulk` - Bulk requests
- `GET /api/reviews/widget` - Get embed widget

### Database Changes
New models added:
- `DBLead` - Lead capture and tracking
- `DBReview` - Review storage and management
- `DBServicePage` - Generated landing pages

New client fields:
- `gbp_account_id`, `gbp_location_id`, `gbp_access_token`
- `lead_notification_email`, `lead_notification_phone`, `lead_notification_enabled`

### Environment Variables
New variables in `.env.example`:
```
# Twilio SMS
TWILIO_ACCOUNT_SID=xxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_FROM_NUMBER=+19415551234

# GBP OAuth
GBP_CLIENT_ID=xxx.apps.googleusercontent.com
GBP_CLIENT_SECRET=xxx
```

### Route Summary
- 166 total API routes
- 11 new lead routes
- 9 new page routes
- 14 new GBP routes
- 13 new review routes

---

## v4.3.0 - Polished Intake Dashboard

### Features
- Opportunity scoring (0-100) for keywords
- Auto-select best keywords
- Mobile-friendly button-based selection
- State persistence (localStorage)
- Enhanced industry keywords (15 per industry)
- Inline competitor analysis

---

## v4.2.0 - Agency Command Center

### Features
- Master dashboard for all clients
- Background scheduler (APScheduler)
- Email notification service
- Competitor monitoring
- Rank tracking
- Content queue management
- Elite client dashboard

---

## Previous Versions
See git history for v4.1 and earlier.
