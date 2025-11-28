"""
Update Existing Clients with Service Pages for Internal Linking
Run this to add service pages to clients that don't have them
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db
from app.models.db_models import DBClient


def generate_service_pages(client):
    """Generate service pages from client keywords"""
    pages = []
    
    # Get website base URL
    website_base = client.website_url or ''
    if website_base:
        website_base = website_base.rstrip('/')
    else:
        # Generate a placeholder URL
        business_slug = client.business_name.lower().replace(' ', '').replace(',', '')
        website_base = f"https://{business_slug}.com"
    
    # Get primary keywords
    primary_keywords = client.get_primary_keywords() or []
    
    for pk in primary_keywords[:8]:  # Max 8 service pages
        # Create URL slug from keyword
        slug = pk.lower().replace(' ', '-').replace(',', '').replace("'", '')
        
        pages.append({
            'keyword': pk,
            'url': f"{website_base}/{slug}/",
            'title': f"{pk.title()} - {client.business_name}"
        })
    
    # Add some standard pages if we have few keywords
    if len(pages) < 3:
        standard_pages = [
            {'keyword': 'contact us', 'url': f"{website_base}/contact/", 'title': f"Contact {client.business_name}"},
            {'keyword': 'about us', 'url': f"{website_base}/about/", 'title': f"About {client.business_name}"},
            {'keyword': 'services', 'url': f"{website_base}/services/", 'title': f"{client.business_name} Services"},
        ]
        for sp in standard_pages:
            if len(pages) >= 8:
                break
            if not any(p['keyword'] == sp['keyword'] for p in pages):
                pages.append(sp)
    
    return pages


def update_all_clients():
    """Update all clients without service pages"""
    app = create_app()
    
    with app.app_context():
        clients = DBClient.query.all()
        
        print(f"Found {len(clients)} clients")
        
        updated = 0
        for client in clients:
            existing_pages = client.get_service_pages()
            
            if not existing_pages:
                new_pages = generate_service_pages(client)
                if new_pages:
                    client.set_service_pages(new_pages)
                    db.session.commit()
                    print(f"✓ Updated {client.business_name}: {len(new_pages)} service pages")
                    updated += 1
            else:
                print(f"  {client.business_name}: Already has {len(existing_pages)} pages")
        
        print(f"\n{'='*50}")
        print(f"Updated {updated} clients with service pages")
        print(f"{'='*50}")


if __name__ == '__main__':
    update_all_clients()
