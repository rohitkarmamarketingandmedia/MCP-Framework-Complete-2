"""
MCP Framework - Client Report Service
Generates and sends 3-day "snapshot" reports that make clients feel valued

The goal: Make every client think "These people are WORKING for me!"
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from app.database import db
from app.models.db_models import DBClient, DBUser, DBLead
from app.services.client_health_service import get_client_health_service
from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)


class ClientReportService:
    """
    Generate and send client reports at configurable intervals
    
    Report types:
    - 3-day snapshot: Quick wins, needs attention, what's coming
    - Weekly summary: Comprehensive metrics
    - Monthly report: Full performance analysis
    """
    
    def __init__(self):
        self.health_service = get_client_health_service()
        self.email_service = get_email_service()
    
    def generate_3day_snapshot(self, client_id: str) -> Dict[str, Any]:
        """
        Generate the 3-day snapshot report data
        
        Sections:
        1. Health Score
        2. The Wins (what's working)
        3. Needs Attention (what we're fixing)
        4. What We're Doing (activity)
        5. Coming Up (scheduled content)
        6. Lead Summary (calls + forms)
        """
        client = DBClient.query.get(client_id)
        if not client:
            return {'error': 'Client not found'}
        
        # Get health score
        health = self.health_service.calculate_health_score(client_id, days=7)
        
        # Get wins (last 3 days)
        wins = self.health_service.get_wins(client_id, days=3)
        
        # Get what's coming
        upcoming = self.health_service.get_whats_coming(client_id, days=7)
        
        # Get activity feed
        activity = self.health_service.get_activity_feed(client_id, limit=10)
        
        # Get lead summary
        lead_summary = self._get_lead_summary(client_id, days=3)
        
        # Get needs attention items
        needs_attention = self._get_needs_attention(client_id)
        
        # Get call metrics if CallRail configured
        call_metrics = self._get_call_metrics(client_id, days=3)
        
        return {
            'client': {
                'id': client_id,
                'name': client.business_name,
                'industry': client.industry
            },
            'period': {
                'days': 3,
                'start': (datetime.utcnow() - timedelta(days=3)).isoformat(),
                'end': datetime.utcnow().isoformat()
            },
            'health_score': health.to_dict(),
            'wins': wins,
            'needs_attention': needs_attention,
            'activity': activity,
            'upcoming': upcoming,
            'leads': lead_summary,
            'calls': call_metrics,
            'generated_at': datetime.utcnow().isoformat()
        }
    
    def _get_lead_summary(self, client_id: str, days: int = 3) -> Dict[str, Any]:
        """Get lead summary for period"""
        period_start = datetime.utcnow() - timedelta(days=days)
        
        # Get leads
        leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= period_start
        ).all()
        
        total = len(leads)
        by_source = {}
        by_status = {}
        
        for lead in leads:
            source = lead.source or 'Direct'
            by_source[source] = by_source.get(source, 0) + 1
            
            status = lead.status or 'new'
            by_status[status] = by_status.get(status, 0) + 1
        
        # Previous period for comparison
        prev_start = period_start - timedelta(days=days)
        prev_leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at.between(prev_start, period_start)
        ).count()
        
        trend = 0
        if prev_leads > 0:
            trend = round(((total - prev_leads) / prev_leads) * 100)
        
        return {
            'total': total,
            'trend': trend,
            'by_source': by_source,
            'by_status': by_status,
            'form_submissions': by_source.get('form', 0) + by_source.get('website', 0),
            'period_days': days
        }
    
    def _get_call_metrics(self, client_id: str, days: int = 3) -> Optional[Dict[str, Any]]:
        """Get call metrics if CallRail is configured"""
        try:
            from app.services.callrail_service import CallRailConfig, get_callrail_service
            
            if not CallRailConfig.is_configured():
                return None
            
            callrail = get_callrail_service()
            
            # Get client's CallRail company ID
            client = DBClient.query.get(client_id)
            callrail_company_id = None
            
            if client:
                # Try to get from client settings
                callrail_company_id = getattr(client, 'callrail_company_id', None)
                
                # Or try to match by name
                if not callrail_company_id:
                    company = callrail.get_company_by_name(client.business_name)
                    if company:
                        callrail_company_id = company.get('id')
            
            if callrail_company_id:
                return callrail.get_client_call_metrics(callrail_company_id, days=days)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting CallRail metrics: {e}")
            return None
    
    def _get_needs_attention(self, client_id: str) -> List[Dict[str, Any]]:
        """
        Identify items that need attention
        
        Be honest but constructive - show we're on top of things
        """
        issues = []
        
        # Check for ranking drops
        from app.models.db_models import DBRankHistory
        period_start = datetime.utcnow() - timedelta(days=7)
        
        drops = DBRankHistory.query.filter(
            DBRankHistory.client_id == client_id,
            DBRankHistory.checked_at >= period_start,
            DBRankHistory.change < -3  # Significant drop
        ).all()
        
        for drop in drops[:3]:  # Max 3 issues
            issues.append({
                'type': 'ranking_drop',
                'severity': 'warning',
                'icon': 'fa-arrow-down',
                'text': f'"{drop.keyword}" dropped {abs(drop.change)} spots',
                'action': 'We\'re optimizing content to recover'
            })
        
        # Check for missed leads (if we have call data)
        # This would come from CallRail missed calls
        
        # Check for overdue content
        from app.models.db_models import DBBlogPost
        overdue = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'scheduled',
            DBBlogPost.scheduled_for < datetime.utcnow()
        ).count()
        
        if overdue > 0:
            issues.append({
                'type': 'overdue_content',
                'severity': 'info',
                'icon': 'fa-clock',
                'text': f'{overdue} scheduled posts pending',
                'action': 'Publishing queue being processed'
            })
        
        # Check for content needing approval
        pending_approval = DBBlogPost.query.filter(
            DBBlogPost.client_id == client_id,
            DBBlogPost.status == 'pending_approval'
        ).count()
        
        if pending_approval > 0:
            issues.append({
                'type': 'needs_approval',
                'severity': 'info',
                'icon': 'fa-clipboard-check',
                'text': f'{pending_approval} items waiting for your approval',
                'action': 'Review in your portal'
            })
        
        return issues
    
    def generate_report_email_html(self, report_data: Dict[str, Any]) -> str:
        """
        Generate beautiful HTML email for the 3-day snapshot
        """
        client_name = report_data['client']['name']
        health = report_data['health_score']
        wins = report_data['wins']
        needs_attention = report_data['needs_attention']
        activity = report_data['activity']
        upcoming = report_data['upcoming']
        leads = report_data['leads']
        calls = report_data.get('calls')
        
        # Build wins section
        wins_html = ""
        for win in wins[:5]:
            wins_html += f"""
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                        <span style="color: #10b981;">✓</span> {win['text']}
                    </td>
                </tr>
            """
        
        if not wins:
            wins_html = """
                <tr>
                    <td style="padding: 12px; color: #64748b;">
                        Building momentum - wins coming soon!
                    </td>
                </tr>
            """
        
        # Build attention section
        attention_html = ""
        for item in needs_attention[:3]:
            attention_html += f"""
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                        <span style="color: #f59e0b;">⚠</span> {item['text']}
                        <br><span style="color: #64748b; font-size: 12px;">{item['action']}</span>
                    </td>
                </tr>
            """
        
        if not needs_attention:
            attention_html = """
                <tr>
                    <td style="padding: 12px; color: #10b981;">
                        ✓ Everything looks good!
                    </td>
                </tr>
            """
        
        # Build activity section
        activity_html = ""
        for act in activity[:5]:
            activity_html += f"""
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">
                        {act['text']}
                    </td>
                </tr>
            """
        
        # Build upcoming section
        upcoming_html = ""
        for item in upcoming[:5]:
            date_str = ""
            if item.get('date'):
                date = datetime.fromisoformat(item['date'].replace('Z', '+00:00'))
                date_str = date.strftime('%b %d')
            upcoming_html += f"""
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">
                        <span style="color: #64748b;">{date_str}</span> {item['title']}
                    </td>
                </tr>
            """
        
        # Lead/call stats
        lead_total = leads.get('total', 0)
        lead_trend = leads.get('trend', 0)
        trend_icon = "↑" if lead_trend > 0 else "↓" if lead_trend < 0 else "→"
        trend_color = "#10b981" if lead_trend > 0 else "#ef4444" if lead_trend < 0 else "#64748b"
        
        call_html = ""
        if calls:
            call_html = f"""
                <td style="padding: 20px; text-align: center; background: #f8fafc; border-radius: 12px;">
                    <div style="font-size: 32px; font-weight: bold; color: #1e293b;">{calls.get('total_calls', 0)}</div>
                    <div style="color: #64748b; font-size: 14px;">Phone Calls</div>
                    <div style="color: #10b981; font-size: 12px; margin-top: 4px;">
                        {calls.get('answered', 0)} answered ({calls.get('answer_rate', 0)}%)
                    </div>
                </td>
            """
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); padding: 32px; text-align: center;">
            <h1 style="color: white; margin: 0 0 8px; font-size: 24px;">📊 Your 3-Day Snapshot</h1>
            <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 14px;">{client_name}</p>
        </div>
        
        <!-- Health Score -->
        <div style="padding: 24px; text-align: center; border-bottom: 1px solid #e2e8f0;">
            <div style="display: inline-block; width: 100px; height: 100px; border-radius: 50%; background: linear-gradient(135deg, {health['color']}20, {health['color']}40); border: 4px solid {health['color']}; line-height: 92px;">
                <span style="font-size: 36px; font-weight: bold; color: {health['color']};">{health['total']}</span>
            </div>
            <div style="margin-top: 12px;">
                <span style="background: {health['color']}20; color: {health['color']}; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 14px;">
                    {health['grade']} - {'Excellent' if health['total'] >= 80 else 'Good' if health['total'] >= 60 else 'Improving'}
                </span>
            </div>
        </div>
        
        <!-- Lead Stats -->
        <div style="padding: 24px; border-bottom: 1px solid #e2e8f0;">
            <table width="100%" cellpadding="0" cellspacing="16">
                <tr>
                    <td style="padding: 20px; text-align: center; background: #f8fafc; border-radius: 12px;">
                        <div style="font-size: 32px; font-weight: bold; color: #1e293b;">{lead_total}</div>
                        <div style="color: #64748b; font-size: 14px;">New Leads</div>
                        <div style="color: {trend_color}; font-size: 12px; margin-top: 4px;">{trend_icon} {abs(lead_trend)}% vs last period</div>
                    </td>
                    {call_html}
                </tr>
            </table>
        </div>
        
        <!-- The Wins -->
        <div style="padding: 24px; border-bottom: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 16px; font-size: 18px; color: #1e293b;">🏆 The Wins</h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f0fdf4; border-radius: 8px;">
                {wins_html}
            </table>
        </div>
        
        <!-- Needs Attention -->
        <div style="padding: 24px; border-bottom: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 16px; font-size: 18px; color: #1e293b;">⚠️ Needs Attention</h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #fffbeb; border-radius: 8px;">
                {attention_html}
            </table>
        </div>
        
        <!-- What We're Doing -->
        <div style="padding: 24px; border-bottom: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 16px; font-size: 18px; color: #1e293b;">🔧 What We're Doing</h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f8fafc; border-radius: 8px;">
                {activity_html}
            </table>
        </div>
        
        <!-- Coming Up -->
        <div style="padding: 24px; border-bottom: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 16px; font-size: 18px; color: #1e293b;">📅 Coming Up</h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="background: #f8fafc; border-radius: 8px;">
                {upcoming_html}
            </table>
        </div>
        
        <!-- CTA -->
        <div style="padding: 32px; text-align: center; background: #f8fafc;">
            <a href="#" style="display: inline-block; background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                View Full Dashboard →
            </a>
            <p style="margin: 16px 0 0; color: #64748b; font-size: 13px;">
                Questions? Reply to this email or call us anytime.
            </p>
        </div>
        
        <!-- Footer -->
        <div style="padding: 24px; text-align: center; background: #1e293b; color: rgba(255,255,255,0.6); font-size: 12px;">
            <p style="margin: 0;">Karma Marketing + Media</p>
            <p style="margin: 8px 0 0;">Working hard to grow your business 💪</p>
        </div>
        
    </div>
</body>
</html>
        """
        
        return html
    
    def send_3day_report(self, client_id: str, recipient_email: str = None) -> bool:
        """
        Generate and send the 3-day snapshot report
        
        Args:
            client_id: The client ID
            recipient_email: Override email (otherwise uses client contact)
        
        Returns:
            True if sent successfully
        """
        try:
            # Generate report
            report = self.generate_3day_snapshot(client_id)
            
            if 'error' in report:
                logger.error(f"Error generating report: {report['error']}")
                return False
            
            # Generate email HTML
            html = self.generate_report_email_html(report)
            
            # Get recipient
            if not recipient_email:
                client = DBClient.query.get(client_id)
                recipient_email = client.email if client else None
            
            if not recipient_email:
                logger.warning(f"No email for client {client_id}")
                return False
            
            # Send email
            success = self.email_service.send_email(
                to_email=recipient_email,
                subject=f"📊 Your 3-Day Marketing Snapshot | {report['client']['name']}",
                html_content=html,
                text_content=f"View your marketing snapshot at your client portal."
            )
            
            if success:
                logger.info(f"Sent 3-day report to {recipient_email} for client {client_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending 3-day report: {e}")
            return False
    
    def send_all_3day_reports(self) -> Dict[str, int]:
        """
        Send 3-day reports to all active clients
        
        Called by scheduler every 3 days
        """
        sent = 0
        failed = 0
        
        # Get all active clients
        clients = DBClient.query.filter_by(status='active').all()
        
        for client in clients:
            if client.email:
                success = self.send_3day_report(client.id)
                if success:
                    sent += 1
                else:
                    failed += 1
        
        logger.info(f"3-day reports: {sent} sent, {failed} failed")
        return {'sent': sent, 'failed': failed}


# Singleton
_report_service = None

def get_client_report_service() -> ClientReportService:
    """Get or create report service singleton"""
    global _report_service
    if _report_service is None:
        _report_service = ClientReportService()
    return _report_service
