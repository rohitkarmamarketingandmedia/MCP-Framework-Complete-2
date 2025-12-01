"""
MCP Framework - Lead Capture Service
Handles lead intake, notifications (email/SMS), and tracking
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
import json

from app.database import db
from app.models.db_models import DBLead, DBClient
from app.services.webhook_service import trigger_lead_created, trigger_lead_converted

logger = logging.getLogger(__name__)


class LeadService:
    """Service for capturing and managing leads"""
    
    def __init__(self):
        self.twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_from = os.getenv('TWILIO_FROM_NUMBER')
        self.sendgrid_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'leads@mcpframework.com')
    
    def is_sms_configured(self) -> bool:
        return bool(self.twilio_sid and self.twilio_token and self.twilio_from)
    
    def is_email_configured(self) -> bool:
        return bool(self.sendgrid_key)
    
    # ==========================================
    # Lead CRUD
    # ==========================================
    
    def capture_lead(self, client_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Capture a new lead and trigger notifications
        
        Args:
            client_id: The client this lead belongs to
            lead_data: {
                name: str (required)
                email: str (optional)
                phone: str (optional)
                service_requested: str (optional)
                message: str (optional)
                source: str (default 'form')
                source_detail: str (optional - which form, page, etc)
                landing_page: str (optional)
                utm_source, utm_medium, utm_campaign: str (optional)
            }
        
        Returns:
            {success: bool, lead: dict, notifications: {email: bool, sms: bool}}
        """
        try:
            # Validate client exists
            client = DBClient.query.get(client_id)
            if not client:
                return {'error': f'Client {client_id} not found'}
            
            # Validate required fields
            if not lead_data.get('name'):
                return {'error': 'Name is required'}
            
            if not lead_data.get('email') and not lead_data.get('phone'):
                return {'error': 'Either email or phone is required'}
            
            # Create lead
            lead = DBLead(
                id=f"lead_{uuid.uuid4().hex[:12]}",
                client_id=client_id,
                name=lead_data['name'],
                email=lead_data.get('email'),
                phone=self._normalize_phone(lead_data.get('phone')),
                service_requested=lead_data.get('service_requested'),
                message=lead_data.get('message'),
                source=lead_data.get('source', 'form'),
                source_detail=lead_data.get('source_detail'),
                landing_page=lead_data.get('landing_page'),
                utm_source=lead_data.get('utm_source'),
                utm_medium=lead_data.get('utm_medium'),
                utm_campaign=lead_data.get('utm_campaign'),
                keyword=lead_data.get('keyword'),
                status='new',
                created_at=datetime.utcnow()
            )
            
            db.session.add(lead)
            db.session.commit()
            
            logger.info(f"Lead captured: {lead.id} for client {client_id}")
            
            # Trigger notifications
            notifications = {'email': False, 'sms': False}
            
            if client.lead_notification_enabled:
                # Email notification
                if client.lead_notification_email:
                    email_sent = self._send_lead_email(client, lead)
                    notifications['email'] = email_sent
                    if email_sent:
                        lead.notified_email = True
                
                # SMS notification
                if client.lead_notification_phone:
                    sms_sent = self._send_lead_sms(client, lead)
                    notifications['sms'] = sms_sent
                    if sms_sent:
                        lead.notified_sms = True
                
                if notifications['email'] or notifications['sms']:
                    lead.notified_at = datetime.utcnow()
                    db.session.commit()
            
            return {
                'success': True,
                'lead': lead.to_dict(),
                'notifications': notifications
            }
            
        except Exception as e:
            logger.error(f"Lead capture error: {e}")
            db.session.rollback()
            return {'error': str(e)}
        finally:
            # Trigger webhook asynchronously (won't block response)
            try:
                trigger_lead_created(lead.to_dict(), client_id)
            except Exception as e:
                pass  # Don't let webhook failure affect lead capture
    
    def get_lead(self, lead_id: str) -> Optional[DBLead]:
        """Get a single lead by ID"""
        return DBLead.query.get(lead_id)
    
    def get_client_leads(
        self, 
        client_id: str, 
        status: Optional[str] = None,
        source: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict]:
        """Get leads for a client with optional filters"""
        query = DBLead.query.filter(DBLead.client_id == client_id)
        
        if status:
            query = query.filter(DBLead.status == status)
        
        if source:
            query = query.filter(DBLead.source == source)
        
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query = query.filter(DBLead.created_at >= cutoff)
        
        leads = query.order_by(DBLead.created_at.desc()).limit(limit).all()
        return [l.to_dict() for l in leads]
    
    def update_lead_status(
        self, 
        lead_id: str, 
        status: str, 
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update lead status"""
        lead = DBLead.query.get(lead_id)
        if not lead:
            return {'error': 'Lead not found'}
        
        valid_statuses = ['new', 'contacted', 'qualified', 'converted', 'lost']
        if status not in valid_statuses:
            return {'error': f'Invalid status. Must be one of: {valid_statuses}'}
        
        old_status = lead.status
        lead.status = status
        if notes:
            lead.notes = notes
        
        if status == 'contacted' and not lead.contacted_at:
            lead.contacted_at = datetime.utcnow()
        
        if status == 'converted' and not lead.converted_at:
            lead.converted_at = datetime.utcnow()
        
        lead.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Trigger conversion webhook if newly converted
        if status == 'converted' and old_status != 'converted':
            try:
                trigger_lead_converted(lead.to_dict(), lead.client_id)
            except Exception as e:
                pass  # Don't let webhook failure affect status update
        
        return {'success': True, 'lead': lead.to_dict()}
    
    def set_lead_value(
        self, 
        lead_id: str, 
        estimated_value: Optional[float] = None,
        actual_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """Set monetary value for a lead"""
        lead = DBLead.query.get(lead_id)
        if not lead:
            return {'error': 'Lead not found'}
        
        if estimated_value is not None:
            lead.estimated_value = estimated_value
        
        if actual_value is not None:
            lead.actual_value = actual_value
        
        db.session.commit()
        return {'success': True, 'lead': lead.to_dict()}
    
    # ==========================================
    # Analytics
    # ==========================================
    
    def get_lead_stats(self, client_id: str, days: int = 30) -> Dict[str, Any]:
        """Get lead statistics for a client"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= cutoff
        ).all()
        
        total = len(leads)
        by_status = {}
        by_source = {}
        total_value = 0
        converted_value = 0
        
        for lead in leads:
            # By status
            by_status[lead.status] = by_status.get(lead.status, 0) + 1
            
            # By source
            by_source[lead.source] = by_source.get(lead.source, 0) + 1
            
            # Value
            if lead.estimated_value:
                total_value += lead.estimated_value
            if lead.actual_value and lead.status == 'converted':
                converted_value += lead.actual_value
        
        conversion_rate = (by_status.get('converted', 0) / total * 100) if total > 0 else 0
        
        return {
            'period_days': days,
            'total_leads': total,
            'by_status': by_status,
            'by_source': by_source,
            'conversion_rate': round(conversion_rate, 1),
            'total_estimated_value': total_value,
            'converted_value': converted_value,
            'avg_lead_value': round(total_value / total, 2) if total > 0 else 0
        }
    
    def get_lead_trends(self, client_id: str, days: int = 30) -> List[Dict]:
        """Get daily lead counts for trending"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        leads = DBLead.query.filter(
            DBLead.client_id == client_id,
            DBLead.created_at >= cutoff
        ).all()
        
        # Group by date
        daily = {}
        for lead in leads:
            date_str = lead.created_at.strftime('%Y-%m-%d')
            if date_str not in daily:
                daily[date_str] = {'date': date_str, 'count': 0, 'converted': 0}
            daily[date_str]['count'] += 1
            if lead.status == 'converted':
                daily[date_str]['converted'] += 1
        
        # Fill in missing days
        result = []
        current = cutoff
        while current <= datetime.utcnow():
            date_str = current.strftime('%Y-%m-%d')
            if date_str in daily:
                result.append(daily[date_str])
            else:
                result.append({'date': date_str, 'count': 0, 'converted': 0})
            current += timedelta(days=1)
        
        return result
    
    # ==========================================
    # Notifications
    # ==========================================
    
    def _send_lead_email(self, client: DBClient, lead: DBLead) -> bool:
        """Send email notification for new lead"""
        if not self.is_email_configured():
            logger.warning("Email not configured, skipping lead notification")
            return False
        
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            sg = sendgrid.SendGridAPIClient(api_key=self.sendgrid_key)
            
            subject = f"🔥 New Lead: {lead.name} - {lead.service_requested or 'General Inquiry'}"
            
            body = f"""
New lead received for {client.business_name}!

CONTACT INFO
Name: {lead.name}
Phone: {lead.phone or 'Not provided'}
Email: {lead.email or 'Not provided'}

SERVICE REQUESTED
{lead.service_requested or 'Not specified'}

MESSAGE
{lead.message or 'No message'}

SOURCE
{lead.source}{f' ({lead.source_detail})' if lead.source_detail else ''}
Landing Page: {lead.landing_page or 'Not tracked'}

---
Respond quickly! Studies show responding within 5 minutes increases conversion by 900%.

Lead ID: {lead.id}
Received: {lead.created_at.strftime('%B %d, %Y at %I:%M %p')}
            """
            
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(client.lead_notification_email),
                subject=subject,
                plain_text_content=Content("text/plain", body)
            )
            
            response = sg.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"Lead email sent to {client.lead_notification_email}")
                return True
            else:
                logger.error(f"Email send failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Email notification error: {e}")
            return False
    
    def _send_lead_sms(self, client: DBClient, lead: DBLead) -> bool:
        """Send SMS notification for new lead"""
        if not self.is_sms_configured():
            logger.warning("Twilio not configured, skipping SMS notification")
            return False
        
        try:
            from twilio.rest import Client
            
            twilio = Client(self.twilio_sid, self.twilio_token)
            
            message_body = f"""🔥 NEW LEAD - {client.business_name}

{lead.name}
{lead.phone or lead.email}
Service: {lead.service_requested or 'General'}

Respond within 5 min for best results!"""
            
            message = twilio.messages.create(
                body=message_body,
                from_=self.twilio_from,
                to=client.lead_notification_phone
            )
            
            logger.info(f"Lead SMS sent: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"SMS notification error: {e}")
            return False
    
    def send_auto_response(self, lead: DBLead, client: DBClient) -> bool:
        """Send auto-response to the lead"""
        if not lead.email or not self.is_email_configured():
            return False
        
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            sg = sendgrid.SendGridAPIClient(api_key=self.sendgrid_key)
            
            subject = f"Thank you for contacting {client.business_name}!"
            
            body = f"""Hi {lead.name.split()[0]},

Thank you for reaching out to {client.business_name}! We've received your inquiry and will get back to you shortly.

{f"You mentioned you're interested in {lead.service_requested}. " if lead.service_requested else ""}We typically respond within a few hours during business hours.

In the meantime, feel free to call us at {client.phone or 'our office'} if you need immediate assistance.

Best regards,
The {client.business_name} Team

---
This is an automated response. A member of our team will follow up personally.
            """
            
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(lead.email),
                subject=subject,
                plain_text_content=Content("text/plain", body)
            )
            
            response = sg.send(message)
            return response.status_code in [200, 202]
            
        except Exception as e:
            logger.error(f"Auto-response error: {e}")
            return False
    
    # ==========================================
    # Utilities
    # ==========================================
    
    def _normalize_phone(self, phone: Optional[str]) -> Optional[str]:
        """Normalize phone number format"""
        if not phone:
            return None
        
        # Remove all non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        
        # Handle US numbers
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        
        return phone  # Return as-is if not standard format
    
    def generate_form_embed(self, client_id: str, form_config: Dict = None) -> str:
        """Generate embeddable form HTML"""
        config = form_config or {}
        
        form_id = f"mcp-form-{client_id[:8]}"
        api_endpoint = config.get('api_endpoint', '/api/leads/capture')
        
        fields = config.get('fields', ['name', 'phone', 'email', 'service', 'message'])
        services = config.get('services', [])
        button_text = config.get('button_text', 'Get Free Quote')
        button_color = config.get('button_color', '#2563eb')
        success_message = config.get('success_message', 'Thank you! We\'ll contact you shortly.')
        
        # Build service options
        service_options = '\n'.join([
            f'<option value="{s}">{s}</option>' for s in services
        ]) if services else ''
        
        html = f'''
<!-- MCP Lead Capture Form -->
<div id="{form_id}" class="mcp-lead-form">
    <style>
        #{form_id} {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 400px;
            margin: 0 auto;
        }}
        #{form_id} .mcp-form-group {{
            margin-bottom: 16px;
        }}
        #{form_id} label {{
            display: block;
            font-weight: 500;
            margin-bottom: 6px;
            color: #374151;
        }}
        #{form_id} input, #{form_id} select, #{form_id} textarea {{
            width: 100%;
            padding: 12px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 16px;
            box-sizing: border-box;
        }}
        #{form_id} input:focus, #{form_id} select:focus, #{form_id} textarea:focus {{
            outline: none;
            border-color: {button_color};
            box-shadow: 0 0 0 3px {button_color}33;
        }}
        #{form_id} button {{
            width: 100%;
            padding: 14px 24px;
            background: {button_color};
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }}
        #{form_id} button:hover {{
            background: {button_color}dd;
        }}
        #{form_id} button:disabled {{
            background: #9ca3af;
            cursor: not-allowed;
        }}
        #{form_id} .mcp-success {{
            background: #ecfdf5;
            border: 1px solid #10b981;
            color: #065f46;
            padding: 16px;
            border-radius: 8px;
            text-align: center;
        }}
        #{form_id} .mcp-error {{
            background: #fef2f2;
            border: 1px solid #ef4444;
            color: #991b1b;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 16px;
        }}
    </style>
    
    <form id="{form_id}-form" onsubmit="return mcpSubmitForm_{client_id[:8]}(event)">
        <div id="{form_id}-error" class="mcp-error" style="display:none;"></div>
        
        {'<div class="mcp-form-group"><label>Name *</label><input type="text" name="name" required></div>' if 'name' in fields else ''}
        
        {'<div class="mcp-form-group"><label>Phone *</label><input type="tel" name="phone" required></div>' if 'phone' in fields else ''}
        
        {'<div class="mcp-form-group"><label>Email</label><input type="email" name="email"></div>' if 'email' in fields else ''}
        
        {f'<div class="mcp-form-group"><label>Service Needed</label><select name="service_requested"><option value="">Select a service...</option>{service_options}</select></div>' if 'service' in fields and services else ''}
        
        {'<div class="mcp-form-group"><label>Message</label><textarea name="message" rows="3"></textarea></div>' if 'message' in fields else ''}
        
        <button type="submit" id="{form_id}-btn">{button_text}</button>
    </form>
    
    <div id="{form_id}-success" class="mcp-success" style="display:none;">
        {success_message}
    </div>
    
    <script>
        function mcpSubmitForm_{client_id[:8]}(e) {{
            e.preventDefault();
            
            var form = document.getElementById('{form_id}-form');
            var btn = document.getElementById('{form_id}-btn');
            var error = document.getElementById('{form_id}-error');
            var success = document.getElementById('{form_id}-success');
            
            var data = {{
                client_id: '{client_id}',
                name: form.name ? form.name.value : '',
                phone: form.phone ? form.phone.value : '',
                email: form.email ? form.email.value : '',
                service_requested: form.service_requested ? form.service_requested.value : '',
                message: form.message ? form.message.value : '',
                source: 'form',
                source_detail: 'embed',
                landing_page: window.location.href
            }};
            
            btn.disabled = true;
            btn.textContent = 'Sending...';
            error.style.display = 'none';
            
            fetch('{api_endpoint}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(data)
            }})
            .then(function(r) {{ return r.json(); }})
            .then(function(result) {{
                if (result.success) {{
                    form.style.display = 'none';
                    success.style.display = 'block';
                }} else {{
                    error.textContent = result.error || 'Something went wrong. Please try again.';
                    error.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = '{button_text}';
                }}
            }})
            .catch(function(err) {{
                error.textContent = 'Network error. Please try again.';
                error.style.display = 'block';
                btn.disabled = false;
                btn.textContent = '{button_text}';
            }});
            
            return false;
        }}
    </script>
</div>
'''
        return html


# Global instance
lead_service = LeadService()
