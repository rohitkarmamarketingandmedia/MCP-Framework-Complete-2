# MCP Deploy v5.5.35 - CRITICAL HOTFIX

## 🔴 URGENT: WordPress Authentication Fix

This is a critical hotfix release that fixes the WordPress authentication regression introduced in v5.5.34.

### What Was Broken

If you upgraded to v5.5.34, WordPress authentication stopped working with the error:
> "The REST API is accessible but authentication failed. Try regenerating the Application Password in WordPress."

Even with valid, working credentials from v5.5.25, authentication failed.

### What Was Fixed

**Single line bug fix:** Restored the `status='any'` parameter that was accidentally removed.

```python
# Before (v5.5.34 - BROKEN):
params={'per_page': 1}

# After (v5.5.35 - FIXED):
params={'per_page': 1, 'status': 'any'}
```

### Why This Matters

- **Without `status='any'`:** WordPress only checks if you can view published posts (anyone can)
- **With `status='any'`:** WordPress checks if you can view draft/private posts (only authenticated editors)

The `status='any'` parameter is essential for properly validating WordPress authentication.

### Additional Improvements

1. Simplified HTTP headers to avoid triggering WordPress security plugins
2. Added clear comments explaining why `status='any'` is required
3. Updated CHANGELOG with detailed explanation

### Who Should Upgrade

- ✅ **Everyone on v5.5.34** - UPGRADE IMMEDIATELY
- ✅ **Anyone experiencing WordPress auth issues** - This will fix it
- ⚠️ **Users on v5.5.25 or earlier** - You can upgrade safely, this restores working behavior

### How to Upgrade

#### Option 1: Replace Entire Deployment
```bash
# Backup your current deployment
mv mcp-deploy-v5_5_34 mcp-deploy-v5_5_34.backup

# Extract this fixed version
unzip mcp-deploy-v5_5_35-FIXED.zip

# Restart your application
```

#### Option 2: Patch Just the WordPress Service
```bash
# Backup the current file
cp app/services/wordpress_service.py app/services/wordpress_service.py.backup

# Replace with fixed version
# (Copy from this zip: app/services/wordpress_service.py)

# Restart your application
```

#### Option 3: Manual One-Line Fix
```bash
# Edit: app/services/wordpress_service.py
# Find line 71: params={'per_page': 1},
# Change to: params={'per_page': 1, 'status': 'any'},
# Save and restart
```

### Verification

After upgrading, test your WordPress connection:

1. Go to Settings → Integrations → WordPress
2. Enter your credentials
3. Click "Test Connection"
4. Should show: ✅ "Connected as [your-username]"

If it still fails, check:
- WordPress user has Editor or Administrator role
- Application Password is correct (regenerate if needed)
- WordPress is version 5.6 or higher
- Permalinks are not set to "Plain"

### Files Changed

- `app/services/wordpress_service.py` - Fixed authentication test method
  - Line 71: Added `status='any'` parameter back
  - Lines 54-62: Simplified HTTP headers
  - Added explanatory comments

- `CHANGELOG.md` - Added v5.5.35 hotfix entry

### Version History

- **v5.5.25** - Working ✅
- **v5.5.34** - Broken ❌ (WordPress auth regression)
- **v5.5.35** - Fixed ✅ (This version)

### Support

If WordPress authentication still doesn't work after upgrading:

1. Check the detailed documentation in `/docs/REGRESSION_BUG_ANALYSIS.md`
2. Review the comparison guide: `/docs/COMPARISON_v5.5.25_vs_v5.5.34.md`
3. Run the diagnostic script: `python test_wordpress_connection.py`

### Technical Details

See the included documentation for complete technical analysis:
- `REGRESSION_BUG_ANALYSIS.md` - Full technical breakdown
- `COMPARISON_v5.5.25_vs_v5.5.34.md` - Side-by-side code comparison
- `QUICK_FIX_GUIDE.md` - Step-by-step fix instructions

---

## Summary

**Issue:** WordPress authentication broken in v5.5.34  
**Cause:** Missing `status='any'` parameter  
**Fix:** One line restored  
**Impact:** All WordPress integrations working again  
**Upgrade Priority:** 🔴 CRITICAL - Upgrade immediately if on v5.5.34

This is a simple, proven fix that restores the working behavior from v5.5.25.
