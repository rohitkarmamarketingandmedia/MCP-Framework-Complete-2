# DEPLOYMENT INSTRUCTIONS - CRITICAL

## The Problem

The error you're seeing is because **Render.com is still running OLD CODE**.

The error shows:
```
http://mcp-framework-complete-2.onrender.com/api/leads/?client_id=...
```

But the fixed code uses:
```
https://mcp-framework-complete-2.onrender.com/api/leads?client_id=...
```

## What Was Fixed

### CRITICAL BUGS FIXED:
1. **Missing `client_id` property** on DBUser model (CRITICAL)
2. **Wrong GBP field name** (`gbp_place_id` → `gbp_location_id`)
3. **Missing logger** in auth.py
4. **Trailing slash** in API URLs (`/api/leads/?` → `/api/leads?`)
5. **HTTP not forced to HTTPS** for Render.com deployments
6. **500 errors** on health-score, wins, and activity endpoints

### Files Modified:
- `app/models/db_models.py` - Added `client_id` property
- `app/routes/leads.py` - Fixed GBP field name
- `app/routes/auth.py` - Added logger
- `app/routes/client_experience.py` - Added error handling
- `portal-dashboard.html` - Removed trailing slash
- `client-dashboard.html` - Ultra-aggressive HTTPS forcing
- `admin-dashboard.html` - HTTPS forcing
- `agency-dashboard.html` - HTTPS forcing
- `elite-dashboard.html` - HTTPS forcing
- `dashboard.html` - HTTPS forcing
- `intake-dashboard.html` - HTTPS forcing

## How to Deploy

### Option 1: Via GitHub (Recommended)

1. Extract the `MCP-Framework-Fixed.zip` file
2. Replace all files in your GitHub repository
3. Commit and push:
   ```bash
   git add .
   git commit -m "Fix: HTTPS forcing, client_id property, API endpoints, error handling"
   git push origin main
   ```
4. Render will auto-deploy (wait 2-3 minutes)
5. **Hard refresh your browser**: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)

### Option 2: Manual Deploy on Render

1. Go to Render.com dashboard
2. Select your service
3. Click "Manual Deploy" → "Deploy latest commit"
4. Wait for deployment to complete
5. **Hard refresh your browser**: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)

### Option 3: Quick Fix (If you can't deploy immediately)

Add this as the FIRST script tag in client-dashboard.html:

```html
<script>
// Ultra-aggressive HTTPS redirect
if (window.location.protocol === 'http:' && window.location.hostname.includes('onrender.com')) {
    window.location.protocol = 'https:';
}
</script>
```

## Verification

After deployment, open browser console and check for:

```
✅ API_URL: https://mcp-framework-complete-2.onrender.com
```

If you see `http://` instead of `https://`, the old code is still running.

## Why This Keeps Happening

Render.com caches static files aggressively. You need to:

1. **Deploy new code** (push to GitHub)
2. **Wait for deployment** to complete (check Render dashboard)
3. **Hard refresh browser** to clear cache
4. **Check browser console** to verify new code is loaded

## Browser Cache Clearing

### Chrome/Firefox:
- Mac: `Cmd + Shift + R`
- Windows: `Ctrl + Shift + R`

### Or clear all cache:
- Chrome: Settings → Privacy → Clear browsing data
- Firefox: Settings → Privacy → Clear Data

## Still Not Working?

If after deployment and hard refresh you STILL see the error:

1. Open browser DevTools (F12)
2. Go to Network tab
3. Check the actual URL being requested
4. If it shows `http://` or `/api/leads/?`, screenshot it
5. Check Render.com logs for any deployment errors

## Testing the Fix

After deployment, test these endpoints in browser:

1. Health check: `https://mcp-framework-complete-2.onrender.com/health`
2. API info: `https://mcp-framework-complete-2.onrender.com/api`
3. Client dashboard: `https://mcp-framework-complete-2.onrender.com/client`

All should load without mixed content errors.

## Support

If you still have issues after following these steps:
1. Screenshot the browser console
2. Screenshot the Network tab showing the failed request
3. Check Render.com deployment logs
4. Verify the GitHub repository has the new code
