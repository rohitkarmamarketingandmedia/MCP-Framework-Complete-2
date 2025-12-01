# N8N Workflows for MCP Framework

## Pre-Built Workflows

These JSON files can be imported directly into N8N.

| File | What It Does |
|------|--------------|
| `workflow-catch-all-testing.json` | **START HERE** - Logs all events to Slack + Google Sheets |
| `workflow-content-publisher.json` | Publishes approved content to WordPress |
| `workflow-lead-processor.json` | Processes new leads → Slack + Sheets + Email |
| `workflow-call-intelligence.json` | Handles call events → Hot lead alerts |

## Quick Start

### Step 1: Import the Test Workflow First

1. Open N8N
2. Click "Add Workflow" → "..." → "Import from File"
3. Select `workflow-catch-all-testing.json`
4. Configure credentials (Slack, Google Sheets)
5. Click "Save" then toggle "Active" to ON
6. Copy the webhook URL

### Step 2: Configure MCP

Add to MCP environment:
```
WEBHOOK_URL_DEFAULT=<paste webhook URL from step 1>
```

### Step 3: Test It

From MCP admin dashboard or API:
```
POST /api/webhooks/fire
{
  "event_type": "test.ping",
  "payload": {"message": "Hello!"}
}
```

You should see the event in:
- Your Slack #mcp-events channel
- Your Google Sheet "Event Log"

### Step 4: Add Production Workflows

Once testing works, import the other workflows:
1. `workflow-content-publisher.json`
2. `workflow-lead-processor.json`
3. `workflow-call-intelligence.json`

## Credentials Needed

Each workflow needs these configured:

| Credential | Used For |
|------------|----------|
| Slack | Notifications and alerts |
| Google Sheets | Simple CRM / logging |
| WordPress | Publishing blog posts |
| SMTP | Sending emails |
| MCP API | Updating content status |

### Setting Up Credentials

**Slack:**
1. Go to api.slack.com → Create App
2. Add Bot Token Scopes: `chat:write`, `channels:read`
3. Install to workspace
4. Copy Bot Token → N8N

**Google Sheets:**
1. N8N → Credentials → Google Sheets OAuth2
2. Follow OAuth flow
3. Create a spreadsheet for each workflow

**WordPress:**
1. WordPress → Users → Application Passwords
2. Generate password
3. N8N → WordPress credentials → Add URL + password

**SMTP:**
1. Use your email provider's SMTP settings
2. Gmail: smtp.gmail.com, port 587, App Password

## Webhook URLs

After importing, each workflow has its own webhook URL:

| Workflow | Path | Full URL |
|----------|------|----------|
| Catch-All | `/mcp-events` | `https://your-n8n.com/webhook/mcp-events` |
| Content | `/content` | `https://your-n8n.com/webhook/content` |
| Leads | `/leads` | `https://your-n8n.com/webhook/leads` |
| Calls | `/calls` | `https://your-n8n.com/webhook/calls` |

Configure MCP to use specific URLs:
```
WEBHOOK_URL_DEFAULT=https://your-n8n.com/webhook/mcp-events
WEBHOOK_URL_CONTENT=https://your-n8n.com/webhook/content
WEBHOOK_URL_LEADS=https://your-n8n.com/webhook/leads
WEBHOOK_URL_CALLS=https://your-n8n.com/webhook/calls
```

## Customizing Workflows

These are starting points. You can:
- Add more Slack channels
- Change email templates
- Add CRM integrations (HubSpot, etc.)
- Add SMS notifications (Twilio)
- Add custom logic

N8N is visual - just drag and drop nodes!

## Troubleshooting

**Webhook not receiving?**
- Check workflow is "Active" (toggle ON)
- Check webhook is "Production" not "Test"
- Check MCP env var matches URL exactly

**Slack not posting?**
- Check bot is in the channel (`/invite @botname`)
- Check bot has `chat:write` permission

**Google Sheets error?**
- Re-authenticate OAuth
- Check sheet name matches exactly

## Support

Questions? Check N8N docs: https://docs.n8n.io
