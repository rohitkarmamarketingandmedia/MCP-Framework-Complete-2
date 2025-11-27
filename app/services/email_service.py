"""
MCP Framework - Email Service
Handles all email notifications via SendGrid or SMTP
"""
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Try to import sendgrid, fall back to SMTP
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.info("SendGrid not installed, using SMTP fallback")

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class EmailService:
    """Email notification service"""
    
    def __init__(self):
        self.sendgrid_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('EMAIL_FROM', 'noreply@karmamarketing.com')
        self.from_name = os.getenv('EMAIL_FROM_NAME', 'Karma Marketing')
        
        # SMTP fallback settings
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_pass = os.getenv('SMTP_PASS')
        
        # Determine which method to use
        self.use_sendgrid = SENDGRID_AVAILABLE and self.sendgrid_key
        
    def send_simple(self, to: str, subject: str, body: str, html: bool = False) -> bool:
        """Send a simple email"""
        try:
            if self.use_sendgrid:
                return self._send_sendgrid(to, subject, body, html)
            elif self.smtp_user and self.smtp_pass:
                return self._send_smtp(to, subject, body, html)
            else:
                logger.warning(f"Email not configured. Would send to {to}: {subject}")
                return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _send_sendgrid(self, to: str, subject: str, body: str, html: bool) -> bool:
        """Send via SendGrid"""
        message = Mail(
            from_email=Email(self.from_email, self.from_name),
            to_emails=To(to),
            subject=subject,
            plain_text_content=body if not html else None,
            html_content=body if html else None
        )
        
        sg = SendGridAPIClient(self.sendgrid_key)
        response = sg.send(message)
        
        if response.status_code in [200, 201, 202]:
            logger.info(f"Email sent to {to}: {subject}")
            return True
        else:
            logger.error(f"SendGrid error: {response.status_code}")
            return False
    
    def _send_smtp(self, to: str, subject: str, body: str, html: bool) -> bool:
        """Send via SMTP"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{self.from_email}>"
        msg['To'] = to
        
        if html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)
        
        logger.info(f"Email sent to {to}: {subject}")
        return True
    
    def send_alert_digest(self, to: str, alerts: List) -> bool:
        """Send digest of alerts"""
        high_priority = [a for a in alerts if a.priority == 'high']
        other = [a for a in alerts if a.priority != 'high']
        
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #111;">🚨 Alert Digest</h2>
            <p style="color: #666;">{len(alerts)} new alerts require your attention</p>
            
            {'<h3 style="color: #dc2626;">High Priority</h3>' if high_priority else ''}
            {''.join(self._alert_html(a) for a in high_priority)}
            
            {'<h3 style="color: #666;">Other Alerts</h3>' if other else ''}
            {''.join(self._alert_html(a) for a in other)}
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                <a href="{os.getenv('APP_URL', 'https://mcp-framework.onrender.com')}/agency" 
                   style="display: inline-block; padding: 12px 24px; background: #111; color: #fff; text-decoration: none; border-radius: 6px;">
                    View Dashboard →
                </a>
            </div>
        </body>
        </html>
        """
        
        return self.send_simple(to, f"🚨 {len(alerts)} New Alerts", html, html=True)
    
    def _alert_html(self, alert) -> str:
        """Generate HTML for a single alert"""
        border_color = '#dc2626' if alert.priority == 'high' else '#f59e0b'
        return f"""
        <div style="padding: 12px; margin: 8px 0; border-left: 3px solid {border_color}; background: #fafafa;">
            <strong>{alert.title}</strong><br>
            <span style="color: #666; font-size: 14px;">{alert.message}</span>
        </div>
        """
    
    def send_daily_summary(self, to: str, summary: Dict) -> bool:
        """Send daily summary email"""
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #111;">📊 Daily Summary - {summary['date']}</h2>
            
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 15px; background: #f8f8f8; border-radius: 8px 0 0 0;">
                        <div style="font-size: 24px; font-weight: bold;">{summary['total_clients']}</div>
                        <div style="color: #666; font-size: 14px;">Active Clients</div>
                    </td>
                    <td style="padding: 15px; background: #f8f8f8; border-radius: 0 8px 0 0;">
                        <div style="font-size: 24px; font-weight: bold; color: #22c55e;">+{summary['ranking_improvements']}</div>
                        <div style="color: #666; font-size: 14px;">Ranking Wins</div>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 15px; background: #f8f8f8; border-radius: 0 0 0 8px;">
                        <div style="font-size: 24px; font-weight: bold; color: #eab308;">{summary['content_pending']}</div>
                        <div style="color: #666; font-size: 14px;">Content Pending</div>
                    </td>
                    <td style="padding: 15px; background: #f8f8f8; border-radius: 0 0 8px 0;">
                        <div style="font-size: 24px; font-weight: bold;">{summary['content_approved']}</div>
                        <div style="color: #666; font-size: 14px;">Approved Yesterday</div>
                    </td>
                </tr>
            </table>
            
            <div style="margin-top: 30px;">
                <a href="{os.getenv('APP_URL', 'https://mcp-framework.onrender.com')}/agency" 
                   style="display: inline-block; padding: 12px 24px; background: #111; color: #fff; text-decoration: none; border-radius: 6px;">
                    Open Dashboard →
                </a>
            </div>
        </body>
        </html>
        """
        
        return self.send_simple(to, f"📊 Daily Summary - {summary['date']}", html, html=True)
    
    def send_content_ready(self, to: str, client_name: str, content_title: str, content_id: int) -> bool:
        """Notify when counter-content is ready for review"""
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #111;">📝 Content Ready for Review</h2>
            
            <div style="padding: 20px; background: #f8f8f8; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0 0 8px 0;"><strong>Client:</strong> {client_name}</p>
                <p style="margin: 0;"><strong>Title:</strong> {content_title}</p>
            </div>
            
            <p>Counter-content has been generated and is ready for your approval.</p>
            
            <div style="margin-top: 30px;">
                <a href="{os.getenv('APP_URL', 'https://mcp-framework.onrender.com')}/elite" 
                   style="display: inline-block; padding: 12px 24px; background: #111; color: #fff; text-decoration: none; border-radius: 6px;">
                    Review Content →
                </a>
            </div>
        </body>
        </html>
        """
        
        return self.send_simple(to, f"📝 Content Ready: {content_title[:40]}...", html, html=True)
    
    def send_competitor_alert(self, to: str, client_name: str, competitor_name: str, new_pages: int) -> bool:
        """Alert when competitor publishes new content"""
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #dc2626;">🚨 Competitor Alert</h2>
            
            <div style="padding: 20px; background: #fef2f2; border-left: 3px solid #dc2626; margin: 20px 0;">
                <p style="margin: 0 0 8px 0;"><strong>{competitor_name}</strong> just published <strong>{new_pages}</strong> new page(s)</p>
                <p style="margin: 0; color: #666;">Client: {client_name}</p>
            </div>
            
            <p>Counter-content is being generated automatically. You'll be notified when it's ready for review.</p>
            
            <div style="margin-top: 30px;">
                <a href="{os.getenv('APP_URL', 'https://mcp-framework.onrender.com')}/agency" 
                   style="display: inline-block; padding: 12px 24px; background: #dc2626; color: #fff; text-decoration: none; border-radius: 6px;">
                    View Details →
                </a>
            </div>
        </body>
        </html>
        """
        
        return self.send_simple(to, f"🚨 {competitor_name} Published {new_pages} New Pages", html, html=True)
    
    def send_ranking_alert(self, to: str, client_name: str, keyword: str, old_pos: int, new_pos: int) -> bool:
        """Alert when ranking changes significantly"""
        improved = new_pos < old_pos
        emoji = "📈" if improved else "📉"
        color = "#22c55e" if improved else "#dc2626"
        change = abs(new_pos - old_pos)
        direction = "improved" if improved else "dropped"
        
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: {color};">{emoji} Ranking {direction.title()}</h2>
            
            <div style="padding: 20px; background: #f8f8f8; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0 0 8px 0;"><strong>Client:</strong> {client_name}</p>
                <p style="margin: 0 0 8px 0;"><strong>Keyword:</strong> {keyword}</p>
                <p style="margin: 0; font-size: 20px;">
                    <span style="color: #666;">#{old_pos}</span>
                    <span style="color: #666;"> → </span>
                    <span style="color: {color}; font-weight: bold;">#{new_pos}</span>
                    <span style="color: {color};"> ({'+' if improved else '-'}{change})</span>
                </p>
            </div>
            
            <div style="margin-top: 30px;">
                <a href="{os.getenv('APP_URL', 'https://mcp-framework.onrender.com')}/elite" 
                   style="display: inline-block; padding: 12px 24px; background: #111; color: #fff; text-decoration: none; border-radius: 6px;">
                    View Rankings →
                </a>
            </div>
        </body>
        </html>
        """
        
        return self.send_simple(to, f"{emoji} {keyword}: #{old_pos} → #{new_pos}", html, html=True)
    
    def send_wordpress_published(self, to: str, client_name: str, post_title: str, post_url: str) -> bool:
        """Notify when content is published to WordPress"""
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #22c55e;">✅ Content Published</h2>
            
            <div style="padding: 20px; background: #f0fdf4; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0 0 8px 0;"><strong>Client:</strong> {client_name}</p>
                <p style="margin: 0;"><strong>Title:</strong> {post_title}</p>
            </div>
            
            <div style="margin-top: 30px;">
                <a href="{post_url}" 
                   style="display: inline-block; padding: 12px 24px; background: #22c55e; color: #fff; text-decoration: none; border-radius: 6px;">
                    View Live Post →
                </a>
            </div>
        </body>
        </html>
        """
        
        return self.send_simple(to, f"✅ Published: {post_title[:40]}...", html, html=True)


# Singleton instance
_email_service = None

def get_email_service() -> EmailService:
    """Get or create email service instance"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
