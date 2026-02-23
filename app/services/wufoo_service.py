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
        """Get all forms for the account including sub-user forms"""
        all_forms = []
        seen_hashes = set()
        
        # Method 1: Try fetching with large pageSize (Wufoo may cap at 100)
        for page_start in range(0, 2000, 100):
            try:
                url = f"{self._get_base_url(subdomain)}/forms.json"
                params = {'pageSize': 100, 'pageStart': page_start}
                logger.info(f"Wufoo: fetching forms (start={page_start})...")
                
                resp = requests.get(url, headers=self._get_auth_header(api_key), params=params, timeout=30)
                
                if resp.status_code != 200:
                    logger.error(f"Wufoo forms error: {resp.status_code}")
                    break
                
                forms = resp.json().get('Forms', [])
                if not forms:
                    break
                
                new_count = 0
                for f in forms:
                    fh = f.get('Hash', '')
                    if fh and fh not in seen_hashes:
                        seen_hashes.add(fh)
                        new_count += 1
                        all_forms.append({
                            'hash': fh,
                            'name': f.get('Name', ''),
                            'description': f.get('Description', ''),
                            'entry_count': int(f.get('EntryCount', 0) or 0),
                            'url': f.get('Url', ''),
                            'created': f.get('DateCreated', ''),
                            'updated': f.get('DateUpdated', '')
                        })
                
                logger.info(f"Wufoo: got {len(forms)} forms, {new_count} new (total unique: {len(all_forms)})")
                
                # If got fewer than 100 or all were duplicates, we're done
                if len(forms) < 100 or new_count == 0:
                    break
                    
            except Exception as e:
                logger.error(f"Wufoo get_forms error: {e}")
                break
        
        # Method 2: If we only got ~100, try fetching via sub-users
        if len(all_forms) <= 100:
            logger.info("Wufoo: only got <=100 forms, trying sub-user forms...")
            try:
                users_url = f"{self._get_base_url(subdomain)}/users.json"
                resp = requests.get(users_url, headers=self._get_auth_header(api_key), timeout=15)
                if resp.status_code == 200:
                    users = resp.json().get('Users', [])
                    logger.info(f"Wufoo: found {len(users)} users, checking their forms...")
                    
                    for user in users:
                        user_hash = user.get('Hash', '')
                        if not user_hash:
                            continue
                        try:
                            user_forms_url = f"{self._get_base_url(subdomain)}/users/{user_hash}/forms.json"
                            uf_resp = requests.get(user_forms_url, headers=self._get_auth_header(api_key), timeout=15)
                            if uf_resp.status_code == 200:
                                user_forms = uf_resp.json().get('Forms', [])
                                for f in user_forms:
                                    fh = f.get('Hash', '')
                                    if fh and fh not in seen_hashes:
                                        seen_hashes.add(fh)
                                        all_forms.append({
                                            'hash': fh,
                                            'name': f.get('Name', ''),
                                            'description': f.get('Description', ''),
                                            'entry_count': int(f.get('EntryCount', 0) or 0),
                                            'url': f.get('Url', ''),
                                            'created': f.get('DateCreated', ''),
                                            'updated': f.get('DateUpdated', '')
                                        })
                        except Exception as ue:
                            logger.warning(f"Wufoo: error getting forms for user {user_hash}: {ue}")
            except Exception as e:
                logger.warning(f"Wufoo: could not fetch sub-user forms: {e}")
        
        logger.info(f"Wufoo: total unique forms: {len(all_forms)}")
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
        Get ALL form entries (submissions) with automatic pagination.
        Wufoo caps at 100 entries per request, so we loop until we get them all.
        
        Args:
            since: ISO date string to filter entries after this date
            page_size: Number of entries per page (max 100)
            page_start: Starting index for pagination
        """
        all_entries = []
        current_start = page_start
        
        while True:
            try:
                url = f"{self._get_base_url(subdomain)}/forms/{form_hash}/entries.json"
                params = {
                    'pageSize': min(page_size, 100),
                    'pageStart': current_start,
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
                    entries = data.get('Entries', [])
                    
                    if not entries:
                        break
                    
                    all_entries.extend(entries)
                    logger.info(f"Wufoo: fetched {len(entries)} entries (page_start={current_start}, total so far={len(all_entries)})")
                    
                    # If we got fewer than page_size, we've reached the end
                    if len(entries) < page_size:
                        break
                    
                    current_start += len(entries)
                    
                    # Safety limit: max 5000 entries per form
                    if len(all_entries) >= 5000:
                        logger.warning(f"Wufoo: hit 5000 entry safety limit for form {form_hash}")
                        break
                else:
                    logger.error(f"Wufoo entries error {resp.status_code}: {resp.text[:200]}")
                    break
            except Exception as e:
                logger.error(f"Wufoo get_entries error: {e}")
                break
        
        logger.info(f"Wufoo: total entries fetched for form {form_hash}: {len(all_entries)}")
        return all_entries
    
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
