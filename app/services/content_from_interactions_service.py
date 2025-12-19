"""
MCP Framework - Content From Interactions Service
Automatically generates content from customer interaction intelligence

Turns calls, chats, and forms into:
- FAQ pages with real Q&A
- Blog posts answering common questions
- Service page enhancements
- "What Customers Ask" sections
- Content calendars based on real demand
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from app.database import db
from app.models.db_models import DBClient, DBBlogPost, DBSocialPost
from app.services.interaction_intelligence_service import get_interaction_intelligence_service
from app.services.ai_service import get_ai_service

logger = logging.getLogger(__name__)


class ContentFromInteractionsService:
    """
    Generate content from customer interaction intelligence
    
    This is the magic that turns customer conversations into SEO content
    """
    
    def __init__(self):
        self.intelligence_service = get_interaction_intelligence_service()
        self.ai_service = get_ai_service()
    
    # ==========================================
    # FAQ GENERATION
    # ==========================================
    
    def generate_faq_page(
        self,
        client_id: str,
        questions: List[Dict] = None,
        max_questions: int = 15
    ) -> Dict[str, Any]:
        """
        Generate a complete FAQ page from real customer questions
        
        Args:
            client_id: Client ID
            questions: Pre-extracted questions (or will fetch from intelligence)
            max_questions: Maximum number of FAQs to include
        
        Returns:
            {
                'title': str,
                'meta_description': str,
                'faqs': [{question, answer, source}],
                'schema_markup': {...},
                'html': str
            }
        """
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        # Get questions from intelligence if not provided
        if not questions:
            report = self.intelligence_service.get_full_intelligence_report(client_id)
            questions = report.get('combined_insights', {}).get('top_questions', [])
        
        if not questions:
            return {'error': 'No questions found to generate FAQ'}
        
        # Limit questions
        questions = questions[:max_questions]
        
        # Generate answers for each question
        faqs = []
        for q in questions:
            question_text = q.get('question', q) if isinstance(q, dict) else q
            
            # Generate answer using AI
            answer = self._generate_faq_answer(question_text, client)
            
            faqs.append({
                'question': question_text,
                'answer': answer,
                'source': q.get('sources', ['customer_interaction']) if isinstance(q, dict) else ['customer_interaction'],
                'frequency': q.get('count', 1) if isinstance(q, dict) else 1
            })
        
        # Generate page metadata
        title = f"Frequently Asked Questions | {client.business_name}"
        meta_description = f"Get answers to common questions about {client.industry} services in {client.geo}. Real questions from real customers answered by {client.business_name}."
        
        # Generate FAQ schema markup
        schema = self._generate_faq_schema(faqs, client)
        
        # Generate HTML
        html = self._generate_faq_html(faqs, client, title)
        
        return {
            'title': title,
            'meta_description': meta_description,
            'faqs': faqs,
            'schema_markup': schema,
            'html': html,
            'word_count': sum(len(f['answer'].split()) for f in faqs),
            'generated_at': datetime.utcnow().isoformat()
        }
    
    def _generate_faq_answer(self, question: str, client: DBClient) -> str:
        """Generate an answer for a FAQ question using AI"""
        prompt = f"""You are a helpful {client.industry} expert at {client.business_name} in {client.geo}.
        
Answer this customer question professionally and helpfully in 2-3 sentences:

Question: {question}

Guidelines:
- Be specific and helpful
- Mention {client.geo} if relevant
- End with a soft call-to-action when appropriate
- Keep it conversational but professional
- If it's a pricing question, give a range and suggest contacting for exact quote

Answer:"""
        
        try:
            # Use AI service
            response = self.ai_service.generate_text(prompt, max_tokens=200)
            return response.strip()
        except Exception as e:
            logger.warning(f"AI FAQ generation failed: {e}")
            # Fallback generic answer
            return f"Great question! For specific details about this, please contact us at {client.business_name}. We're happy to provide personalized information for your situation in {client.geo}."
    
    def _generate_faq_schema(self, faqs: List[Dict], client: DBClient) -> Dict:
        """Generate FAQ Schema markup for SEO"""
        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq['question'],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq['answer']
                    }
                }
                for faq in faqs
            ]
        }
    
    def _generate_faq_html(self, faqs: List[Dict], client: DBClient, title: str) -> str:
        """Generate HTML for FAQ page"""
        faq_items = ""
        for i, faq in enumerate(faqs):
            faq_items += f"""
            <div class="faq-item" itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
                <button class="faq-question" onclick="toggleFaq({i})">
                    <h3 itemprop="name">{faq['question']}</h3>
                    <span class="faq-icon">+</span>
                </button>
                <div class="faq-answer" id="faq-{i}" itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
                    <p itemprop="text">{faq['answer']}</p>
                </div>
            </div>
            """
        
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        .faq-container {{ max-width: 800px; margin: 0 auto; padding: 40px 20px; }}
        .faq-item {{ border-bottom: 1px solid #e2e8f0; }}
        .faq-question {{ 
            width: 100%; background: none; border: none; padding: 20px 0; 
            display: flex; justify-content: space-between; align-items: center;
            cursor: pointer; text-align: left;
        }}
        .faq-question h3 {{ margin: 0; font-size: 18px; color: #1e293b; }}
        .faq-icon {{ font-size: 24px; color: #3b82f6; transition: transform 0.3s; }}
        .faq-answer {{ display: none; padding: 0 0 20px; color: #64748b; line-height: 1.6; }}
        .faq-answer.active {{ display: block; }}
        .faq-question.active .faq-icon {{ transform: rotate(45deg); }}
        .faq-header {{ text-align: center; margin-bottom: 40px; }}
        .faq-header h1 {{ color: #1e293b; margin-bottom: 10px; }}
        .faq-header p {{ color: #64748b; }}
        .faq-cta {{ text-align: center; margin-top: 40px; padding: 30px; background: #f8fafc; border-radius: 12px; }}
        .faq-cta h3 {{ margin-bottom: 15px; }}
        .faq-cta a {{ 
            display: inline-block; background: #3b82f6; color: white; 
            padding: 12px 24px; border-radius: 8px; text-decoration: none;
        }}
    </style>
</head>
<body itemscope itemtype="https://schema.org/FAQPage">
    <div class="faq-container">
        <div class="faq-header">
            <h1>{title}</h1>
            <p>Real questions from our customers in {client.geo}</p>
        </div>
        
        {faq_items}
        
        <div class="faq-cta">
            <h3>Still Have Questions?</h3>
            <p>Our team at {client.business_name} is here to help!</p>
            <a href="tel:{client.phone}">Call Us Now</a>
        </div>
    </div>
    
    <script>
        function toggleFaq(index) {{
            const answer = document.getElementById('faq-' + index);
            const question = answer.previousElementSibling;
            answer.classList.toggle('active');
            question.classList.toggle('active');
        }}
    </script>
</body>
</html>
        """
    
    # ==========================================
    # BLOG POST GENERATION
    # ==========================================
    
    def generate_blog_from_questions(
        self,
        client_id: str,
        questions: List[str],
        topic: str = None,
        save_draft: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a blog post that answers a cluster of related questions
        
        Args:
            client_id: Client ID
            questions: List of questions to answer in the blog
            topic: Optional topic override
            save_draft: Whether to save as draft in database
        
        Returns:
            Blog post data with title, content, meta, etc.
        """
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        if not questions:
            return {'error': 'No questions provided'}
        
        # Determine topic if not provided
        if not topic:
            topic = self._infer_topic_from_questions(questions)
        
        # Generate blog using AI
        blog_data = self._generate_blog_content(client, questions, topic)
        
        # Save as draft if requested
        if save_draft:
            blog_post = DBBlogPost(
                client_id=client_id,
                title=blog_data['title'],
                meta_description=blog_data['meta_description'],
                body=blog_data['content'],
                primary_keyword=blog_data['primary_keyword'],
                status='draft',
                seo_score=blog_data.get('seo_score', 75),
                word_count=blog_data['word_count'],
                source='customer_questions'  # Track that this came from real questions
            )
            db.session.add(blog_post)
            db.session.commit()
            blog_data['id'] = blog_post.id
            blog_data['saved'] = True
        
        return blog_data
    
    def _generate_blog_content(
        self,
        client: DBClient,
        questions: List[str],
        topic: str
    ) -> Dict[str, Any]:
        """Generate full blog content from questions using AI"""
        
        questions_text = "\n".join([f"- {q}" for q in questions[:10]])
        
        prompt = f"""You are an expert content writer for {client.business_name}, a {client.industry} company in {client.geo}.

Write a comprehensive, SEO-optimized blog post that answers these REAL questions from customers:

{questions_text}

Topic: {topic}

Requirements:
1. Title must include the primary keyword AND {client.geo}
2. Start with an engaging introduction (no H1)
3. Each H2 heading must start with the keyword + {client.geo}
4. Answer each question thoroughly in its own section
5. Include practical tips and actionable advice
6. Add internal linking opportunities (mark with [INTERNAL LINK: topic])
7. Minimum 1800 words
8. End with a strong call-to-action mentioning {client.business_name}
9. Conversational but professional tone
10. Include a "Key Takeaways" section before the conclusion

Format the response as:
TITLE: [Your title here]
META: [Meta description under 160 chars]
PRIMARY_KEYWORD: [Main keyword]
CONTENT:
[Your blog content with proper H2 headings in markdown]
"""
        
        try:
            response = self.ai_service.generate_text(prompt, max_tokens=3000)
            return self._parse_blog_response(response, client)
        except Exception as e:
            logger.error(f"Blog generation failed: {e}")
            return {
                'error': str(e),
                'title': f"{topic} - {client.geo}",
                'content': '',
                'meta_description': '',
                'primary_keyword': topic
            }
    
    def _parse_blog_response(self, response: str, client: DBClient) -> Dict[str, Any]:
        """Parse AI blog response into structured data"""
        lines = response.split('\n')
        
        title = ""
        meta = ""
        keyword = ""
        content_lines = []
        in_content = False
        
        for line in lines:
            if line.startswith('TITLE:'):
                title = line.replace('TITLE:', '').strip()
            elif line.startswith('META:'):
                meta = line.replace('META:', '').strip()
            elif line.startswith('PRIMARY_KEYWORD:'):
                keyword = line.replace('PRIMARY_KEYWORD:', '').strip()
            elif line.startswith('CONTENT:'):
                in_content = True
            elif in_content:
                content_lines.append(line)
        
        content = '\n'.join(content_lines).strip()
        
        return {
            'title': title or f"Customer Questions Answered | {client.business_name}",
            'meta_description': meta[:160] if meta else f"Get answers to common {client.industry} questions in {client.geo}.",
            'primary_keyword': keyword or client.industry,
            'content': content,
            'word_count': len(content.split()),
            'seo_score': 80,  # Base score for AI-generated content
            'source': 'customer_questions'
        }
    
    def _infer_topic_from_questions(self, questions: List[str]) -> str:
        """Infer the main topic from a list of questions"""
        # Simple word frequency approach
        from collections import Counter
        
        words = []
        stop_words = {'how', 'what', 'when', 'where', 'why', 'who', 'which', 'the', 'a', 'an', 'is', 'are', 'do', 'does', 'can', 'will', 'should', 'would', 'could', 'my', 'your', 'for', 'to', 'in', 'on', 'at', 'of'}
        
        for q in questions:
            for word in q.lower().split():
                word = word.strip('?.,!').strip()
                if word and len(word) > 3 and word not in stop_words:
                    words.append(word)
        
        if words:
            most_common = Counter(words).most_common(3)
            return ' '.join([w[0] for w in most_common]).title()
        
        return "Customer Questions"
    
    # ==========================================
    # SERVICE PAGE ENHANCEMENT
    # ==========================================
    
    def generate_service_page_qa_section(
        self,
        client_id: str,
        service: str,
        questions: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate a "What Customers Ask" section for a service page
        
        Perfect for adding to existing service pages to boost SEO
        """
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        # Get service-specific questions if not provided
        if not questions:
            report = self.intelligence_service.get_full_intelligence_report(client_id)
            all_questions = report.get('combined_insights', {}).get('top_questions', [])
            
            # Filter for this service
            questions = [q for q in all_questions if service.lower() in q.get('question', '').lower()]
        
        if not questions:
            return {'error': f'No questions found for service: {service}'}
        
        # Generate Q&A pairs
        qa_pairs = []
        for q in questions[:8]:
            question_text = q.get('question', q) if isinstance(q, dict) else q
            answer = self._generate_faq_answer(question_text, client)
            qa_pairs.append({
                'question': question_text,
                'answer': answer
            })
        
        # Generate HTML section
        html = self._generate_qa_section_html(qa_pairs, service, client)
        
        return {
            'service': service,
            'qa_pairs': qa_pairs,
            'html': html,
            'schema_markup': self._generate_faq_schema(qa_pairs, client),
            'section_title': f"What {client.geo} Customers Ask About {service.title()}"
        }
    
    def _generate_qa_section_html(self, qa_pairs: List[Dict], service: str, client: DBClient) -> str:
        """Generate HTML for a Q&A section to embed in service pages"""
        qa_items = ""
        for qa in qa_pairs:
            qa_items += f"""
            <div class="qa-item">
                <h4 class="qa-question">{qa['question']}</h4>
                <p class="qa-answer">{qa['answer']}</p>
            </div>
            """
        
        return f"""
<section class="service-qa-section" itemscope itemtype="https://schema.org/FAQPage">
    <h3>What {client.geo} Customers Ask About {service.title()}</h3>
    <p class="qa-intro">Real questions from customers just like you:</p>
    
    <div class="qa-grid">
        {qa_items}
    </div>
    
    <div class="qa-cta">
        <p>Have a question not answered here?</p>
        <a href="tel:{client.phone}" class="btn-primary">Call Us: {client.phone}</a>
    </div>
</section>

<style>
.service-qa-section {{ padding: 40px 0; background: #f8fafc; border-radius: 12px; margin: 30px 0; }}
.service-qa-section h3 {{ text-align: center; margin-bottom: 10px; }}
.qa-intro {{ text-align: center; color: #64748b; margin-bottom: 30px; }}
.qa-grid {{ display: grid; gap: 20px; padding: 0 20px; }}
.qa-item {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
.qa-question {{ color: #1e293b; margin-bottom: 10px; font-size: 16px; }}
.qa-answer {{ color: #64748b; line-height: 1.6; margin: 0; }}
.qa-cta {{ text-align: center; margin-top: 30px; }}
.btn-primary {{ display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; }}
</style>
        """
    
    # ==========================================
    # CONTENT CALENDAR GENERATION
    # ==========================================
    
    def generate_content_calendar(
        self,
        client_id: str,
        weeks: int = 4,
        posts_per_week: int = 2
    ) -> Dict[str, Any]:
        """
        Generate a content calendar based on customer question trends
        
        Creates blog topics for the next N weeks based on real demand
        """
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        # Get intelligence report
        report = self.intelligence_service.get_full_intelligence_report(client_id)
        opportunities = report.get('content_opportunities', [])
        top_questions = report.get('combined_insights', {}).get('top_questions', [])
        
        # Generate calendar
        calendar = []
        start_date = datetime.utcnow() + timedelta(days=7 - datetime.utcnow().weekday())  # Next Monday
        
        blog_topics = []
        
        # Use content opportunities first
        for opp in opportunities:
            if opp.get('type') in ['blog_post', 'content_series']:
                blog_topics.append({
                    'title': opp.get('title') or opp.get('suggested_title'),
                    'questions': opp.get('questions', [])[:5],
                    'priority': opp.get('priority', 5),
                    'source': 'content_opportunity'
                })
        
        # Add question clusters
        question_clusters = self._cluster_questions_for_calendar(top_questions)
        for cluster in question_clusters:
            blog_topics.append({
                'title': cluster['title'],
                'questions': cluster['questions'],
                'priority': len(cluster['questions']),
                'source': 'question_cluster'
            })
        
        # Sort by priority
        blog_topics.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        # Create weekly schedule
        topic_index = 0
        for week in range(weeks):
            week_start = start_date + timedelta(weeks=week)
            week_posts = []
            
            for post_num in range(posts_per_week):
                if topic_index >= len(blog_topics):
                    break
                
                topic = blog_topics[topic_index]
                publish_date = week_start + timedelta(days=post_num * 3 + 1)  # Spread across week
                
                week_posts.append({
                    'date': publish_date.strftime('%Y-%m-%d'),
                    'day': publish_date.strftime('%A'),
                    'title': topic['title'],
                    'questions_to_answer': topic['questions'],
                    'status': 'planned',
                    'source': topic['source']
                })
                
                topic_index += 1
            
            calendar.append({
                'week': week + 1,
                'week_start': week_start.strftime('%Y-%m-%d'),
                'posts': week_posts
            })
        
        return {
            'client_id': client_id,
            'client_name': client.business_name,
            'calendar': calendar,
            'total_posts': sum(len(w['posts']) for w in calendar),
            'generated_at': datetime.utcnow().isoformat(),
            'based_on': {
                'questions_analyzed': len(top_questions),
                'content_opportunities': len(opportunities)
            }
        }
    
    def _cluster_questions_for_calendar(self, questions: List[Dict]) -> List[Dict]:
        """Cluster questions into blog-worthy groups"""
        # Reuse intelligence service clustering
        clustered = self.intelligence_service._cluster_questions(questions)
        
        result = []
        for cluster in clustered:
            result.append({
                'title': cluster['suggested_title'],
                'questions': cluster['questions'][:5],
                'keywords': cluster['keywords']
            })
        
        return result
    
    # ==========================================
    # AUTO-GENERATE ALL CONTENT TYPES
    # ==========================================
    
    def auto_generate_content_package(
        self,
        client_id: str,
        call_transcripts: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete content package from customer interactions
        
        Includes:
        - FAQ page
        - 3 blog posts
        - Service page Q&A sections
        - Content calendar
        """
        results = {
            'client_id': client_id,
            'generated_at': datetime.utcnow().isoformat(),
            'content': {}
        }
        
        # Get full intelligence report
        report = self.intelligence_service.get_full_intelligence_report(
            client_id,
            call_transcripts=call_transcripts
        )
        
        results['intelligence'] = {
            'total_interactions': report.get('combined_insights', {}).get('total_interactions', 0),
            'questions_extracted': len(report.get('combined_insights', {}).get('top_questions', [])),
            'pain_points_found': len(report.get('combined_insights', {}).get('top_pain_points', [])),
            'content_opportunities': len(report.get('content_opportunities', []))
        }
        
        # Generate FAQ page
        try:
            faq = self.generate_faq_page(
                client_id,
                questions=report.get('combined_insights', {}).get('top_questions', [])
            )
            results['content']['faq_page'] = {
                'generated': True,
                'questions': len(faq.get('faqs', [])),
                'title': faq.get('title')
            }
        except Exception as e:
            results['content']['faq_page'] = {'generated': False, 'error': str(e)}
        
        # Generate blog posts from top question clusters
        top_questions = report.get('combined_insights', {}).get('top_questions', [])
        if top_questions:
            clusters = self._cluster_questions_for_calendar(top_questions)
            
            blogs_generated = []
            for cluster in clusters[:3]:  # Top 3 clusters
                try:
                    blog = self.generate_blog_from_questions(
                        client_id,
                        questions=cluster['questions'],
                        topic=cluster.get('title'),
                        save_draft=True
                    )
                    blogs_generated.append({
                        'title': blog.get('title'),
                        'word_count': blog.get('word_count'),
                        'id': blog.get('id')
                    })
                except Exception as e:
                    logger.warning(f"Blog generation failed: {e}")
            
            results['content']['blog_posts'] = {
                'generated': True,
                'count': len(blogs_generated),
                'posts': blogs_generated
            }
        
        # Generate content calendar
        try:
            calendar = self.generate_content_calendar(client_id, weeks=4)
            results['content']['content_calendar'] = {
                'generated': True,
                'weeks': len(calendar.get('calendar', [])),
                'total_posts': calendar.get('total_posts', 0)
            }
        except Exception as e:
            results['content']['content_calendar'] = {'generated': False, 'error': str(e)}
        
        return results


# Singleton
_content_service = None

def get_content_from_interactions_service() -> ContentFromInteractionsService:
    """Get or create content service singleton"""
    global _content_service
    if _content_service is None:
        _content_service = ContentFromInteractionsService()
    return _content_service
