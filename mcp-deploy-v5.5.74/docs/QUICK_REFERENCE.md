# MCP Framework Quick Reference

## File Locations

### Dashboards
```
intake-dashboard.html     → /intake          Client onboarding wizard
client-dashboard.html     → /client/<id>     Individual client management
agency-dashboard.html     → /agency          Agency overview
admin-dashboard.html      → /admin           System administration
```

### Backend Routes
```
app/routes/auth.py        → /api/auth/*      Authentication
app/routes/intake.py      → /api/intake/*    Client onboarding
app/routes/clients.py     → /api/clients/*   Client CRUD
app/routes/blogs.py       → /api/blogs/*     Blog management
app/routes/social.py      → /api/social/*    Social media
app/routes/leads.py       → /api/leads/*     Lead tracking
app/routes/reviews.py     → /api/reviews/*   Review management
app/routes/seo.py         → /api/seo/*       SEO tools
app/routes/competitors.py → /api/competitors/* Competitor analysis
```

---

## JavaScript Functions (intake-dashboard.html)

### Validation & Progress
```javascript
validateField(input, fieldName)  // Show checkmark on valid field
updateFormProgress()             // Update completion percentage
validateStep1()                  // Validate and store Step 1 data
validateStep2()                  // Validate keyword selection
```

### Service Areas
```javascript
handleServiceAreaInput(event)    // Handle Enter/comma keypress
renderServiceAreaTags()          // Render tag chips
removeServiceArea(idx)           // Remove tag by index
```

### USPs (Unique Selling Points)
```javascript
updateIndustryUSPs()             // Called on industry change
collectSelectedUSPs()            // Read all checked USPs
addCustomUSP()                   // Add custom USP from input
```

### Competitors
```javascript
checkWebsiteForCompetitors()     // Auto-discover from website
```

### Draft Management
```javascript
saveDraft()                      // Save to localStorage
loadDraft()                      // Restore from localStorage
```

### Navigation
```javascript
goToStep(step)                   // Navigate to step (1-4)
startFresh()                     // Reset wizard to Step 1
resumeSavedSession()             // Resume from saved state
```

### Security
```javascript
escapeHtml(text)                 // Prevent XSS attacks
```

---

## Global Variables

```javascript
// Authentication
let token = localStorage.getItem('mcp_token') || '';
let headers = { 'Content-Type': 'application/json' };
const API_URL = window.location.origin;

// Wizard State
let currentStep = 1;
let clientData = {};
let keywords = [];

// Step 1 Specific
let serviceAreas = [];
let selectedUSPs = [];
let discoveredCompetitors = [];

// Step 2 Specific
let seoResearchResults = null;
```

---

## localStorage Keys

| Key | Type | Purpose |
|-----|------|---------|
| `mcp_token` | String | JWT authentication token |
| `intake_draft` | JSON | Step 1 form data (24hr expiry) |
| `intake_state` | JSON | Full wizard state for resume |

---

## API Request Template

```javascript
const response = await fetch(`${API_URL}/api/endpoint`, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
        // request data
    })
});

if (response.ok) {
    const data = await response.json();
    // handle success
} else {
    // handle error
}
```

---

## HTML Element Patterns

### Input with Validation Checkmark
```html
<div class="relative">
    <input type="text" id="field_name" 
           oninput="validateField(this, 'field_name')">
    <span id="check_field_name" class="absolute right-3 top-1/2 -translate-y-1/2 text-green-500 hidden">
        <svg><!-- checkmark --></svg>
    </span>
</div>
```

### Tag Input Container
```html
<div class="flex flex-wrap gap-2 p-3 border-2 rounded-xl" 
     onclick="document.getElementById('input_id').focus()">
    <div id="tags_container"></div>
    <input type="text" id="input_id" 
           onkeydown="handleInput(event)">
</div>
<input type="hidden" id="hidden_value">
```

### Checkbox Group
```html
<div id="checkbox_container" class="grid grid-cols-3 gap-2">
    <label class="flex items-center gap-2 p-2 cursor-pointer">
        <input type="checkbox" class="checkbox-class" 
               value="Value" onchange="collectValues()">
        <span>Label</span>
    </label>
</div>
```

---

## Common Tailwind Classes

```css
/* Buttons */
.btn-primary: px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700
.btn-secondary: px-6 py-3 border border-gray-300 rounded-xl hover:bg-gray-50

/* Cards */
.card: bg-white rounded-xl shadow-lg p-6

/* Inputs */
.input: w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500

/* Tags */
.tag: inline-flex items-center px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm

/* Toast Notifications */
.toast: fixed bottom-4 right-4 px-6 py-3 rounded-xl shadow-lg z-50
.toast-success: bg-green-500 text-white
.toast-error: bg-red-500 text-white
```

---

## Version Bumping

```bash
# Update version in app/__init__.py
sed -i 's/__version__ = "X.X.XX"/__version__ = "X.X.YY"/' app/__init__.py

# Create deployment package
zip -r mcp-deploy-vX.X.YY.zip . \
    -x "*.pyc" -x "__pycache__/*" -x ".git/*" \
    -x "instance/*" -x "*.db" -x "*.log" -x ".env"
```
