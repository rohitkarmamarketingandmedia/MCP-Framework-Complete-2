# MCP Framework Bug Report
## Generated: December 16, 2025

---

## CRITICAL BUGS (Must Fix Immediately)

### BUG #1: Missing `client_id` Property on DBUser Model
**Severity:** CRITICAL  
**Files Affected:** 
- `app/routes/leads.py` (lines 95, 133)
- `app/routes/clients.py` (lines 267, 272)

**Issue:**  
The code references `current_user.client_id` (singular) but the `DBUser` model only has `client_ids` (plural, stored as JSON array). This causes an `AttributeError` when a client user tries to access the leads tab.

**Current Code (leads.py:95):**
```python
elif current_user.client_id and str(current_user.client_id) == str(client_id):
```

**Fix Required:**  
Add a `client_id` property to the `DBUser` model in `app/models/db_models.py`:

```python
@property
def client_id(self) -> Optional[str]:
    """Return the first client_id for backwards compatibility"""
    ids = self.get_client_ids()
    return ids[0] if ids else None
```

---

### BUG #2: Missing `gbp_place_id` Field in DBClient Model
**Severity:** HIGH  
**Files Affected:**
- `app/routes/leads.py` (line 187)
- `app/models/db_models.py`

**Issue:**  
The leads route references `client.gbp_place_id` but the `DBClient` model only has `gbp_location_id`. This will cause an `AttributeError` when a lead is converted and auto-review is triggered.

**Current Code (leads.py:187):**
```python
if client and client.gbp_place_id:
    review_url = f"https://search.google.com/local/writereview?placeid={client.gbp_place_id}"
```

**Fix Required:**  
Change to use `gbp_location_id`:
```python
if client and client.gbp_location_id:
    review_url = f"https://search.google.com/local/writereview?placeid={client.gbp_location_id}"
```

---

### BUG #3: Missing Logger Definition in auth.py
**Severity:** HIGH  
**File:** `app/routes/auth.py` (lines 524, 602, 673)

**Issue:**  
The file uses `logger.info()`, `logger.warning()`, etc. but never defines the logger variable. This will cause `NameError: name 'logger' is not defined`.

**Fix Required:**  
Add at the top of the file (after imports):
```python
import logging
logger = logging.getLogger(__name__)
```

---

## HIGH SEVERITY BUGS

### BUG #4: Trailing Slash in API URL Causing Request Failures
**Severity:** HIGH  
**File:** `portal-dashboard.html` (line 881)

**Issue:**  
The API URL has a trailing slash before query parameters: `/api/leads/?client_id=`
This can cause routing issues or 404 errors on some server configurations.

**Current Code:**
```javascript
const leadsRes = await fetch(`${API_URL}/api/leads/?client_id=${clientId}&days=${days}&limit=100`, { headers });
```

**Fix Required:**
```javascript
const leadsRes = await fetch(`${API_URL}/api/leads?client_id=${clientId}&days=${days}&limit=100`, { headers });
```

---

### BUG #5: HTTPS Not Forced for Render.com in Multiple Dashboards
**Severity:** HIGH  
**Files Affected:**
- `elite-dashboard.html`
- `agency-dashboard.html`
- `portal-dashboard.html`
- `dashboard.html`

**Issue:**  
The `API_URL` configuration does not explicitly force HTTPS for Render.com deployments. If the page is accessed via HTTP, API calls may fail due to mixed content blocking.

**Fix Required:**  
Update the API_URL configuration in all affected files:

```javascript
// FORCE HTTPS for API_URL
let API_URL = window.location.origin;
// Always force HTTPS for Render.com deployments
if (API_URL.includes('onrender.com') || API_URL.includes('render.com')) {
    API_URL = API_URL.replace('http://', 'https://');
}
if (API_URL.startsWith('http://') && !API_URL.includes('localhost') && !API_URL.includes('127.0.0.1')) {
    API_URL = API_URL.replace('http://', 'https://');
}
console.log('✅ API_URL:', API_URL);
```

---

## MEDIUM SEVERITY BUGS

### BUG #6: Inconsistent API Endpoint Paths
**Severity:** MEDIUM  
**Files Affected:** Multiple HTML dashboards

**Issue:**  
Some files use `/api/leads/` (with trailing slash) while others use `/api/leads` (without). This inconsistency can cause issues.

**Locations:**
- `portal-dashboard.html:881` - uses `/api/leads/`
- `client-dashboard.html:4522` - uses `/api/leads`

**Fix Required:**  
Standardize all API endpoints to NOT have trailing slashes.

---

### BUG #7: Missing Null Checks Before Accessing Properties
**Severity:** MEDIUM  
**Files Affected:** Multiple dashboard HTML files

**Issue:**  
Several places access `currentClient.id` without first checking if `currentClient` is defined.

**Example vulnerable code:**
```javascript
let url = `${API_URL}/api/leads?client_id=${currentClient.id}`;
```

**Fix Required:**  
Add null checks:
```javascript
if (!currentClient) {
    showError('No client selected');
    return;
}
let url = `${API_URL}/api/leads?client_id=${currentClient.id}`;
```

---

## LOW SEVERITY ISSUES

### ISSUE #1: Test Files Contain Hardcoded Credentials
**Severity:** LOW (test files only)  
**Files:** `test_smoke.py`, `test_all.py`

**Issue:**  
Test files contain hardcoded test credentials. While this is acceptable for testing, it should be noted.

---

## SUMMARY OF REQUIRED FIXES

| Priority | Bug | File(s) | Status |
|----------|-----|---------|--------|
| 🔴 CRITICAL | Missing client_id property | db_models.py | NEEDS FIX |
| 🔴 CRITICAL | Wrong gbp field name | leads.py | NEEDS FIX |
| 🟠 HIGH | Missing logger | auth.py | NEEDS FIX |
| 🟠 HIGH | Trailing slash in URL | portal-dashboard.html | NEEDS FIX |
| 🟠 HIGH | HTTPS not forced | Multiple HTML files | NEEDS FIX |
| 🟡 MEDIUM | Inconsistent endpoints | Multiple files | NEEDS FIX |
| 🟡 MEDIUM | Missing null checks | Multiple files | OPTIONAL |

---

## NEXT STEPS

1. Apply all CRITICAL and HIGH severity fixes
2. Test the leads tab functionality
3. Test on Render.com deployment
4. Verify HTTPS is working correctly

