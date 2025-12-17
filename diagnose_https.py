#!/usr/bin/env python3
"""
Diagnostic Script for MCP Framework HTTPS Issues
Run this after deployment to check what's happening
"""

import requests
import json

RENDER_URL = "https://mcp-framework-complete-2.onrender.com"

print("=" * 80)
print("MCP FRAMEWORK DIAGNOSTIC SCRIPT")
print("=" * 80)

# Test 1: Health check
print("\n[TEST 1] Health Check")
try:
    response = requests.get(f"{RENDER_URL}/health", timeout=10)
    print(f"✓ Status: {response.status_code}")
    print(f"✓ Response: {response.json()}")
    print(f"✓ Final URL: {response.url}")
    if response.url.startswith('http://'):
        print("✗ WARNING: Redirected to HTTP!")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Check if HTTP redirects to HTTPS
print("\n[TEST 2] HTTP to HTTPS Redirect")
try:
    response = requests.get("https://mcp-framework-complete-2.onrender.com/health", 
                          allow_redirects=True, timeout=10)
    print(f"✓ Final URL: {response.url}")
    if response.url.startswith('https://'):
        print("✓ HTTP properly redirects to HTTPS")
    else:
        print("✗ ERROR: HTTP does NOT redirect to HTTPS!")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Check API endpoint
print("\n[TEST 3] API Info Endpoint")
try:
    response = requests.get(f"{RENDER_URL}/api", timeout=10)
    print(f"✓ Status: {response.status_code}")
    data = response.json()
    print(f"✓ Version: {data.get('version', 'unknown')}")
    print(f"✓ Status: {data.get('status', 'unknown')}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 4: Check client dashboard loads
print("\n[TEST 4] Client Dashboard")
try:
    response = requests.get(f"{RENDER_URL}/client-dashboard", timeout=10)
    print(f"✓ Status: {response.status_code}")
    if 'API_URL' in response.text:
        print("✓ Dashboard HTML loaded")
        # Check for version marker
        if 'Version: 1.0.1' in response.text:
            print("✓ NEW CODE DEPLOYED (version 1.0.1)")
        else:
            print("✗ OLD CODE STILL DEPLOYED (no version marker)")
    else:
        print("✗ Dashboard may be corrupted")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 5: Check chatbot embed code
print("\n[TEST 5] Chatbot Embed Code Generation")
print("(Requires auth token - manual test)")
print(f"URL: {RENDER_URL}/api/chatbot/config/CLIENT_ID/embed-code")
print("Check if embed code contains 'https://' not 'http://'")

# Test 6: Check leads endpoint
print("\n[TEST 6] Leads API Endpoint")
print("(Requires auth token - manual test)")  
print(f"URL: {RENDER_URL}/api/leads?client_id=CLIENT_ID")
print("Should return 401 (unauthorized) not 404 or mixed content error")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
print("\nIf tests fail:")
print("1. Check Render dashboard for deployment status")
print("2. Check Render logs for errors")
print("3. Wait 2-3 minutes for deployment to complete")
print("4. Hard refresh browser (Cmd+Shift+R / Ctrl+Shift+R)")
print("5. Clear browser cache completely")
