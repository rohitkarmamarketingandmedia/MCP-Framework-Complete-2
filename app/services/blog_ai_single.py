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
        
        city_escaped = re.escape(city)
        state_escaped = re.escape(state)
        
        # Patterns to fix (order matters - more specific patterns first)
        patterns = [
            # "Top 10 Dentist in Sarasota Florida in Sarasota" -> "Top 10 Dentist in Sarasota, Florida"
            (rf'in\s+{city_escaped}\s+Florida\s+in\s+{city_escaped}', f'in {city}, Florida'),
            (rf'in\s+{city_escaped}\s+FL\s+in\s+{city_escaped}', f'in {city}, FL'),
            (rf'in\s+{city_escaped},?\s*{state_escaped}\s+in\s+{city_escaped}', f'in {city}, {state}'),
            # "Service Sarasota Sarasota" -> "Service Sarasota"
            (rf'(\w+)\s+{city_escaped}\s+{city_escaped}', rf'\1 {city}'),
            # "Sarasota Sarasota" -> "Sarasota"
            (rf'\b{city_escaped}\s+{city_escaped}\b', city),
            # "in Sarasota in Sarasota" -> "in Sarasota"
            (rf'in\s+{city_escaped}\s+in\s+{city_escaped}', f'in {city}'),
            # "Sarasota, Florida Sarasota" -> "Sarasota, Florida"
            (rf'{city_escaped},?\s*Florida\s+{city_escaped}', f'{city}, Florida'),
            (rf'{city_escaped},?\s*FL\s+{city_escaped}', f'{city}, FL'),
            # "| Sarasota Sarasota" -> "| Sarasota"
            (rf'\|\s*{city_escaped}\s+{city_escaped}', f'| {city}'),
        ]
        
        # Apply to title fields
        for field in ['title', 'h1', 'meta_title', 'meta_description']:
            if field in result and isinstance(result[field], str):
                original = result[field]
                for pattern, replacement in patterns:
                    result[field] = re.sub(pattern, replacement, result[field], flags=re.IGNORECASE)
                if result[field] != original:
                    logger.info(f"Fixed duplicate location in {field}: '{original}' -> '{result[field]}'")
        
        # Also fix in body content
        if 'body' in result and isinstance(result['body'], str):
            original_body = result['body']
            for pattern, replacement in patterns:
                result['body'] = re.sub(pattern, replacement, result['body'], flags=re.IGNORECASE)
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
        faq_questions = [
            f'{{"question": "[Specific question about {keyword}]", "answer": "[60-80 word expert answer]"}}',
            '{"question": "[Question about cost/pricing]", "answer": "[60-80 word answer]"}',
            '{"question": "[Question about timeline/process]", "answer": "[60-80 word answer]"}',
            f'{{"question": "[Question about {req.company_name}]", "answer": "[60-80 word answer]"}}',
            '{"question": "[Question about service area]", "answer": "[60-80 word answer]"}',
            '{"question": "[Question about warranty/guarantee]", "answer": "[60-80 word answer]"}',
            '{"question": "[Question about scheduling]", "answer": "[60-80 word answer]"}',
        ]
        faq_items_template = ',\n    '.join(faq_questions[:faq_count])

        # Build system prompt - Professional Content Generator
        self._system_prompt = f"""You are a SENIOR TECHNICAL WRITER who has spent 20+ years working IN the {req.industry or 'service industry'} - not writing about it, but actually doing the work.

YOUR IDENTITY:
- You've personally done thousands of {req.industry or 'service'} jobs
- You know the tools, the common mistakes, the real costs
- You write like you're explaining to a smart friend, not selling to a stranger
- You hate generic marketing fluff - it insults customers' intelligence

WRITING RULES (MANDATORY):

1. EVERY PARAGRAPH MUST CONTAIN AT LEAST ONE OF:
   ✓ A specific number (PSI, degrees, dollars, hours, years, percentages)
   ✓ A technical term with explanation
   ✓ A step-by-step process
   ✓ A real-world example or scenario
   ✓ A common mistake and how to avoid it
   
   NO paragraph should be generic advice that could apply to any service.

2. KEYWORD USAGE:
   - Primary keyword: "{keyword}" - use EXACTLY as written 4-6 times
   - Do NOT add extra locations or duplicate place names
   - Weave naturally - forced repetition is obvious and hurts rankings

3. BANNED PHRASES (Using these = FAILURE - content will be rejected):
   
   NEVER START SENTENCES WITH:
   ❌ "It's important to..." / "When it comes to..." / "In today's world..."
   ❌ "As a homeowner..." / "If you're looking for..." / "Are you tired of..."
   ❌ "Let's face it..." / "The truth is..." / "Here's the thing..."
   ❌ "We pride ourselves..." / "Rest assured..." / "Look no further..."
   
   NEVER USE THESE WORDS/PHRASES:
   ❌ "state-of-the-art" / "top-notch" / "second to none" / "world-class"
   ❌ "exceptional service" / "unmatched quality" / "industry-leading"
   ❌ "peace of mind" / "trusted professionals" / "years of experience"
   ❌ "your satisfaction is our priority" / "we go above and beyond"
   ❌ "don't hesitate to call" / "feel free to contact" / "we're here to help"
   ❌ "whatever your needs" / "from X to Y, we've got you covered"
   
   INSTEAD, BE SPECIFIC:
   ✅ "A 3-ton AC unit typically costs $4,500-$7,000 installed, depending on SEER rating and ductwork modifications"
   ✅ "We pull permits same-day through the county portal - inspections usually happen within 48 hours"
   ✅ "Low refrigerant means there's a leak - adding more without finding it wastes money and harms the compressor"

4. STRUCTURE REQUIREMENTS:
   - H2 headings: Descriptive, keyword-rich, NOT salesy
   - Each section: Must have unique, valuable content (no repetition)
   - Paragraphs: 3-5 sentences each, dense with information
   - No filler: If a sentence doesn't add value, delete it

5. TONE:
   - Write like This Old House or Mayo Clinic - authoritative but accessible
   - Explain the "why" behind recommendations
   - Acknowledge trade-offs honestly (cheap vs quality, DIY vs pro)
   - Don't be afraid to say "this job needs a professional because..."

QUALITY TEST (ask yourself before outputting):
□ Would I be embarrassed if a competitor read this? (Should be NO)
□ Does every paragraph have specific, checkable facts?
□ Is there anything a high schooler could have written? (Remove it)
□ Would this help a real person make an informed decision?

OUTPUT: Return ONLY valid JSON. No markdown. No commentary."""

        # Build user prompt - keyword driven, SEO optimized
        return f"""GENERATE SEO-OPTIMIZED BLOG POST (Target: 90+ SEO Score)

PRIMARY KEYWORD: {keyword}
BUSINESS: {req.company_name}
INDUSTRY: {req.industry or 'Professional Services'}
LOCATION: {req.city or 'your area'}, {req.state or ''}
CONTACT: {req.phone} | {req.email}
WORD COUNT: {req.target_words}+ words (CRITICAL - aim for 2200+)

{expertise}

{internal_links_text}

═══════════════════════════════════════════════════════════════
SEO REQUIREMENTS (FOLLOW EXACTLY FOR 90+ SCORE)
═══════════════════════════════════════════════════════════════

1. META TITLE (55-60 chars):
   Format: "[Keyword] in [City] | Cost, Process & Benefits"
   - Primary keyword FIRST
   - Include location
   - Add hook (Cost, Process, Benefits)

2. META DESCRIPTION (150-160 chars):
   Include: keyword + benefit + CTA + location
   Example: "Learn how [service] works in [city], costs, and types. Call [company] for professional [service]. Free estimates available."

3. INTRO (First 100 words - CRITICAL FOR SEO):
   MUST contain in first paragraph:
   - Primary keyword in FIRST sentence
   - Location mention
   - User intent addressed
   - E-E-A-T statement: "This guide was written by [industry] professionals at {req.company_name}, serving {req.city or 'the area'} for over X years."

═══════════════════════════════════════════════════════════════
CONTENT STRUCTURE (Use these EXACT H2s - keyword variations)
═══════════════════════════════════════════════════════════════

<h2>What Is [Service from keyword]?</h2>
200+ words: Definition, how it works, why it matters

<h2>Signs You Need [Service]</h2>
200+ words: 5-7 warning signs with explanations

<h2>Types of [Service/Equipment] for {req.city or 'Local'} Homes</h2>
200+ words: Options, pros/cons, best for climate

<h2>Professional [Service] Process</h2>
250+ words with H3 subheadings:
<h3>Initial Assessment</h3>
<h3>Preparation and Setup</h3>
<h3>The [Service] Process</h3>
<h3>Testing and Verification</h3>

<h2>Cost of [Service] in {req.city or 'Your Area'}</h2>
200+ words: Price factors, ranges, value proposition

<h2>DIY vs Professional [Service]</h2>
150+ words: What homeowners can do, what needs pros

<h2>Benefits of Professional [Service]</h2>
200+ words: Warranty, safety, efficiency, savings

<h2>Common [Service] Problems</h2>
150+ words: Frequent issues, causes, prevention

<h2>Why Choose {req.company_name} for [Service]?</h2>
200+ words: Credentials, certifications, guarantees, contact info ({req.phone})

IMPORTANT: Do NOT include FAQ section in the body - FAQs go ONLY in the faq_items array.

═══════════════════════════════════════════════════════════════
INTERNAL LINKS (4-6 required)
═══════════════════════════════════════════════════════════════
Weave naturally into content:
- "Learn more about our <a href='/services'>[related service]</a>"
- "<a href='/contact'>Contact us</a> for a free estimate"
- "See our <a href='/service-area'>{req.city or 'service area'} coverage</a>"

═══════════════════════════════════════════════════════════════
KEYWORD OPTIMIZATION
═══════════════════════════════════════════════════════════════
- Primary keyword: 4-6 times naturally
- In first 100 words: YES
- In 2+ H2 headings: YES
- In conclusion: YES

NLP/Supporting keywords to include:
- professional [service]
- [service] cost/pricing
- licensed [professional type]
- [equipment] types
- energy efficient
- [city] [service]

═══════════════════════════════════════════════════════════════
RETURN THIS JSON
═══════════════════════════════════════════════════════════════
{{
  "h1": "[Keyword] in [City]: How It Works, Cost & Benefits",
  "meta_title": "[Keyword] in [City] | Cost, Process & Benefits",
  "meta_description": "Learn how [keyword] works in [city], costs, types, and when to call. Contact {req.company_name} for professional service. [150-160 chars]",
  "body": "[FULL HTML - All H2 sections listed above, 2000+ words, NO FAQ section in body]",
  "faq_items": [{faq_items_template}],
  "cta": {{"company_name": "{req.company_name}", "phone": "{req.phone}", "email": "{req.email}"}}
}}

FAQ ITEMS RULES:
- {faq_count} questions total in faq_items array
- Each answer: 40-60 words, direct and specific
- Include numbers, timeframes, or prices where relevant
- These will be displayed separately AND used for schema markup

FINAL CHECKLIST:
✓ Keyword in first sentence of intro
✓ E-E-A-T credibility statement in intro
✓ Keyword in meta title (first position)
✓ Keyword in 2+ H2 headings
✓ Location in intro, cost section, why choose section
✓ NO FAQ section in body (FAQs only in faq_items array)
✓ 4-6 internal links woven naturally
✓ Word count 2000+
✓ Valid JSON only

OUTPUT JSON ONLY:"""

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
    
    def _fix_meta_title(self, meta_title: str, keyword: str, company_name: str) -> str:
        """
        Fix meta title to follow SEO best practices:
        - Format: "Keyword Phrase in City | Brand Name"
        - Length: 55-60 characters
        - Title Case capitalization
        """
        # Convert keyword to title case
        kw_title = self._title_case(keyword)
        
        # Target length: 55-60 characters
        target_min = 55
        target_max = 60
        
        # Check if current title is acceptable
        if meta_title and target_min <= len(meta_title) <= target_max:
            # Just ensure title case
            parts = meta_title.split('|')
            if len(parts) == 2:
                return self._title_case(parts[0].strip()) + ' | ' + parts[1].strip()
            return meta_title
        
        # Build optimal meta title
        # Format: "Keyword Phrase | Company Name"
        base = f"{kw_title} | {company_name}"
        
        if len(base) >= target_min and len(base) <= target_max:
            return base
        
        # If too short, add helpful prefix/suffix
        if len(base) < target_min:
            # Try adding "Expert" or "Professional" prefix
            prefixes = ["Expert", "Professional", "Quality", "Trusted", "Top-Rated"]
            for prefix in prefixes:
                enhanced = f"{prefix} {kw_title} | {company_name}"
                if target_min <= len(enhanced) <= target_max:
                    return enhanced
            
            # Try adding service type suffix
            suffixes = ["Services", "Solutions", "Experts"]
            for suffix in suffixes:
                enhanced = f"{kw_title} {suffix} | {company_name}"
                if target_min <= len(enhanced) <= target_max:
                    return enhanced
            
            # If still too short, just return what we have (it's better than nothing)
            return base
        
        # If too long, truncate intelligently
        if len(base) > target_max:
            # Try to keep full keyword and truncate company name
            available = target_max - len(kw_title) - 3  # 3 for " | "
            if available > 10:
                return f"{kw_title} | {company_name[:available]}"
            else:
                # Truncate keyword instead
                return base[:target_max-3] + "..."
        
        return base

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

        # Fix meta title - SEO best practices: 55-60 chars, "Keyword Phrase | Brand Name"
        meta_title = result.get("meta_title", "")
        meta_title = self._fix_meta_title(meta_title, kw, req.company_name)
        result["meta_title"] = meta_title

        # Fix meta description - use keyword as-is, don't duplicate location
        meta_desc = result.get("meta_description", "")
        if len(meta_desc) > 165:
            result["meta_description"] = meta_desc[:157] + "..."
        elif len(meta_desc) < 120:
            # Use keyword which already contains location
            result["meta_description"] = f"Looking for {kw.lower()}? {req.company_name} provides expert service. Call {req.phone or 'today'} for a free estimate."[:160]
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
