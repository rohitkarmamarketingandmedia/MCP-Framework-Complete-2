# app/services/blog_ai_single.py
"""
Robust blog generator that:
- Never hard-fails JSON (handles Invalid escape)
- Forces required fields
- Enforces word count via continuation
- Fixes SEO basics automatically
- Handles city correctly from keyword
"""
from __future__ import annotations

import json
import re
import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class BlogRequest:
    keyword: str
    target_words: int = 1800
    city: str = ""
    state: str = ""
    company_name: str = ""
    phone: str = ""
    email: str = ""
    industry: str = ""
    internal_links: Optional[List[Dict[str, str]]] = None
    external_links: Optional[List[Dict[str, str]]] = None


class BlogAISingle:
    """
    Single-file generator that:
      - Calls the model
      - Robustly parses JSON (even if model returns junk or invalid escapes)
      - Enforces required fields
      - Enforces word count via continuation
      - Fixes SEO basics (keyword in H1, internal/external links)
      - Handles city from keyword correctly
    """

    REQUIRED_KEYS = [
        "title",
        "h1",
        "meta_title",
        "meta_description",
        "body",
        "faq_items",
        "cta",
    ]
    
    # Known cities to detect in keyword
    KNOWN_CITIES = [
        'sarasota', 'port charlotte', 'fort myers', 'naples', 'tampa', 'orlando',
        'jacksonville', 'miami', 'bradenton', 'venice', 'punta gorda', 'north port',
        'cape coral', 'bonita springs', 'estero', 'lehigh acres', 'englewood',
        'arcadia', 'nokomis', 'osprey', 'lakewood ranch', 'palmetto', 'ellenton',
        'parrish', 'ruskin', 'sun city center', 'apollo beach', 'brandon', 'riverview',
        'clearwater', 'st petersburg', 'largo', 'pinellas park', 'dunedin'
    ]

    def __init__(self, api_key: str = None, model_primary: str = "gpt-4o", model_fallback: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model_primary = model_primary
        self.model_fallback = model_fallback
        self._settings_city = ""
        self._keyword_city = ""

    def generate(self, req: BlogRequest) -> Dict[str, Any]:
        """Main entry point for blog generation"""
        if not self.client:
            logger.error("OpenAI client not initialized - missing API key")
            return self._empty_result(req)
        
        # Detect city from keyword
        self._detect_city(req)
        
        logger.info(f"BlogAISingle.generate: keyword='{req.keyword}', target={req.target_words}, city='{req.city}'")
        
        base_prompt = self._build_prompt(req)

        # 1) Try primary then fallback
        raw = self._call_model(self.model_primary, base_prompt)
        parsed = self._robust_parse_json(raw)

        if not parsed or not parsed.get("body"):
            logger.warning("Primary model failed, trying fallback")
            raw2 = self._call_model(self.model_fallback, base_prompt)
            parsed = self._robust_parse_json(raw2)

        # 2) Normalize shape
        result = self._normalize_result(parsed, req)

        # 3) Enforce word count by continuation
        result = self._ensure_word_count(result, req)

        # 4) SEO auto-fixes
        result = self._seo_autofix(result, req)
        
        # 5) Fix wrong city references
        result = self._fix_wrong_city(result)

        # 6) Build HTML
        result["html"] = result.get("body", "")
        
        # 7) Calculate word count
        result["word_count"] = self._word_count(result.get("body", ""))
        
        logger.info(f"BlogAISingle.generate complete: {result['word_count']} words")

        return result
    
    def _detect_city(self, req: BlogRequest):
        """Detect city from keyword and store for later correction"""
        keyword_lower = req.keyword.lower()
        keyword_city = None
        
        for city in self.KNOWN_CITIES:
            if city in keyword_lower:
                keyword_city = city.title()
                break
        
        self._settings_city = req.city
        self._keyword_city = keyword_city
        
        # Override req.city with keyword city if found
        if keyword_city:
            logger.info(f"Detected city '{keyword_city}' from keyword (ignoring settings city '{req.city}')")
            req.city = keyword_city

    def _call_model(self, model: str, prompt: str) -> str:
        """Call OpenAI API"""
        try:
            logger.info(f"Calling {model}...")
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional SEO content writer. Return ONLY valid JSON. No markdown code blocks."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=8000,
            )
            content = resp.choices[0].message.content or ""
            logger.info(f"Got {len(content)} chars from {model}")
            return content
        except Exception as e:
            logger.error(f"Model call failed: {e}")
            return ""

    def _call_model_continue(self, model: str, current_body: str, words_needed: int, req: BlogRequest) -> str:
        """Call model to continue/expand body content"""
        prompt = f"""You are continuing a blog post about "{req.keyword}" for {req.company_name} in {req.city}, {req.state}.

TASK: Write {words_needed} MORE WORDS of high-quality content to add to the existing article.

CURRENT ARTICLE (last portion):
{current_body[-1500:]}

WRITE NEW CONTENT WITH:
- New <h2> section with detailed information
- At least 2-3 paragraphs under each heading
- Practical tips and helpful information
- Mention {req.company_name} and {req.city} naturally
- Do NOT repeat existing content

REQUIRED: Write exactly {words_needed} words of NEW content.

Return ONLY valid JSON:
{{"body_append": "<h2>New Section Title</h2><p>Detailed paragraph 1 with at least 100 words...</p><p>Detailed paragraph 2 with at least 100 words...</p><h2>Another Section</h2><p>More detailed content...</p>"}}

IMPORTANT: The body_append must contain {words_needed}+ words of new content!"""
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert SEO content writer. Return ONLY valid JSON with the body_append key containing HTML content."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Continue call failed: {e}")
            return ""

    def _build_prompt(self, req: BlogRequest) -> str:
        """Build the main generation prompt using improved SEO template"""
        city = req.city
        state = req.state.upper() if len(req.state) == 2 else req.state
        city_state = f"{city}, {state}".strip(", ")
        
        # Build internal links section
        internal = req.internal_links or []
        internal_text = ""
        if internal:
            internal_text = "INTERNAL LINKS (insert 3+ as <a href> tags in body):\n"
            for link in internal[:6]:
                if link.get("url") and link.get("title"):
                    internal_text += f'- {link["title"]}: {link["url"]}\n'
        
        return f"""You are an expert SEO content writer generating a high-quality, location-specific blog post.

STRICT GUARDRAILS (DO NOT BREAK):
- Use ONLY "{city}" as the city name - never substitute or use other cities
- Do NOT put city name in H2/H3 headings (e.g., write "Introduction" not "Introduction in {city}")
- Convert all titles to Proper Title Case
- Generate original, human-sounding content (no fluff, no keyword stuffing)
- Write EXACTLY {req.target_words}+ words - this is CRITICAL

INPUT:
- Primary Keyword: {req.keyword}
- Service: {req.industry or 'Professional Service'}
- City: {city}
- State: {state}
- Business Name: {req.company_name}
- Phone: {req.phone}
- Email: {req.email}
- Target Word Count: {req.target_words} words MINIMUM

{internal_text}

REQUIRED STRUCTURE (follow exactly):

1. H1 TITLE (55-65 characters)
   - Include keyword + city ONCE
   - Proper Title Case
   - Example: "{req.keyword} - Expert Service in {city}"

2. META TITLE (50-60 characters)
   - "{req.keyword} | {req.company_name}"

3. META DESCRIPTION (150-160 characters)
   - Include service + city once
   - Call to action

4. BODY CONTENT ({req.target_words}+ words total):

   <h2>Understanding {req.keyword}</h2>
   <p>300+ words explaining the service and its importance...</p>

   <h2>Benefits of Professional Service</h2>
   <h3>Benefit One</h3>
   <p>100+ words...</p>
   <h3>Benefit Two</h3>
   <p>100+ words...</p>
   <h3>Benefit Three</h3>
   <p>100+ words...</p>

   <h2>Our Service Process</h2>
   <p>200+ words explaining how {req.company_name} works...</p>

   <h2>Cost and Pricing Factors</h2>
   <p>200+ words about pricing considerations...</p>

   <h2>Common Problems We Solve</h2>
   <p>200+ words about issues customers face...</p>

   <h2>Why Choose {req.company_name}</h2>
   <p>200+ words about company benefits, include phone {req.phone}...</p>

   <h2>Service Areas</h2>
   <p>100+ words mentioning {city} and surrounding areas...</p>

   <h2>Get Started Today</h2>
   <p>150+ words with strong CTA, phone {req.phone}, email {req.email}...</p>

5. FAQ SECTION (in faq_items array, NOT in body):
   - 5 high-intent questions with detailed answers

TOTAL BODY: {req.target_words}+ words (THIS IS MANDATORY - COUNT YOUR WORDS!)

OUTPUT AS VALID JSON ONLY (no markdown):
{{
  "title": "[Compelling title with keyword - Proper Case]",
  "h1": "{req.keyword} - Expert {req.industry or 'Service'} in {city}",
  "meta_title": "{req.keyword} | {req.company_name}",
  "meta_description": "Professional {req.keyword.lower()} in {city}, {state}. {req.company_name} offers expert service. Call {req.phone or 'today'} for a free estimate.",
  "body": "<h2>Understanding {req.keyword}</h2><p>...</p><h2>Benefits</h2>...",
  "faq_items": [
    {{"question": "How much does {req.keyword.lower()} cost?", "answer": "..."}},
    {{"question": "How long does it take?", "answer": "..."}},
    {{"question": "Is {req.company_name} licensed?", "answer": "..."}},
    {{"question": "Do you offer warranties?", "answer": "..."}},
    {{"question": "What areas do you serve?", "answer": "..."}}
  ],
  "cta": {{"company_name": "{req.company_name}", "phone": "{req.phone}", "email": "{req.email}"}}
}}

CRITICAL REMINDERS:
1. Body MUST have {req.target_words}+ words - write detailed paragraphs
2. Do NOT put city in H2/H3 headings
3. Use ONLY {city} as the city
4. Include 3+ internal links as <a href> tags in body
5. State abbreviation must be uppercase: {state}"""

    def _robust_parse_json(self, text: str) -> Dict[str, Any]:
        """Parse JSON robustly, handling common issues"""
        if not text:
            return {}

        # Remove markdown code blocks if present
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        text = text.strip()

        # Try direct parse
        result = self._try_json_loads(text)
        if result:
            return result

        # Try extract first {...} block
        extracted = self._extract_first_json_object(text)
        if extracted:
            result = self._try_json_loads(extracted)
            if result:
                return result

        # Try escape repair
        repaired = self._repair_invalid_escapes(extracted or text)
        result = self._try_json_loads(repaired)
        if result:
            return result
        
        logger.warning("All JSON parsing attempts failed")
        return {}

    def _try_json_loads(self, s: str) -> Dict[str, Any]:
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _extract_first_json_object(self, s: str) -> str:
        start = s.find("{")
        if start == -1:
            return ""
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        return ""

    def _repair_invalid_escapes(self, s: str) -> str:
        """Fix invalid JSON escape sequences"""
        def repl(m):
            return "\\\\"
        return re.sub(r"\\(?![\"\\/bfnrtu])", repl, s)

    def _normalize_result(self, data: Dict[str, Any], req: BlogRequest) -> Dict[str, Any]:
        """Ensure all required fields exist with proper values"""
        out: Dict[str, Any] = {}

        out["title"] = (data.get("title") or data.get("meta_title") or f"{req.keyword} - {req.company_name}").strip()
        out["h1"] = (data.get("h1") or out["title"]).strip()
        out["meta_title"] = (data.get("meta_title") or out["title"][:60]).strip()
        out["meta_description"] = (data.get("meta_description") or "").strip()
        out["body"] = (data.get("body") or "").strip()

        # Clean body
        out["body"] = self._clean_body(out["body"])

        faq = data.get("faq_items") or data.get("faq") or []
        out["faq_items"] = faq if isinstance(faq, list) else []

        cta = data.get("cta") or {}
        if not isinstance(cta, dict):
            cta = {}
        out["cta"] = {
            "company_name": (cta.get("company_name") or req.company_name or "").strip(),
            "phone": (cta.get("phone") or req.phone or "").strip(),
            "email": (cta.get("email") or req.email or "").strip(),
        }

        return out
    
    def _clean_body(self, body: str) -> str:
        """Clean up body content"""
        if not body:
            return body
        
        # Remove escaped characters
        body = body.replace('\\n', '\n')
        body = body.replace('\\r', '')
        body = body.replace('\\/', '/')
        body = body.replace('\\"', '"')
        body = body.replace("\\'", "'")
        
        # Remove stray backslashes
        body = re.sub(r'\\+([<>])', r'\1', body)
        body = re.sub(r'\\([^\\])', r'\1', body)
        body = body.replace('\\', '')
        
        return body.strip()

    def _word_count(self, html: str) -> int:
        """Count words in HTML content"""
        text = re.sub(r"<[^>]+>", " ", html)
        words = re.findall(r"\b[\w']+\b", text)
        return len(words)

    def _ensure_word_count(self, result: Dict[str, Any], req: BlogRequest) -> Dict[str, Any]:
        """Ensure minimum word count by requesting continuations"""
        target_min = int(req.target_words * 0.80)  # Allow 20% tolerance

        if not result.get("body"):
            logger.warning("Empty body, cannot ensure word count")
            return result

        current = self._word_count(result["body"])
        logger.info(f"Initial word count: {current}, target minimum: {target_min}")
        
        if current >= target_min:
            return result

        # Continue in chunks - more aggressive
        attempts = 0
        max_attempts = 5  # Increased from 4
        
        while current < target_min and attempts < max_attempts:
            words_needed = max(400, target_min - current)  # Increased from 300
            logger.info(f"Continuation attempt {attempts + 1}: need {words_needed} more words (current: {current})")
            
            raw = self._call_model_continue(self.model_primary, result["body"], words_needed, req)
            cont = self._robust_parse_json(raw)

            append = (cont.get("body_append") or "").strip()
            if append:
                append = self._clean_body(append)
                result["body"] += "\n" + append
                new_count = self._word_count(result["body"])
                logger.info(f"Added {new_count - current} words, total: {new_count}")
                current = new_count
            else:
                logger.warning("No content returned from continuation, trying fallback model")
                # Try fallback model
                raw2 = self._call_model_continue(self.model_fallback, result["body"], words_needed, req)
                cont2 = self._robust_parse_json(raw2)
                append2 = (cont2.get("body_append") or "").strip()
                if append2:
                    append2 = self._clean_body(append2)
                    result["body"] += "\n" + append2
                    new_count = self._word_count(result["body"])
                    logger.info(f"Fallback added {new_count - current} words, total: {new_count}")
                    current = new_count
                else:
                    break
            
            attempts += 1
        
        final_count = self._word_count(result["body"])
        if final_count < target_min:
            logger.warning(f"Could not reach target word count: {final_count}/{target_min}")

        return result

    def _seo_autofix(self, result: Dict[str, Any], req: BlogRequest) -> Dict[str, Any]:
        """Auto-fix common SEO issues"""
        kw = req.keyword.strip()
        kw_l = kw.lower()
        state_upper = req.state.upper() if len(req.state) == 2 else req.state

        # Fix H1 if keyword missing
        h1 = (result.get("h1") or "").strip()
        if kw_l not in h1.lower():
            result["h1"] = f"{kw} - Expert Service in {req.city}"
            logger.info(f"Fixed H1 to include keyword")

        # Fix meta title - ensure proper format and uppercase state
        meta_title = result.get("meta_title", "")
        # Fix lowercase state abbreviations (Fl -> FL)
        meta_title = re.sub(r'\b([A-Z][a-z])\b', lambda m: m.group(1).upper(), meta_title)
        if len(meta_title) > 65:
            result["meta_title"] = meta_title[:60] + "..."
        elif len(meta_title) < 30:
            result["meta_title"] = f"{kw} | {req.company_name}"[:60]
        else:
            result["meta_title"] = meta_title

        # Fix meta description - ensure proper length and uppercase state
        meta_desc = result.get("meta_description", "")
        meta_desc = re.sub(r'\b([A-Z][a-z])\b(?=\.|\s|$)', lambda m: m.group(1).upper(), meta_desc)
        if len(meta_desc) > 165:
            result["meta_description"] = meta_desc[:157] + "..."
        elif len(meta_desc) < 120:
            result["meta_description"] = f"Professional {kw.lower()} in {req.city}, {state_upper}. {req.company_name} provides expert service. Call today for a free estimate."[:160]
        else:
            result["meta_description"] = meta_desc

        # Add internal links if missing
        internal = req.internal_links or []
        body = result.get("body", "")
        link_count = len(re.findall(r'<a\s+href=', body, re.IGNORECASE))
        
        if link_count < 3 and internal:
            logger.info(f"Adding internal links (currently {link_count})")
            links_html = ""
            for link in internal[:4]:
                if link.get("url") and link.get("title"):
                    links_html += f'<li><a href="{link["url"]}">{link["title"]}</a></li>\n'
            
            if links_html:
                result["body"] += f'\n<h2>Related Services</h2>\n<ul>\n{links_html}</ul>'

        # Fix heading structure - remove "in City" or "in City, State" pattern from h2/h3
        body = result.get("body", "")
        city_escaped = re.escape(req.city)
        state_escaped = re.escape(req.state)
        
        # Fix patterns like "<h2>Introduction in Venice, Florida</h2>" -> "<h2>Introduction</h2>"
        # Also handles "in Venice, FL" and "in Venice"
        patterns_to_fix = [
            (rf'(<h[23][^>]*>)([^<]+)\s+in\s+{city_escaped},?\s*{state_escaped}(</h[23]>)', r'\1\2\3'),
            (rf'(<h[23][^>]*>)([^<]+)\s+in\s+{city_escaped},?\s*Florida(</h[23]>)', r'\1\2\3'),
            (rf'(<h[23][^>]*>)([^<]+)\s+in\s+{city_escaped},?\s*FL(</h[23]>)', r'\1\2\3'),
            (rf'(<h[23][^>]*>)([^<]+)\s+in\s+{city_escaped}(</h[23]>)', r'\1\2\3'),
        ]
        
        for pattern, replacement in patterns_to_fix:
            body = re.sub(pattern, replacement, body, flags=re.IGNORECASE)
        
        result["body"] = body

        return result
    
    def _fix_wrong_city(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Replace wrong city (from settings) with correct city (from keyword)"""
        if not self._settings_city or not self._keyword_city:
            return result
        
        if self._settings_city.lower() == self._keyword_city.lower():
            return result
        
        logger.info(f"Replacing wrong city '{self._settings_city}' with '{self._keyword_city}'")
        
        settings_city = self._settings_city.title()
        keyword_city = self._keyword_city.title()
        
        def replace_city(text):
            if not text or not isinstance(text, str):
                return text
            # Replace all case variations
            text = re.sub(re.escape(settings_city), keyword_city, text, flags=re.IGNORECASE)
            return text
        
        # Fix all text fields
        for field in ['title', 'h1', 'meta_title', 'meta_description', 'body']:
            if field in result and isinstance(result[field], str):
                result[field] = replace_city(result[field])
        
        # Fix FAQ items
        if 'faq_items' in result and isinstance(result['faq_items'], list):
            for i, faq in enumerate(result['faq_items']):
                if isinstance(faq, dict):
                    if 'question' in faq:
                        result['faq_items'][i]['question'] = replace_city(faq['question'])
                    if 'answer' in faq:
                        result['faq_items'][i]['answer'] = replace_city(faq['answer'])
        
        return result
    
    def _empty_result(self, req: BlogRequest) -> Dict[str, Any]:
        """Return empty result structure"""
        return {
            "title": f"{req.keyword} - {req.company_name}",
            "h1": f"{req.keyword} - Expert Service in {req.city}",
            "meta_title": f"{req.keyword} | {req.company_name}",
            "meta_description": f"Professional {req.keyword.lower()} in {req.city}. Contact {req.company_name} today.",
            "body": "<p>Content generation failed. Please try again.</p>",
            "faq_items": [],
            "cta": {"company_name": req.company_name, "phone": req.phone, "email": req.email},
            "html": "",
            "word_count": 0
        }


# Singleton instance
_blog_ai_single = None

def get_blog_ai_single() -> BlogAISingle:
    """Get or create BlogAISingle instance"""
    global _blog_ai_single
    if _blog_ai_single is None:
        _blog_ai_single = BlogAISingle()
    return _blog_ai_single
