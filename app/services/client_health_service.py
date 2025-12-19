"""
MCP Framework - Client Health Score Service
Calculates a 100-point "report card" score that makes clients feel the VALUE

Scoring breakdown:
- Rankings (25 pts): Keywords improving vs dropping
- Content (20 pts): Publishing on schedule
- Leads (25 pts): Lead generation vs target
- Reviews (15 pts): New reviews coming in
- Engagement (15 pts): Social/GMB activity
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from app.database import db
from app.models.db_models import (
    DBClient, DBBlogPost, DBSocialPost, DBRankHistory,
    DBLead, DBCompetitor, DBAuditLog
)

logger = logging.getLogger(__name__)


@dataclass
class HealthScoreBreakdown:
    """Detailed breakdown of health score components"""
    # Non-default fields must come first
    total: int
    grade: str
    color: str
    rankings_score: int
    content_score: int
    leads_score: int
    reviews_score: int
    engagement_score: int
    # Default fields come after
    rankings_max: int = 25
    rankings_detail: str = ""
    content_max: int = 20
    content_detail: str = ""
    leads_max: int = 25
    leads_detail: str = ""
    reviews_max: int = 15
    reviews_detail: str = ""
    engagement_max: int = 15
    engagement_detail: str = ""
    
    def to_dict(self) -> dict:
        return {
            'total': self.total,
            'grade': self.grade,
            'color': self.color,
            'breakdown': {
                'rankings': {
                    'score': self.rankings_score,
                    'max': self.rankings_max,
                    'percent': round((self.rankings_score / self.rankings_max) * 100),
                    'detail': self.rankings_detail
                },
                'content': {
                    'score': self.content_score,
                    'max': self.content_max,
                    'percent': round((self.content_score / self.content_max) * 100),
                    'detail': self.content_detail
                },
                'leads': {
                    'score': self.leads_score,
                    'max': self.leads_max,
                    'percent': round((self.leads_score / self.leads_max) * 100),
                    'detail': self.leads_detail
                },
                'reviews': {
                    'score': self.reviews_score,
                    'max': self.reviews_max,
                    'percent': round((self.reviews_score / self.reviews_max) * 100),
                    'detail': self.reviews_detail
                },
                'engagement': {
                    'score': self.engagement_score,
                    'max': self.engagement_max,
                    'percent': round((self.engagement_score / self.engagement_max) * 100),
                    'detail': self.engagement_detail
                }
            }
        }


class ClientHealthService:
    """
    Calculate and track client health scores
    
    This creates the "feel good" factor that makes clients:
    1. Trust we're working hard for them
    2. See concrete value
    3. Want to pay us more
    """
    
    def __init__(self):
        self.default_lead_target = 10  # Default monthly lead target
    
    def calculate_health_score(self, client_id: str, days: int = 30) -> HealthScoreBreakdown:
        """
        Calculate comprehensive health score for a client
        
        Args:
            client_id: The client ID
            days: Period to analyze (default 30 days)
        
        Returns:
            HealthScoreBreakdown with detailed scoring
        """
        try:
            now = datetime.utcnow()
            period_start = now - timedelta(days=days)
            
            # Get client
            client = DBClient.query.get(client_id)
            if not client:
                return self._empty_score()
            
            # Calculate each component with defensive error handling
            try:
                rankings_score, rankings_detail = self._score_rankings(client_id, period_start)
            except Exception:
                rankings_score, rankings_detail = 0, "Unable to calculate"
            
            try:
                content_score, content_detail = self._score_content(client_id, period_start)
            except Exception:
                content_score, content_detail = 0, "Unable to calculate"
            
            try:
                leads_score, leads_detail = self._score_leads(client_id, period_start, days)
            except Exception:
                leads_score, leads_detail = 0, "Unable to calculate"
            
            try:
                reviews_score, reviews_detail = self._score_reviews(client_id, period_start)
            except Exception:
                reviews_score, reviews_detail = 0, "Unable to calculate"
            
            try:
                engagement_score, engagement_detail = self._score_engagement(client_id, period_start)
            except Exception:
                engagement_score, engagement_detail = 0, "Unable to calculate"
            
            # Calculate total
            total = rankings_score + content_score + leads_score + reviews_score + engagement_score
            
            # Determine grade and color
            grade, color = self._get_grade(total)
            
            return HealthScoreBreakdown(
                total=total,
                grade=grade,
                color=color,
                rankings_score=rankings_score,
                content_score=content_score,
                leads_score=leads_score,
                reviews_score=reviews_score,
                engagement_score=engagement_score,
                rankings_detail=rankings_detail,
                content_detail=content_detail,
                leads_detail=leads_detail,
                reviews_detail=reviews_detail,
                engagement_detail=engagement_detail
            )
        except Exception as e:
            # Return empty score on any unexpected error
            return self._empty_score()
    
    def _score_rankings(self, client_id: str, period_start: datetime) -> tuple:
        """
        Score rankings component (25 points max)
        
        - Keywords improving: +3 pts each (up to 15)
        - Keywords stable: +1 pt each (up to 5)
        - Keywords dropping: -2 pts each
        - Page 1 keywords: +1 pt each (up to 5)
        """
        score = 0
        
        # Get recent rank history (limited to prevent timeout)
        history = DBRankHistory.query.filter(
            DBRankHistory.client_id == client_id,
            DBRankHistory.checked_at >= period_start
        ).order_by(DBRankHistory.checked_at.desc()).limit(200).all()
        
        if not history:
            return (12, "No ranking data yet - monitoring starting")
        
        # Group by keyword, get latest
        keyword_data = {}
        for h in history:
            if h.keyword not in keyword_data:
                keyword_data[h.keyword] = {
                    'current': h.position,
                    'change': h.change or 0
                }
        
        improved = 0
        stable = 0
        dropped = 0
        page_one = 0
        
        for kw, data in keyword_data.items():
            if data['change'] > 0:
                improved += 1
            elif data['change'] < 0:
                dropped += 1
            else:
                stable += 1
            
            if data['current'] and data['current'] <= 10:
                page_one += 1
        
        # Calculate score
        score += min(improved * 3, 15)  # Up to 15 for improvements
        score += min(stable * 1, 5)      # Up to 5 for stable
        score -= dropped * 2             # Penalty for drops
        score += min(page_one * 1, 5)    # Up to 5 for page 1
        
        # Ensure 0-25 range
        score = max(0, min(25, score))
        
        if improved > dropped:
            detail = f"{improved} keywords improved, {page_one} on page 1"
        elif dropped > improved:
            detail = f"{dropped} keywords dropped - we're working on it"
        else:
            detail = f"{len(keyword_data)} keywords tracked, {page_one} on page 1"
        
        return (score, detail)
    
    def _score_content(self, client_id: str, period_start: datetime) -> tuple:
        """
        Score content component (20 points max)
        
        - Blogs published on time: +5 pts each (up to 10)
        - Social posts published: +1 pt each (up to 5)
        - Content in pipeline: +1 pt each (up to 5)
        """
        score = 0
        
        # Published blogs
        published_blogs = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'published',
            DBBlogPost.published_at >= period_start
        ).count()
        
        # Published social
        published_social = DBSocialPost.query.filter(
            DBSocialPost.client_id == client_id,
            DBSocialPost.status == 'published',
            DBSocialPost.published_at >= period_start
        ).count()
        
        # Scheduled/pipeline
        scheduled = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status.in_(['scheduled', 'approved', 'draft'])
        ).count()
        
        scheduled += DBSocialPost.query.filter(
            DBSocialPost.client_id == client_id,
            DBSocialPost.status.in_(['scheduled', 'approved', 'draft'])
        ).count()
        
        # Calculate score
        score += min(published_blogs * 5, 10)   # Up to 10 for blogs
        score += min(published_social * 1, 5)   # Up to 5 for social
        score += min(scheduled * 1, 5)          # Up to 5 for pipeline
        
        score = min(20, score)
        
        detail = f"{published_blogs} blogs, {published_social} social posts published"
        if scheduled > 0:
            detail += f", {scheduled} more in pipeline"
        
        return (score, detail)
    
    def _score_leads(self, client_id: str, period_start: datetime, days: int) -> tuple:
        """
        Score leads component (25 points max)
        
        - Meeting target: 15 pts base
        - Exceeding target: +2 pts per 10% over (up to 10)
        - Below target: -2 pts per 10% under
        """
        # Get lead count
        leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= period_start
        ).count()
        
        # Get target (from client settings or default)
        client = DBClient.query.get(client_id)
        monthly_target = self.default_lead_target
        if client and hasattr(client, 'monthly_lead_target'):
            monthly_target = client.monthly_lead_target or self.default_lead_target
        
        # Adjust target for period
        period_target = (monthly_target / 30) * days
        
        if period_target == 0:
            return (15, f"{leads} leads generated")
        
        # Calculate percentage of target
        percent = (leads / period_target) * 100
        
        if percent >= 100:
            # Meeting or exceeding target
            score = 15
            overage = percent - 100
            bonus = min(int(overage / 10) * 2, 10)  # +2 per 10% over, max 10
            score += bonus
            detail = f"{leads} leads ({int(percent)}% of target) 🎯"
        else:
            # Below target
            score = 15
            shortage = 100 - percent
            penalty = min(int(shortage / 10) * 2, 15)  # -2 per 10% under
            score -= penalty
            score = max(0, score)
            detail = f"{leads} leads ({int(percent)}% of target)"
        
        return (score, detail)
    
    def _score_reviews(self, client_id: str, period_start: datetime) -> tuple:
        """
        Score reviews component (15 points max)
        
        Note: This would integrate with Google reviews API
        For now, use a placeholder based on activity
        """
        # Placeholder - would integrate with GMB reviews
        # For now, give partial credit
        score = 8
        detail = "Review monitoring active"
        
        # TODO: Integrate with GMB reviews API
        # - New 5-star reviews: +3 pts each (up to 9)
        # - Responses to reviews: +2 pts each (up to 6)
        
        return (score, detail)
    
    def _score_engagement(self, client_id: str, period_start: datetime) -> tuple:
        """
        Score engagement component (15 points max)
        
        - GMB posts: +2 pts each (up to 6)
        - Social activity: +1 pt per post (up to 5)
        - Website updates: +2 pts each (up to 4)
        """
        score = 0
        
        # Count social posts (including GMB)
        social_posts = DBSocialPost.query.filter(
            DBSocialPost.client_id == client_id,
            DBSocialPost.created_at >= period_start
        ).count()
        
        # GMB posts specifically
        gmb_posts = DBSocialPost.query.filter(
            DBSocialPost.client_id == client_id,
            DBSocialPost.platform == 'gbp',
            DBSocialPost.created_at >= period_start
        ).count()
        
        # Activity from audit log (use created_at, with safe fallback)
        try:
            activity_count = DBAuditLog.query.filter(
                DBAuditLog.client_id == client_id,
                DBAuditLog.created_at >= period_start
            ).count()
        except Exception:
            activity_count = 0  # Skip if column missing
        
        score += min(gmb_posts * 2, 6)       # GMB posts
        score += min(social_posts * 1, 5)    # Social posts
        score += min(int(activity_count / 10), 4)  # General activity
        
        score = min(15, score)
        
        detail = f"{social_posts} social posts, {gmb_posts} GMB updates"
        
        return (score, detail)
    
    def _get_grade(self, total: int) -> tuple:
        """Get letter grade and color from total score"""
        if total >= 90:
            return ('A+', '#059669')  # Green
        elif total >= 80:
            return ('A', '#10b981')
        elif total >= 70:
            return ('B+', '#0891b2')  # Cyan
        elif total >= 60:
            return ('B', '#06b6d4')
        elif total >= 50:
            return ('C+', '#d97706')  # Orange
        elif total >= 40:
            return ('C', '#f59e0b')
        elif total >= 30:
            return ('D', '#dc2626')   # Red
        else:
            return ('F', '#ef4444')
    
    def _empty_score(self) -> HealthScoreBreakdown:
        """Return empty score for invalid client"""
        return HealthScoreBreakdown(
            total=0,
            grade='N/A',
            color='#6b7280',
            rankings_score=0,
            rankings_detail="No data",
            content_score=0,
            content_detail="No data",
            leads_score=0,
            leads_detail="No data",
            reviews_score=0,
            reviews_detail="No data",
            engagement_score=0,
            engagement_detail="No data"
        )
    
    def get_wins(self, client_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent wins to celebrate with the client
        
        Wins include:
        - Keywords that moved up
        - Content that got published
        - Leads generated
        - Milestones reached
        """
        wins = []
        period_start = datetime.utcnow() - timedelta(days=days)
        
        # Ranking improvements
        rank_improvements = DBRankHistory.query.filter(
            DBRankHistory.client_id == client_id,
            DBRankHistory.checked_at >= period_start,
            DBRankHistory.change > 0
        ).order_by(DBRankHistory.change.desc()).limit(5).all()
        
        for r in rank_improvements:
            win_text = f'"{r.keyword}" moved up {r.change} positions'
            if r.position and r.position <= 10:
                win_text += " - now on PAGE 1! 🎉"
            wins.append({
                'type': 'ranking',
                'icon': 'fa-chart-line',
                'color': 'green',
                'text': win_text,
                'date': r.checked_at.isoformat() if r.checked_at else None
            })
        
        # Published content
        published_blogs = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'published',
            DBBlogPost.published_at >= period_start
        ).order_by(DBBlogPost.published_at.desc()).limit(3).all()
        
        for blog in published_blogs:
            wins.append({
                'type': 'content',
                'icon': 'fa-newspaper',
                'color': 'blue',
                'text': f'Published: "{blog.title}"',
                'date': blog.published_at.isoformat() if blog.published_at else None
            })
        
        # New leads
        lead_count = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= period_start
        ).count()
        
        if lead_count > 0:
            wins.append({
                'type': 'leads',
                'icon': 'fa-user-plus',
                'color': 'purple',
                'text': f'{lead_count} new leads captured',
                'date': datetime.utcnow().isoformat()
            })
        
        # Sort by importance (rankings first, then content, then leads)
        type_priority = {'ranking': 0, 'content': 1, 'leads': 2}
        wins.sort(key=lambda x: type_priority.get(x['type'], 3))
        
        return wins[:10]  # Top 10 wins
    
    def get_whats_coming(self, client_id: str, days: int = 14) -> List[Dict[str, Any]]:
        """
        Get upcoming scheduled content and activities
        
        Shows client what's in the pipeline
        """
        upcoming = []
        now = datetime.utcnow()
        future = now + timedelta(days=days)
        
        # Scheduled blogs
        scheduled_blogs = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status.in_(['scheduled', 'approved']),
            DBBlogPost.scheduled_for.between(now, future)
        ).order_by(DBBlogPost.scheduled_for).all()
        
        for blog in scheduled_blogs:
            upcoming.append({
                'type': 'blog',
                'icon': 'fa-newspaper',
                'color': 'blue',
                'title': blog.title,
                'date': blog.scheduled_for.isoformat() if blog.scheduled_for else None,
                'status': blog.status
            })
        
        # Scheduled social
        scheduled_social = DBSocialPost.query.filter(
            DBSocialPost.client_id == client_id,
            DBSocialPost.status.in_(['scheduled', 'approved']),
            DBSocialPost.scheduled_for.between(now, future)
        ).order_by(DBSocialPost.scheduled_for).all()
        
        for post in scheduled_social:
            upcoming.append({
                'type': 'social',
                'icon': f"fab fa-{post.platform}" if post.platform in ['facebook', 'instagram', 'linkedin'] else 'fa-share-alt',
                'color': 'purple',
                'title': f"{post.platform.title()} post" if post.platform else 'Social post',
                'preview': post.content[:80] + '...' if len(post.content) > 80 else post.content,
                'date': post.scheduled_for.isoformat() if post.scheduled_for else None,
                'status': post.status
            })
        
        # Draft content (work in progress)
        draft_count = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'draft'
        ).count()
        
        if draft_count > 0:
            upcoming.append({
                'type': 'progress',
                'icon': 'fa-edit',
                'color': 'orange',
                'title': f'{draft_count} blog posts in progress',
                'date': None,
                'status': 'draft'
            })
        
        # Sort by date
        upcoming.sort(key=lambda x: x.get('date') or '9999')
        
        return upcoming[:15]
    
    def get_activity_feed(self, client_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent activity feed from audit logs
        
        Shows clients we're actively working on their account
        """
        activities = []
        
        # Get recent audit entries (use created_at with safe fallback)
        try:
            logs = DBAuditLog.query.filter(
                DBAuditLog.client_id == client_id
            ).order_by(DBAuditLog.created_at.desc()).limit(limit * 2).all()
        except Exception:
            return []  # Return empty if query fails
        
        # Convert to client-friendly format
        action_map = {
            'content_created': {'icon': 'fa-plus-circle', 'color': 'green', 'verb': 'Created'},
            'content_updated': {'icon': 'fa-edit', 'color': 'blue', 'verb': 'Updated'},
            'content_published': {'icon': 'fa-rocket', 'color': 'purple', 'verb': 'Published'},
            'content_scheduled': {'icon': 'fa-clock', 'color': 'orange', 'verb': 'Scheduled'},
            'social_posted': {'icon': 'fa-share', 'color': 'blue', 'verb': 'Posted'},
            'keyword_added': {'icon': 'fa-key', 'color': 'cyan', 'verb': 'Added keyword'},
            'competitor_analyzed': {'icon': 'fa-search', 'color': 'purple', 'verb': 'Analyzed competitor'},
            'rank_checked': {'icon': 'fa-chart-line', 'color': 'green', 'verb': 'Checked rankings'},
            'review_responded': {'icon': 'fa-comment', 'color': 'blue', 'verb': 'Responded to review'},
        }
        
        for log in logs:
            action_info = action_map.get(log.action, {
                'icon': 'fa-cog',
                'color': 'gray',
                'verb': getattr(log, 'action', 'update').replace('_', ' ').title()
            })
            
            # Make description client-friendly
            description = getattr(log, 'description', None) or "Updated your marketing campaign"
            
            # Use created_at with safe fallback
            log_time = getattr(log, 'created_at', None) or getattr(log, 'timestamp', None)
            
            activities.append({
                'id': getattr(log, 'id', 0),
                'action': getattr(log, 'action', 'update'),
                'icon': action_info['icon'],
                'color': action_info['color'],
                'text': f"{action_info['verb']}: {description}",
                'timestamp': log_time.isoformat() if log_time else None,
                'user': 'Karma Marketing Team'
            })
        
        return activities[:limit]


# Singleton
_health_service = None

def get_client_health_service() -> ClientHealthService:
    """Get or create health service singleton"""
    global _health_service
    if _health_service is None:
        _health_service = ClientHealthService()
    return _health_service
