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
        
        # 5) Fix wrong city references (settings city -> keyword city)
        result = self._fix_wrong_city(result)
        
        # 6) Validate and fix any other wrong cities (enterprise-level validation)
        result = self._validate_and_fix_cities(result, req.city)

        # 7) Build HTML
        result["html"] = result.get("body", "")
        
        # 8) Calculate word count
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
        """Call OpenAI API with optimized settings"""
        try:
            logger.info(f"Calling {model}...")
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an SEO content generator. You must follow ALL constraints exactly. If any rule is violated, the output is considered invalid."
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.45,  # Lower temp for better constraint following
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
        prompt = f"""You are continuing an SEO blog post. Return ONLY valid JSON.

TASK: Add {words_needed} MORE words to the article about "{req.keyword}".

CITY RULE: Use ONLY "{req.city}" - no other cities allowed.
HEADING RULE: Do NOT put city name in H2/H3 headings.

CURRENT ARTICLE ENDING:
{current_body[-1500:]}

REQUIREMENTS:
- Write {words_needed}+ words of NEW content
- Add 2-3 new <h2> sections with detailed paragraphs (80-100+ words each)
- Sound like an industry expert in {req.industry or 'this field'}
- Include specific technical details
- Do NOT repeat existing content

Return ONLY this JSON:
{{"body_append": "<h2>Section Title</h2><p>80-100+ words of expert content...</p><h2>Another Section</h2><p>More detailed content...</p>"}}"""
        
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an SEO content generator. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.45,  # Lower temp for constraint following
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
            internal_text = "INTERNAL LINKS TO INSERT (minimum 3 required):\n"
            for link in internal[:6]:
                if link.get("url") and link.get("title"):
                    internal_text += f'<a href="{link["url"]}">{link["title"]}</a>\n'
        
        return f"""You are a STRICT SEO CONTENT ENGINE, not a creative writer.
Your job is to generate LOCAL SEO BLOG POSTS that MUST follow ALL rules below.
If ANY rule is violated, you must FIX the output BEFORE returning it.
FAILURE TO FOLLOW RULES IS NOT ALLOWED.

========================
INPUT PARAMETERS
========================
Primary Keyword: {req.keyword}
Business Name: {req.company_name}
City: {city}
State: {state}
Industry: {req.industry or 'Local Services'}
Phone: {req.phone}
Email: {req.email}
Target Word Count: {req.target_words} words MINIMUM

{internal_text}

========================
ABSOLUTE RULES (NON-NEGOTIABLE)
========================

1. LOCATION ENFORCEMENT
- Use ONLY the city "{city}" - NO OTHER CITIES ALLOWED
- NEVER introduce any other city, nearby area, county, or region
- If the primary keyword already contains a city name, DO NOT add another city anywhere
- City name may appear naturally 3-5 times, NOT repetitively
- Do NOT put city name in H2 or H3 headings

2. HEADLINES & CASING
- ALL headlines must be in Proper Title Case
- NO lowercase headlines
- H1 must be human-readable, not keyword-stuffed
- H2/H3 headings should NOT include the city name

3. WORD COUNT
- You MUST meet or exceed {req.target_words} words
- Output AT LEAST {req.target_words} words in the body
- Do NOT summarize, compress, or shorten content
- Write detailed, comprehensive paragraphs

4. CONTENT QUALITY
- NO generic filler or vague marketing language
- NO statements like "ultimate guide," "epitome," "unparalleled"
- Write as a subject-matter expert in {req.industry or 'this field'}
- Include specific technical details relevant to {req.keyword}
- Address real customer pain points and concerns

5. INTERNAL LINKS
- Insert AT LEAST 3 internal links using HTML: <a href="URL">Anchor Text</a>
- Links must be contextually relevant and woven naturally into sentences
- Use the links provided above

6. CTA RULES
- CTA must include: {req.company_name}, {req.phone}, {req.email}
- CTA must appear at least TWICE in the body
- CTA must be persuasive, not generic
- Example: "Call {req.company_name} at {req.phone} for your free estimate"

7. FAQ + SCHEMA
- Include 5 real, specific FAQs about {req.keyword}
- NO placeholder questions - make them specific to the service
- Generate valid FAQPage schema JSON
- Questions must match the article topic exactly

8. SEO SCORE TARGET
- Content must achieve SEO score of 90+
- Optimize headings, keyword placement, internal links, and readability
- Use keyword "{req.keyword}" naturally 8-12 times
- Meta description must be 150-160 characters

========================
REQUIRED CONTENT STRUCTURE
========================

<h2>What Is {req.keyword}?</h2>
<p>250+ words defining the service, when it's needed, what it involves</p>

<h2>Signs You Need Professional Help</h2>
<p>200+ words listing 5-7 specific warning signs with explanations</p>

<h2>Benefits Of Choosing Expert Service</h2>
<h3>Benefit One Title</h3>
<p>80+ words</p>
<h3>Benefit Two Title</h3>
<p>80+ words</p>
<h3>Benefit Three Title</h3>
<p>80+ words</p>

<h2>Our Service Process</h2>
<p>200+ words explaining step-by-step process, timeline, what to expect</p>

<h2>Cost And Pricing Factors</h2>
<p>200+ words about what affects pricing, value vs cost, financing options</p>

<h2>Why Choose {req.company_name}</h2>
<p>200+ words about company strengths, experience, guarantees - INCLUDE CTA</p>

<h2>Service Areas We Cover</h2>
<p>100+ words mentioning {city} and commitment to local community</p>

<h2>Get Started Today</h2>
<p>150+ words with strong CTA - phone {req.phone}, email {req.email}</p>

========================
OUTPUT FORMAT (MANDATORY)
========================

Return ONLY valid JSON. NO markdown. NO commentary. NO explanations.

{{
  "meta_title": "{req.keyword} | Expert {req.industry or 'Service'} | {req.company_name}",
  "meta_description": "Need {req.keyword.lower()} in {city}? {req.company_name} provides expert service. Call {req.phone or 'today'} for a free estimate!",
  "h1": "{req.keyword} - Trusted {city} Experts | {req.company_name}",
  "body": "<h2>What Is {req.keyword}?</h2><p>[250+ words]</p><h2>Signs You Need Professional Help</h2><p>[200+ words]</p>...[ALL SECTIONS WITH FULL WORD COUNTS]...",
  "faq_items": [
    {{"question": "How much does {req.keyword.lower()} cost in {city}?", "answer": "[Detailed 50+ word answer about pricing factors]"}},
    {{"question": "How long does {req.keyword.lower()} typically take?", "answer": "[Detailed answer about timeline]"}},
    {{"question": "Is {req.company_name} licensed and insured?", "answer": "[Answer confirming credentials]"}},
    {{"question": "Do you offer emergency services?", "answer": "[Answer about availability]"}},
    {{"question": "What areas do you serve?", "answer": "[Answer mentioning {city} and surrounding areas]"}}
  ],
  "faq_schema": {{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {{"@type": "Question", "name": "...", "acceptedAnswer": {{"@type": "Answer", "text": "..."}}}},
      {{"@type": "Question", "name": "...", "acceptedAnswer": {{"@type": "Answer", "text": "..."}}}},
      {{"@type": "Question", "name": "...", "acceptedAnswer": {{"@type": "Answer", "text": "..."}}}},
      {{"@type": "Question", "name": "...", "acceptedAnswer": {{"@type": "Answer", "text": "..."}}}},
      {{"@type": "Question", "name": "...", "acceptedAnswer": {{"@type": "Answer", "text": "..."}}}}
    ]
  }},
  "cta": {{
    "contact_name": "",
    "business_name": "{req.company_name}",
    "phone": "{req.phone}",
    "email": "{req.email}"
  }}
}}

========================
SELF-VALIDATION (MANDATORY)
========================

Before returning output, you MUST internally verify:
✓ Word count is {req.target_words}+ words
✓ Only "{city}" is used as the city - no other cities
✓ No city name in H2/H3 headings
✓ Headlines are Proper Title Case
✓ CTA appears at least twice in body
✓ 3+ internal links are included
✓ FAQs are specific to {req.keyword}
✓ JSON is valid

If ANY check fails → FIX IT → then return the JSON."""

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

        # Add internal links if missing or insufficient
        internal = req.internal_links or []
        body = result.get("body", "")
        link_count = len(re.findall(r'<a\s+href=', body, re.IGNORECASE))
        
        logger.info(f"SEO autofix: body has {link_count} internal links, have {len(internal)} available")
        
        if link_count < 3 and internal:
            logger.info(f"Adding internal links (currently {link_count}, need 3+)")
            
            # Try to inject links into existing paragraphs first
            links_to_add = internal[:4]
            links_added = 0
            
            for link in links_to_add:
                if link.get("url") and link.get("title"):
                    link_html = f'<a href="{link["url"]}">{link["title"]}</a>'
                    
                    # Find a good place to inject - after a paragraph that doesn't already have a link
                    # Look for </p> that isn't followed by <a
                    if '</p>' in body and links_added < 3:
                        # Find paragraphs without links
                        paragraphs = body.split('</p>')
                        new_paragraphs = []
                        link_injected = False
                        
                        for i, p in enumerate(paragraphs):
                            new_paragraphs.append(p)
                            # Inject link after some paragraphs (not all)
                            if not link_injected and i > 0 and i % 3 == 0 and '<a href' not in p and links_added < 3:
                                # Add contextual text with link
                                new_paragraphs[-1] += f'</p>\n<p>Learn more about {link_html}.'
                                links_added += 1
                                link_injected = True
                        
                        body = '</p>'.join(new_paragraphs)
            
            # If still not enough links, add a "Related Services" section
            current_link_count = len(re.findall(r'<a\s+href=', body, re.IGNORECASE))
            if current_link_count < 3 and internal:
                links_html = ""
                for link in internal[:4]:
                    if link.get("url") and link.get("title"):
                        links_html += f'<li><a href="{link["url"]}">{link["title"]}</a></li>\n'
                
                if links_html:
                    body += f'\n<h2>Related Services</h2>\n<ul>\n{links_html}</ul>'
                    logger.info("Added Related Services section with links")
            
            result["body"] = body

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
    
    def _validate_and_fix_cities(self, result: Dict[str, Any], correct_city: str) -> Dict[str, Any]:
        """
        Post-generation validator: scan for any city != correct_city and remove/replace them.
        This is how enterprise SEO tools ensure city accuracy.
        """
        if not correct_city:
            return result
        
        correct_city_lower = correct_city.lower()
        correct_city_title = correct_city.title()
        
        # List of Florida cities that might incorrectly appear
        other_cities = [
            city for city in self.KNOWN_CITIES 
            if city.lower() != correct_city_lower
        ]
        
        violations_found = []
        
        def scan_and_fix(text: str) -> str:
            if not text or not isinstance(text, str):
                return text
            
            fixed_text = text
            for other_city in other_cities:
                other_city_title = other_city.title()
                # Check if this wrong city appears in the text
                if re.search(re.escape(other_city_title), fixed_text, re.IGNORECASE):
                    violations_found.append(other_city_title)
                    # Replace with correct city
                    fixed_text = re.sub(
                        re.escape(other_city_title), 
                        correct_city_title, 
                        fixed_text, 
                        flags=re.IGNORECASE
                    )
            return fixed_text
        
        # Scan and fix all text fields
        for field in ['title', 'h1', 'meta_title', 'meta_description', 'body']:
            if field in result and isinstance(result[field], str):
                result[field] = scan_and_fix(result[field])
        
        # Scan and fix FAQ items
        if 'faq_items' in result and isinstance(result['faq_items'], list):
            for i, faq in enumerate(result['faq_items']):
                if isinstance(faq, dict):
                    if 'question' in faq:
                        result['faq_items'][i]['question'] = scan_and_fix(faq['question'])
                    if 'answer' in faq:
                        result['faq_items'][i]['answer'] = scan_and_fix(faq['answer'])
        
        if violations_found:
            unique_violations = list(set(violations_found))
            logger.warning(f"City validator found and fixed wrong cities: {unique_violations} -> {correct_city_title}")
        else:
            logger.info(f"City validator: no wrong cities found, content uses only '{correct_city_title}'")
        
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
