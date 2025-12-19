# MCP Webhook Integration Guide

Direct webhook integration - no middleware required.

## Overview

MCP handles all webhooks directly. No need for n8n, Zapier, or other automation tools.

```
External Service → MCP API → Database → Automated Actions
                   ↑
              Direct, simple, fast
```

---

## CallRail Integration

### Setup in CallRail

1. Log into CallRail → Settings → Webhooks
2. Add webhook URL: `https://your-domain.com/api/webhooks/callrail`
3. Select events: `call_completed`, `form_submission`, `text_message`
4. Save

### What Happens Automatically

When a call comes in, MCP:
1. Receives the webhook
2. Extracts caller info, duration, recording URL
3. If transcript available → analyzes for content opportunities
4. Creates lead record
5. Sends notification to agency dashboard

### Environment Variables

```env
CALLRAIL_API_KEY=your_api_key
CALLRAIL_ACCOUNT_ID=your_account_id
```

### Endpoint Details

```
POST /api/webhooks/callrail
Content-Type: application/json

{
  "call_type": "inbound",
  "company_id": "...",
  "caller_number": "+1234567890",
  "duration": 180,
  "recording_url": "https://...",
  "transcript": "..."
}
```

---

## Google Business Profile (GBP) Integration

### Setup

1. Connect GBP via OAuth in MCP dashboard (Settings → Integrations)
2. MCP automatically syncs reviews every 2 hours
3. Auto-generates response suggestions for new reviews

### Automated Actions

- New review detected → AI generates response suggestion
- Response approved → Posts directly to GBP
- Negative review → Sends alert to agency dashboard

---

## WordPress Publishing

### Setup in WordPress

1. Install "Application Passwords" (built into WP 5.6+)
2. Create application password for MCP
3. Add to client settings in MCP

### Environment/Client Settings

```
wordpress_url: https://client-site.com
wordpress_username: mcp-publisher
wordpress_app_password: xxxx xxxx xxxx xxxx
```

### What MCP Does

- Publishes blogs with full formatting
- Uploads featured images
- Creates tags from keywords
- Adds FAQ schema automatically
- Sets proper meta descriptions

---

## Social Media Publishing

### Supported Platforms

- Facebook Pages (OAuth)
- LinkedIn Company Pages (OAuth)
- Google Business Profile (OAuth)

### Setup

1. Go to Settings → Social Connections
2. Click "Connect" for each platform
3. Authorize MCP access
4. Select pages/profiles to manage

### Automated Scheduling

MCP's scheduler handles:
- Auto-publish at scheduled times (checks every 5 min)
- Retry failed posts
- Track engagement metrics

---

## Scheduled Jobs (Built-in Automation)

MCP runs these automatically via APScheduler:

| Job | Schedule | Purpose |
|-----|----------|---------|
| auto_publish | Every 5 min | Publish scheduled content |
| competitor_crawl | Daily 3 AM | Check competitor websites |
| rank_check | Daily 5 AM | Track keyword rankings |
| content_due | Daily 7 AM | Notify about due content |
| daily_summary | Daily 8 AM | Send daily reports |
| review_responses | Every 2 hrs | Generate review responses |
| client_reports | Mon/Thu 9 AM | Send 3-day reports |

No external scheduler needed!

---

## Custom Webhooks (Receiving)

### Generic Webhook Endpoint

```
POST /api/webhooks/generic
Authorization: Bearer {your_api_token}
Content-Type: application/json

{
  "event": "custom_event",
  "client_id": "xxx",
  "data": {...}
}
```

### Supported Events

- `lead_created` - New lead from any source
- `review_received` - New review notification
- `content_approved` - Content approved externally
- `ranking_change` - External rank tracking

---

## Outgoing Webhooks (Sending)

MCP can notify your systems when events occur.

### Setup

1. Go to Settings → Webhooks
2. Add destination URL
3. Select events to trigger

### Available Events

```javascript
// Events MCP can send
{
  "blog.published": { blog_id, title, url },
  "social.posted": { post_id, platform, url },
  "review.received": { review_id, rating, text },
  "lead.created": { lead_id, source, contact },
  "ranking.changed": { keyword, old_position, new_position }
}
```

---

## Testing Webhooks

### Test CallRail Webhook

```bash
curl -X POST https://your-domain.com/api/webhooks/callrail \
  -H "Content-Type: application/json" \
  -d '{
    "call_type": "inbound",
    "caller_number": "+1234567890",
    "duration": 120,
    "company_name": "Test Company"
  }'
```

### Test Generic Webhook

```bash
curl -X POST https://your-domain.com/api/webhooks/generic \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "lead_created",
    "client_id": "client_123",
    "data": {
      "name": "John Doe",
      "phone": "+1234567890"
    }
  }'
```

---

## Troubleshooting

### Webhook Not Received

1. Check URL is publicly accessible (not localhost)
2. Verify HTTPS certificate is valid
3. Check MCP logs: `docker logs mcp-app`

### Webhook Received But No Action

1. Check payload format matches expected schema
2. Verify client_id exists in database
3. Check service-specific API keys are configured

### View Webhook History

```
GET /api/webhooks/history?limit=50
Authorization: Bearer {token}
```

---

## Architecture Decision

**Why no n8n/Zapier?**

MCP is a complete platform. Adding middleware:
- Adds latency to every request
- Creates additional failure points
- Costs more to host
- Adds complexity to maintain

Everything routes directly to MCP endpoints. Simple, fast, reliable.
