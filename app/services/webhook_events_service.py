"""
MCP Framework - Webhook Events Service
Fires webhooks to external systems (N8N, Zapier, etc.) when events occur

This is the BRIDGE between MCP (the brain) and N8N (the hands)

Events fired:
- content.approved      → Blog/content approved, ready to publish
- content.published     → Content published to WordPress
- lead.created          → New lead from form/chatbot
- lead.qualified        → Lead marked as qualified
- call.received         → New call from CallRail
- call.transcribed      → Call transcript ready
- client.onboarded      → New client setup complete
- report.generated      → Client report ready
- alert.triggered       → Something needs attention
"""
import os
import json
import logging
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import requests
from concurrent.futures import ThreadPoolExecutor

from app.database import db

logger = logging.getLogger(__name__)

# Thread pool for async webhook delivery
_executor = ThreadPoolExecutor(max_workers=5)


@dataclass
class WebhookEvent:
    """A webhook event to be fired"""
    event_type: str
    payload: Dict[str, Any]
    timestamp: str = None
    event_id: str = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        if not self.event_id:
            import uuid
            self.event_id = f"evt_{uuid.uuid4().hex[:16]}"
    
    def to_dict(self) -> Dict:
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'timestamp': self.timestamp,
            'payload': self.payload
        }


class WebhookEventsService:
    """
    Service to fire webhooks when events occur in MCP
    
    Configure webhook URLs in environment or database:
    - WEBHOOK_URL_DEFAULT: Catch-all webhook URL
    - WEBHOOK_URL_CONTENT: Content events
    - WEBHOOK_URL_LEADS: Lead events
    - WEBHOOK_URL_CALLS: Call events
    - WEBHOOK_SECRET: HMAC secret for signing
    
    Or configure per-client in database.
    """
    
    # Event type to URL mapping
    EVENT_CATEGORIES = {
        'content.approved': 'content',
        'content.published': 'content',
        'content.rejected': 'content',
        'content.scheduled': 'content',
        'lead.created': 'leads',
        'lead.qualified': 'leads',
        'lead.converted': 'leads',
        'call.received': 'calls',
        'call.transcribed': 'calls',
        'call.analyzed': 'calls',
        'client.onboarded': 'default',
        'client.updated': 'default',
        'report.generated': 'default',
        'alert.triggered': 'default',
    }
    
    def __init__(self):
        self.default_url = os.environ.get('WEBHOOK_URL_DEFAULT', '')
        self.content_url = os.environ.get('WEBHOOK_URL_CONTENT', '')
        self.leads_url = os.environ.get('WEBHOOK_URL_LEADS', '')
        self.calls_url = os.environ.get('WEBHOOK_URL_CALLS', '')
        self.secret = os.environ.get('WEBHOOK_SECRET', '')
        
        # Track if webhooks are configured
        self.is_configured = bool(self.default_url or self.content_url or self.leads_url or self.calls_url)
    
    def _get_webhook_url(self, event_type: str, client_id: str = None) -> Optional[str]:
        """Get the webhook URL for an event type"""
        # Check for client-specific webhook first
        if client_id:
            from app.models.db_models import DBClient
            client = DBClient.query.get(client_id)
            if client and hasattr(client, 'webhook_url') and client.webhook_url:
                return client.webhook_url
        
        # Fall back to category-specific URL
        category = self.EVENT_CATEGORIES.get(event_type, 'default')
        
        url_map = {
            'content': self.content_url,
            'leads': self.leads_url,
            'calls': self.calls_url,
            'default': self.default_url
        }
        
        url = url_map.get(category) or self.default_url
        return url if url else None
    
    def _sign_payload(self, payload: str) -> str:
        """Create HMAC signature for payload"""
        if not self.secret:
            return ''
        
        signature = hmac.new(
            self.secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    def _send_webhook(self, url: str, event: WebhookEvent) -> bool:
        """Send webhook to URL"""
        try:
            payload = json.dumps(event.to_dict())
            
            headers = {
                'Content-Type': 'application/json',
                'X-MCP-Event': event.event_type,
                'X-MCP-Event-ID': event.event_id,
                'X-MCP-Timestamp': event.timestamp,
            }
            
            # Add signature if secret configured
            if self.secret:
                headers['X-MCP-Signature'] = self._sign_payload(payload)
            
            response = requests.post(
                url,
                data=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Webhook delivered: {event.event_type} to {url}")
                return True
            else:
                logger.warning(f"Webhook failed: {event.event_type} to {url} - {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Webhook error: {event.event_type} to {url} - {e}")
            return False
    
    def fire(self, event_type: str, payload: Dict[str, Any], client_id: str = None, async_send: bool = True) -> bool:
        """
        Fire a webhook event
        
        Args:
            event_type: Type of event (e.g., 'content.approved')
            payload: Event data
            client_id: Optional client ID for client-specific webhooks
            async_send: If True, send in background thread
        
        Returns:
            True if webhook was queued/sent, False if no URL configured
        """
        url = self._get_webhook_url(event_type, client_id)
        
        if not url:
            logger.debug(f"No webhook URL for event: {event_type}")
            return False
        
        # Add client_id to payload if provided
        if client_id:
            payload['client_id'] = client_id
        
        event = WebhookEvent(event_type=event_type, payload=payload)
        
        # Log the event
        self._log_event(event, url)
        
        if async_send:
            # Send in background
            _executor.submit(self._send_webhook, url, event)
            return True
        else:
            # Send synchronously
            return self._send_webhook(url, event)
    
    def _log_event(self, event: WebhookEvent, url: str):
        """Log webhook event to database for debugging"""
        try:
            from app.models.db_models import DBWebhookLog
            
            log = DBWebhookLog(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=json.dumps(event.payload),
                url=url,
                status='queued'
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            # Don't fail if logging fails
            logger.warning(f"Could not log webhook event: {e}")
    
    # ==========================================
    # CONVENIENCE METHODS FOR COMMON EVENTS
    # ==========================================
    
    def content_approved(self, content_id: str, content_type: str, client_id: str, data: Dict = None):
        """Fire when content is approved and ready to publish"""
        payload = {
            'content_id': content_id,
            'content_type': content_type,  # 'blog', 'social', 'page'
            'action': 'approved',
            **(data or {})
        }
        return self.fire('content.approved', payload, client_id)
    
    def content_published(self, content_id: str, content_type: str, client_id: str, url: str = None, data: Dict = None):
        """Fire when content is published"""
        payload = {
            'content_id': content_id,
            'content_type': content_type,
            'action': 'published',
            'published_url': url,
            **(data or {})
        }
        return self.fire('content.published', payload, client_id)
    
    def lead_created(self, lead_id: str, client_id: str, source: str, data: Dict = None):
        """Fire when new lead is created"""
        payload = {
            'lead_id': lead_id,
            'source': source,  # 'form', 'chatbot', 'call', 'manual'
            **(data or {})
        }
        return self.fire('lead.created', payload, client_id)
    
    def lead_qualified(self, lead_id: str, client_id: str, score: int = None, data: Dict = None):
        """Fire when lead is marked as qualified"""
        payload = {
            'lead_id': lead_id,
            'qualified': True,
            'score': score,
            **(data or {})
        }
        return self.fire('lead.qualified', payload, client_id)
    
    def call_received(self, call_id: str, client_id: str, caller: str, duration: int, data: Dict = None):
        """Fire when call is received from CallRail"""
        payload = {
            'call_id': call_id,
            'caller': caller,
            'duration_seconds': duration,
            'source': 'callrail',
            **(data or {})
        }
        return self.fire('call.received', payload, client_id)
    
    def call_transcribed(self, call_id: str, client_id: str, transcript: str, data: Dict = None):
        """Fire when call transcript is ready"""
        payload = {
            'call_id': call_id,
            'transcript_preview': transcript[:500] if transcript else '',
            'has_full_transcript': bool(transcript),
            **(data or {})
        }
        return self.fire('call.transcribed', payload, client_id)
    
    def client_onboarded(self, client_id: str, client_name: str, data: Dict = None):
        """Fire when new client is fully onboarded"""
        payload = {
            'client_name': client_name,
            'action': 'onboarded',
            **(data or {})
        }
        return self.fire('client.onboarded', payload, client_id)
    
    def report_generated(self, report_type: str, client_id: str, report_url: str = None, data: Dict = None):
        """Fire when client report is generated"""
        payload = {
            'report_type': report_type,  # '3day_snapshot', 'monthly', 'seo_audit'
            'report_url': report_url,
            **(data or {})
        }
        return self.fire('report.generated', payload, client_id)
    
    def alert_triggered(self, alert_type: str, client_id: str, message: str, severity: str = 'warning', data: Dict = None):
        """Fire when an alert needs attention"""
        payload = {
            'alert_type': alert_type,
            'message': message,
            'severity': severity,  # 'info', 'warning', 'critical'
            **(data or {})
        }
        return self.fire('alert.triggered', payload, client_id)


# Singleton
_webhook_service = None

def get_webhook_events_service() -> WebhookEventsService:
    """Get or create webhook events service singleton"""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookEventsService()
    return _webhook_service


# ==========================================
# EASY IMPORT FUNCTIONS
# ==========================================

def fire_webhook(event_type: str, payload: Dict, client_id: str = None) -> bool:
    """Quick function to fire a webhook"""
    return get_webhook_events_service().fire(event_type, payload, client_id)

def fire_content_approved(content_id: str, content_type: str, client_id: str, **data) -> bool:
    """Quick function for content approved event"""
    return get_webhook_events_service().content_approved(content_id, content_type, client_id, data)

def fire_lead_created(lead_id: str, client_id: str, source: str, **data) -> bool:
    """Quick function for lead created event"""
    return get_webhook_events_service().lead_created(lead_id, client_id, source, data)

def fire_call_received(call_id: str, client_id: str, caller: str, duration: int, **data) -> bool:
    """Quick function for call received event"""
    return get_webhook_events_service().call_received(call_id, client_id, caller, duration, data)
