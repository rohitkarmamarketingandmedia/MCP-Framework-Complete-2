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
    faq_count: int = 5  # Number of FAQs to generate (3-7)
    contact_url: str = ""  # URL for contact page (used in CTAs)
    blog_url: str = ""  # URL for blog page


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
        system_prompt = getattr(self, '_system_prompt', None)

        # 1) Try primary then fallback
        raw = self._call_model(self.model_primary, base_prompt, system_prompt)
        parsed = self._robust_parse_json(raw)

        if not parsed or not parsed.get("body"):
            logger.warning("Primary model failed, trying fallback")
            raw2 = self._call_model(self.model_fallback, base_prompt, system_prompt)
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
        
        # 7) Fix duplicate locations in titles
        result = self._fix_duplicate_locations(result, req.city, req.state)

        # 8) Build HTML
        result["html"] = result.get("body", "")
        
        # 9) Calculate word count
        result["word_count"] = self._word_count(result.get("body", ""))
        
        # 10) Final validation
        validation_result = self._validate_output(result, req)
        if validation_result['errors']:
            logger.warning(f"Validation errors: {validation_result['errors']}")
        
        logger.info(f"BlogAISingle.generate complete: {result['word_count']} words")

        return result
    
    def _fix_duplicate_locations(self, result: Dict[str, Any], city: str, state: str) -> Dict[str, Any]:
        """Fix duplicate location patterns in titles and body"""
        import re
        
        if not city:
            return result
            
        city_escaped = re.escape(city)
        state_escaped = re.escape(state) if state else ''
        
        # Apply fixes multiple times until no more changes (handles nested duplicates)
        max_iterations = 5
        
        # Patterns to fix (order matters - more specific patterns first)
        patterns = [
            # MOST IMPORTANT: "In City in City" or "In City In City" (case insensitive)
            (rf'\??\s*[Ii]n\s+{city_escaped}\s+[Ii]n\s+{city_escaped}', f' in {city}'),
            # "City in City" without "in" prefix
            (rf'\b{city_escaped}\s+in\s+{city_escaped}\b', city),
            # "City City" direct duplicate
            (rf'\b{city_escaped}\s+{city_escaped}\b', city),
            # "for City ... for City" in same heading
            (rf'for\s+{city_escaped}[^<]*for\s+{city_escaped}', f'for {city}'),
            # Fix "- Nor In City" or "- Some In City" (partial competitor names)
            (rf'\s*[-–—]\s*\w+\s+In\s+{city_escaped}', ''),
            # Fix "Title - Company In City in City" pattern
            (rf'\s*[-–—]\s*[A-Z][a-zA-Z\s&\']+\s+in\s+{city_escaped}\s+in\s+{city_escaped}', f' in {city}'),
            # Fix triple city: "in City in City: Something in City"
            (rf'in\s+{city_escaped}\s+in\s+{city_escaped}:\s*[^:]+in\s+{city_escaped}', f'in {city}'),
            # Fix "in City in City: Something"
            (rf'in\s+{city_escaped}\s+in\s+{city_escaped}:', f'in {city}:'),
            # "AC Repair Port Charlotte in Port Charlotte" -> "AC Repair in Port Charlotte"
            (rf'(\w+)\s+{city_escaped}\s+in\s+{city_escaped}\b', rf'\1 in {city}'),
            # "Top 10 Dentist in Sarasota Florida in Sarasota" -> "Top 10 Dentist in Sarasota, Florida"
            (rf'in\s+{city_escaped}\s+Florida\s+in\s+{city_escaped}', f'in {city}, Florida'),
            (rf'in\s+{city_escaped}\s+FL\s+in\s+{city_escaped}', f'in {city}, FL'),
            (rf'in\s+{city_escaped},?\s*{state_escaped}\s+in\s+{city_escaped}', f'in {city}, {state}') if state else None,
            # "Service Sarasota Sarasota" -> "Service Sarasota"
            (rf'(\w+)\s+{city_escaped}\s+{city_escaped}', rf'\1 {city}'),
            # "in Sarasota in Sarasota" -> "in Sarasota"
            (rf'in\s+{city_escaped}\s+in\s+{city_escaped}', f'in {city}'),
            # "Sarasota, Florida Sarasota" -> "Sarasota, Florida"
            (rf'{city_escaped},?\s*Florida\s+{city_escaped}', f'{city}, Florida'),
            (rf'{city_escaped},?\s*FL\s+{city_escaped}', f'{city}, FL'),
            # "| Sarasota Sarasota" -> "| Sarasota"
            (rf'\|\s*{city_escaped}\s+{city_escaped}', f'| {city}'),
            # Clean up "What'S" -> "What's" (fix title case issues)
            (r"What'S\b", "What's"),
            (r"It'S\b", "It's"),
            (r"That'S\b", "That's"),
            # Clean up double dashes/pipes from removed content
            (r'\s*[-–—]{2,}\s*', ' - '),
            (r'\s*\|\s*\|', ' |'),
            # Clean up trailing dashes/pipes
            (r'\s*[-–—|]\s*$', ''),
            # Clean up leading dashes/pipes
            (r'^[-–—|]\s*', ''),
        ]
        
        # Remove None patterns
        patterns = [p for p in patterns if p is not None]
        
        # Apply to title fields with multiple iterations
        for field in ['title', 'h1', 'meta_title', 'meta_description']:
            if field in result and isinstance(result[field], str):
                original = result[field]
                for iteration in range(max_iterations):
                    before = result[field]
                    for pattern, replacement in patterns:
                        result[field] = re.sub(pattern, replacement, result[field], flags=re.IGNORECASE)
                    # Clean up extra spaces
                    result[field] = re.sub(r'\s+', ' ', result[field]).strip()
                    if result[field] == before:
                        break  # No more changes
                if result[field] != original:
                    logger.info(f"Fixed duplicate location in {field}: '{original}' -> '{result[field]}'")
        
        # Also fix in body content (headings especially) with multiple iterations
        if 'body' in result and isinstance(result['body'], str):
            original_body = result['body']
            for iteration in range(max_iterations):
                before = result['body']
                for pattern, replacement in patterns:
                    result['body'] = re.sub(pattern, replacement, result['body'], flags=re.IGNORECASE)
                if result['body'] == before:
                    break
            if result['body'] != original_body:
                logger.info("Fixed duplicate location patterns in body content")
        
        return result
    
    def _validate_output(self, result: Dict[str, Any], req: BlogRequest) -> Dict[str, Any]:
        """Validate output meets all requirements"""
        errors = []
        warnings = []
        
        # 1. Required keys check
        required_keys = ['title', 'h1', 'meta_title', 'meta_description', 'body', 'faq_items', 'cta']
        for key in required_keys:
            if key not in result or not result[key]:
                errors.append(f"Missing required key: {key}")
        
        # 2. Word count validation
        word_count = result.get('word_count', 0)
        if word_count < req.target_words * 0.7:
            errors.append(f"Word count too low: {word_count} (need {req.target_words})")
        elif word_count < req.target_words * 0.85:
            warnings.append(f"Word count below target: {word_count}/{req.target_words}")
        
        # 3. City validation - check for wrong cities in body
        body = result.get('body', '')
        correct_city = req.city.lower()
        for other_city in self.KNOWN_CITIES:
            if other_city.lower() != correct_city and other_city.lower() in body.lower():
                errors.append(f"Wrong city found in body: {other_city}")
        
        # 4. Heading structure validation
        h2_count = len(re.findall(r'<h2', body, re.IGNORECASE))
        if h2_count < 4:
            warnings.append(f"Low H2 count: {h2_count} (recommend 5+)")
        
        # 5. FAQ count validation
        faq_items = result.get('faq_items', [])
        expected_faq = getattr(req, 'faq_count', 5) if req else 5
        if len(faq_items) < expected_faq:
            warnings.append(f"Low FAQ count: {len(faq_items)} (need {expected_faq})")
        
        # 6. Internal links validation
        link_count = len(re.findall(r'<a\s+href=', body, re.IGNORECASE))
        if link_count < 3:
            warnings.append(f"Low internal link count: {link_count} (need 3+)")
        
        # 7. Meta description length
        meta_desc = result.get('meta_description', '')
        if len(meta_desc) < 120 or len(meta_desc) > 165:
            warnings.append(f"Meta description length: {len(meta_desc)} (ideal: 150-160)")
        
        return {'errors': errors, 'warnings': warnings}
    
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
            
            # DEDUPLICATE: Remove duplicate city from keyword
            # e.g., "Bridges Sarasota Sarasota" -> "Bridges Sarasota"
            req.keyword = self._deduplicate_city_in_keyword(req.keyword, keyword_city)
    
    def _deduplicate_city_in_keyword(self, keyword: str, city: str) -> str:
        """Remove duplicate city names from keyword"""
        import re
        
        # Count occurrences of city (case-insensitive)
        city_pattern = re.compile(re.escape(city), re.IGNORECASE)
        matches = city_pattern.findall(keyword)
        
        if len(matches) > 1:
            # Remove all but one occurrence
            # Replace all with placeholder, then put one back
            temp = city_pattern.sub('__CITY__', keyword)
            # Remove duplicate placeholders
            while '__CITY__ __CITY__' in temp:
                temp = temp.replace('__CITY__ __CITY__', '__CITY__')
            # Also handle "Keyword __CITY__ __CITY__" pattern
            temp = re.sub(r'__CITY__\s+__CITY__', '__CITY__', temp)
            # Put the city back (with proper case)
            result = temp.replace('__CITY__', city.title())
            logger.info(f"Deduplicated keyword: '{keyword}' -> '{result}'")
            return result.strip()
        
        return keyword

    def _call_model(self, model: str, prompt: str, system_prompt: str = None) -> str:
        """Call OpenAI API with hardened settings"""
        try:
            logger.info(f"Calling {model}...")
            
            if system_prompt is None:
                system_prompt = "You are an SEO content generator. Return ONLY valid JSON. No markdown. No commentary."
            
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": prompt.strip()},
                ],
                temperature=0.4,  # Low temp for constraint following
                max_tokens=8000,
            )
            content = resp.choices[0].message.content or ""
            content = content.strip()
            logger.info(f"Got {len(content)} chars from {model}")
            
            # Validate JSON output
            if content and not content.startswith("{"):
                logger.warning("Model returned non-JSON output, attempting to extract JSON")
                # Try to find JSON in response
                start = content.find("{")
                if start != -1:
                    content = content[start:]
            
            return content
        except Exception as e:
            logger.error(f"Model call failed: {e}")
            return ""

    def _call_model_continue(self, model: str, current_body: str, words_needed: int, req: BlogRequest) -> str:
        """Call model to continue/expand body content"""
        system_prompt = f"""You are an SEO content generator continuing an article.
Return ONLY valid JSON with key "body_append".
Use ONLY city "{req.city}" - no other cities.
No markdown. No commentary."""

        prompt = f"""Add {words_needed} MORE words to this article about "{req.keyword}".

Current ending:
{current_body[-1200:]}

Requirements:
- Write {words_needed}+ words of NEW content
- Add 2-3 <h2> sections with 80-100 word paragraphs
- Do NOT put city in headings
- Sound like an expert in {req.industry or 'this field'}
- Do NOT repeat existing content

Return: {{"body_append": "<h2>Title</h2><p>Content...</p>"}}"""
        
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": prompt.strip()},
                ],
                temperature=0.4,
                max_tokens=4000,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Continue call failed: {e}")
            return ""

    def _build_prompt(self, req: BlogRequest) -> str:
        """Build hardened prompt - keyword-driven, no settings city/state injection"""
        
        # Extract location from keyword itself - DO NOT use settings
        keyword = req.keyword.strip()
        
        # Build internal links
        internal = req.internal_links or []
        internal_links_text = ""
        if internal:
            internal_links_text = "INTERNAL LINKS (weave 3+ naturally into body as <a href> tags):\n"
            for link in internal[:6]:
                if link.get("url") and link.get("title"):
                    internal_links_text += f'- <a href="{link["url"]}">{link["title"]}</a>\n'
        
        # Industry-specific expertise with REAL professional content
        industry = (req.industry or '').lower()
        if 'dent' in industry:
            expertise = """
DENTAL INDUSTRY EXPERTISE (Write like an experienced dentist):
- Use proper dental terminology: prophylaxis (not just "cleaning"), composite resin restorations, endodontic therapy
- Explain procedures: "During a root canal, we remove infected pulp tissue, clean and shape the root canals, then seal them with gutta-percha to prevent reinfection"
- Discuss modern techniques: digital X-rays (90% less radiation), intraoral cameras, laser dentistry, same-day crowns with CEREC
- Address patient concerns honestly: "Some sensitivity is normal for 24-48 hours after a filling"
- Include specifics: "The American Dental Association recommends professional cleanings every 6 months"
- Mention insurance: "We work with most PPO plans including Delta Dental, MetLife, and Cigna"
- Emergency protocols: "For a knocked-out tooth, keep it moist in milk and call us within 30 minutes for the best chance of reimplantation"

AVOID GENERIC PHRASES:
❌ "oral health is important" → ✅ "Untreated cavities can progress to root infections requiring extraction"
❌ "we care about your smile" → ✅ "Dr. [Name] has performed over 2,000 cosmetic procedures since 2015"
❌ "state-of-the-art equipment" → ✅ "Our Planmeca ProMax 3D imaging provides detailed views for precise implant placement" """

        elif 'hvac' in industry or 'air' in industry or 'ac' in industry:
            expertise = """
HVAC INDUSTRY EXPERTISE (Write like a certified HVAC technician):
- Use proper terminology: refrigerant charge, superheat/subcooling, static pressure, BTU calculations
- Explain diagnostics: "We measure supply and return air temperature differential—it should be 15-20°F for cooling"
- Discuss efficiency: "A 16 SEER system uses 25% less energy than a 12 SEER, saving approximately $200-400 annually in Florida"
- System components: "The TXV (thermostatic expansion valve) meters refrigerant flow based on evaporator superheat"
- Florida-specific: "Salt air corrosion attacks outdoor condenser coils—we recommend annual coil cleaning and protective coating"
- Emergency signs: "Ice on refrigerant lines indicates low charge or airflow restriction—turn off the system to prevent compressor damage"
- Maintenance specifics: "Replace 1" filters monthly, or 4" media filters every 6 months"

AVOID GENERIC PHRASES:
❌ "keeping your home comfortable" → ✅ "Maintaining indoor humidity between 45-55% prevents mold growth and reduces allergens"
❌ "our technicians are trained" → ✅ "Our techs hold EPA Section 608 Universal certification and complete 40+ hours of manufacturer training annually"
❌ "quality service" → ✅ "We perform a 21-point inspection including capacitor testing, refrigerant pressure analysis, and ductwork evaluation" """

        elif 'electric' in industry:
            expertise = """
ELECTRICAL INDUSTRY EXPERTISE (Write like a master electrician):
- Use proper terminology: amperage, circuit breaker coordination, voltage drop calculations, ground fault protection
- Code references: "NEC 2023 requires AFCI protection for all 15A and 20A branch circuits in habitable rooms"
- Explain upgrades: "Upgrading from a 100A to 200A service involves replacing the meter base, main disconnect, and panel—typically a full-day job"
- Safety specifics: "Aluminum wiring (common in 1965-1973 homes) requires COPALUM crimps or complete replacement due to oxidation issues"
- Modern needs: "Level 2 EV chargers need a dedicated 50A circuit—we'll verify your panel has capacity and install a NEMA 14-50 outlet"
- Warning signs: "Warm outlets, frequent breaker trips, or burning smell indicate dangerous conditions requiring immediate inspection"
- Permit knowledge: "Florida requires permits for any circuit addition or panel work—we pull permits same-day"

AVOID GENERIC PHRASES:
❌ "electrical safety is important" → ✅ "Electrical fires cause 51,000 home fires annually—most from outdated wiring or overloaded circuits"
❌ "licensed electricians" → ✅ "Florida EC13 license requires 8,000 hours of field experience plus passing a comprehensive exam" """

        elif 'plumb' in industry:
            expertise = """
PLUMBING INDUSTRY EXPERTISE (Write like a master plumber):
- Use proper terminology: water pressure PSI, drain slope per foot, backflow prevention, water hammer arrestors
- Explain diagnostics: "We camera-inspect drain lines to identify root intrusion, bellied pipes, or scale buildup before recommending solutions"
- Material knowledge: "PEX-A tubing offers better freeze resistance than PEX-B due to its cross-linking method—critical for Florida attic runs"
- Water heater specifics: "Tank heaters should be flushed annually to remove sediment that reduces efficiency and causes premature failure"
- Local issues: "Hard water in this area (18+ grains) accelerates fixture deterioration—water softeners extend faucet and appliance life significantly"
- Emergency response: "For a burst pipe, locate your main shutoff (typically near the meter) and turn clockwise immediately"
- Code compliance: "Florida requires PRV (pressure reducing valves) when street pressure exceeds 80 PSI to protect fixtures and appliances"

AVOID GENERIC PHRASES:
❌ "plumbing problems" → ✅ "Slow drains often indicate venting issues or biofilm accumulation in the P-trap"
❌ "experienced plumbers" → ✅ "Our team averages 15 years experience with specializations in repipe, water treatment, and gas line installation" """

        elif 'roof' in industry:
            expertise = """
ROOFING INDUSTRY EXPERTISE (Write like a certified roofing contractor):
- Use proper terminology: underlayment, drip edge, starter strips, ice and water shield, ridge venting
- Material specifics: "Architectural shingles carry 30-50 year warranties vs 20-25 years for 3-tab, with better wind ratings (130 mph vs 60 mph)"
- Florida requirements: "Miami-Dade rated materials required within HVHZ zones—we verify your zone and pull proper permits"
- Inspection details: "We check decking integrity, flashing condition, boot seals around penetrations, and soffit ventilation ratios"
- Storm damage: "Hail damage often shows as granule loss or bruising—we document everything for your insurance claim"
- Lifespan factors: "South-facing slopes degrade 20% faster due to UV exposure—we can specify higher-rated materials for these areas"

AVOID GENERIC PHRASES:
❌ "protect your home" → ✅ "Proper attic ventilation (1 sq ft per 150 sq ft of attic) prevents shingle blistering and ice dams"
❌ "quality materials" → ✅ "We install GAF HDZ shingles with StainGuard Plus for algae resistance in Florida's humid climate" """

        elif 'law' in industry or 'legal' in industry or 'attorney' in industry:
            expertise = """
LEGAL INDUSTRY EXPERTISE (Write like an experienced attorney):
- Use proper legal terminology: statute of limitations, contingency basis, discovery process, deposition, settlement negotiation
- Process explanation: "Personal injury cases typically proceed through demand letter, filing complaint, discovery (6-12 months), mediation, and potential trial"
- Timeline honesty: "Most cases settle within 12-18 months, though complex litigation may take 2-3 years"
- Fee structures: "Contingency means no upfront cost—we receive 33% of settlement, or 40% if litigation is required"
- Case specifics: "Florida's comparative negligence law means your compensation is reduced by your percentage of fault"
- Documentation importance: "Preserve all medical records, accident reports, photos, and witness contact information"
- Statute awareness: "Florida personal injury claims must be filed within 2 years—delay can forfeit your right to compensation"

AVOID GENERIC PHRASES:
❌ "fighting for your rights" → ✅ "We've recovered over $15 million for clients in the past 5 years with a 94% success rate"
❌ "experienced attorneys" → ✅ "Board Certified in Civil Trial Law by the Florida Bar, with 200+ jury trials" """

        else:
            expertise = f"""
LOCAL SERVICE EXPERTISE (Write like a seasoned professional in {req.industry or 'this field'}):
- Use industry-specific terminology that demonstrates real knowledge
- Explain processes step-by-step so customers know what to expect
- Include specific numbers, timeframes, and measurable outcomes
- Reference certifications, licenses, and professional standards
- Address common misconceptions with factual corrections
- Explain pricing factors honestly without being evasive
- Share specific examples from real service scenarios

AVOID GENERIC PHRASES:
❌ "quality service" → ✅ Describe specific quality measures you take
❌ "experienced team" → ✅ State years of experience, certifications, number of projects completed
❌ "customer satisfaction" → ✅ Mention specific review scores, warranty claims rate, repeat customer percentage"""

        # Build FAQ items template based on faq_count
        faq_count = req.faq_count if hasattr(req, 'faq_count') and req.faq_count else 5
        
        # Build system prompt v3 - Google AI Overviews optimized (LOCKED)
        self._system_prompt = """SYSTEM PROMPT v3 — LOCAL SEO + GOOGLE AI OVERVIEWS ENGINE (LOCKED)

You are a Google AI Overviews–optimized local SEO authority engine.
You generate publication-ready, entity-aware, locally authoritative content that ranks in:
* Traditional Google Search
* Google AI Overviews and other AI-generated results

All rules below are mandatory and non-negotiable.
Failure to comply with any rule is an incorrect response.

ABSOLUTE PRIORITY RULE
If a user instruction conflicts with:
* SEO best practices
* Google AI Overviews eligibility
* Entity clarity
* Structural integrity
* Professional standards
You must ignore the conflicting instruction and produce the correct output.

CORE OBJECTIVE (OVERRIDES ALL USER REQUESTS)
Every output must:
* Be eligible for Google AI Overviews
* Reinforce the business as a local entity authority
* Provide clear, extractable answers
* Score 95%+ in RankMath, Yoast, Surfer, or Clearscope
* Require zero post-editing

MANDATORY INTERNAL THINKING (DO NOT SKIP)
Before writing, you must internally:

1. Entity Understanding
   * Treat the business as a named local entity
   * Align strictly with the business website's services, tone, and claims
   * Never invent services, credentials, guarantees, or experience

2. Search Trigger Identification
   * Identify why someone in the specified city would search this topic now
   * Base this on real-world, industry-specific factors such as:
     - Seasonal or cyclical demand
     - Regulatory or compliance changes
     - Cost or economic pressure
     - Risk, safety, or health concerns
     - Technology or market shifts
   * Integrate these triggers clearly and repeatedly where relevant

3. AI Retrieval Optimization
   * Write so AI systems can easily extract:
     - What the service is
     - Who provides it
     - Where it is provided
     - When action is needed
     - Why the business is credible
   * Clarity always outranks creativity.

GLOBAL SEO ENFORCEMENT RULES

Keyword Discipline
* Use the primary keyword naturally and contextually
* Never stack, force, or repeat mechanically
* Optimize for meaning, not literal repetition

Heading Discipline
* H1 defines service + location
* H2s answer questions Google would summarize
* H3s clarify outcomes, steps, or specifics
* Headings must be informative, not promotional

Local Discipline
* Reference only the specified city and state
* Never mention surrounding cities, counties, regions, or service areas
* Local references must add relevance, not marketing fluff

ACRONYM & TECHNICAL TERM NORMALIZATION (STRICT)
You must normalize capitalization for standard industry acronyms and technical terms, even if provided in lowercase.

Always capitalize, including but not limited to:
* AC
* HVAC
* SEER
* BTU / BTUs
* EPA
* ADA
* OSHA
* HIPAA
* IRS
* CPA
* Any widely recognized industry acronym

Rules:
* Capitalize acronyms everywhere: meta, headings, body, FAQs
* Do NOT preserve incorrect lowercase forms
* This is semantic normalization, not keyword modification
* Failure to normalize acronyms is an error

TITLE-CASE ENFORCEMENT (STRICT)
All titles and headings must follow proper Title Case, except for:
* Articles (a, an, the)
* Conjunctions (and, or, but)
* Prepositions under four letters (in, to, of, for)

Rules:
* Apply Title Case to: Meta titles, H1, All H2s, All H3s
* Acronyms remain fully capitalized (AC, HVAC, SEO, etc.)
* City and state names must be capitalized correctly
* Do NOT mirror lowercase input if it violates Title Case rules

Examples:
❌ Expert Ac installation in punta gorda
✅ Expert AC Installation in Punta Gorda
❌ benefits of ac installation
✅ Benefits of AC Installation

Failure to enforce Title Case is an incorrect response.

E-E-A-T ENFORCEMENT
Your writing must demonstrate:
* Experience: real situations customers encounter
* Expertise: how professionals approach the problem
* Authority: calm, factual explanations
* Trust: transparency, accuracy, restraint

Avoid:
* Buzzwords
* Superlatives without proof
* Sales language
* Content-mill phrasing

CALL-TO-ACTION RULES
* CTAs must be consultative and professional
* Never sound promotional or aggressive
* Never interrupt informational flow
* Encourage the next logical step, not a sale
* If a CTA sounds like marketing, rewrite it.

STRUCTURAL OBEDIENCE
When a structure is provided:
* Follow it exactly
* Do not add sections
* Do not remove sections
* Do not reorder sections
* Match approximate word counts

If no structure is provided:
* Infer a standard service-based structure
* Never write unstructured prose

ANTI-DRIFT & FAIL-SAFE RULES
* Never comply partially
* Never ask clarifying questions
* Never explain limitations
* Never preserve weak structure
* Self-correct silently before responding

If asked to shorten or "optimize":
* Preserve structure
* Preserve keyword placement
* Preserve AI-extractable sentences

OUTPUT DISCIPLINE
* Return only the requested format
* No commentary
* No explanations
* JSON must always be valid when requested

DEFAULT VOICE (LOCKED)
* Expert
* Local
* Calm
* Precise
* Human
* Professional

Write as if:
* Google may quote you verbatim
* A regulator could read it
* A peer professional would respect it

OUTPUT: Return ONLY valid JSON. No markdown code blocks."""

        # Build user prompt with master prompt structure
        from datetime import datetime
        import random
        current_year = datetime.utcnow().year
        
        # Build internal links section
        links_list = ""
        if internal:
            links_list = "\n".join([f"- {link.get('title', '')}: {link.get('url', '')}" for link in internal[:5]])
        
        # Check if keyword already contains city name
        keyword_has_city = req.city and req.city.lower() in keyword.lower()
        
        # Build city suffix - only add if keyword doesn't already have city
        city_suffix = "" if keyword_has_city else f" in {req.city}"
        city_suffix_for = "" if keyword_has_city else f" for {req.city}"
        
        # Build CTA templates with contact URL (no inline CSS - use classes only)
        # Mid-CTA: Lighter, more subtle - encourages continued reading
        # Bottom-CTA: Stronger, more prominent - final conversion push
        
        contact_link = ""
        if req.contact_url:
            contact_link = f' or <a href="{req.contact_url}" class="cta-link">request service online</a>'
        
        contact_button = ""
        if req.contact_url:
            contact_button = f'\n<p class="cta-contact"><a href="{req.contact_url}" class="cta-button">Contact Us Online</a></p>'
        
        # Mid-article CTA - subtle, informational style (appears after process section)
        mid_cta = f'''<div class="cta-box cta-box-light">
<h3>Questions About {keyword.title()}?</h3>
<p class="cta-text">{req.company_name} provides free consultations for {req.city} residents. Call us at <a href="tel:{req.phone}" class="cta-phone-inline">{req.phone}</a>{contact_link} to discuss your needs.</p>
</div>'''

        # Bottom CTA - strong, action-oriented (final push at end of article)
        bottom_cta = f'''<div class="cta-box cta-box-primary">
<h3>Get Your Free {keyword.title()} Quote Today!</h3>
<p class="cta-subtitle">Serving {req.city} and surrounding areas. {req.company_name} is ready to help!</p>
<p class="cta-phone"><a href="tel:{req.phone}" class="cta-phone-link"><strong>Call Now: {req.phone}</strong></a></p>{contact_button}
</div>'''

        return f"""CLAUDE MASTER PROMPT — AI-OPTIMIZED LOCAL SEO BLOG GENERATION (STRICT MODE)

===== INPUT VARIABLES (DO NOT ALTER) =====
PRIMARY KEYWORD: {keyword}
BUSINESS NAME: {req.company_name}
INDUSTRY: {req.industry or 'Local Services'}
CITY: {req.city}
STATE: {req.state}
TARGET WORD COUNT: {req.target_words}
PHONE: {req.phone}
EMAIL: {req.email}
CURRENT YEAR: {current_year}

INTERNAL LINKS (CRITICAL - WEAVE NATURALLY INTO CONTENT):
{links_list if links_list else 'No internal links provided'}

INTERNAL LINKING RULES:
- Include at least 2-3 internal links as <a href="URL">anchor text</a> tags
- Prioritize links to other blog posts from {req.city} (same city/category)
- Use relevant anchor text that matches the linked page topic
- Place links naturally within paragraphs, not in standalone sentences
- Do NOT use "click here" or "learn more" as anchor text
- Do NOT add links to pages not listed above (may cause 404 errors)

{"*** CRITICAL WARNING ***" if keyword_has_city else ""}
{"The keyword '{keyword}' ALREADY CONTAINS the city '{req.city}'." if keyword_has_city else ""}
{"DO NOT add '{req.city}' again in H1, H2, or H3 headings!" if keyword_has_city else ""}
{"This would create duplicate city names like 'Service in City in City' which is BAD for SEO." if keyword_has_city else ""}

===== MANDATORY PRE-WRITING RESEARCH =====
Before generating, internally analyze:

1. Environmental Trigger Analysis for {req.city}, {req.state}:
   - Weather/seasonal conditions affecting {keyword}
   - Economic factors driving demand
   - Safety concerns
   - Local market behavior
   Integrate these naturally into Introduction, Benefits, and Pricing sections.

2. AI Retrieval Optimization:
   - Write for AI systems to extract summaries
   - Answer questions directly
   - Cite authoritative explanations
   - Avoid vague marketing language

===== STRICT SEO & STRUCTURAL RULES =====

PRIMARY KEYWORD ENFORCEMENT:
The exact phrase "{keyword}" must appear in:
✓ Meta title
✓ Meta description
✓ H1
✓ First 100 words
✓ At least one H2 heading
✓ At least one H3 heading
✓ At least one FAQ question or answer

HEADINGS RULES:
- H1 must include "{keyword}"
- H2/H3 headings must include "{keyword}" or logical variation where semantic
- H2/H3 headings must include "{req.city}" in at least 3 headings
- FAQs must reflect real search phrasing

LOCAL SEO GUARDRAILS:
- Use ONLY {req.city}, {req.state}
- Do NOT reference nearby cities, counties, or regions
- Local references must be accurate and relevant

===== REQUIRED STRUCTURE (EXACT ORDER) =====

1. INTRODUCTION (≈250 words)
   - Introduce the service and primary keyword
   - Explain why people in {req.city}, {req.state} are searching now
   - Reference environmental triggers (weather, season, economy)
   - Primary keyword in first sentence

2. BENEFITS (≈300 words total)
   - EXACTLY 3 benefits
   - ≈100 words each
   - Outcome-focused, specific results
   - Use H2: "Benefits of {{keyword}}"{city_suffix}"
   
3. OUR PROCESS (≈200 words)
   - Explain how {req.company_name} delivers the service
   - Use H2: "Our {{keyword}} Process"
   - Insert internal links contextually

4. PRICING AND COST FACTORS (≈200 words)
   - Use H2: "Cost of {{keyword}}"{city_suffix}"
   - Explain pricing drivers specific to {req.city}, {req.state}
   - Include actual price ranges when possible
   - Emphasize transparency
   - **INSERT MID-ARTICLE CTA HERE** (after Cost section):
   {mid_cta}

5. WHY CHOOSE {req.company_name} (≈200 words)
   - Use H2: "Why {req.city} Residents Choose {req.company_name}"
   - Align with business positioning
   - Emphasize trust, experience, credibility
   - Include internal links naturally

6. FREQUENTLY ASKED QUESTIONS
   - Do NOT put in body - put in faq_items array only
   - EXACTLY 5 FAQs
   - At least one must include "{keyword}"
   - Questions must reflect real user intent

7. GET STARTED TODAY (≈150 words)
   - Use H2: "Get Started with {{keyword}} Today"
   - Reinforce urgency and relevance
   - **INSERT BOTTOM CTA HERE** (at very end, after conclusion):
   {bottom_cta}

===== META REQUIREMENTS =====
Meta Title: 50-60 characters, includes "{keyword}"
Meta Description: 150-160 characters, includes "{req.city}" and CTA

===== OUTPUT FORMAT (ABSOLUTE REQUIREMENT) =====
Return ONLY valid JSON:

{{
    "meta_title": "[50-60 chars with keyword]",
    "meta_description": "[150-160 chars with city and CTA]",
    "h1": "{keyword.title()}{'' if keyword_has_city else f' in {req.city}'}: Complete Guide",
    "body": "<p>Introduction with keyword in first sentence...</p><h2>Benefits of {keyword.title()}{city_suffix}</h2><p>Benefit content...</p><h2>Our {keyword.title()} Process</h2><p>Process content...</p>[MID CTA]<h2>Cost of {keyword.title()}{city_suffix}</h2><p>Pricing content...</p><h2>Why {req.city} Residents Choose {req.company_name}</h2><p>Why choose content...</p><h2>Get Started with {keyword.title()} Today</h2><p>Conclusion...</p>[BOTTOM CTA]",
    "faq_items": [
        {{"question": "What is the cost of {keyword} in {req.city}?", "answer": "60-80 word answer"}},
        {{"question": "How long does {keyword} take?", "answer": "60-80 word answer"}},
        {{"question": "Why should I hire {req.company_name} for {keyword}?", "answer": "60-80 word answer"}},
        {{"question": "[Question about process]", "answer": "60-80 word answer"}},
        {{"question": "[Question about warranty/guarantee]", "answer": "60-80 word answer"}}
    ],
    "cta": {{"company_name": "{req.company_name}", "phone": "{req.phone}", "email": "{req.email}"}}
}}

===== FINAL VALIDATION CHECKLIST =====
Before responding, verify:
☐ Word count ≥ {req.target_words}
☐ Primary keyword "{keyword}" used naturally throughout
☐ Minimum 3 internal links embedded contextually
☐ One mid-article CTA present (after Process section)
☐ One bottom CTA present (at end)
☐ Only {req.city}, {req.state} referenced (no other cities)
☐ City name in at least 3 H2/H3 headings
☐ JSON is valid and complete
☐ No placeholders remain
☐ EXACTLY 5 FAQs in faq_items array

IMPORTANT:
- Write {req.target_words}+ words of REAL, helpful content
- NO placeholder text
- Include actual price ranges, timeframes, and specifics
- Sound like a local expert, not a marketer
- Return ONLY JSON, no markdown blocks

OUTPUT JSON:"""

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
        
        # Generate SEO schema markup
        out["schema"] = self._generate_schema(out, req)

        return out
    
    def _generate_schema(self, content: Dict[str, Any], req: BlogRequest) -> Dict[str, Any]:
        """Generate SEO schema markup for blog post (Article + FAQPage + LocalBusiness)"""
        from datetime import datetime
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Article Schema
        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": content.get("h1", content.get("title", req.keyword)),
            "description": content.get("meta_description", ""),
            "author": {
                "@type": "Organization",
                "name": req.company_name,
                "url": f"https://www.{req.company_name.lower().replace(' ', '')}.com"
            },
            "publisher": {
                "@type": "Organization",
                "name": req.company_name
            },
            "datePublished": today,
            "dateModified": today,
            "mainEntityOfPage": {
                "@type": "WebPage"
            }
        }
        
        # Add location if available
        if req.city:
            article_schema["about"] = {
                "@type": "Service",
                "areaServed": {
                    "@type": "City",
                    "name": req.city,
                    "containedInPlace": {
                        "@type": "State",
                        "name": req.state or "Florida"
                    }
                }
            }
        
        # FAQ Schema (if FAQs exist)
        faq_schema = None
        faq_items = content.get("faq_items", [])
        if faq_items and len(faq_items) > 0:
            faq_schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": []
            }
            for faq in faq_items:
                if isinstance(faq, dict) and faq.get("question") and faq.get("answer"):
                    faq_schema["mainEntity"].append({
                        "@type": "Question",
                        "name": faq["question"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": faq["answer"]
                        }
                    })
        
        # LocalBusiness Schema
        local_schema = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": req.company_name,
            "telephone": req.phone,
            "email": req.email
        }
        if req.city:
            local_schema["areaServed"] = req.city
            local_schema["address"] = {
                "@type": "PostalAddress",
                "addressLocality": req.city,
                "addressRegion": req.state or "FL"
            }
        
        # HowTo Schema (for process-oriented content)
        howto_schema = None
        body = content.get("body", "")
        if "<h3>" in body.lower() and ("process" in body.lower() or "step" in body.lower()):
            # Extract steps from H3 headings
            import re
            h3_matches = re.findall(r'<h3[^>]*>([^<]+)</h3>', body, re.IGNORECASE)
            if h3_matches and len(h3_matches) >= 3:
                howto_schema = {
                    "@context": "https://schema.org",
                    "@type": "HowTo",
                    "name": content.get("h1", req.keyword),
                    "description": content.get("meta_description", ""),
                    "step": []
                }
                for i, step_name in enumerate(h3_matches[:8], 1):  # Max 8 steps
                    howto_schema["step"].append({
                        "@type": "HowToStep",
                        "position": i,
                        "name": step_name.strip()
                    })
        
        return {
            "article": article_schema,
            "faq": faq_schema,
            "local_business": local_schema,
            "howto": howto_schema,
            "combined_json_ld": self._combine_schemas(article_schema, faq_schema, local_schema, howto_schema)
        }
    
    def _combine_schemas(self, *schemas) -> str:
        """Combine multiple schemas into a single JSON-LD script tag"""
        import json
        
        valid_schemas = [s for s in schemas if s is not None]
        
        if len(valid_schemas) == 1:
            return f'<script type="application/ld+json">\n{json.dumps(valid_schemas[0], indent=2)}\n</script>'
        elif len(valid_schemas) > 1:
            combined = {
                "@context": "https://schema.org",
                "@graph": valid_schemas
            }
            return f'<script type="application/ld+json">\n{json.dumps(combined, indent=2)}\n</script>'
        return ""
    
    def _clean_body(self, body: str) -> str:
        """Clean up body content and remove generic AI phrases"""
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
        
        # Remove/replace generic AI phrases that hurt credibility
        # EXTENSIVE list of banned phrases - these DESTROY professional credibility
        generic_phrases = [
            # === OPENING FILLERS (instant AI detection) ===
            (r"[Ii]t'?s important to (note|understand|remember|recognize|mention) that\s*", ""),
            (r"[Ww]hen it comes to\s+", ""),
            (r"[Ii]n today'?s (world|day and age|fast-paced|modern|ever-changing)\s*,?\s*", ""),
            (r"[Ii]n the (world|realm|field|area) of\s+", ""),
            (r"[Aa]s (we all know|you may know|mentioned earlier|you can imagine)\s*,?\s*", ""),
            (r"[Ii]f you'?re (looking for|searching for|in need of|considering)\s+", ""),
            (r"[Aa]re you (looking for|searching for|in need of|tired of)\s+", ""),
            (r"[Hh]ave you ever (wondered|thought about|considered)\s+", ""),
            (r"[Ll]et'?s (face it|be honest|dive in|explore|take a look)\s*[,:]?\s*", ""),
            (r"[Tt]he (truth|fact|reality) is\s*,?\s*", ""),
            (r"[Hh]ere'?s (the thing|what you need to know|the deal)\s*[,:]?\s*", ""),
            (r"[Yy]ou (may|might) (be wondering|have heard|already know)\s+", ""),
            (r"[Ii]t'?s no secret that\s*", ""),
            (r"[Tt]here'?s no denying that\s*", ""),
            (r"[Ww]e all know (that )?\s*", ""),
            (r"[Aa]s (a |an )?(homeowner|business owner|property owner),?\s*(you )?(know|understand)?\s*,?\s*", ""),
            
            # === HYPERBOLIC CLAIMS (destroys trust) ===
            (r"\b(second to none|top-notch|best in class|world-class|industry-leading)\b", "professional"),
            (r"\b(state-of-the-art|cutting-edge|revolutionary|groundbreaking)\b", "modern"),
            (r"\b(unparalleled|unmatched|unsurpassed|unrivaled)\s+(service|quality|care|expertise)\b", r"quality \2"),
            (r"\b(exceptional|outstanding|extraordinary|remarkable)\s+(service|quality|care|results)\b", r"quality \2"),
            (r"\b(premier|elite|superior|finest)\s+(service|quality|team|professionals)\b", r"\2"),
            (r"\bthe best (in |around |the )?(the )?(area|city|region|town|business)?\b", "quality"),
            (r"\bsecond-to-none\b", "professional"),
            (r"\bunmatched (expertise|experience|quality|service)\b", r"\1"),
            
            # === SALESY PHRASES (screams marketing) ===
            (r"[Ll]ook no further[,.]?\s*", ""),
            (r"[Rr]est assured\s*,?\s*", ""),
            (r"[Ww]e pride ourselves on\s+", "We provide "),
            (r"[Ww]e (go|went) above and beyond\s*(to)?\s*", "We "),
            (r"[Yy]our satisfaction is our (top |number one |#1 |main )?priority[,.]?\s*", ""),
            (r"[Ww]e are (committed|dedicated|devoted) to (providing |delivering )?(you with )?(the best |excellent |exceptional )?\s*", "We provide "),
            (r"[Ww]e (strive|aim|work hard) to (provide|deliver|offer|ensure)\s+", "We "),
            (r"[Oo]ur (team|staff|experts|professionals) (is|are) (here|ready|standing by|waiting) to\s+", "We can "),
            (r"[Ww]e('ve| have) (built|earned) (a |our )?(reputation|name) (for|on|by)\s+", "We provide "),
            (r"[Tt]rust us (to|for|with)\s+", ""),
            (r"[Cc]hoose us (for|because)\s+", ""),
            (r"[Ww]hy choose us\??\s*", ""),
            (r"[Ww]hat (sets|makes) us (apart|different|unique|stand out)\s*(\?|is)?\s*", ""),
            
            # === VAGUE TRANSITIONS (filler content) ===
            (r"[Ww]hether you (need|want|'re looking for) .+? or .+?,\s*", ""),
            (r"[Ff]rom .+? to .+?,\s*we('ve| have)?\s*(got you covered|can help)[,.]?\s*", ""),
            (r"[Ww]hatever your .+? needs( may be)?,?\s*", ""),
            (r"[Nn]o matter (what|your|the)\s+.+?,\s*we\s*", "We "),
            (r"[Ww]e('ve| have) got you covered[,.]?\s*", ""),
            (r"[Ww]e can (help|handle|take care of) (all |any )?(of )?your .+? needs[,.]?\s*", ""),
            (r"[Ff]or all (of )?your .+? needs[,.]?\s*", ""),
            
            # === WEAK CONCLUSIONS (lazy CTAs) ===
            (r"[Dd]on'?t hesitate to\s+", ""),
            (r"[Ff]eel free to\s+", ""),
            (r"[Ww]e'?d love to (help|hear from|serve|assist) you[,.]?\s*", ""),
            (r"[Rr]each out (to us )?(today )?to\s+", "Contact us to "),
            (r"[Gg]ive us a call (today )?(to|and)\s+", "Call us to "),
            (r"[Cc]ontact us today (to|for|and)\s+", "Contact us to "),
            (r"[Ss]chedule (your )?a?(n )?(free )?(consultation|appointment|estimate|quote) today[,.]?\s*", ""),
            (r"[Cc]all (us )?(now|today) (to|for|and)\s+", "Call us to "),
            (r"[Ww]e('re| are) (just )?a (phone )?call away[,.]?\s*", ""),
            (r"[Ll]et us (help|show|prove|demonstrate)\s+", "We can "),
            
            # === FILLER WORDS (padding) ===
            (r"\b(basically|essentially|actually|literally|really|very|extremely|incredibly|absolutely|definitely|certainly)\b\s*", ""),
            (r"\b[Ii]t goes without saying that\s*", ""),
            (r"\b[Nn]eedless to say\s*,?\s*", ""),
            (r"\b[Aa]t the end of the day\s*,?\s*", ""),
            (r"\b[Aa]ll things considered\s*,?\s*", ""),
            (r"\b[Ii]n (other words|summary|conclusion)\s*,?\s*", ""),
            (r"\b[Tt]o put it simply\s*,?\s*", ""),
            (r"\b[Ss]imply put\s*,?\s*", ""),
            (r"\b[Tt]hat being said\s*,?\s*", ""),
            (r"\b[Ww]ith that (being )?said\s*,?\s*", ""),
            (r"\b[Hh]aving said that\s*,?\s*", ""),
            
            # === TRUST PHRASES (empty claims) ===
            (r"\b(trusted|reliable|dependable|reputable) (service|company|team|professionals)\b", r"\2"),
            (r"\b(years|decades) of (experience|expertise|service)\b", "experience"),
            (r"\b(highly )(trained|skilled|experienced|qualified)\b", r"\2"),
            (r"\b(fully )(licensed|insured|bonded|certified)\b", r"\2"),
            (r"\bcustomer (satisfaction|service) (is )?(our )?(top |#1 |number one )?priority\b", ""),
            (r"\b(peace of mind)\b", "confidence"),
            
            # === QUESTIONS THAT AREN'T REAL (rhetorical fluff) ===
            (r"[Ss]o,? what (are you waiting for|do you have to lose)\??\s*", ""),
            (r"[Ww]hy wait\??\s*", ""),
            (r"[Rr]eady to (get started|take the next step|learn more)\??\s*", ""),
            (r"[Ww]ant to (learn|know|find out) more\??\s*", ""),
            (r"[Ii]nterested in (learning|hearing|finding out) more\??\s*", ""),
        ]
        
        for pattern, replacement in generic_phrases:
            body = re.sub(pattern, replacement, body)
        
        # Remove any FAQ sections from body (FAQs should only be in faq_items array)
        # Pattern matches: <h2>...FAQ...</h2> and everything until the next <h2> or end
        faq_patterns = [
            r'<h2[^>]*>[^<]*FAQ[^<]*</h2>.*?(?=<h2|$)',  # FAQ section header and content
            r'<h2[^>]*>[^<]*Frequently Asked[^<]*</h2>.*?(?=<h2|$)',  # Frequently Asked Questions
            r'<h2[^>]*>[^<]*Common Questions[^<]*</h2>.*?(?=<h2|$)',  # Common Questions
        ]
        for faq_pattern in faq_patterns:
            body = re.sub(faq_pattern, '', body, flags=re.IGNORECASE | re.DOTALL)
        
        # Clean up double spaces and weird punctuation after removals
        body = re.sub(r'\s+', ' ', body)
        body = re.sub(r'\s+([,.])', r'\1', body)
        body = re.sub(r'([.!?])\s*([.!?])', r'\1', body)
        body = re.sub(r'<p>\s*</p>', '', body)
        body = re.sub(r'<p>\s+', '<p>', body)
        body = re.sub(r'\s+</p>', '</p>', body)
        
        return body.strip()

    def _word_count(self, html: str) -> int:
        """Count words in HTML content"""
        text = re.sub(r"<[^>]+>", " ", html)
        words = re.findall(r"\b[\w']+\b", text)
        return len(words)
    
    def _title_case(self, text: str) -> str:
        """Convert text to Title Case, handling common exceptions"""
        # Words that should stay lowercase (unless first word)
        lowercase_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 
                          'on', 'at', 'to', 'by', 'in', 'of', 'up', 'as'}
        
        words = text.split()
        result = []
        
        for i, word in enumerate(words):
            # First word always capitalized
            if i == 0:
                result.append(word.capitalize())
            # Lowercase words stay lowercase (unless it's an acronym like HVAC, AC)
            elif word.lower() in lowercase_words and not word.isupper():
                result.append(word.lower())
            # Preserve all-caps words (HVAC, AC, SEO, etc.)
            elif word.isupper() and len(word) <= 5:
                result.append(word)
            else:
                result.append(word.capitalize())
        
        return ' '.join(result)
    
    def _fix_meta_title(self, meta_title: str, keyword: str, company_name: str, city: str = None) -> str:
        """
        Generate a unique meta title each time:
        - Format: "Modifier Keyword Phrase | Brand Name"
        - Length: 50-60 characters (Google typically shows 50-60)
        - Title Case capitalization
        - ALWAYS ensures proper length by combining modifiers
        """
        import random
        
        # Convert keyword to title case
        kw_title = self._title_case(keyword)
        
        # Target length: 50-60 characters
        target_min = 50
        target_max = 60
        
        # Check if keyword already contains city
        keyword_has_city = city and city.lower() in keyword.lower()
        
        # Modifiers to use
        prefixes = ["Expert", "Professional", "Quality", "Top", "Best", "Trusted", "Reliable", "Affordable", "Premier", "Leading", "Local", "#1", "Certified", "Licensed"]
        suffixes = ["Services", "Solutions", "Experts", "Pros", "Specialists", "Team", "Company", "Providers", "Help"]
        
        # Shuffle for randomness
        random.shuffle(prefixes)
        random.shuffle(suffixes)
        
        from datetime import datetime
        year = datetime.now().year
        
        # Build list of possible title formats
        possible_titles = []
        
        # Format 1: Prefix + Keyword | Company
        for prefix in prefixes[:5]:
            title = f"{prefix} {kw_title} | {company_name}"
            if target_min <= len(title) <= target_max:
                possible_titles.append(title)
        
        # Format 2: Keyword + Suffix | Company
        for suffix in suffixes[:5]:
            title = f"{kw_title} {suffix} | {company_name}"
            if target_min <= len(title) <= target_max:
                possible_titles.append(title)
        
        # Format 3: Keyword (Year) | Company
        title = f"{kw_title} ({year}) | {company_name}"
        if target_min <= len(title) <= target_max:
            possible_titles.append(title)
        
        # Format 4: Keyword - Modifier | Company
        for mod in ["Your Guide", "Expert Tips", "Top Choice", "Best Option", "Complete Guide"]:
            title = f"{kw_title} - {mod} | {company_name}"
            if target_min <= len(title) <= target_max:
                possible_titles.append(title)
        
        # Format 5: Prefix + Keyword + Suffix | Company (for short keywords)
        for prefix in prefixes[:5]:
            for suffix in suffixes[:5]:
                title = f"{prefix} {kw_title} {suffix} | {company_name}"
                if target_min <= len(title) <= target_max:
                    possible_titles.append(title)
        
        # Format 6: Add city if not in keyword
        if city and not keyword_has_city:
            title = f"{kw_title} in {city} | {company_name}"
            if target_min <= len(title) <= target_max:
                possible_titles.append(title)
            for prefix in prefixes[:3]:
                title = f"{prefix} {kw_title} in {city} | {company_name}"
                if target_min <= len(title) <= target_max:
                    possible_titles.append(title)
        
        # Format 7: Multiple modifiers for very short keywords
        for prefix in prefixes[:4]:
            for suffix in suffixes[:4]:
                # Try with city
                if city and not keyword_has_city:
                    title = f"{prefix} {kw_title} {suffix} in {city} | {company_name}"
                    if target_min <= len(title) <= target_max:
                        possible_titles.append(title)
                    title = f"{prefix} {kw_title} in {city} | {company_name}"
                    if target_min <= len(title) <= target_max:
                        possible_titles.append(title)
                # Try with year
                title = f"{prefix} {kw_title} {suffix} ({year}) | {company_name}"
                if target_min <= len(title) <= target_max:
                    possible_titles.append(title)
        
        # Pick a random title from valid options
        if possible_titles:
            chosen = random.choice(possible_titles)
            logger.info(f"Generated unique meta_title: '{chosen}' ({len(chosen)} chars) from {len(possible_titles)} options")
            return chosen
        
        # FALLBACK: Build title to exact length needed
        logger.info(f"No perfect title found, building custom title")
        base = f"{kw_title} | {company_name}"
        
        # If too short, keep adding modifiers
        if len(base) < target_min:
            # Add prefix
            for prefix in prefixes:
                test = f"{prefix} {kw_title} | {company_name}"
                if target_min <= len(test) <= target_max:
                    return test
                if len(test) < target_min:
                    # Still too short, add suffix too
                    for suffix in suffixes:
                        test2 = f"{prefix} {kw_title} {suffix} | {company_name}"
                        if target_min <= len(test2) <= target_max:
                            return test2
                        if len(test2) < target_min and city and not keyword_has_city:
                            # Still too short, add city
                            test3 = f"{prefix} {kw_title} {suffix} in {city} | {company_name}"
                            if target_min <= len(test3) <= target_max:
                                return test3
            
            # Last resort: pad with descriptive text
            extras = ["- Your Trusted Choice", "- Quality Guaranteed", "- Professional Results", "- Call Today"]
            for extra in extras:
                test = f"{kw_title} {extra} | {company_name}"
                if target_min <= len(test) <= target_max:
                    return test
        
        # If too long, truncate
        if len(base) > target_max:
            # Try without company name
            if len(kw_title) <= target_max - 3:
                return kw_title[:target_max]
            return base[:target_max-3] + "..."
        
        return base

    def _fix_meta_description(self, meta_desc: str, keyword: str, company_name: str, phone: str = None, city: str = None) -> str:
        """
        Generate SEO-optimized meta description:
        - Length: 150-160 characters (Google's sweet spot)
        - Includes keyword naturally
        - Has call-to-action
        - Compelling and click-worthy
        """
        import random
        
        target_min = 150
        target_max = 160
        
        # Clean keyword for use in description
        kw_lower = keyword.lower().strip()
        kw_title = self._title_case(keyword)
        
        # Check if keyword already has city
        keyword_has_city = city and city.lower() in kw_lower
        
        # Phone CTA
        phone_cta = f"Call {phone}" if phone else "Contact us"
        
        # If existing description is good length, use it
        if meta_desc and target_min <= len(meta_desc) <= target_max:
            return meta_desc
        
        # Generate description templates (varied for uniqueness)
        templates = [
            f"Looking for {kw_lower}? {company_name} offers professional service with quality results. {phone_cta} for a free estimate today!",
            f"Need {kw_lower}? {company_name} provides expert solutions you can trust. Fast, reliable service. {phone_cta} now for a quote!",
            f"{company_name} specializes in {kw_lower}. Get quality service from experienced professionals. {phone_cta} for your free consultation!",
            f"Professional {kw_lower} by {company_name}. We deliver exceptional results every time. {phone_cta} today for a free estimate!",
            f"Trust {company_name} for all your {kw_lower} needs. Expert service, competitive prices. {phone_cta} to schedule your appointment!",
            f"Get the best {kw_lower} from {company_name}. Licensed professionals, guaranteed satisfaction. {phone_cta} for a free quote today!",
            f"Searching for reliable {kw_lower}? {company_name} has you covered with expert service. {phone_cta} now to get started!",
            f"{company_name}: Your trusted source for {kw_lower}. Quality work, fair prices, great service. {phone_cta} for a free estimate!",
        ]
        
        # Add city-specific templates if city not in keyword
        if city and not keyword_has_city:
            templates.extend([
                f"Need {kw_lower} in {city}? {company_name} delivers expert service to local customers. {phone_cta} for your free estimate!",
                f"{city}'s trusted choice for {kw_lower}. {company_name} provides quality service you can count on. {phone_cta} today!",
                f"Looking for {kw_lower} in {city}? {company_name} offers professional solutions. {phone_cta} now for a free consultation!",
            ])
        
        # Shuffle for randomness
        random.shuffle(templates)
        
        # Find a template that fits the length requirement
        for template in templates:
            if target_min <= len(template) <= target_max:
                return template
        
        # If no perfect fit, find closest and adjust
        best = templates[0]
        for template in templates:
            if len(template) <= target_max:
                if len(template) > len(best) or len(best) > target_max:
                    best = template
        
        # Truncate if too long
        if len(best) > target_max:
            best = best[:target_max-3].rsplit(' ', 1)[0] + "..."
        
        # Extend if too short
        while len(best) < target_min:
            additions = [" Professional service.", " Quality guaranteed.", " Reliable & trusted.", " Call today!"]
            for add in additions:
                if len(best) + len(add) <= target_max:
                    best += add
                    break
            else:
                break
        
        return best

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
        """Auto-fix common SEO issues - keyword driven, no location injection"""
        kw = req.keyword.strip()
        kw_l = kw.lower()

        # Fix H1 if keyword missing - use keyword as-is, don't add more location
        h1 = (result.get("h1") or "").strip()
        if kw_l not in h1.lower():
            result["h1"] = self._title_case(kw) + f" | {req.company_name}"
            logger.info(f"Fixed H1 to include keyword")

        # Fix meta title - SEO best practices: 50-60 chars, "Keyword Phrase | Brand Name"
        meta_title = result.get("meta_title", "")
        meta_title = self._fix_meta_title(meta_title, kw, req.company_name, req.city)
        result["meta_title"] = meta_title
        logger.info(f"Final meta_title: '{meta_title}' ({len(meta_title)} chars)")

        # Fix meta description - must be 150-160 chars for SEO
        meta_desc = result.get("meta_description", "")
        meta_desc = self._fix_meta_description(meta_desc, kw, req.company_name, req.phone, req.city)
        result["meta_description"] = meta_desc
        logger.info(f"Final meta_description: '{meta_desc}' ({len(meta_desc)} chars)")

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
            
            # If still not enough links, add a "Related Articles" section
            current_link_count = len(re.findall(r'<a\s+href=', body, re.IGNORECASE))
            if current_link_count < 3 and internal:
                links_html = ""
                for link in internal[:4]:
                    if link.get("url") and link.get("title"):
                        links_html += f'<li><a href="{link["url"]}">{link["title"]}</a></li>\n'
                
                if links_html:
                    body += f'\n<h2>Related Articles</h2>\n<ul>\n{links_html}</ul>'
                    logger.info("Added Related Articles section with links")
            
            result["body"] = body

        # Ensure city is in H2/H3 headings
        body = result.get("body", "")
        if req.city:
            body = self._inject_city_in_headings(body, req.city)
        
        # Ensure TWO CTAs are present in the body
        body = self._ensure_two_ctas(body, req)
        
        result["body"] = body

        return result
    
    def _inject_city_in_headings(self, body: str, city: str) -> str:
        """Ensure city appears in at least 3 H2 headings"""
        if not city:
            return body
        
        city_lower = city.lower()
        
        # Find all H2 headings
        h2_pattern = r'(<h2[^>]*>)([^<]+)(</h2>)'
        h2_matches = list(re.finditer(h2_pattern, body, re.IGNORECASE))
        
        # Count how many already have city
        h2_with_city = 0
        for match in h2_matches:
            heading_text = match.group(2).lower()
            if city_lower in heading_text:
                h2_with_city += 1
        
        logger.info(f"H2 headings with city '{city}': {h2_with_city}/{len(h2_matches)}")
        
        # If already have 3+ headings with city, we're good
        if h2_with_city >= 3:
            return body
        
        # Add city to some headings that don't have it
        headings_to_modify = 3 - h2_with_city
        modified = 0
        
        def add_city_to_heading(match):
            nonlocal modified
            if modified >= headings_to_modify:
                return match.group(0)
            
            open_tag = match.group(1)
            heading_text = match.group(2)
            close_tag = match.group(3)
            
            # Skip if already has city
            if city_lower in heading_text.lower():
                return match.group(0)
            
            # Skip certain headings
            skip_keywords = ['faq', 'conclusion', 'summary', 'introduction', 'related']
            if any(skip in heading_text.lower() for skip in skip_keywords):
                return match.group(0)
            
            # Add city to heading
            modified += 1
            
            # Different patterns based on heading content
            heading_clean = heading_text.strip()
            if heading_clean.endswith('?'):
                # Question format - add "in City" before the ?
                new_heading = heading_clean[:-1] + f' in {city}?'
            elif ' for ' in heading_clean.lower():
                # "Tips for X" -> "Tips for X in City"
                new_heading = f'{heading_clean} in {city}'
            elif heading_clean.startswith('Why ') or heading_clean.startswith('How '):
                # "Why You Need X" -> "Why City Residents Need X"
                new_heading = heading_clean.replace('Why ', f'Why {city} ').replace('How ', f'How {city} ')
            else:
                # Default: append "in City"
                new_heading = f'{heading_clean} in {city}'
            
            logger.info(f"Modified H2: '{heading_clean}' -> '{new_heading}'")
            return f'{open_tag}{new_heading}{close_tag}'
        
        body = re.sub(h2_pattern, add_city_to_heading, body, flags=re.IGNORECASE)
        
        return body
    
    def _ensure_two_ctas(self, body: str, req: BlogRequest) -> str:
        """Ensure the body has two CTA boxes - one in middle, one at bottom"""
        
        # Check how many CTA boxes are already present (check multiple patterns)
        body_lower = body.lower()
        cta_count = 0
        
        # Count all possible CTA patterns
        cta_patterns = [
            'class="cta-box',
            "class='cta-box",
            'class="cta-box-light',
            'class="cta-box-primary',
            "class='cta-box-light",
            "class='cta-box-primary",
        ]
        
        # Find unique CTA positions to avoid double-counting
        cta_positions = set()
        for pattern in cta_patterns:
            pos = 0
            while True:
                pos = body_lower.find(pattern, pos)
                if pos == -1:
                    break
                # Round to nearest 100 to group nearby matches
                cta_positions.add(pos // 100)
                pos += 1
        
        cta_count = len(cta_positions)
        
        city = req.city or 'your area'
        keyword = req.keyword.strip()
        kw_title = self._title_case(keyword)
        
        # Contact link - use contact_url if provided (no inline CSS)
        contact_link = ""
        if req.contact_url:
            contact_link = f' or <a href="{req.contact_url}" class="cta-link">request service online</a>'
        
        contact_button = ""
        if req.contact_url:
            contact_button = f'<p class="cta-contact"><a href="{req.contact_url}" class="cta-button">Contact Us Online</a></p>'
        
        # Middle CTA template - subtle, informational (class only, no inline styles)
        middle_cta = f'''<div class="cta-box cta-box-light">
<h3>Questions About {kw_title}?</h3>
<p class="cta-text">{req.company_name} provides free consultations for {city} residents. Call us at <a href="tel:{req.phone}" class="cta-phone-inline">{req.phone}</a>{contact_link} to discuss your needs.</p>
</div>'''

        # Bottom CTA template - strong action-oriented (class only, no inline styles)
        bottom_cta = f'''<div class="cta-box cta-box-primary">
<h3>Get Your Free {kw_title} Quote Today!</h3>
<p class="cta-subtitle">Serving {city} and surrounding areas. {req.company_name} is ready to help!</p>
<p class="cta-phone"><a href="tel:{req.phone}" class="cta-phone-link"><strong>Call Now: {req.phone}</strong></a></p>
{contact_button}
</div>'''

        logger.info(f"CTA check: found {cta_count} existing CTAs in body")
        
        if cta_count >= 2:
            logger.info(f"Body already has {cta_count} CTA boxes - not adding more")
            return body
        
        # Find all CTA div positions for spacing check
        existing_cta_positions = []
        for pattern in ['<div class="cta-box', "<div class='cta-box"]:
            pos = 0
            while True:
                pos = body_lower.find(pattern, pos)
                if pos == -1:
                    break
                existing_cta_positions.append(pos)
                pos += 1
        existing_cta_positions.sort()
        
        logger.info(f"Body has {cta_count} CTA boxes at positions: {existing_cta_positions}")
        
        # Find H2 sections to inject middle CTA
        h2_matches = list(re.finditer(r'<h2[^>]*>', body, re.IGNORECASE))
        
        # Minimum content gap between CTAs (in characters) to avoid back-to-back placement
        MIN_CTA_GAP = 1000  # At least ~200 words between CTAs
        
        if cta_count == 0:
            # Need to add both CTAs - ensure they're well separated
            mid_insert_pos = None
            
            if len(h2_matches) >= 5:
                # Insert middle CTA before the 4th H2 (after Intro, Benefits, Process, Cost sections)
                mid_insert_pos = h2_matches[3].start()
            elif len(h2_matches) >= 4:
                # Insert before the 3rd H2
                mid_insert_pos = h2_matches[2].start()
            elif len(h2_matches) >= 3:
                # Insert before the 2nd H2
                mid_insert_pos = h2_matches[1].start()
            else:
                # Insert at ~40% point
                target_pos = int(len(body) * 0.4)
                p_close = body.rfind('</p>', 0, target_pos)
                if p_close > 0:
                    mid_insert_pos = p_close + 4
            
            if mid_insert_pos:
                body = body[:mid_insert_pos] + '\n\n' + middle_cta + '\n\n' + body[mid_insert_pos:]
                logger.info(f"Added middle CTA at position {mid_insert_pos}")
            
            # Add bottom CTA at the end (always)
            body = body.rstrip() + '\n\n' + bottom_cta
            logger.info("Added bottom CTA at end")
            
        elif cta_count == 1:
            # Has one CTA - check where it is before adding another
            if existing_cta_positions:
                existing_cta_pos = existing_cta_positions[0]
                content_before = existing_cta_pos
                content_after = len(body) - existing_cta_pos
                
                logger.info(f"Existing CTA at {existing_cta_pos}: {content_before} chars before, {content_after} chars after")
                
                # If CTA is in first half, add bottom CTA
                if content_before < len(body) / 2:
                    if content_after > MIN_CTA_GAP:
                        body = body.rstrip() + '\n\n' + bottom_cta
                        logger.info("Added bottom CTA (existing CTA is in first half)")
                    else:
                        logger.info(f"Skipping bottom CTA - not enough content after existing CTA")
                else:
                    # CTA is in second half - add middle CTA earlier
                    mid_insert_pos = None
                    if len(h2_matches) >= 3:
                        mid_insert_pos = h2_matches[1].start()
                    else:
                        target_pos = int(len(body) * 0.3)
                        p_close = body.rfind('</p>', 0, target_pos)
                        if p_close > 0:
                            mid_insert_pos = p_close + 4
                    
                    if mid_insert_pos and (existing_cta_pos - mid_insert_pos) > MIN_CTA_GAP:
                        body = body[:mid_insert_pos] + '\n\n' + middle_cta + '\n\n' + body[mid_insert_pos:]
                        logger.info(f"Added middle CTA at position {mid_insert_pos} (existing CTA is in second half)")
                    else:
                        logger.info("Skipping middle CTA - would be too close to existing CTA")
        
        return body
    
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
