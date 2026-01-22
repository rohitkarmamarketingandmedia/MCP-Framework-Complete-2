# Google Integration Setup Guide

If you are seeing errors in the logs related to **Google Analytics 4 (GA4)** or **Google Search Console (GSC)**, follow these steps to fix the permissions.

## 1. Enable Google Search Console API

If you see `accessNotConfigured` or "Google Search Console API has not been used in project..." in the logs:

1.  Go to the [Google Cloud Console API Library](https://console.developers.google.com/apis/api/searchconsole.googleapis.com/overview).
2.  Select your project from the top dropdown.
3.  Click the blue **ENABLE** button.
4.  Wait a few minutes for the change to propagate.

## 2. Grant Permissions to GA4 Property

If you see `User does not have sufficient permissions` for GA4:

1.  Open your `credentials.json` file (or check the `GA4_CREDENTIALS_JSON` environment variable).
2.  Find the `client_email` field (e.g., `service-account@project-id.iam.gserviceaccount.com`).
3.  Copy this email address.
4.  Go to your [Google Analytics Admin](https://analytics.google.com/analytics/web/#/admin).
5.  Select your Property.
6.  Click **Property Access Management**.
7.  Click the **+** button -> **Add users**.
8.  Paste the service account email.
9.  Assign the **Viewer** role (or higher).
10. Save.

## 3. Grant Permissions to Google Search Console

1.  Go to [Google Search Console](https://search.google.com/search-console).
2.  Select your property (website).
3.  Go to **Settings** -> **Users and permissions**.
4.  Click **Add User**.
5.  Paste the same service account email from step 2.
6.  Permission: **Full** or **Restricted** (Restricted is usually enough for reading data).
7.  Add.

## 4. Verify Configuration

Restart your application and check the logs. The error messages should disappear and be replaced with successful data retrieval logs.
