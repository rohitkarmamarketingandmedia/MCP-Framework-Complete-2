"""
MCP Framework - Chatbot Routes
API endpoints for chatbot management and conversations
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import json
import logging

from app.database import db
from app.models.db_models import (
    DBChatbotConfig, DBChatConversation, DBChatMessage, 
    DBChatbotFAQ, DBClient, DBLead
)
from app.routes.auth import token_required, optional_token
from app.utils import safe_int
from app.services.chatbot_service import chatbot_service

logger = logging.getLogger(__name__)

chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/api/chatbot')


# ==========================================
# Chatbot Configuration
# ==========================================

@chatbot_bp.route('/config/<client_id>', methods=['GET'])
@token_required
def get_chatbot_config(current_user, client_id):
    """Get chatbot configuration for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    config = DBChatbotConfig.query.filter_by(client_id=client_id).first()
    
    if not config:
        # Create default config
        config = DBChatbotConfig(client_id=client_id)
        db.session.add(config)
        db.session.commit()
    
    return jsonify(config.to_dict())


@chatbot_bp.route('/config/<client_id>', methods=['PUT'])
@token_required
def update_chatbot_config(current_user, client_id):
    """Update chatbot configuration"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    config = DBChatbotConfig.query.filter_by(client_id=client_id).first()
    
    if not config:
        config = DBChatbotConfig(client_id=client_id)
        db.session.add(config)
    
    data = request.get_json() or {}
    
    # Update allowed fields
    allowed_fields = [
        'name', 'welcome_message', 'placeholder_text',
        'primary_color', 'secondary_color', 'position', 'avatar_url',
        'auto_open_delay', 'show_on_mobile',
        'collect_email', 'collect_phone', 'collect_name',
        'system_prompt_override', 'temperature', 'max_tokens',
        'lead_capture_enabled', 'lead_capture_trigger',
        'email_notifications', 'notification_email',
        'sms_notifications', 'notification_phone',
        'business_hours_only', 'business_hours_start', 'business_hours_end',
        'timezone', 'offline_message', 'is_active'
    ]
    
    for field in allowed_fields:
        if field in data:
            setattr(config, field, data[field])
    
    config.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'message': 'Chatbot configuration updated',
        'config': config.to_dict()
    })


@chatbot_bp.route('/config/<client_id>/embed-code', methods=['GET'])
@token_required
def get_embed_code(current_user, client_id):
    """Get the embed code for client's website"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    config = DBChatbotConfig.query.filter_by(client_id=client_id).first()
    
    if not config:
        return jsonify({'error': 'Chatbot not configured'}), 404
    
    base_url = request.host_url.rstrip('/')
    embed_code = chatbot_service.generate_embed_code(config.id, base_url)
    
    return jsonify({
        'chatbot_id': config.id,
        'embed_code': embed_code
    })


# ==========================================
# Public Widget Endpoints (No Auth)
# ==========================================

@chatbot_bp.route('/widget/<chatbot_id>/config', methods=['GET'])
def get_widget_config(chatbot_id):
    """Public endpoint - Get chatbot config for widget"""
    config = DBChatbotConfig.query.get(chatbot_id)
    
    if not config or not config.is_active:
        return jsonify({'error': 'Chatbot not found or inactive'}), 404
    
    # Return only public config
    return jsonify({
        'id': config.id,
        'name': config.name,
        'welcome_message': config.welcome_message,
        'placeholder_text': config.placeholder_text,
        'primary_color': config.primary_color,
        'secondary_color': config.secondary_color,
        'position': config.position,
        'avatar_url': config.avatar_url,
        'auto_open_delay': config.auto_open_delay,
        'show_on_mobile': config.show_on_mobile,
        'collect_email': config.collect_email,
        'collect_phone': config.collect_phone,
        'collect_name': config.collect_name,
        'business_hours_only': config.business_hours_only,
        'offline_message': config.offline_message
    })


@chatbot_bp.route('/widget/<chatbot_id>/start', methods=['POST'])
def start_conversation(chatbot_id):
    """Public endpoint - Start a new conversation"""
    config = DBChatbotConfig.query.get(chatbot_id)
    
    if not config or not config.is_active:
        return jsonify({'error': 'Chatbot not found or inactive'}), 404
    
    data = request.get_json() or {}
    
    # Get visitor info
    visitor_id = data.get('visitor_id', f"anon_{datetime.utcnow().timestamp()}")
    
    # Check for existing active conversation
    existing = DBChatConversation.query.filter_by(
        chatbot_id=chatbot_id,
        visitor_id=visitor_id,
        status='active'
    ).first()
    
    if existing:
        # Return existing conversation
        messages = [m.to_dict() for m in existing.messages.order_by(DBChatMessage.created_at).all()]
        return jsonify({
            'conversation_id': existing.id,
            'messages': messages,
            'resumed': True
        })
    
    # Create new conversation
    conversation = DBChatConversation(
        chatbot_id=chatbot_id,
        client_id=config.client_id,
        visitor_id=visitor_id,
        page_url=data.get('page_url'),
        page_title=data.get('page_title'),
        referrer=data.get('referrer'),
        user_agent=request.headers.get('User-Agent'),
        ip_address=request.remote_addr
    )
    db.session.add(conversation)
    
    # Add welcome message
    welcome_msg = DBChatMessage(
        conversation_id=conversation.id,
        role='assistant',
        content=config.welcome_message
    )
    db.session.add(welcome_msg)
    conversation.message_count = 1
    
    # Update chatbot stats
    config.total_conversations += 1
    
    db.session.commit()
    
    return jsonify({
        'conversation_id': conversation.id,
        'messages': [welcome_msg.to_dict()],
        'resumed': False
    })


@chatbot_bp.route('/widget/<chatbot_id>/message', methods=['POST'])
def send_message(chatbot_id):
    """Public endpoint - Send a message and get AI response"""
    config = DBChatbotConfig.query.get(chatbot_id)
    
    if not config or not config.is_active:
        return jsonify({'error': 'Chatbot not found or inactive'}), 404
    
    data = request.get_json() or {}
    conversation_id = data.get('conversation_id')
    message_content = data.get('message', '').strip()
    
    if not conversation_id:
        return jsonify({'error': 'conversation_id required'}), 400
    
    if not message_content:
        return jsonify({'error': 'message required'}), 400
    
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation or conversation.chatbot_id != chatbot_id:
        return jsonify({'error': 'Invalid conversation'}), 404
    
    # Save user message
    user_msg = DBChatMessage(
        conversation_id=conversation_id,
        role='user',
        content=message_content
    )
    db.session.add(user_msg)
    conversation.message_count += 1
    conversation.last_message_at = datetime.utcnow()
    
    # Get client data for context
    client = DBClient.query.get(config.client_id)
    client_data = client.to_dict() if client else {}
    
    # Build system prompt
    system_prompt = chatbot_service.build_system_prompt(client_data, config.to_dict())
    
    # Get conversation history
    history = []
    for msg in conversation.messages.order_by(DBChatMessage.created_at).all():
        history.append({
            'role': msg.role,
            'content': msg.content
        })
    history.append({'role': 'user', 'content': message_content})
    
    # Check FAQ match first
    faqs = DBChatbotFAQ.query.filter_by(client_id=config.client_id, is_active=True).all()
    faq_match = chatbot_service.check_faq_match(message_content, [f.to_dict() for f in faqs])
    
    if faq_match:
        response_content = faq_match
        tokens_used = 0
        response_time = 0
    else:
        # Get AI response
        ai_result = chatbot_service.get_ai_response_sync(
            messages=history,
            system_prompt=system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )
        response_content = ai_result['content']
        tokens_used = ai_result.get('tokens_used', 0)
        response_time = ai_result.get('response_time_ms', 0)
    
    # Check if we should add lead capture prompt
    should_capture = chatbot_service.should_capture_lead(
        conversation.message_count,
        config.lead_capture_trigger
    )
    
    if should_capture and not conversation.is_lead_captured and config.lead_capture_enabled:
        lead_prompt = chatbot_service.get_lead_capture_message(
            config.collect_name,
            config.collect_email,
            config.collect_phone
        )
        if lead_prompt:
            response_content += f"\n\n{lead_prompt}"
    
    # Save assistant message
    assistant_msg = DBChatMessage(
        conversation_id=conversation_id,
        role='assistant',
        content=response_content,
        tokens_used=tokens_used,
        response_time_ms=response_time
    )
    db.session.add(assistant_msg)
    conversation.message_count += 1
    
    db.session.commit()
    
    return jsonify({
        'message': assistant_msg.to_dict(),
        'should_capture_lead': should_capture and not conversation.is_lead_captured
    })


@chatbot_bp.route('/widget/<chatbot_id>/lead', methods=['POST'])
def capture_lead(chatbot_id):
    """Public endpoint - Capture lead information"""
    config = DBChatbotConfig.query.get(chatbot_id)
    
    if not config or not config.is_active:
        return jsonify({'error': 'Chatbot not found or inactive'}), 404
    
    data = request.get_json() or {}
    conversation_id = data.get('conversation_id')
    
    if not conversation_id:
        return jsonify({'error': 'conversation_id required'}), 400
    
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation or conversation.chatbot_id != chatbot_id:
        return jsonify({'error': 'Invalid conversation'}), 404
    
    # Update conversation with visitor info
    if data.get('name'):
        conversation.visitor_name = data['name']
    if data.get('email'):
        conversation.visitor_email = data['email']
    if data.get('phone'):
        conversation.visitor_phone = data['phone']
    
    conversation.is_lead_captured = True
    
    # Create lead in leads table
    try:
        lead = DBLead(
            client_id=config.client_id,
            name=data.get('name', ''),
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            source='chatbot',
            source_detail=f"Chat conversation: {conversation_id}",
            page_url=conversation.page_url,
            notes=f"Captured via chatbot widget"
        )
        db.session.add(lead)
        
        # Link to conversation
        conversation.lead_id = lead.id
        
        # Update chatbot stats
        config.total_leads_captured += 1
        
        db.session.commit()
        
        # TODO: Send notification email/SMS
        
        return jsonify({
            'success': True,
            'message': 'Thank you! We\'ll be in touch soon.',
            'lead_id': lead.id
        })
        
    except Exception as e:
        logger.error(f"Lead capture error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Thank you! We received your information.'
        })


@chatbot_bp.route('/widget/<chatbot_id>/end', methods=['POST'])
def end_conversation(chatbot_id):
    """Public endpoint - End a conversation"""
    data = request.get_json() or {}
    conversation_id = data.get('conversation_id')
    
    if not conversation_id:
        return jsonify({'error': 'conversation_id required'}), 400
    
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation or conversation.chatbot_id != chatbot_id:
        return jsonify({'error': 'Invalid conversation'}), 404
    
    conversation.status = 'closed'
    conversation.ended_at = datetime.utcnow()
    
    if data.get('rating'):
        conversation.rating = min(5, max(1, int(data['rating'])))
    if data.get('feedback'):
        conversation.feedback = data['feedback'][:1000]
    
    db.session.commit()
    
    return jsonify({'success': True})


# ==========================================
# Internal MCP Support Chatbot
# ==========================================

@chatbot_bp.route('/mcp-support/message', methods=['POST'])
@optional_token
def mcp_support_message(current_user):
    """Internal MCP support chatbot endpoint"""
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    history = data.get('history', [])
    
    if not message:
        return jsonify({'error': 'message required'}), 400
    
    # Build system prompt for MCP support
    system_prompt = chatbot_service.build_mcp_support_prompt()
    
    # Add current message to history
    messages = history + [{'role': 'user', 'content': message}]
    
    # Get AI response
    result = chatbot_service.get_ai_response_sync(
        messages=messages,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=600
    )
    
    return jsonify({
        'response': result['content'],
        'tokens_used': result.get('tokens_used', 0)
    })


# ==========================================
# Conversation Management
# ==========================================

@chatbot_bp.route('/conversations', methods=['GET'])
@token_required
def list_conversations(current_user):
    """Get all conversations for accessible clients"""
    client_id = request.args.get('client_id')
    status = request.args.get('status')
    limit = safe_int(request.args.get('limit'), 50, max_val=200)
    
    query = DBChatConversation.query
    
    if client_id:
        if not current_user.has_access_to_client(client_id):
            return jsonify({'error': 'Access denied'}), 403
        query = query.filter_by(client_id=client_id)
    elif not current_user.is_admin:
        client_ids = current_user.get_client_ids()
        query = query.filter(DBChatConversation.client_id.in_(client_ids))
    
    if status:
        query = query.filter_by(status=status)
    
    conversations = query.order_by(DBChatConversation.last_message_at.desc()).limit(limit).all()
    
    return jsonify({
        'conversations': [c.to_dict() for c in conversations],
        'total': query.count()
    })


@chatbot_bp.route('/conversations/<conversation_id>', methods=['GET'])
@token_required
def get_conversation(current_user, conversation_id):
    """Get a specific conversation with messages"""
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    if not current_user.has_access_to_client(conversation.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(conversation.to_dict(include_messages=True))


@chatbot_bp.route('/conversations/<conversation_id>/reply', methods=['POST'])
@token_required
def reply_to_conversation(current_user, conversation_id):
    """Manual reply to a conversation (human takeover)"""
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    if not current_user.has_access_to_client(conversation.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    message_content = data.get('message', '').strip()
    
    if not message_content:
        return jsonify({'error': 'message required'}), 400
    
    # Save message
    msg = DBChatMessage(
        conversation_id=conversation_id,
        role='assistant',
        content=message_content
    )
    db.session.add(msg)
    
    conversation.message_count += 1
    conversation.last_message_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'message': msg.to_dict()
    })


# ==========================================
# FAQ Management
# ==========================================

@chatbot_bp.route('/faqs/<client_id>', methods=['GET'])
@token_required
def get_faqs(current_user, client_id):
    """Get FAQs for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    faqs = DBChatbotFAQ.query.filter_by(client_id=client_id).all()
    
    return jsonify({
        'faqs': [f.to_dict() for f in faqs]
    })


@chatbot_bp.route('/faqs/<client_id>', methods=['POST'])
@token_required
def add_faq(current_user, client_id):
    """Add a new FAQ"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    
    faq = DBChatbotFAQ(
        client_id=client_id,
        question=data.get('question', ''),
        answer=data.get('answer', ''),
        category=data.get('category')
    )
    
    if data.get('keywords'):
        faq.set_keywords(data['keywords'])
    
    db.session.add(faq)
    db.session.commit()
    
    return jsonify({
        'message': 'FAQ added',
        'faq': faq.to_dict()
    })


@chatbot_bp.route('/faqs/<client_id>/<int:faq_id>', methods=['PUT'])
@token_required
def update_faq(current_user, client_id, faq_id):
    """Update an FAQ"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    faq = DBChatbotFAQ.query.filter_by(id=faq_id, client_id=client_id).first()
    
    if not faq:
        return jsonify({'error': 'FAQ not found'}), 404
    
    data = request.get_json() or {}
    
    if 'question' in data:
        faq.question = data['question']
    if 'answer' in data:
        faq.answer = data['answer']
    if 'category' in data:
        faq.category = data['category']
    if 'keywords' in data:
        faq.set_keywords(data['keywords'])
    if 'is_active' in data:
        faq.is_active = data['is_active']
    
    db.session.commit()
    
    return jsonify({
        'message': 'FAQ updated',
        'faq': faq.to_dict()
    })


@chatbot_bp.route('/faqs/<client_id>/<int:faq_id>', methods=['DELETE'])
@token_required
def delete_faq(current_user, client_id, faq_id):
    """Delete an FAQ"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    faq = DBChatbotFAQ.query.filter_by(id=faq_id, client_id=client_id).first()
    
    if not faq:
        return jsonify({'error': 'FAQ not found'}), 404
    
    db.session.delete(faq)
    db.session.commit()
    
    return jsonify({'success': True})


# ==========================================
# Analytics
# ==========================================

@chatbot_bp.route('/analytics/<client_id>', methods=['GET'])
@token_required
def get_chatbot_analytics(current_user, client_id):
    """Get chatbot analytics for a client"""
    if not current_user.has_access_to_client(client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    config = DBChatbotConfig.query.filter_by(client_id=client_id).first()
    
    if not config:
        return jsonify({
            'total_conversations': 0,
            'total_leads': 0,
            'avg_rating': None,
            'conversations_by_status': {},
            'recent_conversations': []
        })
    
    # Get conversation stats
    from sqlalchemy import func
    
    status_counts = db.session.query(
        DBChatConversation.status,
        func.count(DBChatConversation.id)
    ).filter_by(client_id=client_id).group_by(DBChatConversation.status).all()
    
    avg_rating = db.session.query(
        func.avg(DBChatConversation.rating)
    ).filter(
        DBChatConversation.client_id == client_id,
        DBChatConversation.rating.isnot(None)
    ).scalar()
    
    recent = DBChatConversation.query.filter_by(
        client_id=client_id
    ).order_by(
        DBChatConversation.started_at.desc()
    ).limit(10).all()
    
    return jsonify({
        'total_conversations': config.total_conversations,
        'total_leads': config.total_leads_captured,
        'avg_rating': round(float(avg_rating), 1) if avg_rating else None,
        'conversations_by_status': dict(status_counts),
        'recent_conversations': [c.to_dict() for c in recent]
    })
