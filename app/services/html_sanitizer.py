"""
MCP Framework - HTML Sanitizer for SEO
Strips framework-specific CSS classes, inline styles, and data attributes
from blog HTML to produce clean, SEO-friendly markup.

Applied automatically to ALL blog content entry points:
  - AI-generated blogs (_clean_body)
  - Manual blog creation (/manual-create)
  - Smart-paste (/smart-paste)
  - Blog updates (PATCH /blog/<id>)
  - WordPress publishing (cms_service)
"""
import re
import logging

logger = logging.getLogger(__name__)


# CSS class patterns from Claude chat UI, Tailwind, and common frameworks
# that should NEVER appear in published blog HTML
_FRAMEWORK_CLASS_PATTERNS = [
    # Claude / Anthropic chat UI classes
    r'font-claude[^\s"]*',
    r'text-text-\d+',
    r'border-border-\d+',
    r'whitespace-\w+',
    r'break-words',
    r'anthropic[^\s"]*',
    r'claude[^\s"]*',
    r'semantic[^\s"]*',
    r'hljs[^\s"]*',
    r'language-[^\s"]*',
    r'highlight[^\s"]*',

    # Tailwind utility classes (when pasted from a rendered UI)
    r'-?m[trblxy]?-\[?[\d.]+(?:rem|px|em)?\]?',   # margin: mt-3, -mb-1, m-1.5, mx-1.5
    r'-?p[trblxy]?-\[?[\d.]+(?:rem|px|em)?\]?',    # padding: pl-8, pl-2, pb-1
    r'gap-\d+',
    r'flex(?:\s|")',
    r'flex-col',
    r'list-disc',
    r'leading-\[[\d.]+\]',
    r'text-\[[\d.]+(?:rem|em)\]',
    r'font-bold',
    r'underline(?:-offset-\d+)?',
    r'decoration-\d+',
    r'decoration-current(?:/\d+)?',
    r'hover:[\w-]+',
    r'focus:[\w-]+',

    # Generic patterns that indicate framework rendering artifacts
    r'\[[\w&:]+\][^\s"]*',     # Tailwind arbitrary selectors like [li_&]:mb-0
]

# Compile into a single pattern for efficiency
_CLASS_STRIP_RE = re.compile(
    r'(?:' + '|'.join(_FRAMEWORK_CLASS_PATTERNS) + r')',
    re.IGNORECASE
)


def sanitize_html_for_seo(html: str) -> str:
    """
    Clean blog HTML for SEO by removing framework CSS classes, inline styles,
    data attributes, and fixing structural issues.

    This is safe to call multiple times (idempotent).

    Args:
        html: Raw HTML blog content

    Returns:
        Cleaned HTML ready for publishing
    """
    if not html or not html.strip():
        return html

    original_len = len(html)

    # 1. Strip all class attributes that contain framework patterns
    html = _strip_framework_classes(html)

    # 2. Remove empty class attributes left behind
    html = re.sub(r'\s+class="\s*"', '', html)
    html = re.sub(r"\s+class='\s*'", '', html)

    # 3. Remove inline styles (blog HTML should use theme CSS)
    html = re.sub(r'\s+style="[^"]*"', '', html, flags=re.IGNORECASE)
    html = re.sub(r"\s+style='[^']*'", '', html, flags=re.IGNORECASE)

    # 4. Remove data-* attributes (framework state, not content)
    html = re.sub(r'\s+data-[a-z0-9-]+="[^"]*"', '', html, flags=re.IGNORECASE)

    # 5. Clean up resulting messy whitespace inside tags
    html = re.sub(r'<(\w+)\s{2,}', r'<\1 ', html)       # multiple spaces after tag name
    html = re.sub(r'\s+>', '>', html)                      # space before >
    html = re.sub(r'<(\w+)\s*>', r'<\1>', html)           # space in self-closing-ish tags

    # 6. Remove empty <span>, <div> wrappers that were only there for styling
    html = re.sub(r'<span\s*>(.*?)</span>', r'\1', html, flags=re.DOTALL)
    html = re.sub(r'<div\s*>(.*?)</div>', r'\1', html, flags=re.DOTALL)

    # 7. Clean up empty paragraphs and excessive whitespace
    html = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '', html)
    html = re.sub(r'<p>\s*</p>', '', html)
    html = re.sub(r'(<hr>)\s*\1+', r'\1', html)           # deduplicate <hr>

    # 8. Normalize <hr> tags (remove class/style leftovers)
    html = re.sub(r'<hr[^>]*/?>', '<hr>', html, flags=re.IGNORECASE)

    # 9. Ensure <ul> and <ol> are clean
    html = re.sub(r'<ul[^>]*>', '<ul>', html, flags=re.IGNORECASE)
    html = re.sub(r'<ol[^>]*>', '<ol>', html, flags=re.IGNORECASE)
    html = re.sub(r'<li[^>]*>', '<li>', html, flags=re.IGNORECASE)

    # 10. Clean <a> tags — keep href and rel, strip everything else
    html = _clean_anchor_tags(html)

    # 11. Clean heading tags — strip classes but keep content
    for tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        html = re.sub(
            rf'<{tag}[^>]*>(.*?)</{tag}>',
            rf'<{tag}>\1</{tag}>',
            html,
            flags=re.IGNORECASE | re.DOTALL
        )

    # 12. Final whitespace cleanup
    html = re.sub(r'\n{3,}', '\n\n', html)
    html = html.strip()

    cleaned_len = len(html)
    if original_len - cleaned_len > 500:
        logger.info(f"HTML sanitizer removed {original_len - cleaned_len} chars of framework markup")

    return html


def ensure_h1(html: str, title: str) -> str:
    """
    Ensure the blog body has exactly one H1 tag.
    If no H1 exists, wraps the title in an H1 and prepends it.
    If the first H2 matches the title, promotes it to H1.

    Args:
        html: Blog body HTML
        title: Blog post title (used as H1 text if none exists)

    Returns:
        HTML with exactly one H1
    """
    if not html or not title:
        return html

    # Check if H1 already exists
    h1_match = re.search(r'<h1[^>]*>.*?</h1>', html, re.IGNORECASE | re.DOTALL)
    if h1_match:
        return html

    # Check if the first H2 is essentially the title — promote it
    first_h2 = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.IGNORECASE | re.DOTALL)
    if first_h2:
        h2_text = re.sub(r'<[^>]+>', '', first_h2.group(1)).strip()
        # Fuzzy match: if H2 text is very similar to title, promote to H1
        if _texts_match(h2_text, title):
            html = html[:first_h2.start()] + f'<h1>{first_h2.group(1)}</h1>' + html[first_h2.end():]
            return html

    # No matching H2 found — prepend H1
    html = f'<h1>{title}</h1>\n{html}'
    return html


def fix_phone_links(html: str, correct_phone: str = None) -> str:
    """
    Fix inconsistent tel: links in the HTML.
    If correct_phone is provided, normalizes all tel: links to use that number.
    Otherwise, finds the most common phone number and uses that.

    Args:
        html: Blog body HTML
        correct_phone: The correct phone number (digits only or formatted)

    Returns:
        HTML with consistent phone links
    """
    if not html:
        return html

    # Find all tel: links
    tel_links = re.findall(r'href="tel:(\+?\d+)"', html)
    if not tel_links:
        return html

    if correct_phone:
        # Normalize correct phone to digits
        correct_digits = re.sub(r'\D', '', correct_phone)
        if len(correct_digits) == 11 and correct_digits.startswith('1'):
            correct_digits = correct_digits[1:]
    else:
        # Find the most common phone number (majority wins)
        from collections import Counter
        normalized = []
        for t in tel_links:
            digits = re.sub(r'\D', '', t)
            if len(digits) == 11 and digits.startswith('1'):
                digits = digits[1:]
            normalized.append(digits)
        counts = Counter(normalized)
        correct_digits = counts.most_common(1)[0][0]

    if len(correct_digits) != 10:
        return html  # Can't determine valid phone

    # Replace all tel: links with the correct number
    def _fix_tel(match):
        return f'href="tel:+1{correct_digits}"'

    html = re.sub(r'href="tel:\+?\d+"', _fix_tel, html)
    return html


def _strip_framework_classes(html: str) -> str:
    """Strip framework-specific CSS classes from class attributes."""

    def _clean_class_attr(match):
        full_attr = match.group(0)
        classes = match.group(1)

        # Remove each framework class pattern
        cleaned = _CLASS_STRIP_RE.sub('', classes)

        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        if not cleaned:
            return ''  # Remove entire class attribute if empty
        return f'class="{cleaned}"'

    # Match class="..." attributes
    html = re.sub(r'class="([^"]*)"', _clean_class_attr, html)
    html = re.sub(r"class='([^']*)'", _clean_class_attr, html)

    return html


def _clean_anchor_tags(html: str) -> str:
    """Clean <a> tags to keep only href and rel attributes."""

    def _clean_a(match):
        full_tag = match.group(0)
        # Extract href
        href_match = re.search(r'href="([^"]*)"', full_tag)
        if not href_match:
            href_match = re.search(r"href='([^']*)'", full_tag)
        href = href_match.group(1) if href_match else ''

        # Extract rel if present
        rel_match = re.search(r'rel="([^"]*)"', full_tag)
        rel = f' rel="{rel_match.group(1)}"' if rel_match else ''

        # Extract target if present
        target_match = re.search(r'target="([^"]*)"', full_tag)
        target = f' target="{target_match.group(1)}"' if target_match else ''

        return f'<a href="{href}"{rel}{target}>'

    html = re.sub(r'<a\s[^>]+>', _clean_a, html, flags=re.IGNORECASE)
    return html


def _texts_match(text1: str, text2: str) -> bool:
    """Fuzzy match two text strings (for title/H2 comparison)."""
    # Normalize both
    t1 = re.sub(r'[^a-z0-9]', '', text1.lower())
    t2 = re.sub(r'[^a-z0-9]', '', text2.lower())

    if not t1 or not t2:
        return False

    # Exact match after normalization
    if t1 == t2:
        return True

    # One contains the other (for cases like "Title" vs "Title | Company Name")
    if t1 in t2 or t2 in t1:
        return len(min(t1, t2, key=len)) / len(max(t1, t2, key=len)) > 0.7

    return False
