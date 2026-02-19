"""
Wufoo Form Integration Service
Fetches form submissions from Wufoo API and imports them as leads
"""
import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from base64 import b64encode

logger = logging.getLogger(__name__)


class WufooService:
    """
    Connects to Wufoo REST API to pull form entries
    
    Config per client (stored in client.integrations JSON):
    {
        "wufoo": {
            "subdomain": "yourcompany",    # yourcompany.wufoo.com
            "api_key": "XXXX-XXXX-...",     # Wufoo API key
            "form_hashes": ["abc123", "def456"],  # Form hash IDs to track
            "last_synced": "2026-02-19T..."
        }
    }
    """
    
    def __init__(self):
        self.base_url_template = "https://{subdomain}.wufoo.com/api/v3"
        self.timeout = 15
    
    def _get_auth_header(self, api_key: str) -> dict:
        """Wufoo uses HTTP Basic Auth with API key as username, any string as password"""
        credentials = b64encode(f"{api_key}:footastic".encode()).decode()
        return {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json'
        }
    
    def _get_base_url(self, subdomain: str) -> str:
        return self.base_url_template.format(subdomain=subdomain)
    
    def get_forms(self, subdomain: str, api_key: str) -> List[Dict]:
        """Get all forms for the account (handles pagination)"""
        all_forms = []
        page_start = 0
        page_size = 100
        max_pages = 10  # Safety limit: 10 pages x 100 = 1000 forms max
        
        for page_num in range(max_pages):
            try:
                url = f"{self._get_base_url(subdomain)}/forms.json"
                params = {'pageSize': page_size, 'pageStart': page_start}
                logger.info(f"Wufoo: fetching forms page {page_num + 1} (start={page_start})...")
                
                resp = requests.get(url, headers=self._get_auth_header(api_key), params=params, timeout=30)
                logger.info(f"Wufoo: page {page_num + 1} response: {resp.status_code}")
                
                if resp.status_code == 200:
                    data = resp.json()
                    forms = data.get('Forms', [])
                    logger.info(f"Wufoo: page {page_num + 1} returned {len(forms)} forms")
                    
                    if not forms:
                        break
                    
                    for f in forms:
                        all_forms.append({
                            'hash': f.get('Hash', ''),
                            'name': f.get('Name', ''),
                            'description': f.get('Description', ''),
                            'entry_count': int(f.get('EntryCount', 0) or 0),
                            'url': f.get('Url', ''),
                            'created': f.get('DateCreated', ''),
                            'updated': f.get('DateUpdated', '')
                        })
                    
                    if len(forms) < page_size:
                        break  # Last page
                    
                    page_start += page_size
                elif resp.status_code == 401 or resp.status_code == 403:
                    logger.error(f"Wufoo: auth failed {resp.status_code}")
                    break
                else:
                    logger.error(f"Wufoo API error {resp.status_code}: {resp.text[:200]}")
                    break
                    
            except requests.exceptions.Timeout:
                logger.error(f"Wufoo: timeout on page {page_num + 1}")
                break
            except Exception as e:
                logger.error(f"Wufoo get_forms error on page {page_num + 1}: {e}")
                import traceback
                traceback.print_exc()
                break
        
        logger.info(f"Wufoo: fetched {len(all_forms)} total forms across {page_num + 1} pages")
        return all_forms
    
    def get_form_fields(self, subdomain: str, api_key: str, form_hash: str) -> List[Dict]:
        """Get field definitions for a form"""
        try:
            url = f"{self._get_base_url(subdomain)}/forms/{form_hash}/fields.json"
            resp = requests.get(url, headers=self._get_auth_header(api_key), timeout=self.timeout)
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get('Fields', [])
            return []
        except Exception as e:
            logger.error(f"Wufoo get_fields error: {e}")
            return []
    
    def get_entries(
        self, 
        subdomain: str, 
        api_key: str, 
        form_hash: str,
        since: str = None,
        page_size: int = 100,
        page_start: int = 0
    ) -> List[Dict]:
        """
        Get form entries (submissions)
        
        Args:
            since: ISO date string to filter entries after this date
            page_size: Number of entries per page (max 100)
            page_start: Starting index for pagination
        """
        try:
            url = f"{self._get_base_url(subdomain)}/forms/{form_hash}/entries.json"
            params = {
                'pageSize': min(page_size, 100),
                'pageStart': page_start,
                'sort': 'EntryId',
                'sortDirection': 'DESC'
            }
            
            if since:
                # Wufoo date filter format
                params['Filter1'] = f'DateCreated Is_after {since}'
            
            resp = requests.get(
                url, 
                headers=self._get_auth_header(api_key), 
                params=params,
                timeout=self.timeout
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get('Entries', [])
            else:
                logger.error(f"Wufoo entries error {resp.status_code}: {resp.text[:200]}")
                return []
        except Exception as e:
            logger.error(f"Wufoo get_entries error: {e}")
            return []
    
    def parse_entry_to_lead(self, entry: Dict, fields: List[Dict], form_name: str = '') -> Dict:
        """
        Parse a Wufoo entry into a lead-compatible dict
        
        Wufoo entries have fields like Field1, Field2, etc.
        We map them to name, email, phone, message based on field type.
        """
        lead = {
            'wufoo_entry_id': entry.get('EntryId', ''),
            'date': entry.get('DateCreated', ''),
            'source': 'wufoo',
            'source_detail': form_name,
            'name': '',
            'email': '',
            'phone': '',
            'message': '',
            'service_requested': '',
            'raw_fields': {}
        }
        
        # Build field ID to definition map
        field_map = {}
        for field in fields:
            fid = field.get('ID', '')
            field_map[fid] = field
        
        # Parse each field value
        for key, value in entry.items():
            if not key.startswith('Field') or not value:
                continue
            
            field_def = field_map.get(key, {})
            field_title = field_def.get('Title', '').lower()
            field_type = field_def.get('Type', '').lower()
            
            lead['raw_fields'][field_def.get('Title', key)] = value
            
            # Map by field type or title
            if field_type == 'email' or 'email' in field_title:
                lead['email'] = value
            elif field_type == 'phone' or 'phone' in field_title or 'number' in field_title:
                lead['phone'] = value
            elif 'name' in field_title:
                if 'first' in field_title or 'full' in field_title or field_title == 'name':
                    lead['name'] = value if not lead['name'] else f"{lead['name']} {value}"
                elif 'last' in field_title:
                    lead['name'] = f"{lead['name']} {value}".strip()
                else:
                    if not lead['name']:
                        lead['name'] = value
            elif 'service' in field_title or 'interest' in field_title or 'type' in field_title:
                lead['service_requested'] = value
            elif field_type in ('textarea', 'text') and ('message' in field_title or 'comment' in field_title or 'note' in field_title or 'detail' in field_title):
                lead['message'] = value
            elif field_type == 'textarea' and not lead['message']:
                lead['message'] = value
        
        # Fallback: if no name, use email prefix
        if not lead['name'] and lead['email']:
            lead['name'] = lead['email'].split('@')[0].replace('.', ' ').title()
        elif not lead['name']:
            lead['name'] = 'Form Submission'
        
        return lead
    
    def sync_entries_for_client(self, client) -> Dict:
        """
        Sync all Wufoo form entries for a client into DBLead records
        
        Returns: {synced: int, errors: [], forms_checked: int}
        """
        from app.models.db_models import DBLead
        from app.database import db
        import uuid
        
        integrations = client.get_integrations()
        wufoo_config = integrations.get('wufoo', {})
        
        if not wufoo_config.get('subdomain') or not wufoo_config.get('api_key'):
            return {'synced': 0, 'errors': ['Wufoo not configured'], 'forms_checked': 0}
        
        subdomain = wufoo_config['subdomain']
        api_key = wufoo_config['api_key']
        form_hashes = wufoo_config.get('form_hashes', [])
        last_synced = wufoo_config.get('last_synced')
        
        # If no specific forms, get all forms
        if not form_hashes:
            forms = self.get_forms(subdomain, api_key)
            form_hashes = [f['hash'] for f in forms]
        
        result = {'synced': 0, 'errors': [], 'forms_checked': 0}
        
        for form_hash in form_hashes:
            try:
                result['forms_checked'] += 1
                
                # Get fields for mapping
                fields = self.get_form_fields(subdomain, api_key, form_hash)
                
                # Get form name
                forms = self.get_forms(subdomain, api_key)
                form_name = next((f['name'] for f in forms if f['hash'] == form_hash), form_hash)
                
                # Fetch entries since last sync
                entries = self.get_entries(subdomain, api_key, form_hash, since=last_synced)
                
                for entry in entries:
                    entry_id = entry.get('EntryId', '')
                    
                    # Check if already imported
                    existing = DBLead.query.filter_by(
                        client_id=client.id,
                        source_detail=f'wufoo:{form_hash}:{entry_id}'
                    ).first()
                    
                    if existing:
                        continue
                    
                    # Parse entry
                    lead_data = self.parse_entry_to_lead(entry, fields, form_name)
                    
                    # Create DBLead
                    lead = DBLead(
                        id=f"wuf_{uuid.uuid4().hex[:12]}",
                        client_id=client.id,
                        name=lead_data['name'][:200],
                        email=lead_data.get('email', '')[:200] if lead_data.get('email') else None,
                        phone=lead_data.get('phone', '')[:50] if lead_data.get('phone') else None,
                        service_requested=lead_data.get('service_requested', '')[:200] if lead_data.get('service_requested') else None,
                        message=lead_data.get('message'),
                        source='form',
                        source_detail=f'wufoo:{form_hash}:{entry_id}',
                        status='new',
                        created_at=datetime.fromisoformat(lead_data['date'].replace('Z', '+00:00')) if lead_data.get('date') else datetime.utcnow()
                    )
                    
                    db.session.add(lead)
                    result['synced'] += 1
                    
            except Exception as e:
                result['errors'].append(f"Form {form_hash}: {str(e)}")
                logger.error(f"Wufoo sync error for form {form_hash}: {e}")
        
        # Update last_synced
        try:
            wufoo_config['last_synced'] = datetime.utcnow().isoformat()
            integrations['wufoo'] = wufoo_config
            client.integrations = json.dumps(integrations)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error updating wufoo last_synced: {e}")
            db.session.rollback()
        
        return result
    
    def test_connection(self, subdomain: str, api_key: str) -> Dict:
        """Quick test - only fetches first page to verify credentials"""
        try:
            url = f"{self._get_base_url(subdomain)}/forms.json"
            params = {'pageSize': 10, 'pageStart': 0}
            resp = requests.get(url, headers=self._get_auth_header(api_key), params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                forms = data.get('Forms', [])
                return {
                    'success': True,
                    'message': f'Connected! Credentials valid.',
                    'forms': []  # Don't return forms here - use get_all_forms endpoint
                }
            elif resp.status_code == 401 or resp.status_code == 403:
                return {
                    'success': False,
                    'forms': [],
                    'message': 'Invalid API key or subdomain'
                }
            else:
                return {
                    'success': False,
                    'forms': [],
                    'message': f'Wufoo returned HTTP {resp.status_code}'
                }
        except Exception as e:
            return {
                'success': False,
                'forms': [],
                'message': f'Connection failed: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'forms': [],
                'message': f'Connection failed: {str(e)}'
            }


# Singleton
_wufoo_service = None

def get_wufoo_service() -> WufooService:
    global _wufoo_service
    if _wufoo_service is None:
        _wufoo_service = WufooService()
    return _wufoo_service
