# N8N Deployment Guide for Rohit

## What is N8N?

N8N is the "hands" that do external work when MCP fires events. Think of it like this:

```
MCP (Brain)                    N8N (Hands)
━━━━━━━━━━━━                   ━━━━━━━━━━━
Content approved  ──webhook──→  Publish to WordPress
New lead          ──webhook──→  Add to CRM + Send email
Call received     ──webhook──→  Transcribe + Analyze
```

MCP fires webhooks. N8N catches them and does the work.

---

## Option A: N8N Cloud (Recommended - Easiest)

### Step 1: Sign Up
1. Go to https://n8n.io
2. Click "Get Started Free"
3. Sign up with email
4. Choose the $20/month plan (or start free trial)

### Step 2: Get Your Webhook URL
1. In N8N dashboard, click "Add Workflow"
2. Click the "+" button
3. Search for "Webhook"
4. Add "Webhook" trigger node
5. Click the webhook node
6. Copy the "Production URL" - it looks like:
   ```
   https://your-account.app.n8n.cloud/webhook/abc123xyz
   ```

### Step 3: Add to MCP Environment
Add these to your Render environment variables:

```
WEBHOOK_URL_DEFAULT=https://your-account.app.n8n.cloud/webhook/abc123xyz
WEBHOOK_SECRET=generate-a-random-string-here
```

### Step 4: Import Workflows
1. Download the workflow JSON files from this package
2. In N8N: Settings → Import Workflow
3. Upload each JSON file
4. Activate the workflows

Done! N8N Cloud handles everything else.

---

## Option B: Self-Host N8N on Render (Same as MCP)

### Step 1: Create New Web Service on Render

1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Select "Deploy an existing image from a registry"
4. Enter: `n8nio/n8n`
5. Configure:

| Setting | Value |
|---------|-------|
| Name | `karma-n8n` |
| Region | Same as MCP (Oregon) |
| Instance Type | Starter ($7/mo) or Standard ($25/mo) |

### Step 2: Add Environment Variables

Click "Environment" and add these:

```
N8N_HOST=0.0.0.0
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://karma-n8n.onrender.com/
N8N_ENCRYPTION_KEY=generate-a-32-char-random-string
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=choose-a-strong-password
```

### Step 3: Add Persistent Disk

N8N needs storage for workflows:

1. Scroll to "Disks"
2. Click "Add Disk"
3. Configure:
   - Name: `n8n-data`
   - Mount Path: `/home/node/.n8n`
   - Size: 1 GB

### Step 4: Deploy

1. Click "Create Web Service"
2. Wait for deployment (2-3 minutes)
3. Access at: `https://karma-n8n.onrender.com`
4. Login with the credentials you set

### Step 5: Connect to MCP

Add to MCP's environment on Render:

```
WEBHOOK_URL_DEFAULT=https://karma-n8n.onrender.com/webhook/mcp-events
WEBHOOK_SECRET=same-secret-in-both-places
```

---

## Step-by-Step: Import The Workflows

### Workflow 1: Content Publisher

This workflow:
- Receives "content approved" from MCP
- Publishes to WordPress
- Updates MCP with published URL
- Sends email notification

**To Import:**
1. In N8N, click "Add Workflow"
2. Click the "..." menu → "Import from File"
3. Select `workflow-content-publisher.json`
4. Click the WordPress node → Add your credentials
5. Click the HTTP Request node → Update MCP URL
6. Click "Save"
7. Toggle "Active" to ON

### Workflow 2: Lead Processor

This workflow:
- Receives "new lead" from MCP
- Sends Slack notification
- Adds to Google Sheets (simple CRM)
- Starts email sequence

**To Import:**
1. Import `workflow-lead-processor.json`
2. Configure Slack credentials
3. Configure Google Sheets credentials
4. Click "Save" → "Active"

### Workflow 3: Call Intelligence

This workflow:
- Receives CallRail webhook
- Forwards to MCP for processing
- Fires alert if hot lead detected

**To Import:**
1. Import `workflow-call-intelligence.json`
2. Update MCP URL
3. Configure Slack for alerts
4. Click "Save" → "Active"

---

## Testing The Connection

### Test 1: From MCP Dashboard

```bash
curl -X POST https://your-mcp.onrender.com/api/webhooks/fire \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "test.ping",
    "payload": {"message": "Hello from MCP"}
  }'
```

### Test 2: Check N8N Received It

1. In N8N, go to "Executions"
2. You should see the test event
3. Click to view details

### Test 3: End-to-End Content Test

1. In MCP Portal, approve a blog post
2. Check N8N Executions - should show "content.approved"
3. Check WordPress - post should be created
4. Check MCP - status should update to "published"

---

## Troubleshooting

### Webhook Not Received

1. Check MCP logs: `WEBHOOK_URL_DEFAULT` is set correctly
2. Check N8N webhook node is set to "Production" not "Test"
3. Check workflow is "Active" (toggle is ON)

### WordPress Publish Failed

1. Check WordPress credentials in N8N
2. Check WP_APP_PASSWORD is correct
3. Check WordPress site is accessible

### N8N Won't Start on Render

1. Check environment variables are set
2. Check disk is mounted at `/home/node/.n8n`
3. Check logs for errors

---

## Environment Variables Summary

### MCP (add to existing Render env)

```
WEBHOOK_URL_DEFAULT=https://karma-n8n.onrender.com/webhook/mcp-events
WEBHOOK_URL_CONTENT=https://karma-n8n.onrender.com/webhook/content
WEBHOOK_URL_LEADS=https://karma-n8n.onrender.com/webhook/leads
WEBHOOK_SECRET=your-shared-secret-key
```

### N8N (new Render service)

```
N8N_HOST=0.0.0.0
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://karma-n8n.onrender.com/
N8N_ENCRYPTION_KEY=random-32-character-string
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=strong-password-here
```

---

## Monthly Costs

| Service | Cost |
|---------|------|
| N8N on Render (Starter) | $7/mo |
| N8N on Render (Standard) | $25/mo |
| N8N Cloud | $20/mo |
| Persistent Disk (1GB) | $0.25/mo |

**Recommendation:** Start with N8N Cloud ($20/mo) for zero maintenance. Move to self-hosted later if you want to save money.

---

## Quick Reference

| What | URL |
|------|-----|
| N8N Dashboard | https://karma-n8n.onrender.com |
| MCP Webhook Events | https://your-mcp.onrender.com/api/webhooks/events |
| MCP Webhook Logs | https://your-mcp.onrender.com/api/webhooks/logs |
| Test Webhook | POST /api/webhooks/fire |

---

## Questions?

The workflows are pre-built. You just need to:
1. Deploy N8N (5 minutes)
2. Import the JSON files (2 minutes each)
3. Add credentials (WordPress, Slack, etc.)
4. Activate

That's it. N8N handles the rest automatically.
