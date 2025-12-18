# MCP Framework Changelog

## Version 5.5.41 (December 17, 2025)

### Client Onboarding Wizard - Step 1 Enhancements

#### New Features
- **Inline Field Validation**: Real-time green checkmarks on valid fields
- **Form Completion Progress Bar**: Shows 0-100% with color changes (yellow → blue → green)
- **Service Area Tags Input**: Type and press Enter to add, visual chips with X to remove
- **USP Checkboxes**: 9 pre-defined unique selling points for quick selection
- **Custom USP Input**: Add custom differentiators
- **Competitor Auto-Discovery**: Enter website URL to find competitors automatically
- **Save Draft**: Saves to localStorage, auto-restores within 24 hours
- **Expanded Optional Fields**: Address, Years in Business, Google Business Profile URL

#### New Industries Added
- Lawn Care / Maintenance
- Snow Removal

#### Bug Fixes
- Fixed `AUTH_TOKEN` undefined variable (should be `token`)
- Fixed XSS vulnerability in service area tag rendering
- Fixed XSS vulnerability in custom USP rendering
- Fixed XSS vulnerability in competitor list rendering

#### Security Improvements
- Added `escapeHtml()` function for safe HTML rendering
- Applied escaping to all user-input and API-response innerHTML insertions

#### New JavaScript Functions (12 total)
1. `validateField(input, fieldName)` - Real-time field validation with checkmarks
2. `updateFormProgress()` - Calculate and display form completion percentage
3. `handleServiceAreaInput(event)` - Handle Enter/comma key for adding areas
4. `renderServiceAreaTags()` - Create visual tag chips for service areas
5. `removeServiceArea(idx)` - Remove a service area tag
6. `updateIndustryUSPs()` - Collect USPs when industry changes
7. `collectSelectedUSPs()` - Read all checked USP checkboxes
8. `addCustomUSP()` - Add custom USP from text input
9. `checkWebsiteForCompetitors()` - Auto-discover competitors via API
10. `saveDraft()` - Save form data to localStorage
11. `loadDraft()` - Restore form data from localStorage
12. `escapeHtml(text)` - Prevent XSS by escaping HTML entities

#### Files Modified
- `intake-dashboard.html` - Step 1 rebuilt (~500 lines HTML, ~300 lines JS)
- `app/__init__.py` - Version bump to 5.5.41

---

## Version 5.5.40 (December 17, 2025)

### Content Generation, SEO Tools & Competitor Intelligence

#### New Features
- Bulk blog generation with progress tracking
- Real-time SEO analysis with scoring
- SERP preview (Google/Bing mock-ups)
- "Beat This Content" competitor analysis
- Content gap identification

#### Bug Fixes
- Removed duplicate `});` in `beatCompetitorContent()`
- Fixed duplicate element IDs (`bulkProgress`, `bulkProgressBar`)
- Restored accidentally renamed `bulkProgressBar`

#### Verification
- All 63 Python files pass syntax check

---

## Version 5.5.39 and Earlier

See previous session transcripts for detailed history.
