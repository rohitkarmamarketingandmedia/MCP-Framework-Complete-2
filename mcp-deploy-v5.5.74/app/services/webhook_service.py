"""
Karma Marketing + Media - Webhook Service
Send outbound webhooks for events
"""
import json
import hmac
import hashlib
import logging
import uuid
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from app.database import db
from app.models.db_models import DBWebhook

logger = logging.getLogger(__name__)

# Thread pool for async webhook delivery
webhook_executor = ThreadPoolExecutor(max_workers=5)


class WebhookService:
    """Service for managing and triggering webhooks"""
    
    # Event types
    EVENT_LEAD_CREATED = 'lead.created'
    EVENT_LEAD_UPDATED = 'lead.updated'
    EVENT_LEAD_CONVERTED = 'lead.converted'
    EVENT_CONTENT_GENERATED = 'content.generated'
    EVENT_CONTENT_PUBLISHED = 'content.published'
    EVENT_CONTENT_APPROVED = 'content.approved'
    EVENT_RANKING_CHANGED = 'ranking.changed'
    EVENT_RANKING_IMPROVED = 'ranking.improved'
    EVENT_RANKING_DROPPED = 'ranking.dropped'
    EVENT_REVIEW_RECEIVED = 'review.received'
    EVENT_COMPETITOR_ALERT = 'competitor.alert'
    EVENT_CLIENT_CREATED = 'client.created'
    
    ALL_EVENTS = [
        EVENT_LEAD_CREATED,
        EVENT_LEAD_UPDATED,
        EVENT_LEAD_CONVERTED,
        EVENT_CONTENT_GENERATED,
        EVENT_CONTENT_PUBLISHED,
        EVENT_CONTENT_APPROVED,
        EVENT_RANKING_CHANGED,
        EVENT_RANKING_IMPROVED,
        EVENT_RANKING_DROPPED,
        EVENT_REVIEW_RECEIVED,
        EVENT_COMPETITOR_ALERT,
        EVENT_CLIENT_CREATED,
    ]
    
    def create_webhook(
        self,
        name: str,
        url: str,
        events: List[str],
        client_id: Optional[str] = None,
        secret: Optional[str] = None
    ) -> Dict:
        """
        Create a new webhook
        
        Args:
            name: Friendly name for the webhook
            url: URL to send webhook payloads to
            events: List of event types to trigger on
            client_id: Optional client ID to scope webhook to
            secret: Optional secret for signing payloads
            
        Returns:
            Created webhook data or error
        """
        try:
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                return {'error': 'URL must start with http:// or https://'}
            
            # Validate events
            invalid_events = [e for e in events if e not in self.ALL_EVENTS]
            if invalid_events:
                return {'error': f'Invalid events: {invalid_events}'}
            
            # Generate secret if not provided
            if not secret:
                secret = f"whsec_{uuid.uuid4().hex}"
            
            webhook = DBWebhook(
                id=f"webhook_{uuid.uuid4().hex[:12]}",
                client_id=client_id,
                name=name,
                url=url,
                secret=secret,
                is_active=True,
                created_at=datetime.utcnow()
            )
            webhook.set_events(events)
            
            db.session.add(webhook)
            db.session.commit()
            
            logger.info(f"Created webhook: {webhook.id} -> {url}")
            
            return {
                'webhook': webhook.to_dict(),
                'secret': secret  # Return secret once on creation
            }
            
        except Exception as e:
            logger.error(f"Failed to create webhook: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    def update_webhook(
        self,
        webhook_id: str,
        name: str = None,
        url: str = None,
        events: List[str] = None,
        is_active: bool = None
    ) -> Dict:
        """Update an existing webhook"""
        try:
            webhook = DBWebhook.query.get(webhook_id)
            if not webhook:
                return {'error': 'Webhook not found'}
            
            if name:
                webhook.name = name
            if url:
                if not url.startswith(('http://', 'https://')):
                    return {'error': 'URL must start with http:// or https://'}
                webhook.url = url
            if events is not None:
                invalid_events = [e for e in events if e not in self.ALL_EVENTS]
                if invalid_events:
                    return {'error': f'Invalid events: {invalid_events}'}
                webhook.set_events(events)
            if is_active is not None:
                webhook.is_active = is_active
            
            webhook.updated_at = datetime.utcnow()
            db.session.commit()
            
            return {'webhook': webhook.to_dict()}
            
        except Exception as e:
            logger.error(f"Failed to update webhook: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    def delete_webhook(self, webhook_id: str) -> Dict:
        """Delete a webhook"""
        try:
            webhook = DBWebhook.query.get(webhook_id)
            if not webhook:
                return {'error': 'Webhook not found'}
            
            db.session.delete(webhook)
            db.session.commit()
            
            logger.info(f"Deleted webhook: {webhook_id}")
            
            return {'message': 'Webhook deleted'}
            
        except Exception as e:
            logger.error(f"Failed to delete webhook: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    def get_webhooks(self, client_id: str = None) -> List[DBWebhook]:
        """Get all webhooks, optionally filtered by client"""
        query = DBWebhook.query
        
        if client_id:
            # Get client-specific and global webhooks
            query = query.filter(
                db.or_(DBWebhook.client_id == client_id, DBWebhook.client_id.is_(None))
            )
        
        return query.order_by(DBWebhook.created_at.desc()).all()
    
    def trigger(
        self,
        event: str,
        data: Dict[str, Any],
        client_id: Optional[str] = None,
        async_delivery: bool = True
    ) -> Dict:
        """
        Trigger webhooks for an event
        
        Args:
            event: Event type (e.g., 'lead.created')
            data: Event payload data
            client_id: Client ID to scope webhooks to
            async_delivery: If True, deliver webhooks in background
            
        Returns:
            Summary of webhooks triggered
        """
        # Find matching webhooks
        query = DBWebhook.query.filter(
            DBWebhook.is_active == True
        )
        
        if client_id:
            query = query.filter(
                db.or_(DBWebhook.client_id == client_id, DBWebhook.client_id.is_(None))
            )
        else:
            query = query.filter(DBWebhook.client_id.is_(None))
        
        webhooks = query.all()
        
        # Filter by event
        matching = [w for w in webhooks if event in w.get_events()]
        
        if not matching:
            return {'triggered': 0, 'webhooks': []}
        
        # Build payload
        payload = {
            'event': event,
            'timestamp': datetime.utcnow().isoformat(),
            'data': data
        }
        if client_id:
            payload['client_id'] = client_id
        
        # Deliver webhooks
        results = []
        for webhook in matching:
            if async_delivery:
                webhook_executor.submit(self._deliver_webhook, webhook.id, payload)
                results.append({'webhook_id': webhook.id, 'status': 'queued'})
            else:
                result = self._deliver_webhook(webhook.id, payload)
                results.append(result)
        
        return {
            'triggered': len(matching),
            'webhooks': results
        }
    
    def _deliver_webhook(self, webhook_id: str, payload: Dict) -> Dict:
        """Deliver a single webhook (internal method)"""
        try:
            # Re-fetch webhook in this thread
            webhook = DBWebhook.query.get(webhook_id)
            if not webhook or not webhook.is_active:
                return {'webhook_id': webhook_id, 'status': 'skipped'}
            
            # Prepare request
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'KarmaMarketing-Webhook/1.0',
                'X-Webhook-Event': payload.get('event', ''),
                'X-Webhook-Timestamp': payload.get('timestamp', ''),
                'X-Webhook-ID': f"{webhook_id}_{datetime.utcnow().timestamp()}"
            }
            
            # Sign payload if secret exists
            if webhook.secret:
                body_bytes = json.dumps(payload).encode('utf-8')
                signature = hmac.new(
                    webhook.secret.encode('utf-8'),
                    body_bytes,
                    hashlib.sha256
                ).hexdigest()
                headers['X-Webhook-Signature'] = f"sha256={signature}"
            
            # Send request with retries
            last_error = None
            success = False
            
            for attempt in range(webhook.retry_count):
                try:
                    response = requests.post(
                        webhook.url,
                        json=payload,
                        headers=headers,
                        timeout=webhook.timeout_seconds
                    )
                    
                    if response.status_code < 400:
                        success = True
                        webhook.total_sent += 1
                        webhook.last_status = 'success'
                        webhook.last_error = None
                        break
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                        
                except requests.exceptions.Timeout:
                    last_error = "Request timeout"
                except requests.exceptions.ConnectionError:
                    last_error = "Connection error"
                except Exception as e:
                    last_error = str(e)
            
            if not success:
                webhook.total_failed += 1
                webhook.last_status = 'failed'
                webhook.last_error = last_error
            
            webhook.last_triggered_at = datetime.utcnow()
            db.session.commit()
            
            return {
                'webhook_id': webhook_id,
                'status': 'success' if success else 'failed',
                'error': last_error if not success else None
            }
            
        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")
            return {
                'webhook_id': webhook_id,
                'status': 'error',
                'error': str(e)
            }
    
    def test_webhook(self, webhook_id: str) -> Dict:
        """Send a test event to a webhook"""
        webhook = DBWebhook.query.get(webhook_id)
        if not webhook:
            return {'error': 'Webhook not found'}
        
        test_payload = {
            'event': 'test',
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'message': 'This is a test webhook from Karma Marketing + Media',
                'webhook_id': webhook_id,
                'webhook_name': webhook.name
            }
        }
        
        return self._deliver_webhook(webhook_id, test_payload)
    
    def get_webhook_stats(self, webhook_id: str = None) -> Dict:
        """Get webhook delivery statistics"""
        if webhook_id:
            webhook = DBWebhook.query.get(webhook_id)
            if not webhook:
                return {'error': 'Webhook not found'}
            
            return {
                'webhook_id': webhook_id,
                'total_sent': webhook.total_sent,
                'total_failed': webhook.total_failed,
                'success_rate': (webhook.total_sent / (webhook.total_sent + webhook.total_failed) * 100) if (webhook.total_sent + webhook.total_failed) > 0 else 0,
                'last_status': webhook.last_status,
                'last_error': webhook.last_error,
                'last_triggered': webhook.last_triggered_at.isoformat() if webhook.last_triggered_at else None
            }
        
        # Global stats
        webhooks = DBWebhook.query.all()
        total_sent = sum(w.total_sent for w in webhooks)
        total_failed = sum(w.total_failed for w in webhooks)
        
        return {
            'total_webhooks': len(webhooks),
            'active_webhooks': sum(1 for w in webhooks if w.is_active),
            'total_sent': total_sent,
            'total_failed': total_failed,
            'success_rate': (total_sent / (total_sent + total_failed) * 100) if (total_sent + total_failed) > 0 else 0
        }


# Singleton instance
webhook_service = WebhookService()


# Convenience functions for triggering webhooks
def trigger_lead_created(lead_data: Dict, client_id: str):
    """Trigger webhook for new lead"""
    webhook_service.trigger(
        WebhookService.EVENT_LEAD_CREATED,
        lead_data,
        client_id
    )


def trigger_lead_converted(lead_data: Dict, client_id: str):
    """Trigger webhook for converted lead"""
    webhook_service.trigger(
        WebhookService.EVENT_LEAD_CONVERTED,
        lead_data,
        client_id
    )


def trigger_content_generated(content_data: Dict, client_id: str):
    """Trigger webhook for generated content"""
    webhook_service.trigger(
        WebhookService.EVENT_CONTENT_GENERATED,
        content_data,
        client_id
    )


def trigger_ranking_changed(ranking_data: Dict, client_id: str, improved: bool):
    """Trigger webhook for ranking change"""
    event = WebhookService.EVENT_RANKING_IMPROVED if improved else WebhookService.EVENT_RANKING_DROPPED
    webhook_service.trigger(event, ranking_data, client_id)
    # Also trigger generic change event
    webhook_service.trigger(WebhookService.EVENT_RANKING_CHANGED, ranking_data, client_id)


def trigger_review_received(review_data: Dict, client_id: str):
    """Trigger webhook for new review"""
    webhook_service.trigger(
        WebhookService.EVENT_REVIEW_RECEIVED,
        review_data,
        client_id
    )
