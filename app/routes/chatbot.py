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
    
    data = request.get_json(silent=True) or {}
    
    # Update allowed fields
    allowed_fields = [
        'name', 'welcome_message', 'placeholder_text',
        'header_title', 'header_subtitle',
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
    
    # Return only public config with fallbacks for null values
    return jsonify({
        'id': config.id,
        'name': config.name or 'Support Assistant',
        'header_title': config.header_title or config.name or 'Chat Support',
        'header_subtitle': config.header_subtitle or 'Online',
        'welcome_message': config.welcome_message or 'Hi! How can I help you today?',
        'placeholder_text': config.placeholder_text or 'Type your message...',
        'primary_color': config.primary_color or '#3b82f6',
        'secondary_color': config.secondary_color or '#1e40af',
        'position': config.position or 'bottom-right',
        'avatar_url': config.avatar_url,
        'auto_open_delay': config.auto_open_delay or 0,
        'show_on_mobile': config.show_on_mobile if config.show_on_mobile is not None else True,
        'collect_email': config.collect_email if config.collect_email is not None else True,
        'collect_phone': config.collect_phone if config.collect_phone is not None else True,
        'collect_name': config.collect_name if config.collect_name is not None else True,
        'lead_capture_enabled': config.lead_capture_enabled if config.lead_capture_enabled is not None else True,
        'business_hours_only': config.business_hours_only if config.business_hours_only is not None else False,
        'offline_message': config.offline_message or "We're currently offline. Leave your info and we'll get back to you!"
    })


@chatbot_bp.route('/widget/<chatbot_id>/start', methods=['POST'])
def start_conversation(chatbot_id):
    """Public endpoint - Start a new conversation"""
    config = DBChatbotConfig.query.get(chatbot_id)
    
    if not config or not config.is_active:
        return jsonify({'error': 'Chatbot not found or inactive'}), 404
    
    data = request.get_json(silent=True) or {}
    
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
    try:
        config = DBChatbotConfig.query.get(chatbot_id)
        
        if not config or not config.is_active:
            return jsonify({'error': 'Chatbot not found or inactive'}), 404
        
        data = request.get_json(silent=True) or {}
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
        if not client:
            logger.warning(f"Client not found for chatbot {chatbot_id}, client_id: {config.client_id}")
            client_data = {'business_name': 'Our Company', 'industry': 'Business'}
        else:
            client_data = client.to_dict()
        
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
            'should_capture_lead': should_capture and not conversation.is_lead_captured and config.lead_capture_enabled
        })
        
    except Exception as e:
        logger.error(f"Chatbot message error for {chatbot_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'message': {
                'role': 'assistant',
                'content': "I'm having trouble responding right now. Please try again or leave your contact info!"
            },
            'should_capture_lead': True,
            'error': str(e)
        })


@chatbot_bp.route('/widget/<chatbot_id>/lead', methods=['POST'])
def capture_lead(chatbot_id):
    """Public endpoint - Capture lead information"""
    config = DBChatbotConfig.query.get(chatbot_id)
    
    if not config or not config.is_active:
        return jsonify({'error': 'Chatbot not found or inactive'}), 404
    
    data = request.get_json(silent=True) or {}
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
        import uuid
        lead = DBLead(
            id=f"lead_{uuid.uuid4().hex[:12]}",
            client_id=config.client_id,
            name=data.get('name', ''),
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            source='chatbot',
            source_detail=f"Chat conversation: {conversation_id}",
            landing_page=conversation.page_url,
            notes=f"Captured via chatbot widget"
        )
        db.session.add(lead)
        
        if data.get('message'):
            lead.message = data['message']
        
        # Link to conversation
        conversation.lead_id = lead.id
        
        # Update chatbot stats
        config.total_leads_captured += 1
        
        db.session.commit()
        
        # Send notification email if enabled
        if config.email_notifications and config.notification_email:
            try:
                # Parse CC/BCC from config
                cc_list = [e.strip() for e in (config.notification_cc or '').split(',') if e.strip()]
                bcc_list = [e.strip() for e in (config.notification_bcc or '').split(',') if e.strip()]
                
                _send_lead_notification_email(
                    to_email=config.notification_email,
                    lead_name=data.get('name', 'Anonymous'),
                    lead_email=data.get('email', 'Not provided'),
                    lead_phone=data.get('phone', 'Not provided'),
                    lead_message=data.get('message', ''),
                    page_url=conversation.page_url or 'Unknown',
                    client_id=config.client_id,
                    conversation_id=conversation_id,
                    chatbot_id=chatbot_id,
                    cc=cc_list or None,
                    bcc=bcc_list or None
                )
            except Exception as e:
                logger.error(f"Failed to send lead notification email: {e}")
        
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


def _send_lead_notification_email(to_email, lead_name, lead_email, lead_phone, lead_message, page_url, client_id, conversation_id=None, chatbot_id=None, cc=None, bcc=None):
    """Send email notification for new chatbot lead with chat history link"""
    from app.services.email_service import get_email_service
    import os
    
    email_service = get_email_service()
    app_url = os.getenv('APP_URL', 'https://mcp.karmamarketingandmedia.com')
    
    # Get client name if available
    client = DBClient.query.get(client_id) if client_id else None
    client_name = client.business_name if client else 'Your Website'
    
    # Build chat history URL (public, no login required)
    chat_history_url = ''
    if conversation_id:
        try:
            conv = DBChatConversation.query.get(conversation_id)
            if conv and conv.share_token:
                chat_history_url = f"{app_url}/chat/{conv.share_token}"
            elif conv:
                # Generate share token if missing
                import uuid as _uuid
                conv.share_token = _uuid.uuid4().hex + _uuid.uuid4().hex[:8]
                db.session.commit()
                chat_history_url = f"{app_url}/chat/{conv.share_token}"
        except Exception as e:
            logger.warning(f"Could not build chat history URL: {e}")
    
    # Get conversation transcript
    chat_transcript_html = ''
    if conversation_id:
        try:
            conversation = DBChatConversation.query.get(conversation_id)
            if conversation:
                messages = DBChatMessage.query.filter_by(
                    conversation_id=conversation_id
                ).order_by(DBChatMessage.created_at.asc()).all()
                
                if messages:
                    rows = ''
                    for msg in messages:
                        if msg.role == 'system':
                            continue
                        is_visitor = msg.role == 'user'
                        label = 'Visitor' if is_visitor else 'Chatbot'
                        bg_color = '#eff6ff' if is_visitor else '#f0fdf4'
                        label_color = '#2563eb' if is_visitor else '#16a34a'
                        # Truncate long messages
                        content = msg.content or ''
                        if len(content) > 300:
                            content = content[:300] + '...'
                        # Escape HTML
                        content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                        
                        rows += f'''
                        <div style="margin-bottom: 8px; padding: 10px 14px; background: {bg_color}; border-radius: 8px;">
                            <span style="font-size: 11px; font-weight: 600; color: {label_color}; text-transform: uppercase;">{label}</span>
                            <p style="margin: 4px 0 0 0; color: #374151; font-size: 14px; line-height: 1.5;">{content}</p>
                        </div>'''
                    
                    chat_transcript_html = f'''
                    <div style="margin-top: 25px; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                        <h3 style="color: #111; font-size: 16px; margin: 0 0 12px 0;">💬 Chat Conversation</h3>
                        <div style="max-height: 400px; overflow: hidden;">
                            {rows}
                        </div>
                    </div>'''
        except Exception as e:
            logger.warning(f"Could not load chat transcript for email: {e}")
    
    # Build chat history button
    chat_history_button = ''
    if chat_history_url:
        chat_history_button = f'''
                <div style="text-align: center; margin-top: 15px;">
                    <a href="{chat_history_url}" 
                       style="display: inline-block; padding: 14px 28px; background: linear-gradient(135deg, #3b82f6, #2563eb); 
                              color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">
                        💬 View Full Chat History →
                    </a>
                </div>'''
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                 background: #f4f4f5; padding: 20px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; 
                    overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <div style="background: linear-gradient(135deg, #22c55e, #16a34a); padding: 24px 30px;">
                <h1 style="color: white; margin: 0; font-size: 22px;">🎉 New Lead from Chatbot!</h1>
            </div>
            
            <div style="padding: 30px;">
                <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                    Great news! A visitor just submitted their contact information through the chatbot widget on <strong>{client_name}</strong>.
                </p>
                
                <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 12px; color: #666; width: 100px; border-bottom: 1px solid #e5e7eb;">Name:</td>
                        <td style="padding: 12px; color: #111; font-weight: 500; border-bottom: 1px solid #e5e7eb;">{lead_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; color: #666; border-bottom: 1px solid #e5e7eb;">Email:</td>
                        <td style="padding: 12px; color: #111; font-weight: 500; border-bottom: 1px solid #e5e7eb;">
                            <a href="mailto:{lead_email}" style="color: #2563eb; text-decoration: none;">{lead_email}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; color: #666; border-bottom: 1px solid #e5e7eb;">Phone:</td>
                        <td style="padding: 12px; color: #111; font-weight: 500; border-bottom: 1px solid #e5e7eb;">
                            <a href="tel:{lead_phone}" style="color: #2563eb; text-decoration: none;">{lead_phone}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; color: #666; border-bottom: 1px solid #e5e7eb;">Page:</td>
                        <td style="padding: 12px; color: #111; font-weight: 500; border-bottom: 1px solid #e5e7eb;">
                            <a href="{page_url}" style="color: #2563eb; text-decoration: none;">{page_url[:50]}...</a>
                        </td>
                    </tr>
                    {f'''<tr>
                        <td style="padding: 12px; color: #666; vertical-align: top;">Message:</td>
                        <td style="padding: 12px; color: #111;">{lead_message}</td>
                    </tr>''' if lead_message else ''}
                </table>
                
                {chat_transcript_html}
                
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{app_url}/client-dashboard?client={client_id}" 
                       style="display: inline-block; padding: 14px 28px; background: linear-gradient(135deg, #22c55e, #16a34a); 
                              color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">
                        View in Dashboard →
                    </a>
                </div>
                {chat_history_button}
            </div>
            
            <div style="background: #f8f8f8; padding: 20px; text-align: center; color: #9ca3af; font-size: 12px;">
                <p style="margin: 0;">This notification was sent from your chatbot widget.</p>
                <p style="margin: 5px 0 0 0;">
                    <a href="{app_url}/settings" style="color: #22c55e;">Manage Notification Settings</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    subject = f"🎉 New Chatbot Lead: {lead_name}"
    
    success = email_service.send_simple(to_email, subject, html, html=True, cc=cc, bcc=bcc)
    if success:
        logger.info(f"Lead notification email sent to {to_email}")
    else:
        logger.warning(f"Failed to send lead notification email to {to_email}")
    
    return success


@chatbot_bp.route('/widget/<chatbot_id>/messages/<conversation_id>', methods=['GET'])
def get_widget_messages(chatbot_id, conversation_id):
    """Public endpoint - Get messages for widget polling (id: 37)"""
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation or conversation.chatbot_id != chatbot_id:
        return jsonify({'error': 'Invalid conversation'}), 404
        
    messages = [m.to_dict() for m in conversation.messages.order_by(DBChatMessage.created_at).all()]
    return jsonify({
        'messages': messages,
        'status': conversation.status
    })


@chatbot_bp.route('/chat/<share_token>', methods=['GET'])
def public_chat_history(share_token):
    """
    Public endpoint - View full chat history via unique share link.
    No login required. Accessed from notification emails.
    """
    from markupsafe import escape
    
    conversation = DBChatConversation.query.filter_by(share_token=share_token).first()
    
    if not conversation:
        return """
        <!DOCTYPE html>
        <html><head><title>Chat Not Found</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                     background: #111827; color: white; display: flex; align-items: center; 
                     justify-content: center; min-height: 100vh; margin: 0;">
            <div style="text-align: center; padding: 40px;">
                <h1 style="font-size: 48px; margin: 0;">🔒</h1>
                <h2 style="margin: 20px 0 10px;">Chat Not Found</h2>
                <p style="color: #9ca3af;">This chat conversation doesn't exist or the link has expired.</p>
            </div>
        </body></html>
        """, 404
    
    # Get client info
    client = DBClient.query.get(conversation.client_id)
    client_name = escape(client.business_name) if client else 'Chat'
    
    # Get messages
    messages = DBChatMessage.query.filter_by(
        conversation_id=conversation.id
    ).order_by(DBChatMessage.created_at.asc()).all()
    
    # Build message bubbles
    message_html = ''
    for msg in messages:
        if msg.role == 'system':
            continue
        
        is_visitor = msg.role == 'user'
        content = escape(msg.content or '')
        content = str(content).replace('\n', '<br>')
        timestamp = msg.created_at.strftime('%b %d, %I:%M %p') if msg.created_at else ''
        
        if is_visitor:
            message_html += f'''
            <div style="display: flex; justify-content: flex-end; margin-bottom: 16px;">
                <div style="max-width: 75%; background: linear-gradient(135deg, #3b82f6, #2563eb); 
                            color: white; padding: 14px 18px; border-radius: 18px 18px 4px 18px;">
                    <p style="margin: 0; font-size: 15px; line-height: 1.5;">{content}</p>
                    <p style="margin: 6px 0 0; font-size: 11px; opacity: 0.7; text-align: right;">{timestamp}</p>
                </div>
            </div>'''
        else:
            message_html += f'''
            <div style="display: flex; justify-content: flex-start; margin-bottom: 16px;">
                <div style="max-width: 75%; background: #1f2937; color: #e5e7eb; 
                            padding: 14px 18px; border-radius: 18px 18px 18px 4px; border: 1px solid #374151;">
                    <p style="margin: 0; font-size: 15px; line-height: 1.5;">{content}</p>
                    <p style="margin: 6px 0 0; font-size: 11px; color: #6b7280;">{timestamp}</p>
                </div>
            </div>'''
    
    # Visitor info section
    visitor_info = ''
    if conversation.visitor_name or conversation.visitor_email or conversation.visitor_phone:
        info_rows = ''
        if conversation.visitor_name:
            info_rows += f'<span style="background: #1f2937; padding: 6px 14px; border-radius: 20px; font-size: 13px;">👤 {escape(conversation.visitor_name)}</span>'
        if conversation.visitor_email:
            info_rows += f'<span style="background: #1f2937; padding: 6px 14px; border-radius: 20px; font-size: 13px;">✉️ {escape(conversation.visitor_email)}</span>'
        if conversation.visitor_phone:
            info_rows += f'<span style="background: #1f2937; padding: 6px 14px; border-radius: 20px; font-size: 13px;">📞 {escape(conversation.visitor_phone)}</span>'
        visitor_info = f'''
        <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; padding: 16px; 
                    background: #111827; border-radius: 12px; border: 1px solid #1f2937;">
            {info_rows}
        </div>'''
    
    started = conversation.started_at.strftime('%B %d, %Y at %I:%M %p') if conversation.started_at else 'Unknown'
    page_url = escape(conversation.page_url or '')
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Chat History - {client_name}</title>
        <meta name="robots" content="noindex, nofollow">
        <style>
            * {{ box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0b0f19; color: #e5e7eb; margin: 0; padding: 0;
            }}
            .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
            @media (max-width: 640px) {{
                .container {{ padding: 12px; }}
                div[style*="max-width: 75%"] {{ max-width: 88% !important; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div style="text-align: center; padding: 30px 20px 20px;">
                <div style="width: 56px; height: 56px; background: linear-gradient(135deg, #22c55e, #16a34a); 
                            border-radius: 16px; display: inline-flex; align-items: center; justify-content: center;
                            font-size: 26px; margin-bottom: 16px;">💬</div>
                <h1 style="color: white; font-size: 22px; margin: 0 0 6px;">{client_name} — Chat History</h1>
                <p style="color: #6b7280; font-size: 14px; margin: 0;">{started}</p>
                {"<p style='color: #6b7280; font-size: 13px; margin: 6px 0 0;'>Page: " + str(page_url)[:60] + "</p>" if page_url else ""}
            </div>
            
            {visitor_info}
            
            <!-- Messages -->
            <div style="padding: 10px 0;">
                {message_html if message_html else '<p style="text-align: center; color: #6b7280; padding: 40px;">No messages in this conversation.</p>'}
            </div>
            
            <!-- Footer -->
            <div style="text-align: center; padding: 30px 20px; color: #4b5563; font-size: 12px; border-top: 1px solid #1f2937; margin-top: 20px;">
                <p style="margin: 0;">{len(messages)} messages • {client_name}</p>
                <p style="margin: 6px 0 0; color: #374151;">Powered by Karma Marketing + Media</p>
            </div>
        </div>
    </body>
    </html>
    """, 200


@chatbot_bp.route('/widget/<chatbot_id>/end', methods=['POST'])
def end_conversation(chatbot_id):
    """Public endpoint - End a conversation"""
    data = request.get_json(silent=True) or {}
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
    data = request.get_json(silent=True) or {}
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
    
    # Filter out empty conversations (id: 34)
    # Most active sessions have at least 1 message (the welcome message)
    # We only want to show ones where the user or AI actually interacted beyond the start
    query = query.filter(DBChatConversation.message_count > 1)
    
    conversations = query.order_by(DBChatConversation.last_message_at.desc()).limit(limit).all()
    
    return jsonify({
        'conversations': [c.to_dict() for c in conversations],
        'total': query.count()
    })


@chatbot_bp.route('/conversations/<conversation_id>', methods=['DELETE'])
@token_required
def delete_conversation(current_user, conversation_id):
    """Delete a conversation (id: 33)"""
    conversation = DBChatConversation.query.get(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    if not current_user.has_access_to_client(conversation.client_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Delete associated messages first (if cascade not set)
    DBChatMessage.query.filter_by(conversation_id=conversation_id).delete()
    
    db.session.delete(conversation)
    db.session.commit()
    
    return jsonify({'success': True})


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
    
    data = request.get_json(silent=True) or {}
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
    
    data = request.get_json(silent=True) or {}
    
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
    
    data = request.get_json(silent=True) or {}
    
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
