# MCP Framework - Complete Workflow Guide

## The Big Picture

```
NEW CLIENT SIGNS UP
        ↓
   YOU DO INTAKE (5 min)
        ↓
   SYSTEM GENERATES EVERYTHING (2-5 min)
        ↓
   CLIENT GETS CONTENT
        ↓
   ONGOING: MONITOR + PUBLISH
```

---

## PHASE 1: Client Signs Up

**What happens:** Client pays you $2,500/month. You schedule a 15-minute kickoff call.

**What you need from them:**
- Business name
- Industry (HVAC, roofing, dental, etc.)
- Primary location (city, state)
- Website (if they have one)
- Services they offer
- Service areas (cities/neighborhoods)
- Any competitors they know about

---

## PHASE 2: Intake (5 minutes)

### Step 1: Log into the Intake Dashboard

1. Go to: `https://your-domain.com/intake`
2. Log in with your admin email/password

### Step 2: Fill Out Business Info

**Screen shows:** "Tell us about the business"

Fill in:
- Business Name: `ABC Roofing`
- Industry: Select from dropdown
- Primary Location: `Sarasota, FL`
- Website: `https://abcroofing.com` (optional)

Click **"Find Keywords"**

### Step 3: Select Keywords

**Screen shows:** Keyword opportunities with search volumes

The system automatically researches keywords for their industry + location.

**You do:**
1. Click **"Auto-Select Best Keywords"** (or manually pick)
2. Select 3-5 PRIMARY keywords (main services like "roof repair sarasota")
3. Select 5-10 SECONDARY keywords (supporting topics like "metal roof cost")

Click **"Review Strategy"**

### Step 4: Review & Launch

**Screen shows:** Summary of client + selected keywords

Review everything looks right, then click **"Launch Client"**

**Wait 2-5 minutes.** The AI is generating:
- 10-20 blog posts
- 30-60 social media posts
- Keyword strategy
- Content calendar

### Step 5: Success!

**Screen shows:** "Client Launched!" with stats

You'll see:
- X blog posts created
- X social posts created
- X keywords targeted
- X monthly search volume

**The client is now in the system.**

---

## PHASE 3: What Got Created

After intake, the client has:

| Content Type | Quantity | Where to Find |
|-------------|----------|---------------|
| Blog Posts | 10-20 | Client Dashboard → Content |
| Social Posts | 30-60 | Client Dashboard → Social |
| Keywords | 5-15 | Client Dashboard → Keywords |
| Service Pages | Generate on-demand | Success screen → "Generate Service Pages" |

---

## PHASE 4: Deliver Content to Client

### Option A: Manual Copy/Paste
1. Go to `/client` dashboard
2. Select the client
3. Click on any blog post
4. Copy the content
5. Paste into their WordPress

### Option B: Connect WordPress (Automated)
1. Go to `/admin` → Integrations
2. Add WordPress credentials for the client
3. Now you can one-click publish from the Content Queue

### Option C: Give Client Access
1. Go to `/admin` → Users
2. Create a user for the client
3. Give them the Portal URL: `/portal`
4. They can view their content, leads, performance

---

## PHASE 5: Ongoing Management

### Daily (Automated)
- System checks competitor rankings at 3 AM
- System checks client rankings at 5 AM
- You get email digest if anything important changes

### Weekly (You Do)
1. Log into `/agency` (Agency Command Center)
2. Review "Health Scores" for all clients
3. Check for any alerts (rankings dropped, etc.)
4. Publish queued content to WordPress

### Monthly (You Do)
1. Generate fresh blog posts for each client
2. Review competitor analysis
3. Adjust keyword strategy if needed

---

## THE DASHBOARDS

| URL | Who Uses It | What It Does |
|-----|-------------|--------------|
| `/intake` | You | Onboard new clients |
| `/admin` | You | Manage users, settings, AI agents |
| `/agency` | You | See all clients at once, health scores |
| `/elite` | You | Deep SEO: rank tracking, competitor monitoring |
| `/client` | You | View/edit content for one client |
| `/portal` | Client | Their view: leads, performance, content |

---

## QUICK REFERENCE

### To Onboard a New Client:
```
/intake → Fill form → Select keywords → Launch
```

### To See All Clients:
```
/agency → View health scores, alerts, quick actions
```

### To Generate More Content:
```
/client → Select client → Content tab → "Generate Blog Posts"
```

### To Publish Content:
```
/client → Content Queue → Select posts → "Publish to WordPress"
```

### To Check Rankings:
```
/elite → Select client → Rankings tab
```

### To Manage AI Prompts:
```
/admin → AI Agents → Edit any of the 7 agents
```

---

## EXAMPLE: Full New Client Flow

**Scenario:** New HVAC client in Tampa signs up.

1. **You receive payment** - $2,500/month

2. **Kickoff call** (15 min) - Get their info:
   - Business: "Tampa Bay Cooling & Heating"
   - Location: Tampa, FL
   - Services: AC repair, AC installation, duct cleaning
   - Competitors: They mention "Aire Serv Tampa"

3. **Intake** (5 min):
   - Go to `/intake`, log in
   - Enter business info
   - System finds keywords like:
     - "ac repair tampa" (2,400/mo)
     - "hvac tampa" (1,900/mo)
     - "air conditioning installation tampa" (880/mo)
   - Select best keywords
   - Click Launch

4. **Generation** (2-5 min):
   - System creates 15 blog posts
   - System creates 45 social posts
   - Done!

5. **Deliver** (same day):
   - Go to `/client`, select Tampa Bay Cooling
   - Review first 3 blog posts
   - Connect their WordPress
   - Publish first post

6. **Ongoing**:
   - Check `/agency` weekly for health score
   - Publish 1-2 posts per week
   - Generate fresh content monthly

---

## TROUBLESHOOTING

**Can't log in?**
→ Check you're using the admin email/password set during deploy

**No keywords appearing?**
→ Make sure SEMRush API key is set in environment variables

**Content generation failed?**
→ Check OpenAI API key is valid and has credits

**WordPress publish failed?**
→ Verify WP credentials in Admin → Integrations

---

## SUMMARY

1. Client pays → You do intake (5 min)
2. System generates months of content (5 min)
3. You deliver via WordPress or client portal
4. Monitor weekly via Agency dashboard
5. Generate fresh content monthly
6. Repeat for next client

**That's it. Same system, every client, $2,500/month each.**
