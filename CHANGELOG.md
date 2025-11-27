# MCP Framework Changelog

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
