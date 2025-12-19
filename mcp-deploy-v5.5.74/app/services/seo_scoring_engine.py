"""
MCP Framework - SEO Scoring Engine
Scores content 0-100 based on SEO best practices
"""
import re
from typing import Dict, List, Optional
from collections import Counter


class SEOScoringEngine:
    """
    Analyzes content and returns SEO score 0-100
    Similar to Surfer SEO / RankMath scoring
    """
    
    def __init__(self):
        # Weights for each factor (must sum to 100)
        self.weights = {
            'keyword_in_title': 10,
            'keyword_in_h1': 8,
            'keyword_in_first_100_words': 7,
            'keyword_density': 10,
            'word_count': 12,
            'heading_structure': 10,
            'meta_title_length': 5,
            'meta_description_length': 5,
            'readability': 10,
            'internal_links': 8,
            'external_links': 3,
            'image_optimization': 5,
            'content_depth': 7
        }
    
    def score_content(
        self,
        content: Dict,
        target_keyword: str,
        location: str = ''
    ) -> Dict:
        """
        Score content against SEO best practices
        
        Args:
            content: {
                'title': str,
                'meta_title': str,
                'meta_description': str,
                'h1': str,
                'body': str (HTML),
                'body_text': str (plain text)
            }
            target_keyword: Primary keyword to optimize for
            location: Geographic location for local SEO
            
        Returns:
            {
                'total_score': int (0-100),
                'grade': str (A+, A, B, C, D, F),
                'factors': {factor: {score, max, message}},
                'recommendations': [str]
            }
        """
        result = {
            'total_score': 0,
            'grade': 'F',
            'factors': {},
            'recommendations': []
        }
        
        # Normalize inputs
        keyword = target_keyword.lower().strip()
        keyword_with_location = f"{keyword} {location}".lower().strip() if location else keyword
        
        title = content.get('title', '') or content.get('meta_title', '')
        meta_title = content.get('meta_title', '') or title
        meta_description = content.get('meta_description', '')
        h1 = content.get('h1', '')
        body_html = content.get('body', '')
        body_text = content.get('body_text', '') or self._strip_html(body_html)
        
        # 1. Keyword in Title
        score, msg = self._score_keyword_in_text(keyword, title.lower(), 'title')
        result['factors']['keyword_in_title'] = {
            'score': score,
            'max': self.weights['keyword_in_title'],
            'message': msg
        }
        if score < self.weights['keyword_in_title']:
            result['recommendations'].append(f'Add "{target_keyword}" to your title')
        
        # 2. Keyword in H1
        score, msg = self._score_keyword_in_text(keyword, h1.lower(), 'H1')
        result['factors']['keyword_in_h1'] = {
            'score': score,
            'max': self.weights['keyword_in_h1'],
            'message': msg
        }
        if score < self.weights['keyword_in_h1']:
            result['recommendations'].append(f'Include "{target_keyword}" in your H1 heading')
        
        # 3. Keyword in First 100 Words
        first_100_words = ' '.join(body_text.lower().split()[:100])
        score, msg = self._score_keyword_in_text(keyword, first_100_words, 'first 100 words')
        result['factors']['keyword_in_first_100_words'] = {
            'score': score,
            'max': self.weights['keyword_in_first_100_words'],
            'message': msg
        }
        if score < self.weights['keyword_in_first_100_words']:
            result['recommendations'].append(f'Use "{target_keyword}" in your opening paragraph')
        
        # 4. Keyword Density
        score, msg, density = self._score_keyword_density(keyword, body_text.lower())
        result['factors']['keyword_density'] = {
            'score': score,
            'max': self.weights['keyword_density'],
            'message': msg,
            'density': density
        }
        if density < 0.5:
            result['recommendations'].append(f'Increase keyword usage (current: {density:.1f}%, target: 1-2%)')
        elif density > 3:
            result['recommendations'].append(f'Reduce keyword stuffing (current: {density:.1f}%, target: 1-2%)')
        
        # 5. Word Count
        word_count = len(body_text.split())
        score, msg = self._score_word_count(word_count)
        result['factors']['word_count'] = {
            'score': score,
            'max': self.weights['word_count'],
            'message': msg,
            'count': word_count
        }
        if word_count < 1000:
            result['recommendations'].append(f'Add more content (current: {word_count} words, target: 1,200+)')
        
        # 6. Heading Structure
        score, msg, heading_data = self._score_heading_structure(body_html)
        result['factors']['heading_structure'] = {
            'score': score,
            'max': self.weights['heading_structure'],
            'message': msg,
            **heading_data
        }
        if heading_data.get('h2_count', 0) < 3:
            result['recommendations'].append('Add more H2 subheadings (target: 3-6)')
        
        # 7. Meta Title Length
        score, msg = self._score_meta_length(len(meta_title), 50, 60, 'Meta title')
        result['factors']['meta_title_length'] = {
            'score': score,
            'max': self.weights['meta_title_length'],
            'message': msg,
            'length': len(meta_title)
        }
        if len(meta_title) < 50:
            result['recommendations'].append(f'Lengthen meta title (current: {len(meta_title)}, target: 50-60)')
        elif len(meta_title) > 60:
            result['recommendations'].append(f'Shorten meta title (current: {len(meta_title)}, target: 50-60)')
        
        # 8. Meta Description Length
        score, msg = self._score_meta_length(len(meta_description), 140, 160, 'Meta description')
        result['factors']['meta_description_length'] = {
            'score': score,
            'max': self.weights['meta_description_length'],
            'message': msg,
            'length': len(meta_description)
        }
        if len(meta_description) < 140:
            result['recommendations'].append(f'Lengthen meta description (current: {len(meta_description)}, target: 140-160)')
        
        # 9. Readability
        score, msg, reading_level = self._score_readability(body_text)
        result['factors']['readability'] = {
            'score': score,
            'max': self.weights['readability'],
            'message': msg,
            'reading_level': reading_level
        }
        
        # 10. Internal Links
        internal_count = len(re.findall(r'<a[^>]*href=["\'][^"\']*["\']', body_html))
        score, msg = self._score_link_count(internal_count, 3, 8, 'Internal links')
        result['factors']['internal_links'] = {
            'score': score,
            'max': self.weights['internal_links'],
            'message': msg,
            'count': internal_count
        }
        if internal_count < 3:
            result['recommendations'].append(f'Add more internal links (current: {internal_count}, target: 3-8)')
        
        # 11. External Links (authority links)
        external_count = len(re.findall(r'<a[^>]*href=["\']https?://[^"\']*["\']', body_html))
        score, msg = self._score_link_count(external_count, 1, 5, 'External links')
        result['factors']['external_links'] = {
            'score': score,
            'max': self.weights['external_links'],
            'message': msg,
            'count': external_count
        }
        
        # 12. Image Optimization
        img_count = len(re.findall(r'<img[^>]*>', body_html))
        alt_count = len(re.findall(r'<img[^>]*alt=["\'][^"\']+["\']', body_html))
        score, msg = self._score_images(img_count, alt_count)
        result['factors']['image_optimization'] = {
            'score': score,
            'max': self.weights['image_optimization'],
            'message': msg,
            'image_count': img_count,
            'with_alt': alt_count
        }
        if img_count == 0:
            result['recommendations'].append('Add relevant images to your content')
        elif alt_count < img_count:
            result['recommendations'].append('Add alt text to all images')
        
        # 13. Content Depth (LSI keywords, semantic richness)
        score, msg = self._score_content_depth(body_text, keyword)
        result['factors']['content_depth'] = {
            'score': score,
            'max': self.weights['content_depth'],
            'message': msg
        }
        
        # Calculate total score
        total = sum(f['score'] for f in result['factors'].values())
        result['total_score'] = min(100, max(0, total))
        result['grade'] = self._score_to_grade(result['total_score'])
        
        return result
    
    def compare_content(
        self,
        our_content: Dict,
        competitor_content: Dict,
        target_keyword: str,
        location: str = ''
    ) -> Dict:
        """
        Compare our content against competitor content
        """
        our_score = self.score_content(our_content, target_keyword, location)
        comp_score = self.score_content(competitor_content, target_keyword, location)
        
        return {
            'our_score': our_score['total_score'],
            'our_grade': our_score['grade'],
            'competitor_score': comp_score['total_score'],
            'competitor_grade': comp_score['grade'],
            'score_difference': our_score['total_score'] - comp_score['total_score'],
            'we_win': our_score['total_score'] > comp_score['total_score'],
            'our_details': our_score,
            'competitor_details': comp_score,
            'advantages': self._find_advantages(our_score, comp_score),
            'disadvantages': self._find_disadvantages(our_score, comp_score)
        }
    
    def _score_keyword_in_text(self, keyword: str, text: str, location: str) -> tuple:
        """Check if keyword appears in text"""
        weight = self.weights.get(f'keyword_in_{location.lower().replace(" ", "_")}', 5)
        
        if keyword in text:
            return weight, f'✓ Keyword found in {location}'
        
        # Check for partial match
        keyword_words = keyword.split()
        matches = sum(1 for word in keyword_words if word in text)
        if matches > 0:
            partial_score = int(weight * (matches / len(keyword_words)))
            return partial_score, f'Partial keyword match in {location} ({matches}/{len(keyword_words)} words)'
        
        return 0, f'✗ Keyword not found in {location}'
    
    def _score_keyword_density(self, keyword: str, text: str) -> tuple:
        """Score keyword density (target: 1-2%)"""
        words = text.split()
        word_count = len(words)
        
        if word_count == 0:
            return 0, 'No content', 0
        
        # Count keyword occurrences
        keyword_count = text.count(keyword)
        keyword_word_count = len(keyword.split())
        
        # Calculate density
        density = (keyword_count * keyword_word_count / word_count) * 100
        
        weight = self.weights['keyword_density']
        
        if 0.8 <= density <= 2.5:
            return weight, f'✓ Optimal density ({density:.1f}%)', density
        elif 0.5 <= density < 0.8 or 2.5 < density <= 3.5:
            return int(weight * 0.7), f'Density slightly off ({density:.1f}%)', density
        elif density < 0.5:
            return int(weight * 0.3), f'Keyword underused ({density:.1f}%)', density
        else:
            return int(weight * 0.2), f'Keyword stuffing detected ({density:.1f}%)', density
    
    def _score_word_count(self, count: int) -> tuple:
        """Score word count (target: 1200-2500)"""
        weight = self.weights['word_count']
        
        if count >= 1500:
            return weight, f'✓ Excellent length ({count} words)'
        elif count >= 1200:
            return int(weight * 0.9), f'Good length ({count} words)'
        elif count >= 800:
            return int(weight * 0.6), f'Moderate length ({count} words)'
        elif count >= 500:
            return int(weight * 0.4), f'Short content ({count} words)'
        else:
            return int(weight * 0.1), f'Very thin content ({count} words)'
    
    def _score_heading_structure(self, html: str) -> tuple:
        """Score heading structure"""
        weight = self.weights['heading_structure']
        
        h1_count = len(re.findall(r'<h1[^>]*>', html, re.IGNORECASE))
        h2_count = len(re.findall(r'<h2[^>]*>', html, re.IGNORECASE))
        h3_count = len(re.findall(r'<h3[^>]*>', html, re.IGNORECASE))
        
        data = {'h1_count': h1_count, 'h2_count': h2_count, 'h3_count': h3_count}
        
        score = 0
        
        # One H1
        if h1_count == 1:
            score += weight * 0.3
        
        # 3-6 H2s
        if 3 <= h2_count <= 8:
            score += weight * 0.5
        elif h2_count >= 1:
            score += weight * 0.25
        
        # Some H3s
        if h3_count >= 2:
            score += weight * 0.2
        elif h3_count >= 1:
            score += weight * 0.1
        
        if score >= weight * 0.9:
            msg = '✓ Well-structured headings'
        elif score >= weight * 0.5:
            msg = 'Heading structure needs improvement'
        else:
            msg = '✗ Poor heading structure'
        
        return int(score), msg, data
    
    def _score_meta_length(self, length: int, min_len: int, max_len: int, name: str) -> tuple:
        """Score meta tag length"""
        weight = self.weights.get(f'{name.lower().replace(" ", "_")}_length', 5)
        
        if min_len <= length <= max_len:
            return weight, f'✓ {name} length optimal ({length} chars)'
        elif length > 0 and (length >= min_len - 10 or length <= max_len + 10):
            return int(weight * 0.6), f'{name} length slightly off ({length} chars)'
        elif length > 0:
            return int(weight * 0.3), f'{name} length needs work ({length} chars)'
        else:
            return 0, f'✗ Missing {name.lower()}'
    
    def _score_readability(self, text: str) -> tuple:
        """Score readability using simple metrics"""
        weight = self.weights['readability']
        
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return 0, 'No readable content', 'N/A'
        
        words = text.split()
        word_count = len(words)
        sentence_count = len(sentences)
        
        # Average sentence length
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        
        # Average word length
        avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
        
        # Simple readability score (lower is easier)
        # Based on Flesch-Kincaid-like formula
        reading_ease = 206.835 - (1.015 * avg_sentence_length) - (84.6 * (avg_word_length / 5))
        
        if reading_ease >= 60:
            return weight, '✓ Easy to read', 'Easy'
        elif reading_ease >= 40:
            return int(weight * 0.7), 'Moderate readability', 'Moderate'
        elif reading_ease >= 20:
            return int(weight * 0.4), 'Difficult to read', 'Difficult'
        else:
            return int(weight * 0.2), 'Very difficult to read', 'Expert'
    
    def _score_link_count(self, count: int, min_count: int, max_count: int, name: str) -> tuple:
        """Score link count"""
        weight = self.weights.get(name.lower().replace(' ', '_'), 5)
        
        if min_count <= count <= max_count:
            return weight, f'✓ Good {name.lower()} ({count})'
        elif count > 0:
            return int(weight * 0.5), f'{name} count could improve ({count})'
        else:
            return 0, f'✗ No {name.lower()}'
    
    def _score_images(self, img_count: int, alt_count: int) -> tuple:
        """Score image optimization"""
        weight = self.weights['image_optimization']
        
        if img_count == 0:
            return int(weight * 0.3), 'No images found'
        
        alt_ratio = alt_count / img_count
        
        if alt_ratio >= 1.0 and img_count >= 2:
            return weight, f'✓ All {img_count} images have alt text'
        elif alt_ratio >= 0.8:
            return int(weight * 0.7), f'{alt_count}/{img_count} images have alt text'
        elif alt_ratio >= 0.5:
            return int(weight * 0.5), f'Only {alt_count}/{img_count} images have alt text'
        else:
            return int(weight * 0.2), f'Missing alt text on most images'
    
    def _score_content_depth(self, text: str, keyword: str) -> tuple:
        """Score content depth and semantic richness"""
        weight = self.weights['content_depth']
        
        # Check for various quality signals
        signals = 0
        
        # Lists
        if re.search(r'\b(first|second|third|1\.|2\.|3\.)\b', text.lower()):
            signals += 1
        
        # Statistics/numbers
        if re.search(r'\b\d+%|\$\d+|\d+ (years|months|days)\b', text.lower()):
            signals += 1
        
        # Questions
        if '?' in text:
            signals += 1
        
        # Expert terms (varies by industry)
        expert_terms = ['research', 'study', 'according to', 'experts', 'professional', 
                       'certified', 'licensed', 'experience', 'industry', 'standard']
        if any(term in text.lower() for term in expert_terms):
            signals += 1
        
        # Comparison words
        comparison_terms = ['vs', 'versus', 'compare', 'difference', 'better', 'best']
        if any(term in text.lower() for term in comparison_terms):
            signals += 1
        
        # Process words
        process_terms = ['step', 'process', 'guide', 'how to', 'tutorial', 'tip']
        if any(term in text.lower() for term in process_terms):
            signals += 1
        
        score_ratio = min(signals / 4, 1.0)
        score = int(weight * score_ratio)
        
        if signals >= 4:
            return score, '✓ Rich, comprehensive content'
        elif signals >= 2:
            return score, 'Moderate content depth'
        else:
            return score, 'Content lacks depth signals'
    
    def _score_to_grade(self, score: int) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return 'A+'
        elif score >= 80:
            return 'A'
        elif score >= 70:
            return 'B'
        elif score >= 60:
            return 'C'
        elif score >= 50:
            return 'D'
        else:
            return 'F'
    
    def _find_advantages(self, our_score: Dict, comp_score: Dict) -> List[str]:
        """Find factors where we beat competitor"""
        advantages = []
        for factor in our_score['factors']:
            our = our_score['factors'][factor]['score']
            comp = comp_score['factors'].get(factor, {}).get('score', 0)
            if our > comp:
                advantages.append(factor.replace('_', ' ').title())
        return advantages
    
    def _find_disadvantages(self, our_score: Dict, comp_score: Dict) -> List[str]:
        """Find factors where competitor beats us"""
        disadvantages = []
        for factor in our_score['factors']:
            our = our_score['factors'][factor]['score']
            comp = comp_score['factors'].get(factor, {}).get('score', 0)
            if comp > our:
                disadvantages.append(factor.replace('_', ' ').title())
        return disadvantages
    
    def _strip_html(self, html: str) -> str:
        """Remove HTML tags"""
        clean = re.sub(r'<[^>]+>', '', html)
        return re.sub(r'\s+', ' ', clean).strip()


# Singleton
seo_scoring_engine = SEOScoringEngine()
