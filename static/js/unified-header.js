/**
 * MCP Framework - Unified Header Component
 * Provides consistent navigation across all dashboards
 * 
 * Usage: Include this script and call initUnifiedHeader() after DOM ready
 */

(function() {
    'use strict';
    
    // Configuration
    const HEADER_CONFIG = {
        brandName: 'Karma Marketing',
        brandLogo: null, // Set to URL for custom logo
        notificationPollInterval: 60000, // 1 minute
    };
    
    // Navigation items based on user role
    const NAV_ITEMS = {
        admin: [
            { label: 'Dashboard', href: '/client', icon: 'fa-th-large' },
            { label: 'Clients', href: '/client', icon: 'fa-users' },
            { label: 'Intake', href: '/intake', icon: 'fa-user-plus' },
            { label: 'Admin', href: '/admin', icon: 'fa-cog', active: true },
        ],
        agency: [
            { label: 'Dashboard', href: '/client', icon: 'fa-th-large' },
            { label: 'Clients', href: '/client', icon: 'fa-users' },
            { label: 'Intake', href: '/intake', icon: 'fa-user-plus' },
            { label: 'Reports', href: '/client?tab=reports', icon: 'fa-chart-bar' },
        ],
        client: [
            { label: 'Dashboard', href: '/portal', icon: 'fa-th-large' },
            { label: 'Content', href: '/portal?tab=content', icon: 'fa-file-alt' },
            { label: 'Calendar', href: '/portal?tab=calendar', icon: 'fa-calendar' },
            { label: 'Reports', href: '/portal?tab=reports', icon: 'fa-chart-bar' },
        ]
    };
    
    // Current page detection
    function getCurrentPage() {
        const path = window.location.pathname;
        if (path.includes('admin')) return 'admin';
        if (path.includes('portal')) return 'portal';
        if (path.includes('intake')) return 'intake';
        if (path.includes('client') || path.includes('elite') || path.includes('agency')) return 'client';
        return 'client';
    }
    
    // Get user info from localStorage or API
    function getUserInfo() {
        const stored = localStorage.getItem('mcp_user');
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch (e) {}
        }
        return {
            name: 'User',
            email: 'user@example.com',
            role: 'agency',
            avatar: null
        };
    }
    
    // Get auth token
    function getAuthToken() {
        return localStorage.getItem('auth_token') || localStorage.getItem('AUTH_TOKEN') || '';
    }
    
    // Create header HTML
    function createHeaderHTML(userInfo, currentPage, notifications) {
        const role = userInfo.role || 'agency';
        const navItems = NAV_ITEMS[role] || NAV_ITEMS.agency;
        const unreadCount = notifications.filter(n => !n.read).length;
        
        // Determine active nav item
        const activeHref = '/' + currentPage;
        
        const navHTML = navItems.map(item => {
            const isActive = window.location.pathname === item.href || 
                           (item.href.includes(currentPage) && currentPage !== 'client');
            return `
                <a href="${item.href}" 
                   class="nav-item flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${isActive ? 'bg-white/20 text-white' : 'text-white/70 hover:text-white hover:bg-white/10'}">
                    <i class="fas ${item.icon} text-sm"></i>
                    <span class="hidden md:inline">${item.label}</span>
                </a>
            `;
        }).join('');
        
        const avatarHTML = userInfo.avatar 
            ? `<img src="${userInfo.avatar}" class="w-8 h-8 rounded-full object-cover">`
            : `<div class="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-sm font-bold">
                 ${(userInfo.name || 'U').charAt(0).toUpperCase()}
               </div>`;
        
        return `
            <header id="unified-header" class="unified-header fixed top-0 left-0 right-0 z-50 bg-gradient-to-r from-slate-900 via-purple-900 to-slate-900 border-b border-white/10 shadow-lg">
                <div class="max-w-[1800px] mx-auto px-4 h-16 flex items-center justify-between">
                    <!-- Brand -->
                    <a href="/client" class="flex items-center gap-3 group">
                        ${HEADER_CONFIG.brandLogo 
                            ? `<img src="${HEADER_CONFIG.brandLogo}" class="h-8" alt="${HEADER_CONFIG.brandName}">`
                            : `<div class="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center shadow-lg group-hover:scale-105 transition">
                                 <i class="fas fa-bolt text-white"></i>
                               </div>`
                        }
                        <span class="text-white font-bold text-lg hidden sm:block">${HEADER_CONFIG.brandName}</span>
                    </a>
                    
                    <!-- Navigation -->
                    <nav class="flex items-center gap-1">
                        ${navHTML}
                    </nav>
                    
                    <!-- Right Section -->
                    <div class="flex items-center gap-4">
                        <!-- Search (Desktop) -->
                        <div class="hidden lg:block relative">
                            <input type="text" id="global-search" placeholder="Search..." 
                                   class="w-48 px-4 py-2 pl-10 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 text-sm focus:outline-none focus:border-purple-400 focus:w-64 transition-all">
                            <i class="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-white/50 text-sm"></i>
                        </div>
                        
                        <!-- Notifications -->
                        <div class="relative" id="notification-dropdown">
                            <button onclick="toggleNotifications()" class="relative p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-lg transition">
                                <i class="fas fa-bell text-lg"></i>
                                ${unreadCount > 0 ? `
                                    <span class="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full text-white text-xs flex items-center justify-center font-bold animate-pulse">
                                        ${unreadCount > 9 ? '9+' : unreadCount}
                                    </span>
                                ` : ''}
                            </button>
                            
                            <!-- Dropdown -->
                            <div id="notifications-panel" class="hidden absolute right-0 top-full mt-2 w-80 bg-slate-800 rounded-xl shadow-2xl border border-white/10 overflow-hidden">
                                <div class="p-4 border-b border-white/10 flex items-center justify-between">
                                    <h3 class="font-bold text-white">Notifications</h3>
                                    ${unreadCount > 0 ? `
                                        <button onclick="markAllRead()" class="text-xs text-purple-400 hover:text-purple-300">Mark all read</button>
                                    ` : ''}
                                </div>
                                <div class="max-h-80 overflow-y-auto" id="notifications-list">
                                    ${renderNotifications(notifications)}
                                </div>
                                <a href="/client?tab=settings" class="block p-3 text-center text-sm text-purple-400 hover:bg-white/5 border-t border-white/10">
                                    Notification Settings
                                </a>
                            </div>
                        </div>
                        
                        <!-- User Menu -->
                        <div class="relative" id="user-dropdown">
                            <button onclick="toggleUserMenu()" class="flex items-center gap-3 p-2 rounded-lg hover:bg-white/10 transition">
                                ${avatarHTML}
                                <div class="hidden md:block text-left">
                                    <div class="text-white text-sm font-medium">${userInfo.name || 'User'}</div>
                                    <div class="text-white/50 text-xs">${role.charAt(0).toUpperCase() + role.slice(1)}</div>
                                </div>
                                <i class="fas fa-chevron-down text-white/50 text-xs hidden md:block"></i>
                            </button>
                            
                            <!-- User Dropdown -->
                            <div id="user-menu-panel" class="hidden absolute right-0 top-full mt-2 w-56 bg-slate-800 rounded-xl shadow-2xl border border-white/10 overflow-hidden">
                                <div class="p-4 border-b border-white/10">
                                    <div class="font-medium text-white">${userInfo.name || 'User'}</div>
                                    <div class="text-sm text-white/50">${userInfo.email || ''}</div>
                                </div>
                                <div class="p-2">
                                    <a href="/client?tab=settings" class="flex items-center gap-3 px-3 py-2 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition">
                                        <i class="fas fa-cog w-5"></i> Settings
                                    </a>
                                    <a href="/client?tab=settings" class="flex items-center gap-3 px-3 py-2 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition">
                                        <i class="fas fa-bell w-5"></i> Notifications
                                    </a>
                                    ${role === 'admin' ? `
                                        <a href="/admin" class="flex items-center gap-3 px-3 py-2 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition">
                                            <i class="fas fa-shield-alt w-5"></i> Admin Panel
                                        </a>
                                    ` : ''}
                                    <hr class="my-2 border-white/10">
                                    <button onclick="handleLogout()" class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-red-400 hover:text-red-300 hover:bg-red-500/10 transition">
                                        <i class="fas fa-sign-out-alt w-5"></i> Sign Out
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </header>
            
            <!-- Spacer to prevent content from going under fixed header -->
            <div id="header-spacer" class="h-16"></div>
        `;
    }
    
    // Render notifications list
    function renderNotifications(notifications) {
        if (!notifications || notifications.length === 0) {
            return `
                <div class="p-8 text-center text-white/50">
                    <i class="fas fa-bell-slash text-3xl mb-2"></i>
                    <p>No notifications</p>
                </div>
            `;
        }
        
        return notifications.slice(0, 10).map(n => {
            const timeAgo = getTimeAgo(n.created_at);
            const icon = getNotificationIcon(n.notification_type);
            const isUnread = !n.read;
            
            return `
                <div class="p-4 hover:bg-white/5 cursor-pointer border-b border-white/5 ${isUnread ? 'bg-purple-500/10' : ''}" 
                     onclick="handleNotificationClick('${n.id}')">
                    <div class="flex gap-3">
                        <div class="w-8 h-8 rounded-full ${icon.bg} flex items-center justify-center flex-shrink-0">
                            <i class="${icon.icon} text-white text-sm"></i>
                        </div>
                        <div class="flex-1 min-w-0">
                            <p class="text-sm text-white ${isUnread ? 'font-medium' : ''} line-clamp-2">${n.subject || n.title || 'Notification'}</p>
                            <p class="text-xs text-white/50 mt-1">${timeAgo}</p>
                        </div>
                        ${isUnread ? '<div class="w-2 h-2 rounded-full bg-purple-500 flex-shrink-0 mt-2"></div>' : ''}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    // Get notification icon based on type
    function getNotificationIcon(type) {
        const icons = {
            'content_published': { icon: 'fas fa-check', bg: 'bg-green-500' },
            'content_scheduled': { icon: 'fas fa-clock', bg: 'bg-blue-500' },
            'content_approval_needed': { icon: 'fas fa-exclamation', bg: 'bg-yellow-500' },
            'wordpress_published': { icon: 'fab fa-wordpress', bg: 'bg-blue-600' },
            'wordpress_failed': { icon: 'fas fa-times', bg: 'bg-red-500' },
            'social_published': { icon: 'fas fa-share', bg: 'bg-purple-500' },
            'ranking_improved': { icon: 'fas fa-arrow-up', bg: 'bg-green-500' },
            'ranking_dropped': { icon: 'fas fa-arrow-down', bg: 'bg-red-500' },
            'competitor_new_content': { icon: 'fas fa-eye', bg: 'bg-orange-500' },
        };
        return icons[type] || { icon: 'fas fa-bell', bg: 'bg-gray-500' };
    }
    
    // Time ago helper
    function getTimeAgo(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);
        
        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
        return date.toLocaleDateString();
    }
    
    // Fetch notifications from API
    async function fetchNotifications() {
        const token = getAuthToken();
        if (!token) return [];
        
        try {
            const response = await fetch('/api/notifications/history?limit=10', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const data = await response.json();
                return data.notifications || [];
            }
        } catch (e) {
            console.warn('Failed to fetch notifications:', e);
        }
        return [];
    }
    
    // Toggle notifications panel
    window.toggleNotifications = function() {
        const panel = document.getElementById('notifications-panel');
        const userPanel = document.getElementById('user-menu-panel');
        
        if (userPanel) userPanel.classList.add('hidden');
        if (panel) panel.classList.toggle('hidden');
    };
    
    // Toggle user menu
    window.toggleUserMenu = function() {
        const panel = document.getElementById('user-menu-panel');
        const notifPanel = document.getElementById('notifications-panel');
        
        if (notifPanel) notifPanel.classList.add('hidden');
        if (panel) panel.classList.toggle('hidden');
    };
    
    // Handle notification click
    window.handleNotificationClick = function(notificationId) {
        // Could mark as read and navigate
        console.log('Notification clicked:', notificationId);
        toggleNotifications();
    };
    
    // Mark all notifications as read
    window.markAllRead = async function() {
        const token = getAuthToken();
        if (!token) return;
        
        try {
            await fetch('/api/notifications/mark-all-read', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            // Refresh notifications
            const notifications = await fetchNotifications();
            updateNotificationsList(notifications);
        } catch (e) {
            console.warn('Failed to mark notifications as read:', e);
        }
    };
    
    // Update notifications list
    function updateNotificationsList(notifications) {
        const list = document.getElementById('notifications-list');
        if (list) {
            list.innerHTML = renderNotifications(notifications);
        }
        
        // Update badge
        const unreadCount = notifications.filter(n => !n.read).length;
        const badge = document.querySelector('#notification-dropdown .animate-pulse');
        if (badge) {
            if (unreadCount > 0) {
                badge.textContent = unreadCount > 9 ? '9+' : unreadCount;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
    }
    
    // Handle logout
    window.handleLogout = function() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('AUTH_TOKEN');
        localStorage.removeItem('mcp_user');
        window.location.href = '/';
    };
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('#notification-dropdown')) {
            const panel = document.getElementById('notifications-panel');
            if (panel) panel.classList.add('hidden');
        }
        if (!e.target.closest('#user-dropdown')) {
            const panel = document.getElementById('user-menu-panel');
            if (panel) panel.classList.add('hidden');
        }
    });
    
    // Global search handler
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + K for search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.getElementById('global-search');
            if (searchInput) searchInput.focus();
        }
    });
    
    // Initialize header
    window.initUnifiedHeader = async function(options = {}) {
        // Merge options
        Object.assign(HEADER_CONFIG, options);
        
        const userInfo = getUserInfo();
        const currentPage = getCurrentPage();
        const notifications = await fetchNotifications();
        
        // Create header
        const headerHTML = createHeaderHTML(userInfo, currentPage, notifications);
        
        // Insert at start of body
        document.body.insertAdjacentHTML('afterbegin', headerHTML);
        
        // Poll for notifications
        setInterval(async () => {
            const newNotifications = await fetchNotifications();
            updateNotificationsList(newNotifications);
        }, HEADER_CONFIG.notificationPollInterval);
        
        // Store user info if we have token
        const token = getAuthToken();
        if (token && !localStorage.getItem('mcp_user')) {
            try {
                const response = await fetch('/api/auth/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const userData = await response.json();
                    localStorage.setItem('mcp_user', JSON.stringify(userData));
                }
            } catch (e) {}
        }
        
        console.log('Unified header initialized');
    };
    
    // Auto-init if data attribute present
    if (document.querySelector('[data-unified-header]')) {
        document.addEventListener('DOMContentLoaded', () => initUnifiedHeader());
    }
})();
