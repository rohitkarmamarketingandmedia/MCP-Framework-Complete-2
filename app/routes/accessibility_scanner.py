"""
MCP Framework - Accessibility Scanner Service
Scans websites for WCAG 2.1 compliance and generates reports
"""
import logging
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


class AccessibilityScanner:
    """Scans web pages for accessibility issues following WCAG 2.1 guidelines"""

    # Each check returns: { id, name, description, relevant, successes, failures, score, details[] }
    
    def scan_html(self, html: str, url: str = '') -> Dict[str, Any]:
        """Scan raw HTML content and return accessibility report"""
        from html.parser import HTMLParser
        
        results = {
            'url': url,
            'scanned_at': datetime.utcnow().isoformat(),
            'checks': [],
            'summary': {
                'total_checks': 0,
                'passed': 0,
                'failed': 0,
                'not_applicable': 0,
                'score': 0
            }
        }
        
        # Parse HTML into a simple structure
        parsed = self._parse_html(html)
        
        # Run all checks
        checks = [
            self._check_img_alt(parsed, html),
            self._check_html_lang(parsed, html),
            self._check_page_title(parsed, html),
            self._check_heading_structure(parsed, html),
            self._check_link_text(parsed, html),
            self._check_form_labels(parsed, html),
            self._check_button_labels(parsed, html),
            self._check_nav_landmark(parsed, html),
            self._check_main_landmark(parsed, html),
            self._check_aria_hidden(parsed, html),
            self._check_color_contrast_hints(parsed, html),
            self._check_meta_viewport(parsed, html),
            self._check_iframe_titles(parsed, html),
            self._check_skip_nav(parsed, html),
            self._check_tabindex(parsed, html),
            self._check_autofocus(parsed, html),
            self._check_empty_links(parsed, html),
            self._check_empty_buttons(parsed, html),
            self._check_duplicate_ids(parsed, html),
            self._check_footer_landmark(parsed, html),
        ]
        
        results['checks'] = checks
        
        # Calculate summary
        relevant_checks = [c for c in checks if c['relevant']]
        results['summary']['total_checks'] = len(checks)
        results['summary']['passed'] = sum(1 for c in relevant_checks if c['score'] == 100)
        results['summary']['failed'] = sum(1 for c in relevant_checks if c['score'] < 100)
        results['summary']['not_applicable'] = sum(1 for c in checks if not c['relevant'])
        
        if relevant_checks:
            results['summary']['score'] = round(
                sum(c['score'] for c in relevant_checks) / len(relevant_checks)
            )
        else:
            results['summary']['score'] = 100
        
        return results

    def _parse_html(self, html: str) -> Dict:
        """Quick regex-based HTML parsing for accessibility checks"""
        parsed = {
            'images': [],
            'links': [],
            'buttons': [],
            'headings': [],
            'forms': [],
            'inputs': [],
            'iframes': [],
            'nav_elements': [],
            'main_elements': [],
            'footer_elements': [],
            'aria_hidden': [],
            'ids': [],
            'html_tag': '',
            'title': '',
            'meta_viewport': '',
        }
        
        # HTML tag
        m = re.search(r'<html[^>]*>', html, re.I)
        if m:
            parsed['html_tag'] = m.group(0)
        
        # Title
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        if m:
            parsed['title'] = m.group(1).strip()
        
        # Meta viewport
        m = re.search(r'<meta[^>]*name=["\']viewport["\'][^>]*>', html, re.I)
        if m:
            parsed['meta_viewport'] = m.group(0)
        
        # Images
        for m in re.finditer(r'<img\b([^>]*)/?>', html, re.I):
            attrs = m.group(1)
            parsed['images'].append({
                'tag': m.group(0)[:200],
                'alt': self._get_attr(attrs, 'alt'),
                'has_alt': 'alt=' in attrs.lower() or 'alt =' in attrs.lower(),
                'src': self._get_attr(attrs, 'src'),
                'role': self._get_attr(attrs, 'role'),
            })
        
        # Links
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', html, re.I | re.S):
            attrs = m.group(1)
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            parsed['links'].append({
                'tag': m.group(0)[:200],
                'text': text,
                'href': self._get_attr(attrs, 'href'),
                'aria_label': self._get_attr(attrs, 'aria-label'),
                'title': self._get_attr(attrs, 'title'),
                'has_img': '<img' in m.group(2).lower(),
            })
        
        # Buttons
        for m in re.finditer(r'<button\b([^>]*)>(.*?)</button>', html, re.I | re.S):
            attrs = m.group(1)
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            parsed['buttons'].append({
                'tag': m.group(0)[:200],
                'text': text,
                'aria_label': self._get_attr(attrs, 'aria-label'),
                'title': self._get_attr(attrs, 'title'),
            })
        
        # Input-type buttons
        for m in re.finditer(r'<input\b([^>]*)/?>', html, re.I):
            attrs = m.group(1)
            input_type = self._get_attr(attrs, 'type')
            if input_type in ('submit', 'button', 'reset'):
                parsed['buttons'].append({
                    'tag': m.group(0)[:200],
                    'text': self._get_attr(attrs, 'value'),
                    'aria_label': self._get_attr(attrs, 'aria-label'),
                    'title': self._get_attr(attrs, 'title'),
                })
        
        # Headings
        for m in re.finditer(r'<(h[1-6])\b[^>]*>(.*?)</\1>', html, re.I | re.S):
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            parsed['headings'].append({
                'level': int(m.group(1)[1]),
                'text': text
            })
        
        # Form inputs
        for m in re.finditer(r'<input\b([^>]*)/?>', html, re.I):
            attrs = m.group(1)
            input_type = self._get_attr(attrs, 'type')
            if input_type not in ('hidden', 'submit', 'button', 'reset', 'image'):
                input_id = self._get_attr(attrs, 'id')
                parsed['inputs'].append({
                    'tag': m.group(0)[:200],
                    'type': input_type or 'text',
                    'id': input_id,
                    'name': self._get_attr(attrs, 'name'),
                    'aria_label': self._get_attr(attrs, 'aria-label'),
                    'aria_labelledby': self._get_attr(attrs, 'aria-labelledby'),
                    'placeholder': self._get_attr(attrs, 'placeholder'),
                    'has_label': bool(input_id and re.search(rf'<label[^>]*for=["\']?{re.escape(input_id)}["\']?', html, re.I)),
                })
        
        # Textareas
        for m in re.finditer(r'<textarea\b([^>]*)>', html, re.I):
            attrs = m.group(1)
            ta_id = self._get_attr(attrs, 'id')
            parsed['inputs'].append({
                'tag': m.group(0)[:200],
                'type': 'textarea',
                'id': ta_id,
                'name': self._get_attr(attrs, 'name'),
                'aria_label': self._get_attr(attrs, 'aria-label'),
                'aria_labelledby': self._get_attr(attrs, 'aria-labelledby'),
                'placeholder': self._get_attr(attrs, 'placeholder'),
                'has_label': bool(ta_id and re.search(rf'<label[^>]*for=["\']?{re.escape(ta_id)}["\']?', html, re.I)),
            })
        
        # Selects
        for m in re.finditer(r'<select\b([^>]*)>', html, re.I):
            attrs = m.group(1)
            sel_id = self._get_attr(attrs, 'id')
            parsed['inputs'].append({
                'tag': m.group(0)[:200],
                'type': 'select',
                'id': sel_id,
                'name': self._get_attr(attrs, 'name'),
                'aria_label': self._get_attr(attrs, 'aria-label'),
                'aria_labelledby': self._get_attr(attrs, 'aria-labelledby'),
                'placeholder': '',
                'has_label': bool(sel_id and re.search(rf'<label[^>]*for=["\']?{re.escape(sel_id)}["\']?', html, re.I)),
            })
        
        # Iframes
        for m in re.finditer(r'<iframe\b([^>]*)>', html, re.I):
            attrs = m.group(1)
            parsed['iframes'].append({
                'tag': m.group(0)[:200],
                'title': self._get_attr(attrs, 'title'),
                'aria_label': self._get_attr(attrs, 'aria-label'),
                'src': self._get_attr(attrs, 'src'),
            })
        
        # Nav elements
        for m in re.finditer(r'<nav\b([^>]*)>', html, re.I):
            parsed['nav_elements'].append({
                'tag': m.group(0)[:200],
                'aria_label': self._get_attr(m.group(1), 'aria-label'),
            })
        
        # Main elements
        for m in re.finditer(r'<main\b([^>]*)>', html, re.I):
            parsed['main_elements'].append({'tag': m.group(0)[:200]})
        
        # Also check role="main"
        for m in re.finditer(r'<\w+\b[^>]*role=["\']main["\'][^>]*>', html, re.I):
            parsed['main_elements'].append({'tag': m.group(0)[:200]})
        
        # Footer
        for m in re.finditer(r'<footer\b([^>]*)>', html, re.I):
            parsed['footer_elements'].append({'tag': m.group(0)[:200]})
        
        # aria-hidden elements
        for m in re.finditer(r'aria-hidden=["\']true["\']', html, re.I):
            parsed['aria_hidden'].append({'count': 1})
        
        # All IDs
        for m in re.finditer(r'\bid=["\']([^"\']+)["\']', html, re.I):
            parsed['ids'].append(m.group(1))
        
        return parsed

    def _get_attr(self, attrs_str: str, attr_name: str) -> str:
        """Extract attribute value from an attribute string"""
        patterns = [
            rf'{attr_name}\s*=\s*"([^"]*)"',
            rf"{attr_name}\s*=\s*'([^']*)'",
            rf'{attr_name}\s*=\s*(\S+)',
        ]
        for p in patterns:
            m = re.search(p, attrs_str, re.I)
            if m:
                return m.group(1)
        return ''

    # ============= INDIVIDUAL CHECKS =============

    def _check_img_alt(self, parsed, html) -> Dict:
        """Check 1: Images must have alt attributes"""
        images = parsed['images']
        if not images:
            return self._result(1, 'Image Alt Text', 
                'Images must have alt attributes for screen readers.',
                False, 0, 0)
        
        successes = [img for img in images if img['has_alt']]
        failures = [img for img in images if not img['has_alt'] and img.get('role') != 'presentation']
        
        return self._result(1, 'Image Alt Text',
            'Images must have alt attributes to provide text alternatives for screen readers.',
            True, len(successes), len(failures),
            [f['tag'][:120] for f in failures[:5]])

    def _check_html_lang(self, parsed, html) -> Dict:
        """Check 2: HTML must have lang attribute"""
        tag = parsed['html_tag']
        has_lang = bool(re.search(r'lang=["\'][^"\']+["\']', tag, re.I))
        
        return self._result(2, 'Page Language',
            'The HTML element must specify a language so screen readers use correct pronunciation.',
            True, 1 if has_lang else 0, 0 if has_lang else 1)

    def _check_page_title(self, parsed, html) -> Dict:
        """Check 3: Page must have a title"""
        title = parsed['title']
        has_title = bool(title and len(title) > 2)
        
        return self._result(3, 'Page Title',
            'Pages must have descriptive titles for screen reader users and browser tab identification.',
            True, 1 if has_title else 0, 0 if has_title else 1,
            [f'Title: "{title}"'] if title else ['No <title> found'])

    def _check_heading_structure(self, parsed, html) -> Dict:
        """Check 4: Headings should be in proper order"""
        headings = parsed['headings']
        if not headings:
            return self._result(4, 'Heading Structure',
                'Pages should use proper heading hierarchy (H1-H6).',
                True, 0, 1, ['No headings found on the page'])
        
        issues = []
        has_h1 = any(h['level'] == 1 for h in headings)
        if not has_h1:
            issues.append('No H1 heading found')
        
        h1_count = sum(1 for h in headings if h['level'] == 1)
        if h1_count > 1:
            issues.append(f'Multiple H1 headings found ({h1_count})')
        
        # Check for skipped levels
        prev_level = 0
        for h in headings:
            if h['level'] > prev_level + 1 and prev_level > 0:
                issues.append(f'Heading level skipped: H{prev_level} to H{h["level"]} ("{h["text"][:40]}")')
            prev_level = h['level']
        
        successes = len(headings) - len(issues)
        return self._result(4, 'Heading Structure',
            'Headings should follow a logical hierarchy without skipping levels.',
            True, max(0, successes), len(issues), issues[:5])

    def _check_link_text(self, parsed, html) -> Dict:
        """Check 5: Links must have discernible text"""
        links = parsed['links']
        if not links:
            return self._result(5, 'Link Text', 'Links must have meaningful text.', False, 0, 0)
        
        failures = []
        ambiguous = {'click here', 'here', 'read more', 'learn more', 'more', 'link', 'click'}
        
        for link in links:
            text = link['text'].lower().strip()
            label = link['aria_label']
            
            if not text and not label and not link['has_img']:
                failures.append(f"Empty link: {link['tag'][:100]}")
            elif text in ambiguous and not label:
                failures.append(f"Ambiguous link text: \"{link['text']}\"")
        
        return self._result(5, 'Link Text',
            'Links must have meaningful, descriptive text for screen reader users.',
            True, len(links) - len(failures), len(failures), failures[:5])

    def _check_form_labels(self, parsed, html) -> Dict:
        """Check 6: Form inputs must have labels"""
        inputs = parsed['inputs']
        if not inputs:
            return self._result(6, 'Form Labels',
                'Form inputs must have associated labels.',
                False, 0, 0)
        
        failures = []
        for inp in inputs:
            has_label = (
                inp['has_label'] or
                inp['aria_label'] or
                inp['aria_labelledby'] or
                inp['placeholder']  # Placeholder as last resort
            )
            if not has_label:
                failures.append(f"Input without label: {inp['tag'][:100]}")
        
        return self._result(6, 'Form Labels',
            'Form controls must have labels so screen readers can announce their purpose.',
            True, len(inputs) - len(failures), len(failures), failures[:5])

    def _check_button_labels(self, parsed, html) -> Dict:
        """Check 7: Buttons must have accessible names"""
        buttons = parsed['buttons']
        if not buttons:
            return self._result(7, 'Button Labels',
                'Buttons must have accessible text.',
                False, 0, 0)
        
        failures = []
        for btn in buttons:
            has_name = btn['text'] or btn['aria_label'] or btn['title']
            if not has_name:
                failures.append(f"Button without label: {btn['tag'][:100]}")
        
        return self._result(7, 'Button Labels',
            'Buttons must contain text or aria-label for screen readers.',
            True, len(buttons) - len(failures), len(failures), failures[:5])

    def _check_nav_landmark(self, parsed, html) -> Dict:
        """Check 8: Navigation should use <nav> elements"""
        navs = parsed['nav_elements']
        has_nav = len(navs) > 0
        
        # Check if navs have labels
        unlabeled = [n for n in navs if not n['aria_label']]
        
        details = []
        if not has_nav:
            details.append('No <nav> elements found')
        if len(unlabeled) > 0 and len(navs) > 1:
            details.append(f'{len(unlabeled)} nav elements without aria-label (needed when multiple navs exist)')
        
        return self._result(8, 'Navigation Landmarks',
            'Navigation regions should use <nav> elements with aria-labels.',
            True, len(navs), len(details), details)

    def _check_main_landmark(self, parsed, html) -> Dict:
        """Check 9: Page should have a <main> landmark"""
        mains = parsed['main_elements']
        issues = []
        
        if not mains:
            issues.append('No <main> element found')
        elif len(mains) > 1:
            issues.append(f'Multiple <main> landmarks found ({len(mains)}) — should be exactly 1')
        
        return self._result(9, 'Main Landmark',
            'Pages should have exactly one <main> landmark for primary content.',
            True, 1 if len(mains) == 1 else 0, len(issues), issues)

    def _check_aria_hidden(self, parsed, html) -> Dict:
        """Check 10: aria-hidden should not hide visible interactive content"""
        # Basic check — just report count
        count = len(parsed['aria_hidden'])
        return self._result(10, 'ARIA Hidden Usage',
            'aria-hidden="true" should only be used on decorative or redundant content.',
            count > 0, count, 0, [f'{count} elements with aria-hidden="true" detected'])

    def _check_color_contrast_hints(self, parsed, html) -> Dict:
        """Check 11: Look for potential contrast issues (limited without rendering)"""
        # We can only detect inline styles with low-contrast colors
        issues = []
        
        # Check for light gray text on white
        light_text = re.findall(r'color:\s*#(?:ccc|ddd|eee|f[0-9a-f]{2}f[0-9a-f]{2}f[0-9a-f]{2}|(?:cc|dd|ee|ff){3})', html, re.I)
        if light_text:
            issues.append(f'{len(light_text)} elements with potentially low-contrast text colors detected')
        
        return self._result(11, 'Color Contrast (Basic)',
            'Text must have sufficient contrast against its background (4.5:1 for normal text).',
            len(issues) > 0, 0 if issues else 1, len(issues), issues,
            note='Full contrast analysis requires visual rendering. This is a basic check only.')

    def _check_meta_viewport(self, parsed, html) -> Dict:
        """Check 12: Meta viewport should not disable zoom"""
        tag = parsed['meta_viewport']
        if not tag:
            return self._result(12, 'Viewport Meta',
                'Page should include a viewport meta tag.',
                True, 0, 1, ['No viewport meta tag found'])
        
        issues = []
        if 'user-scalable=no' in tag.lower() or 'user-scalable = no' in tag.lower():
            issues.append('user-scalable=no prevents users from zooming')
        if re.search(r'maximum-scale\s*=\s*1([^0-9]|$)', tag, re.I):
            issues.append('maximum-scale=1 prevents users from zooming')
        
        return self._result(12, 'Viewport Zoom',
            'Viewport should allow user scaling for low-vision users.',
            True, 1 if not issues else 0, len(issues), issues)

    def _check_iframe_titles(self, parsed, html) -> Dict:
        """Check 13: Iframes must have titles"""
        iframes = parsed['iframes']
        if not iframes:
            return self._result(13, 'Iframe Titles',
                'Iframes must have title attributes for screen readers.',
                False, 0, 0)
        
        failures = [f for f in iframes if not f['title'] and not f['aria_label']]
        
        return self._result(13, 'Iframe Titles',
            'Each iframe needs a title attribute describing its purpose.',
            True, len(iframes) - len(failures), len(failures),
            [f"Iframe without title: {f['src'][:80]}" for f in failures[:5]])

    def _check_skip_nav(self, parsed, html) -> Dict:
        """Check 14: Page should have a skip navigation link"""
        has_skip = bool(re.search(r'<a[^>]*href=["\']#(main|content|skip|maincontent)["\'][^>]*>', html, re.I))
        if not has_skip:
            has_skip = bool(re.search(r'skip\s*(to\s*)?(main|content|nav)', html, re.I))
        
        return self._result(14, 'Skip Navigation',
            'Pages should provide a skip navigation link for keyboard users.',
            True, 1 if has_skip else 0, 0 if has_skip else 1,
            [] if has_skip else ['No skip navigation link detected'])

    def _check_tabindex(self, parsed, html) -> Dict:
        """Check 15: tabindex should not be greater than 0"""
        bad_tabindex = re.findall(r'tabindex=["\']([2-9]|\d{2,})["\']', html)
        
        return self._result(15, 'Tab Order',
            'tabindex values greater than 0 disrupt natural keyboard navigation order.',
            len(bad_tabindex) > 0, 0 if bad_tabindex else 1, len(bad_tabindex),
            [f'{len(bad_tabindex)} elements with tabindex > 0'] if bad_tabindex else [])

    def _check_autofocus(self, parsed, html) -> Dict:
        """Check 16: Autofocus should not be used"""
        has_autofocus = bool(re.search(r'\bautofocus\b', html, re.I))
        return self._result(16, 'No Autofocus',
            'autofocus can disorient screen reader users and keyboard users.',
            has_autofocus, 0 if has_autofocus else 1, 1 if has_autofocus else 0,
            ['autofocus attribute detected'] if has_autofocus else [])

    def _check_empty_links(self, parsed, html) -> Dict:
        """Check 17: Links should not be empty"""
        links = parsed['links']
        if not links:
            return self._result(17, 'Non-Empty Links', 'Links must have content.', False, 0, 0)
        
        empty = [l for l in links if not l['text'] and not l['aria_label'] and not l['has_img']]
        
        return self._result(17, 'Non-Empty Links',
            'Links must contain text, an image with alt text, or aria-label.',
            True, len(links) - len(empty), len(empty),
            [f"Empty link: href=\"{e['href'][:60]}\"" for e in empty[:5]])

    def _check_empty_buttons(self, parsed, html) -> Dict:
        """Check 18: Buttons should not be empty"""
        buttons = parsed['buttons']
        if not buttons:
            return self._result(18, 'Non-Empty Buttons', 'Buttons must have content.', False, 0, 0)
        
        empty = [b for b in buttons if not b['text'] and not b['aria_label'] and not b['title']]
        
        return self._result(18, 'Non-Empty Buttons',
            'Buttons must contain text or have an aria-label.',
            True, len(buttons) - len(empty), len(empty),
            [b['tag'][:100] for b in empty[:5]])

    def _check_duplicate_ids(self, parsed, html) -> Dict:
        """Check 19: IDs must be unique"""
        ids = parsed['ids']
        if not ids:
            return self._result(19, 'Unique IDs', 'Element IDs must be unique.', False, 0, 0)
        
        seen = {}
        duplicates = []
        for id_val in ids:
            if id_val in seen:
                if seen[id_val] == 1:
                    duplicates.append(id_val)
                seen[id_val] += 1
            else:
                seen[id_val] = 1
        
        return self._result(19, 'Unique IDs',
            'Element IDs must be unique — duplicate IDs break ARIA references and label associations.',
            True, len(set(ids)) - len(duplicates), len(duplicates),
            [f'Duplicate id="{d}"' for d in duplicates[:5]])

    def _check_footer_landmark(self, parsed, html) -> Dict:
        """Check 20: Page should have a footer/contentinfo landmark"""
        footers = parsed['footer_elements']
        has_footer = len(footers) > 0
        has_role = bool(re.search(r'role=["\']contentinfo["\']', html, re.I))
        
        return self._result(20, 'Footer Landmark',
            'Pages should have a <footer> or contentinfo landmark.',
            True, 1 if (has_footer or has_role) else 0,
            0 if (has_footer or has_role) else 1)

    # ============= HELPERS =============
    
    def _result(self, check_id: int, name: str, description: str,
                relevant: bool, successes: int, failures: int,
                details: List[str] = None, note: str = '') -> Dict:
        """Build a standardized check result"""
        if relevant and (successes + failures) > 0:
            score = round((successes / (successes + failures)) * 100)
        elif relevant and failures == 0:
            score = 100
        else:
            score = 100
        
        return {
            'id': check_id,
            'name': name,
            'description': description,
            'relevant': relevant,
            'successes': successes,
            'failures': failures,
            'score': score,
            'details': details or [],
            'note': note
        }


# Singleton
_scanner = None

def get_accessibility_scanner() -> AccessibilityScanner:
    global _scanner
    if _scanner is None:
        _scanner = AccessibilityScanner()
    return _scanner
