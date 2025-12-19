"""
Setup Demo Chatbot for Karma Marketing Website
Run this after deploying to create the chatbot for karmamarketingandmedia.com
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db
from app.models.db_models import DBClient, DBChatbotConfig, DBChatbotFAQ

# Karma Marketing client data
KARMA_CLIENT = {
    'business_name': 'Karma Marketing + Media',
    'industry': 'Digital Marketing Agency',
    'geo': 'Sarasota, Florida',
    'website_url': 'https://karmamarketingandmedia.com',
    'phone': '(941) 809-5067',
    'email': 'info@karmamarketingandmedia.com',
    'services': [
        'AI-Powered SEO',
        'Website Design',
        'Content Marketing',
        'Social Media Management',
        'Google Business Profile Optimization',
        'Lead Generation',
        'WordPress Development',
        'Local SEO'
    ],
    'service_areas': ['Sarasota', 'Bradenton', 'Tampa Bay', 'Florida', 'Nationwide'],
    'primary_keywords': [
        'digital marketing agency sarasota',
        'SEO services sarasota',
        'AI marketing agency',
        'website design sarasota',
        'local SEO florida'
    ],
    'unique_selling_points': [
        '22 years of digital marketing experience',
        'AI-powered SEO automation',
        'Proprietary MCP Framework technology',
        'Specializing in trade contractors and medical practices',
        'Triple your business growth guarantee',
        '$2,500/month all-inclusive with no setup fees'
    ]
}

KARMA_CHATBOT_CONFIG = {
    'name': 'Karma Assistant',
    'welcome_message': "👋 Hey there! I'm the Karma Marketing assistant. Whether you need help with SEO, website design, or want to learn how AI can triple your business growth - I'm here to help! What brings you here today?",
    'placeholder_text': 'Ask about our services...',
    'primary_color': '#8b5cf6',
    'secondary_color': '#ec4899',
    'position': 'bottom-right',
    'collect_name': True,
    'collect_email': True,
    'collect_phone': True,
    'lead_capture_trigger': 'after_3_messages',
    'email_notifications': True,
    'notification_email': 'leads@karmamarketingandmedia.com',
    'is_active': True
}

KARMA_FAQS = [
    {
        'question': 'What services do you offer?',
        'answer': "We offer AI-powered SEO, WordPress website design, content marketing, social media management, Google Business Profile optimization, and lead generation. Our specialty is helping trade contractors (HVAC, electricians, etc.) and medical practices dominate their local market!",
        'keywords': ['services', 'offer', 'do you do', 'help with']
    },
    {
        'question': 'How much do your services cost?',
        'answer': "Our AI-powered marketing service is $2,500/month with NO setup fees. This includes SEO, content creation, social media management, and our proprietary MCP Framework technology. We guarantee to triple your business growth! Want to schedule a free consultation to learn more?",
        'keywords': ['cost', 'price', 'pricing', 'how much', 'rates', 'fees']
    },
    {
        'question': 'What is the MCP Framework?',
        'answer': "MCP (Marketing Control Platform) is our proprietary AI-powered system that automates SEO content creation, competitor monitoring, rank tracking, and lead generation. It's like having a full marketing team powered by AI, working for your business 24/7!",
        'keywords': ['MCP', 'framework', 'platform', 'technology', 'AI system']
    },
    {
        'question': 'Do you work with businesses outside Florida?',
        'answer': "Absolutely! While we're based in Sarasota, Florida, we work with businesses nationwide. Our AI-powered systems work for any location. We have clients across the US and can help businesses anywhere dominate their local SEO!",
        'keywords': ['location', 'where', 'area', 'nationwide', 'outside florida', 'other states']
    },
    {
        'question': 'How long does it take to see results?',
        'answer': "Most clients start seeing ranking improvements within 30-60 days, with significant results in 90 days. Our AI system generates optimized content daily, so search engines see consistent activity. We provide monthly reports showing your progress!",
        'keywords': ['results', 'how long', 'time', 'when', 'timeline']
    },
    {
        'question': 'Can I see examples of your work?',
        'answer': "Of course! We'd love to show you case studies and results from clients in your industry. Schedule a free consultation and we'll walk you through real examples of businesses we've helped triple their growth!",
        'keywords': ['examples', 'portfolio', 'case studies', 'work', 'show me']
    }
]


def setup_karma_chatbot():
    """Create or update Karma Marketing client and chatbot"""
    app = create_app()
    
    with app.app_context():
        # Check if Karma client exists
        karma_client = DBClient.query.filter_by(
            business_name='Karma Marketing + Media'
        ).first()
        
        if not karma_client:
            print("Creating Karma Marketing client...")
            karma_client = DBClient(**KARMA_CLIENT)
            db.session.add(karma_client)
            db.session.commit()
            print(f"✓ Created client: {karma_client.id}")
        else:
            print(f"✓ Karma client already exists: {karma_client.id}")
        
        # Check if chatbot exists
        chatbot = DBChatbotConfig.query.filter_by(client_id=karma_client.id).first()
        
        if not chatbot:
            print("Creating chatbot configuration...")
            chatbot = DBChatbotConfig(client_id=karma_client.id, **KARMA_CHATBOT_CONFIG)
            db.session.add(chatbot)
            db.session.commit()
            print(f"✓ Created chatbot: {chatbot.id}")
        else:
            # Update existing
            for key, value in KARMA_CHATBOT_CONFIG.items():
                setattr(chatbot, key, value)
            db.session.commit()
            print(f"✓ Updated chatbot: {chatbot.id}")
        
        # Add FAQs
        print("Setting up FAQs...")
        existing_faqs = DBChatbotFAQ.query.filter_by(client_id=karma_client.id).count()
        
        if existing_faqs == 0:
            for faq_data in KARMA_FAQS:
                faq = DBChatbotFAQ(
                    client_id=karma_client.id,
                    question=faq_data['question'],
                    answer=faq_data['answer']
                )
                faq.set_keywords(faq_data['keywords'])
                db.session.add(faq)
            db.session.commit()
            print(f"✓ Added {len(KARMA_FAQS)} FAQs")
        else:
            print(f"✓ FAQs already exist ({existing_faqs})")
        
        # Generate embed code
        base_url = os.getenv('BASE_URL', 'https://mcp-framework-complete-2.onrender.com')
        
        embed_code = f'''<!-- Karma Marketing Chatbot -->
<script>
(function() {{
    var script = document.createElement('script');
    script.src = '{base_url}/static/chatbot-widget.js';
    script.async = true;
    script.onload = function() {{
        MCPChatbot.init({{
            chatbotId: '{chatbot.id}',
            apiUrl: '{base_url}'
        }});
    }};
    document.head.appendChild(script);
}})();
</script>
<!-- End Karma Marketing Chatbot -->'''
        
        print("\n" + "="*60)
        print("KARMA MARKETING CHATBOT SETUP COMPLETE!")
        print("="*60)
        print(f"\nClient ID: {karma_client.id}")
        print(f"Chatbot ID: {chatbot.id}")
        print(f"\n📋 EMBED CODE FOR karmamarketingandmedia.com:")
        print("-"*60)
        print(embed_code)
        print("-"*60)
        print("\n📌 Add this code before </body> on your website!")
        print("\n✅ Your chatbot is ready to capture leads 24/7!")
        
        return {
            'client_id': karma_client.id,
            'chatbot_id': chatbot.id,
            'embed_code': embed_code
        }


if __name__ == '__main__':
    setup_karma_chatbot()
