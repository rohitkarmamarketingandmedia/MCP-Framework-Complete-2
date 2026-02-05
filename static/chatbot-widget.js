/**
 * MCP Chatbot Widget
 * Embeddable AI-powered chatbot for client websites
 * 
 * Usage:
 * <script>
 * (function() {
 *     var script = document.createElement('script');
 *     script.src = 'YOUR_MCP_URL/static/chatbot-widget.js';
 *     script.async = true;
 *     script.onload = function() {
 *         MCPChatbot.init({
 *             chatbotId: 'YOUR_CHATBOT_ID',
 *             apiUrl: 'YOUR_MCP_URL'
 *         });
 *     };
 *     document.head.appendChild(script);
 * })();
 * </script>
 */

(function () {
    'use strict';

    // Prevent double initialization
    if (window.MCPChatbot && window.MCPChatbot.initialized) {
        return;
    }

    const MCPChatbot = {
        initialized: false,
        config: null,
        conversationId: null,
        visitorId: null,
        messages: [],
        isOpen: false,
        isMinimized: false,
        leadCaptured: false,

        init: function (options) {
            if (this.initialized) return;

            this.chatbotId = options.chatbotId;
            this.apiUrl = options.apiUrl.replace(/\/$/, '');
            this.visitorId = this.getVisitorId();

            this.loadConfig().then(() => {
                this.createWidget();
                this.bindEvents();
                this.initialized = true;

                // Auto-open if configured
                if (this.config.auto_open_delay > 0) {
                    setTimeout(() => {
                        if (!this.isOpen) this.open();
                    }, this.config.auto_open_delay * 1000);
                }
            }).catch(err => {
                console.error('MCP Chatbot: Failed to initialize', err);
            });
        },

        getVisitorId: function () {
            let id = localStorage.getItem('mcp_visitor_id');
            if (!id) {
                id = 'v_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
                localStorage.setItem('mcp_visitor_id', id);
            }
            return id;
        },

        loadConfig: async function () {
            const response = await fetch(`${this.apiUrl}/api/chatbot/widget/${this.chatbotId}/config`);
            if (!response.ok) throw new Error('Failed to load config');
            this.config = await response.json();
        },

        createWidget: function () {
            // Check mobile
            if (!this.config.show_on_mobile && window.innerWidth < 768) {
                return;
            }

            // Inject styles
            this.injectStyles();

            // Create container
            const container = document.createElement('div');
            container.id = 'mcp-chatbot-container';
            container.className = `mcp-chatbot-${this.config.position}`;
            container.innerHTML = this.getWidgetHTML();
            document.body.appendChild(container);

            // Cache elements
            this.elements = {
                container: container,
                bubble: container.querySelector('.mcp-chat-bubble'),
                window: container.querySelector('.mcp-chat-window'),
                messages: container.querySelector('.mcp-chat-messages'),
                input: container.querySelector('.mcp-chat-input'),
                sendBtn: container.querySelector('.mcp-chat-send'),
                closeBtn: container.querySelector('.mcp-chat-close'),
                minimizeBtn: container.querySelector('.mcp-chat-minimize'),
                leadForm: container.querySelector('.mcp-lead-form'),
                typingIndicator: container.querySelector('.mcp-typing')
            };

            // Apply branding
            this.applyBranding();
        },

        injectStyles: function () {
            if (document.getElementById('mcp-chatbot-styles')) return;

            const styles = document.createElement('style');
            styles.id = 'mcp-chatbot-styles';
            styles.textContent = `
                #mcp-chatbot-container {
                    position: fixed;
                    z-index: 999999;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                }
                #mcp-chatbot-container * {
                    box-sizing: border-box;
                }
                .mcp-chatbot-bottom-right {
                    bottom: 20px;
                    right: 20px;
                }
                .mcp-chatbot-bottom-left {
                    bottom: 20px;
                    left: 20px;
                }
                .mcp-chat-bubble {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                    transition: transform 0.2s, box-shadow 0.2s;
                }
                .mcp-chat-bubble:hover {
                    transform: scale(1.05);
                    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
                }
                #mcp-chatbot-container svg path {
                    fill: inherit !important;
                }
                .mcp-chat-bubble svg {
                    width: 28px !important;
                    height: 28px !important;
                    fill: #ffffff !important;
                    display: block !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                    transform: none !important;
                }
                .mcp-chat-bubble.mcp-has-unread::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    right: 0;
                    width: 14px;
                    height: 14px;
                    background: #ef4444;
                    border-radius: 50%;
                    border: 2px solid white;
                }
                .mcp-chat-window {
                    position: absolute;
                    bottom: 75px;
                    width: 380px;
                    height: 520px;
                    background: white;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    display: none;
                    flex-direction: column;
                    overflow: hidden;
                }
                .mcp-chatbot-bottom-right .mcp-chat-window {
                    right: 0;
                }
                .mcp-chatbot-bottom-left .mcp-chat-window {
                    left: 0;
                }
                .mcp-chat-window.mcp-open {
                    display: flex;
                    animation: mcp-slideUp 0.3s ease;
                }
                @keyframes mcp-slideUp {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .mcp-chat-header {
                    padding: 16px 20px;
                    color: white;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }
                .mcp-chat-avatar {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: rgba(255,255,255,0.2);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    overflow: hidden;
                }
                .mcp-chat-avatar img {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }
                .mcp-chat-avatar svg {
                    width: 24px !important;
                    height: 24px !important;
                    fill: #ffffff !important;
                    display: block !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                    transform: none !important;
                }
                .mcp-chat-title {
                    flex: 1;
                }
                .mcp-chat-title h4 {
                    margin: 0;
                    font-size: 16px;
                    font-weight: 600;
                }
                .mcp-chat-title span {
                    font-size: 12px;
                    opacity: 0.8;
                }
                .mcp-chat-controls {
                    display: flex;
                    gap: 8px;
                }
                .mcp-chat-controls button {
                    background: rgba(255,255,255,0.2) !important;
                    border: none !important;
                    width: 32px !important;
                    height: 32px !important;
                    min-width: 32px !important;
                    min-height: 32px !important;
                    border-radius: 8px !important;
                    cursor: pointer !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    transition: background 0.2s !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                }
                .mcp-chat-controls button:hover {
                    background: rgba(255,255,255,0.3) !important;
                }
                .mcp-chat-controls button svg {
                    width: 18px !important;
                    height: 18px !important;
                    fill: #ffffff !important;
                    display: block !important;
                    pointer-events: none !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                    transform: none !important;
                }
                .mcp-chat-messages {
                    flex: 1;
                    overflow-y: auto;
                    padding: 16px;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                .mcp-message {
                    max-width: 85%;
                    padding: 12px 16px;
                    border-radius: 16px;
                    font-size: 14px;
                    line-height: 1.5;
                    animation: mcp-fadeIn 0.2s ease;
                }
                @keyframes mcp-fadeIn {
                    from { opacity: 0; transform: translateY(5px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .mcp-message-user {
                    align-self: flex-end;
                    color: white;
                    border-bottom-right-radius: 4px;
                }
                .mcp-message-assistant {
                    align-self: flex-start;
                    background: #f1f5f9;
                    color: #1e293b;
                    border-bottom-left-radius: 4px;
                }
                .mcp-typing {
                    display: none;
                    align-self: flex-start;
                    padding: 12px 16px;
                    background: #f1f5f9;
                    border-radius: 16px;
                    border-bottom-left-radius: 4px;
                }
                .mcp-typing.mcp-show {
                    display: flex;
                    gap: 4px;
                }
                .mcp-typing span {
                    width: 8px;
                    height: 8px;
                    background: #94a3b8;
                    border-radius: 50%;
                    animation: mcp-bounce 1.4s infinite;
                }
                .mcp-typing span:nth-child(2) { animation-delay: 0.2s; }
                .mcp-typing span:nth-child(3) { animation-delay: 0.4s; }
                @keyframes mcp-bounce {
                    0%, 60%, 100% { transform: translateY(0); }
                    30% { transform: translateY(-4px); }
                }
                .mcp-chat-footer {
                    padding: 16px;
                    border-top: 1px solid #e2e8f0;
                    display: flex;
                    gap: 12px;
                }
                .mcp-chat-input {
                    flex: 1;
                    padding: 12px 16px;
                    border: 1px solid #e2e8f0;
                    border-radius: 24px;
                    font-size: 14px;
                    outline: none;
                    transition: border-color 0.2s;
                }
                .mcp-chat-input:focus {
                    border-color: #3b82f6;
                }
                .mcp-chat-send {
                    width: 44px !important;
                    height: 44px !important;
                    min-width: 44px !important;
                    min-height: 44px !important;
                    border-radius: 50% !important;
                    border: none !important;
                    cursor: pointer !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    transition: transform 0.2s !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                }
                .mcp-chat-send:hover {
                    transform: scale(1.05) !important;
                }
                .mcp-chat-send:disabled {
                    opacity: 0.5 !important;
                    cursor: not-allowed !important;
                }
                .mcp-chat-send svg {
                    width: 20px !important;
                    height: 20px !important;
                    fill: #ffffff !important;
                    display: block !important;
                    pointer-events: none !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                    transform: none !important;
                }
                .mcp-lead-form {
                    display: none;
                    padding: 16px;
                    background: #f8fafc;
                    border-top: 1px solid #e2e8f0;
                }
                .mcp-lead-form.mcp-show {
                    display: block;
                }
                .mcp-lead-form h5 {
                    margin: 0 0 12px;
                    font-size: 14px;
                    color: #1e293b;
                }
                .mcp-lead-form input {
                    width: 100%;
                    padding: 10px 12px;
                    margin-bottom: 8px;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    font-size: 14px;
                }
                .mcp-lead-form button {
                    width: 100% !important;
                    padding: 10px !important;
                    border: none !important;
                    border-radius: 8px !important;
                    font-size: 14px !important;
                    font-weight: 500 !important;
                    color: white !important;
                    cursor: pointer !important;
                }
                .mcp-powered {
                    text-align: center;
                    padding: 8px;
                    font-size: 11px;
                    color: #94a3b8;
                }
                .mcp-powered a {
                    color: #64748b;
                    text-decoration: none;
                }
                @media (max-width: 480px) {
                    .mcp-chat-window {
                        width: calc(100vw - 20px) !important;
                        height: calc(100vh - 100px) !important;
                        max-height: 80vh !important;
                        bottom: 70px !important;
                    }
                    .mcp-chatbot-bottom-right .mcp-chat-window,
                    .mcp-chatbot-bottom-left .mcp-chat-window {
                        right: 10px !important;
                        left: 10px !important;
                    }
                }
            `;
            document.head.appendChild(styles);
        },

        getWidgetHTML: function () {
            return `
                <div class="mcp-chat-bubble" title="Chat with us">
                    <svg viewBox="0 0 24 24" width="28" height="28"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h10v2H7zm0-4h10v2H7z"/></svg>
                </div>
                <div class="mcp-chat-window">
                    <div class="mcp-chat-header">
                        <div class="mcp-chat-avatar">
                            ${this.config.avatar_url
                    ? `<img src="${this.config.avatar_url}" alt="Avatar">`
                    : '<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/></svg>'
                }
                        </div>
                        <div class="mcp-chat-title">
                            <h4>${this.escapeHtml(this.config.name)}</h4>
                            <span>Online now</span>
                        </div>
                        <div class="mcp-chat-controls">
                            <button class="mcp-chat-minimize" title="Minimize">
                                <svg viewBox="0 0 24 24" width="18" height="18"><path d="M19 13H5v-2h14v2z"/></svg>
                            </button>
                            <button class="mcp-chat-close" title="Close">
                                <svg viewBox="0 0 24 24" width="18" height="18"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="mcp-chat-messages"></div>
                    <div class="mcp-typing">
                        <span></span><span></span><span></span>
                    </div>
                    <div class="mcp-lead-form">
                        <h5>📬 Get in touch</h5>
                        ${this.config.collect_name ? '<input type="text" placeholder="Your name" class="mcp-lead-name">' : ''}
                        ${this.config.collect_email ? '<input type="email" placeholder="Email address" class="mcp-lead-email">' : ''}
                        ${this.config.collect_phone ? '<input type="tel" placeholder="Phone number" class="mcp-lead-phone">' : ''}
                        <textarea placeholder="Message (optional)" class="mcp-lead-message" style="width:100%; padding:10px; border:1px solid #e2e8f0; border-radius:8px; font-size:14px; margin-bottom:8px; resize:none; height:60px;"></textarea>
                        <button class="mcp-lead-submit">Submit</button>
                    </div>
                    <div class="mcp-chat-footer">
                        <input type="text" class="mcp-chat-input" placeholder="${this.escapeHtml(this.config.placeholder_text)}">
                        <button class="mcp-chat-send" title="Send message">
                            <svg viewBox="0 0 24 24" width="20" height="20"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        </button>
                    </div>
                    <div class="mcp-powered">
                        Powered by <a href="https://karmamarketingandmedia.com" target="_blank">Karma Marketing</a>
                    </div>
                </div>
            `;
        },

        applyBranding: function () {
            const primary = this.config.primary_color;
            const secondary = this.config.secondary_color || primary;

            this.elements.bubble.style.background = `linear-gradient(135deg, ${primary}, ${secondary})`;
            this.elements.window.querySelector('.mcp-chat-header').style.background =
                `linear-gradient(135deg, ${primary}, ${secondary})`;

            const userMessages = this.elements.messages.querySelectorAll('.mcp-message-user');
            userMessages.forEach(msg => {
                msg.style.background = `linear-gradient(135deg, ${primary}, ${secondary})`;
            });

            this.elements.sendBtn.style.setProperty('background', primary, 'important');

            const leadBtn = this.elements.leadForm.querySelector('button');
            if (leadBtn) leadBtn.style.setProperty('background', primary, 'important');
        },

        bindEvents: function () {
            // Bubble click
            this.elements.bubble.addEventListener('click', () => this.toggle());

            // Close button
            this.elements.closeBtn.addEventListener('click', () => this.close());

            // Minimize button
            this.elements.minimizeBtn.addEventListener('click', () => this.close());

            // Send message
            this.elements.sendBtn.addEventListener('click', () => this.sendMessage());

            // Enter key
            this.elements.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.sendMessage();
            });

            // Lead form submit
            const submitBtn = this.elements.leadForm.querySelector('.mcp-lead-submit');
            if (submitBtn) {
                submitBtn.addEventListener('click', () => this.submitLead());
            }
        },

        toggle: function () {
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        },

        open: async function () {
            this.isOpen = true;
            this.elements.window.classList.add('mcp-open');
            this.elements.bubble.classList.remove('mcp-has-unread');

            // Start conversation if needed
            if (!this.conversationId) {
                await this.startConversation();
            }

            // Focus input
            setTimeout(() => this.elements.input.focus(), 300);
        },

        close: function () {
            this.isOpen = false;
            this.elements.window.classList.remove('mcp-open');
        },

        startConversation: async function () {
            try {
                const response = await fetch(`${this.apiUrl}/api/chatbot/widget/${this.chatbotId}/start`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        visitor_id: this.visitorId,
                        page_url: window.location.href,
                        page_title: document.title,
                        referrer: document.referrer
                    })
                });

                if (!response.ok) throw new Error('Failed to start conversation');

                const data = await response.json();
                this.conversationId = data.conversation_id;
                this.messages = data.messages || [];

                // Render messages
                this.messages.forEach(msg => this.renderMessage(msg));

            } catch (err) {
                console.error('MCP Chatbot: Failed to start conversation', err);
                this.renderMessage({
                    role: 'assistant',
                    content: this.config.welcome_message
                });
            }
        },

        sendMessage: async function () {
            const content = this.elements.input.value.trim();
            if (!content) return;

            // Clear input
            this.elements.input.value = '';

            // Add user message
            this.renderMessage({ role: 'user', content });

            // Show typing indicator
            this.showTyping();

            try {
                const response = await fetch(`${this.apiUrl}/api/chatbot/widget/${this.chatbotId}/message`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        conversation_id: this.conversationId,
                        message: content
                    })
                });

                if (!response.ok) throw new Error('Failed to send message');

                const data = await response.json();

                // Hide typing
                this.hideTyping();

                // Add assistant response
                this.renderMessage(data.message);

                // Show lead form if needed
                if (data.should_capture_lead && !this.leadCaptured) {
                    this.showLeadForm();
                }

            } catch (err) {
                console.error('MCP Chatbot: Failed to send message', err);
                this.hideTyping();
                this.renderMessage({
                    role: 'assistant',
                    content: "I'm having trouble responding right now. Please try again or leave your contact info!"
                });
            }
        },

        renderMessage: function (msg) {
            const div = document.createElement('div');
            div.className = `mcp-message mcp-message-${msg.role}`;
            div.textContent = msg.content;

            if (msg.role === 'user') {
                div.style.background = `linear-gradient(135deg, ${this.config.primary_color}, ${this.config.secondary_color || this.config.primary_color})`;
            }

            this.elements.messages.appendChild(div);
            this.scrollToBottom();
        },

        showTyping: function () {
            this.elements.typingIndicator.classList.add('mcp-show');
            this.scrollToBottom();
        },

        hideTyping: function () {
            this.elements.typingIndicator.classList.remove('mcp-show');
        },

        scrollToBottom: function () {
            this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
        },

        showLeadForm: function () {
            this.elements.leadForm.classList.add('mcp-show');
        },

        hideLeadForm: function () {
            this.elements.leadForm.classList.remove('mcp-show');
        },

        submitLead: async function () {
            const nameInput = this.elements.leadForm.querySelector('.mcp-lead-name');
            const emailInput = this.elements.leadForm.querySelector('.mcp-lead-email');
            const phoneInput = this.elements.leadForm.querySelector('.mcp-lead-phone');
            const messageInput = this.elements.leadForm.querySelector('.mcp-lead-message');

            const data = {
                conversation_id: this.conversationId,
                name: nameInput ? nameInput.value.trim() : '',
                email: emailInput ? emailInput.value.trim() : '',
                phone: phoneInput ? phoneInput.value.trim() : '',
                message: messageInput ? messageInput.value.trim() : ''
            };

            // Validate
            if (!data.name && !data.email && !data.phone) {
                alert('Please fill in at least one field');
                return;
            }

            try {
                const response = await fetch(`${this.apiUrl}/api/chatbot/widget/${this.chatbotId}/lead`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                this.leadCaptured = true;
                this.hideLeadForm();

                // Show thank you message
                this.renderMessage({
                    role: 'assistant',
                    content: result.message || "Thank you! We'll be in touch soon."
                });

            } catch (err) {
                console.error('MCP Chatbot: Failed to submit lead', err);
                alert('Failed to submit. Please try again.');
            }
        },

        escapeHtml: function (text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    };

    // Expose to window
    window.MCPChatbot = MCPChatbot;

})();
