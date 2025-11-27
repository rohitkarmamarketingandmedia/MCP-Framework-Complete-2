"""
MCP Framework - Review Management Service
Monitor, respond to, and request reviews across platforms
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
import json

from app.database import db
from app.models.db_models import DBReview, DBClient, DBLead

logger = logging.getLogger(__name__)


class ReviewService:
    """Service for managing reviews across platforms"""
    
    def __init__(self):
        self.sendgrid_key = os.getenv('SENDGRID_API_KEY')
        self.twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_from = os.getenv('TWILIO_FROM_NUMBER')
        self.from_email = os.getenv('FROM_EMAIL', 'reviews@mcpframework.com')
    
    # ==========================================
    # Review CRUD
    # ==========================================
    
    def add_review(self, client_id: str, review_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a review to the database
        
        Args:
            client_id: Client ID
            review_data: {
                platform: str (google, yelp, facebook)
                platform_review_id: str (optional)
                reviewer_name: str
                rating: int (1-5)
                review_text: str (optional)
                review_date: datetime
            }
        """
        try:
            review = DBReview(
                id=f"rev_{uuid.uuid4().hex[:12]}",
                client_id=client_id,
                platform=review_data['platform'],
                platform_review_id=review_data.get('platform_review_id'),
                reviewer_name=review_data['reviewer_name'],
                reviewer_avatar=review_data.get('reviewer_avatar'),
                rating=review_data['rating'],
                review_text=review_data.get('review_text'),
                review_date=review_data.get('review_date', datetime.utcnow()),
                status='pending',
                sentiment=self._analyze_sentiment(review_data['rating'], review_data.get('review_text')),
                created_at=datetime.utcnow()
            )
            
            db.session.add(review)
            db.session.commit()
            
            logger.info(f"Review added: {review.id} for client {client_id}")
            
            return {'success': True, 'review': review.to_dict()}
            
        except Exception as e:
            logger.error(f"Add review error: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    def get_reviews(
        self,
        client_id: str,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        days: int = 90,
        limit: int = 100
    ) -> List[Dict]:
        """Get reviews with filters"""
        query = DBReview.query.filter(DBReview.client_id == client_id)
        
        if platform:
            query = query.filter(DBReview.platform == platform)
        
        if status:
            query = query.filter(DBReview.status == status)
        
        if min_rating:
            query = query.filter(DBReview.rating >= min_rating)
        
        if max_rating:
            query = query.filter(DBReview.rating <= max_rating)
        
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query = query.filter(DBReview.review_date >= cutoff)
        
        reviews = query.order_by(DBReview.review_date.desc()).limit(limit).all()
        return [r.to_dict() for r in reviews]
    
    def get_review(self, review_id: str) -> Optional[DBReview]:
        """Get a single review"""
        return DBReview.query.get(review_id)
    
    def update_review_response(
        self,
        review_id: str,
        response_text: str,
        mark_responded: bool = True
    ) -> Dict[str, Any]:
        """Update review with response"""
        review = DBReview.query.get(review_id)
        if not review:
            return {'error': 'Review not found'}
        
        review.response_text = response_text
        if mark_responded:
            review.response_date = datetime.utcnow()
            review.status = 'responded'
        
        db.session.commit()
        
        return {'success': True, 'review': review.to_dict()}
    
    def set_suggested_response(self, review_id: str, suggested: str) -> Dict[str, Any]:
        """Set AI-suggested response for a review"""
        review = DBReview.query.get(review_id)
        if not review:
            return {'error': 'Review not found'}
        
        review.suggested_response = suggested
        db.session.commit()
        
        return {'success': True, 'review': review.to_dict()}
    
    # ==========================================
    # Analytics
    # ==========================================
    
    def get_review_stats(self, client_id: str, days: int = 90) -> Dict[str, Any]:
        """Get review statistics"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        reviews = DBReview.query.filter(
            DBReview.client_id == client_id,
            DBReview.review_date >= cutoff
        ).all()
        
        if not reviews:
            return {
                'total': 0,
                'average_rating': 0,
                'by_platform': {},
                'by_rating': {},
                'by_sentiment': {},
                'response_rate': 0
            }
        
        total = len(reviews)
        total_rating = sum(r.rating for r in reviews)
        
        by_platform = {}
        by_rating = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        by_sentiment = {'positive': 0, 'neutral': 0, 'negative': 0}
        responded = 0
        
        for review in reviews:
            # By platform
            platform = review.platform
            if platform not in by_platform:
                by_platform[platform] = {'count': 0, 'total_rating': 0}
            by_platform[platform]['count'] += 1
            by_platform[platform]['total_rating'] += review.rating
            
            # By rating
            by_rating[review.rating] = by_rating.get(review.rating, 0) + 1
            
            # By sentiment
            sentiment = review.sentiment or 'neutral'
            by_sentiment[sentiment] = by_sentiment.get(sentiment, 0) + 1
            
            # Response tracking
            if review.status == 'responded':
                responded += 1
        
        # Calculate platform averages
        for platform in by_platform:
            by_platform[platform]['average'] = round(
                by_platform[platform]['total_rating'] / by_platform[platform]['count'], 1
            )
        
        return {
            'period_days': days,
            'total': total,
            'average_rating': round(total_rating / total, 1),
            'by_platform': by_platform,
            'by_rating': by_rating,
            'by_sentiment': by_sentiment,
            'response_rate': round(responded / total * 100, 1),
            'pending_responses': total - responded
        }
    
    # ==========================================
    # Review Request Automation
    # ==========================================
    
    def send_review_request_email(
        self,
        client: DBClient,
        customer_email: str,
        customer_name: str,
        review_url: str,
        service_provided: Optional[str] = None
    ) -> bool:
        """Send email requesting a review"""
        if not self.sendgrid_key:
            logger.warning("SendGrid not configured")
            return False
        
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            sg = sendgrid.SendGridAPIClient(api_key=self.sendgrid_key)
            
            subject = f"How was your experience with {client.business_name}?"
            
            first_name = customer_name.split()[0] if customer_name else 'there'
            
            body = f"""Hi {first_name},

Thank you for choosing {client.business_name}{f' for your {service_provided}' if service_provided else ''}! We hope you had a great experience.

We'd love to hear your feedback! Your review helps other customers find us and helps us continue to improve our service.

**Leave us a review:**
{review_url}

It only takes a minute, and we truly appreciate it!

Thank you again for your business.

Best regards,
The {client.business_name} Team

---
If you had any issues with your service, please reply to this email or call us at {client.phone or 'our office'} so we can make it right.
"""
            
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(customer_email),
                subject=subject,
                plain_text_content=Content("text/plain", body)
            )
            
            response = sg.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"Review request email sent to {customer_email}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Review request email error: {e}")
            return False
    
    def send_review_request_sms(
        self,
        client: DBClient,
        customer_phone: str,
        customer_name: str,
        review_url: str
    ) -> bool:
        """Send SMS requesting a review"""
        if not self.twilio_sid or not self.twilio_token:
            logger.warning("Twilio not configured")
            return False
        
        try:
            from twilio.rest import Client
            
            twilio = Client(self.twilio_sid, self.twilio_token)
            
            first_name = customer_name.split()[0] if customer_name else ''
            
            message_body = f"""Hi{' ' + first_name if first_name else ''}! Thanks for choosing {client.business_name}. We'd love your feedback!

Leave a quick review: {review_url}

Thank you! 🙏"""
            
            message = twilio.messages.create(
                body=message_body,
                from_=self.twilio_from,
                to=customer_phone
            )
            
            logger.info(f"Review request SMS sent: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Review request SMS error: {e}")
            return False
    
    def send_review_request_to_lead(
        self,
        lead_id: str,
        review_url: str,
        method: str = 'both'  # email, sms, both
    ) -> Dict[str, Any]:
        """
        Send review request to a converted lead
        
        Args:
            lead_id: Lead ID
            review_url: Google/Yelp review URL
            method: 'email', 'sms', or 'both'
        """
        lead = DBLead.query.get(lead_id)
        if not lead:
            return {'error': 'Lead not found'}
        
        if lead.status != 'converted':
            return {'error': 'Review requests should only be sent to converted leads'}
        
        client = DBClient.query.get(lead.client_id)
        if not client:
            return {'error': 'Client not found'}
        
        results = {'email': False, 'sms': False}
        
        if method in ['email', 'both'] and lead.email:
            results['email'] = self.send_review_request_email(
                client=client,
                customer_email=lead.email,
                customer_name=lead.name,
                review_url=review_url,
                service_provided=lead.service_requested
            )
        
        if method in ['sms', 'both'] and lead.phone:
            results['sms'] = self.send_review_request_sms(
                client=client,
                customer_phone=lead.phone,
                customer_name=lead.name,
                review_url=review_url
            )
        
        return {
            'success': results['email'] or results['sms'],
            'results': results
        }
    
    def bulk_send_review_requests(
        self,
        client_id: str,
        review_url: str,
        days_since_conversion: int = 7,
        method: str = 'email'
    ) -> Dict[str, Any]:
        """
        Send review requests to recently converted leads
        
        Args:
            client_id: Client ID
            review_url: Review URL
            days_since_conversion: Only send to leads converted within this many days
            method: 'email', 'sms', or 'both'
        """
        cutoff = datetime.utcnow() - timedelta(days=days_since_conversion)
        
        leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.status == 'converted',
            DBLead.converted_at >= cutoff
        ).all()
        
        sent = 0
        failed = 0
        
        for lead in leads:
            result = self.send_review_request_to_lead(lead.id, review_url, method)
            if result.get('success'):
                sent += 1
            else:
                failed += 1
        
        return {
            'success': True,
            'sent': sent,
            'failed': failed,
            'total_leads': len(leads)
        }
    
    # ==========================================
    # AI Response Generation
    # ==========================================
    
    def generate_response(
        self,
        review: DBReview,
        client: DBClient,
        ai_service=None
    ) -> str:
        """Generate AI response for a review using agent config"""
        if ai_service:
            # Build the user input for the agent
            user_input = f"""Generate a response to this review:

Business: {client.business_name}
Industry: {client.industry}
Location: {client.geo}
Rating: {review.rating}/5 stars
Reviewer: {review.reviewer_name or 'Anonymous'}
Review: {review.review_text or 'No comment provided'}

Respond with just the response text, no JSON formatting needed."""
            
            try:
                # Try to use the review_responder agent
                response = ai_service.generate_raw_with_agent(
                    agent_name='review_responder',
                    user_input=user_input
                )
                
                if response:
                    # Clean up response if it's JSON
                    if response.strip().startswith('{'):
                        import json
                        try:
                            data = json.loads(response)
                            response = data.get('response', response)
                        except:
                            pass
                    return response.strip()
                    
            except Exception as e:
                logger.error(f"AI response generation error: {e}")
        
        # Fallback templates
        return self._get_template_response(review, client)
    
    def _get_template_response(self, review: DBReview, client: DBClient) -> str:
        """Get template response based on rating"""
        name = review.reviewer_name or 'valued customer'
        
        if review.rating >= 4:
            return f"Thank you so much for the wonderful review, {name}! We're thrilled to hear about your positive experience with {client.business_name}. Your support means the world to us, and we look forward to serving you again soon!"
        
        elif review.rating == 3:
            return f"Thank you for your feedback, {name}. We appreciate you taking the time to share your experience. We're always working to improve, and we'd love the opportunity to exceed your expectations next time. Please don't hesitate to reach out if there's anything we can do better."
        
        else:
            return f"Thank you for bringing this to our attention, {name}. We're sorry to hear your experience didn't meet expectations. We take all feedback seriously and would love the opportunity to make this right. Please contact us directly{f' at {client.phone}' if client.phone else ''} so we can address your concerns."
    
    def generate_responses_for_pending(
        self,
        client_id: str,
        ai_service=None
    ) -> Dict[str, Any]:
        """Generate AI responses for all pending reviews"""
        reviews = DBReview.query.filter(
            DBReview.client_id == client_id,
            DBReview.status == 'pending',
            DBReview.suggested_response.is_(None)
        ).all()
        
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        generated = 0
        for review in reviews:
            response = self.generate_response(review, client, ai_service)
            review.suggested_response = response
            generated += 1
        
        db.session.commit()
        
        return {
            'success': True,
            'generated': generated
        }
    
    # ==========================================
    # Review Widget
    # ==========================================
    
    def generate_review_widget(
        self,
        client_id: str,
        config: Dict = None
    ) -> str:
        """Generate embeddable review display widget"""
        config = config or {}
        
        # Get recent positive reviews
        reviews = self.get_reviews(
            client_id=client_id,
            min_rating=4,
            limit=config.get('max_reviews', 5)
        )
        
        widget_id = f"mcp-reviews-{client_id[:8]}"
        
        # Build review HTML
        reviews_html = ''
        for review in reviews:
            stars = '★' * review['rating'] + '☆' * (5 - review['rating'])
            reviews_html += f'''
                <div class="mcp-review">
                    <div class="mcp-review-header">
                        <span class="mcp-review-stars">{stars}</span>
                        <span class="mcp-review-author">{review['reviewer_name']}</span>
                    </div>
                    <p class="mcp-review-text">{review.get('review_text', '')[:200]}{'...' if len(review.get('review_text', '')) > 200 else ''}</p>
                    <div class="mcp-review-platform">{review['platform'].title()}</div>
                </div>
            '''
        
        html = f'''
<!-- MCP Reviews Widget -->
<div id="{widget_id}" class="mcp-reviews-widget">
    <style>
        #{widget_id} {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 600px;
        }}
        #{widget_id} .mcp-reviews-header {{
            text-align: center;
            margin-bottom: 20px;
        }}
        #{widget_id} .mcp-reviews-title {{
            font-size: 24px;
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 8px;
        }}
        #{widget_id} .mcp-reviews-summary {{
            font-size: 18px;
            color: #f59e0b;
        }}
        #{widget_id} .mcp-review {{
            background: #f9fafb;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        #{widget_id} .mcp-review-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        #{widget_id} .mcp-review-stars {{
            color: #f59e0b;
            font-size: 16px;
        }}
        #{widget_id} .mcp-review-author {{
            font-weight: 500;
            color: #374151;
        }}
        #{widget_id} .mcp-review-text {{
            color: #4b5563;
            line-height: 1.5;
            margin: 0;
        }}
        #{widget_id} .mcp-review-platform {{
            font-size: 12px;
            color: #9ca3af;
            margin-top: 8px;
        }}
    </style>
    
    <div class="mcp-reviews-header">
        <div class="mcp-reviews-title">What Our Customers Say</div>
        <div class="mcp-reviews-summary">★★★★★ {len(reviews)} 5-Star Reviews</div>
    </div>
    
    <div class="mcp-reviews-list">
        {reviews_html if reviews_html else '<p style="text-align:center;color:#9ca3af;">No reviews yet</p>'}
    </div>
</div>
'''
        return html
    
    # ==========================================
    # Utilities
    # ==========================================
    
    def _analyze_sentiment(self, rating: int, text: Optional[str]) -> str:
        """Simple sentiment analysis based on rating"""
        if rating >= 4:
            return 'positive'
        elif rating == 3:
            return 'neutral'
        else:
            return 'negative'
    
    def get_review_url(self, client: DBClient, platform: str = 'google') -> Optional[str]:
        """Get the review URL for a platform"""
        integrations = client.get_integrations()
        
        if platform == 'google' and integrations.get('gbp_place_id'):
            place_id = integrations['gbp_place_id']
            return f"https://search.google.com/local/writereview?placeid={place_id}"
        
        if platform == 'yelp' and integrations.get('yelp_business_id'):
            biz_id = integrations['yelp_business_id']
            return f"https://www.yelp.com/writeareview/biz/{biz_id}"
        
        if platform == 'facebook' and integrations.get('facebook_page_id'):
            page_id = integrations['facebook_page_id']
            return f"https://www.facebook.com/{page_id}/reviews"
        
        return None


# Global instance
review_service = ReviewService()
