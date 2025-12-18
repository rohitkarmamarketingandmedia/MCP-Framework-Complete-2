# Bug Tracking - Fixed Issues

## v5.5.41 Bugs Fixed

### BUG-001: AUTH_TOKEN Undefined Variable
- **Severity**: 🔴 Critical
- **File**: `intake-dashboard.html`
- **Location**: `checkWebsiteForCompetitors()` function, line ~1732
- **Issue**: Used `AUTH_TOKEN` variable which doesn't exist. The correct variable is `token`.
- **Impact**: Function would throw `ReferenceError: AUTH_TOKEN is not defined`
- **Fix**: Changed `Bearer ${AUTH_TOKEN}` to `Bearer ${token}`
- **Date Fixed**: December 17, 2025

### BUG-002: XSS in Service Area Tags
- **Severity**: 🔴 High
- **File**: `intake-dashboard.html`
- **Location**: `renderServiceAreaTags()` function
- **Issue**: User input (`area`) directly inserted into innerHTML without escaping
- **Impact**: Malicious input like `<script>alert('xss')</script>` would execute
- **Fix**: Added `escapeHtml()` function, applied to area before rendering
- **Date Fixed**: December 17, 2025

### BUG-003: XSS in Custom USP
- **Severity**: 🔴 High
- **File**: `intake-dashboard.html`
- **Location**: `addCustomUSP()` function
- **Issue**: User input (`value`) directly inserted into innerHTML
- **Impact**: Same as BUG-002
- **Fix**: Applied `escapeHtml()` to value before rendering
- **Date Fixed**: December 17, 2025

### BUG-004: XSS in Competitor List
- **Severity**: 🟡 Medium
- **File**: `intake-dashboard.html`
- **Location**: `checkWebsiteForCompetitors()` function
- **Issue**: API response data (`comp.domain`, `comp.name`) inserted without escaping
- **Impact**: Lower risk since data comes from our API, but could be exploited
- **Fix**: Applied `escapeHtml()` to domain and name before rendering
- **Date Fixed**: December 17, 2025

---

## v5.5.40 Bugs Fixed

### BUG-005: Duplicate Closing Bracket
- **Severity**: 🔴 Critical
- **File**: `client-dashboard.html`
- **Location**: `beatCompetitorContent()` function
- **Issue**: Extra `});` causing syntax error
- **Fix**: Removed duplicate bracket
- **Date Fixed**: December 17, 2025

### BUG-006: Duplicate Element IDs
- **Severity**: 🟡 Medium
- **File**: `client-dashboard.html`
- **Location**: Multiple `bulkProgress` and `bulkProgressBar` IDs
- **Issue**: Same IDs used in legacy and new sections
- **Fix**: Renamed legacy section IDs to `oldBulkProgress` and `oldBulkProgressBar`
- **Date Fixed**: December 17, 2025

### BUG-007: Accidentally Renamed Element
- **Severity**: 🟡 Medium
- **File**: `client-dashboard.html`
- **Location**: New bulk generation section
- **Issue**: `bulkProgressBar` accidentally renamed during duplicate fix
- **Fix**: Restored correct ID for new section
- **Date Fixed**: December 17, 2025

---

## Security Fixes

### SEC-001: escapeHtml() Function Added
- **Date**: December 17, 2025
- **Purpose**: Prevent XSS attacks by escaping HTML entities
- **Implementation**:
```javascript
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```
- **Applied To**:
  1. `renderServiceAreaTags()` - area names
  2. `addCustomUSP()` - custom USP values
  3. `checkWebsiteForCompetitors()` - competitor domain
  4. `checkWebsiteForCompetitors()` - competitor name

---

## Known Issues (Not Yet Fixed)

### KNOWN-001: Form Validation Could Be More User-Friendly
- **Severity**: 🟢 Low
- **Description**: When validation fails, focus jumps to first invalid field but doesn't scroll smoothly
- **Workaround**: User can manually scroll
- **Planned Fix**: Add smooth scroll to invalid field

### KNOWN-002: Draft Not Cleared After Successful Submit
- **Severity**: 🟢 Low
- **Description**: localStorage draft persists even after successful client creation
- **Workaround**: Manual clear or wait 24 hours
- **Planned Fix**: Clear draft in launchClient() success handler

### KNOWN-003: Competitor Discovery Requires All Fields
- **Severity**: 🟢 Low
- **Description**: Must fill industry and geo before competitor discovery works
- **Workaround**: Fill those fields first
- **Planned Fix**: Show helpful message if fields missing
