/**
 * MCP Accessibility Widget
 * Embeddable ADA compliance widget for client websites
 * 
 * Usage:
 * <script>
 * (function() {
 *     var s = document.createElement('script');
 *     s.src = 'YOUR_MCP_URL/static/accessibility-widget.js';
 *     s.async = true;
 *     s.onload = function() {
 *         MCPAccessibility.init({
 *             clientId: 'YOUR_CLIENT_ID',
 *             apiUrl: 'YOUR_MCP_URL',
 *             position: 'left',      // 'left' or 'right'
 *             color: '#0064fe'        // primary accent color
 *         });
 *     };
 *     document.head.appendChild(s);
 * })();
 * </script>
 */

(function () {
    'use strict';

    if (window.MCPAccessibility && window.MCPAccessibility.initialized) return;

    const A11Y = {
        initialized: false,
        isOpen: false,
        settings: {},
        defaults: {
            position: 'left',
            color: '#0064fe',
            triggerSize: 56,
            zIndex: 999999
        },

        init: function (options) {
            if (this.initialized) return;
            this.options = Object.assign({}, this.defaults, options);
            this.loadSettings();
            this.injectStyles();
            this.createTrigger();
            this.createPanel();
            this.applySettings();
            this.initialized = true;
            window.MCPAccessibility = this;
        },

        // ============= STORAGE =============
        loadSettings: function () {
            try {
                const saved = localStorage.getItem('mcp_a11y_settings');
                this.settings = saved ? JSON.parse(saved) : {};
            } catch (e) {
                this.settings = {};
            }
        },

        saveSettings: function () {
            try {
                localStorage.setItem('mcp_a11y_settings', JSON.stringify(this.settings));
            } catch (e) { }
        },

        resetSettings: function () {
            this.settings = {};
            this.saveSettings();
            this.removeAllAdjustments();
            this.updateToggles();
        },

        // ============= STYLES =============
        injectStyles: function () {
            const color = this.options.color;
            const css = `
                /* Trigger Button */
                .mcp-a11y-trigger {
                    position: fixed;
                    ${this.options.position === 'left' ? 'left: 16px' : 'right: 16px'};
                    bottom: 16px;
                    width: ${this.options.triggerSize}px;
                    height: ${this.options.triggerSize}px;
                    border-radius: 50%;
                    background: ${color};
                    border: none;
                    cursor: pointer;
                    z-index: ${this.options.zIndex};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
                    transition: transform 0.2s, box-shadow 0.2s;
                }
                .mcp-a11y-trigger:hover { transform: scale(1.08); box-shadow: 0 6px 24px rgba(0,0,0,0.35); }
                .mcp-a11y-trigger:focus { outline: 3px solid #fff; outline-offset: 2px; }
                .mcp-a11y-trigger svg { width: 28px; height: 28px; fill: #fff; }

                /* Panel */
                .mcp-a11y-panel {
                    position: fixed;
                    ${this.options.position === 'left' ? 'left: 0' : 'right: 0'};
                    top: 0;
                    width: 380px;
                    max-width: 100vw;
                    height: 100vh;
                    background: #fff;
                    z-index: ${this.options.zIndex + 1};
                    overflow-y: auto;
                    box-shadow: 4px 0 30px rgba(0,0,0,0.2);
                    transform: translateX(${this.options.position === 'left' ? '-100%' : '100%'});
                    transition: transform 0.3s ease;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    color: #1a1a1a;
                    font-size: 14px;
                    line-height: 1.5;
                }
                .mcp-a11y-panel.open {
                    transform: translateX(0);
                }
                .mcp-a11y-panel * { box-sizing: border-box; margin: 0; padding: 0; }

                /* Header */
                .mcp-a11y-header {
                    background: ${color};
                    color: #fff;
                    padding: 20px;
                    position: sticky;
                    top: 0;
                    z-index: 2;
                }
                .mcp-a11y-header h2 { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
                .mcp-a11y-header p { font-size: 12px; opacity: 0.85; }
                .mcp-a11y-close {
                    position: absolute; top: 16px; ${this.options.position === 'left' ? 'right' : 'left'}: 16px;
                    background: rgba(255,255,255,0.2); border: none; color: #fff;
                    width: 32px; height: 32px; border-radius: 50%; cursor: pointer;
                    font-size: 18px; display: flex; align-items: center; justify-content: center;
                    transition: background 0.2s;
                }
                .mcp-a11y-close:hover { background: rgba(255,255,255,0.35); }

                /* Header Actions */
                .mcp-a11y-header-actions {
                    display: flex; gap: 8px; margin-top: 12px;
                }
                .mcp-a11y-header-btn {
                    padding: 6px 14px; border-radius: 20px; border: 1.5px solid rgba(255,255,255,0.6);
                    background: transparent; color: #fff; font-size: 12px; font-weight: 600;
                    cursor: pointer; transition: background 0.2s;
                }
                .mcp-a11y-header-btn:hover { background: rgba(255,255,255,0.15); }

                /* Profiles Section */
                .mcp-a11y-section {
                    padding: 16px 20px;
                    border-bottom: 1px solid #eee;
                }
                .mcp-a11y-section-title {
                    font-size: 15px; font-weight: 600; color: #333; margin-bottom: 12px;
                }

                /* Profile Row */
                .mcp-a11y-profile {
                    display: flex; align-items: center; justify-content: space-between;
                    padding: 10px 0; border-bottom: 1px solid #f0f0f0;
                }
                .mcp-a11y-profile:last-child { border-bottom: none; }
                .mcp-a11y-profile-info { flex: 1; }
                .mcp-a11y-profile-name { font-size: 14px; font-weight: 600; color: #222; }
                .mcp-a11y-profile-desc { font-size: 12px; color: #888; margin-top: 2px; }
                .mcp-a11y-profile-icon { width: 36px; text-align: center; margin-left: 8px; font-size: 18px; color: #666; }

                /* Toggle */
                .mcp-a11y-toggle {
                    display: flex; border-radius: 20px; overflow: hidden; border: 1.5px solid #ddd;
                    margin-right: 12px; flex-shrink: 0;
                }
                .mcp-a11y-toggle button {
                    padding: 5px 12px; font-size: 11px; font-weight: 700; border: none;
                    cursor: pointer; background: #f5f5f5; color: #999; transition: all 0.2s;
                    text-transform: uppercase; letter-spacing: 0.5px;
                }
                .mcp-a11y-toggle button.active {
                    background: ${color}; color: #fff;
                }

                /* Slider Controls */
                .mcp-a11y-slider-row {
                    display: flex; align-items: center; justify-content: space-between;
                    padding: 8px 0;
                }
                .mcp-a11y-slider-label { font-size: 13px; font-weight: 500; color: #333; }
                .mcp-a11y-slider-controls {
                    display: flex; align-items: center; gap: 8px;
                }
                .mcp-a11y-slider-btn {
                    width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #ddd;
                    background: #fff; cursor: pointer; font-size: 16px; font-weight: 700;
                    color: ${color}; display: flex; align-items: center; justify-content: center;
                    transition: all 0.2s;
                }
                .mcp-a11y-slider-btn:hover { background: ${color}; color: #fff; border-color: ${color}; }
                .mcp-a11y-slider-value {
                    font-size: 13px; font-weight: 700; color: ${color}; min-width: 40px; text-align: center;
                }

                /* Color Pickers */
                .mcp-a11y-color-row {
                    display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 0;
                }
                .mcp-a11y-color-btn {
                    width: 36px; height: 36px; border-radius: 50%; border: 3px solid transparent;
                    cursor: pointer; transition: border-color 0.2s, transform 0.15s;
                }
                .mcp-a11y-color-btn:hover { transform: scale(1.1); }
                .mcp-a11y-color-btn.active { border-color: ${color}; transform: scale(1.1); }

                /* Overlay */
                .mcp-a11y-overlay {
                    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
                    z-index: ${this.options.zIndex}; opacity: 0; pointer-events: none;
                    transition: opacity 0.3s;
                }
                .mcp-a11y-overlay.open { opacity: 1; pointer-events: auto; }

                /* Footer */
                .mcp-a11y-footer {
                    padding: 12px 20px; text-align: center; font-size: 11px; color: #bbb;
                    border-top: 1px solid #eee; background: #fafafa;
                }
                .mcp-a11y-footer a { color: ${color}; text-decoration: none; }

                /* Global adjustments applied to body */
                body.mcp-a11y-bigger-text { font-size: 120% !important; }
                body.mcp-a11y-biggest-text { font-size: 140% !important; }
                body.mcp-a11y-dyslexia-font, body.mcp-a11y-dyslexia-font * { font-family: 'OpenDyslexic', Comic Sans MS, sans-serif !important; }
                body.mcp-a11y-readable-font, body.mcp-a11y-readable-font * { font-family: Arial, Helvetica, sans-serif !important; }
                body.mcp-a11y-highlight-links a { outline: 3px solid #ff0 !important; outline-offset: 2px !important; }
                body.mcp-a11y-highlight-links a:focus { outline: 3px solid #f00 !important; }
                body.mcp-a11y-big-cursor, body.mcp-a11y-big-cursor * { cursor: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Cpath d='M4 4 L4 36 L14 26 L24 40 L30 36 L20 22 L34 22 Z' fill='black' stroke='white' stroke-width='2'/%3E%3C/svg%3E") 4 4, auto !important; }
                body.mcp-a11y-stop-animations, body.mcp-a11y-stop-animations * { animation: none !important; transition: none !important; }
                body.mcp-a11y-stop-animations img[src$=".gif"] { visibility: hidden !important; }
                body.mcp-a11y-grayscale { filter: grayscale(100%) !important; }
                body.mcp-a11y-high-contrast { filter: contrast(1.5) !important; }
                body.mcp-a11y-negative-contrast { filter: invert(1) hue-rotate(180deg) !important; }
                body.mcp-a11y-light-bg { background-color: #fff !important; }
                body.mcp-a11y-dark-bg { background-color: #1a1a2e !important; color: #e0e0e0 !important; }
                body.mcp-a11y-dark-bg a { color: #8ab4f8 !important; }
                body.mcp-a11y-dark-bg h1, body.mcp-a11y-dark-bg h2, body.mcp-a11y-dark-bg h3, body.mcp-a11y-dark-bg h4 { color: #fff !important; }
                body.mcp-a11y-line-height-1 { line-height: 1.8 !important; }
                body.mcp-a11y-line-height-1 * { line-height: 1.8 !important; }
                body.mcp-a11y-line-height-2 { line-height: 2.2 !important; }
                body.mcp-a11y-line-height-2 * { line-height: 2.2 !important; }
                body.mcp-a11y-letter-spacing-1 { letter-spacing: 1px !important; }
                body.mcp-a11y-letter-spacing-1 * { letter-spacing: 1px !important; }
                body.mcp-a11y-letter-spacing-2 { letter-spacing: 2.5px !important; }
                body.mcp-a11y-letter-spacing-2 * { letter-spacing: 2.5px !important; }
                body.mcp-a11y-text-align-left, body.mcp-a11y-text-align-left * { text-align: left !important; }
                body.mcp-a11y-hide-images img:not(.mcp-a11y-trigger svg) { opacity: 0.1 !important; }
                body.mcp-a11y-reading-guide .mcp-reading-line {
                    position: fixed; left: 0; right: 0; height: 12px;
                    background: rgba(255, 255, 0, 0.35); pointer-events: none;
                    z-index: ${this.options.zIndex - 1}; transition: top 0.05s;
                }

                @media (max-width: 420px) {
                    .mcp-a11y-panel { width: 100vw; }
                }
            `;
            const style = document.createElement('style');
            style.id = 'mcp-a11y-styles';
            style.textContent = css;
            document.head.appendChild(style);
        },

        // ============= TRIGGER BUTTON =============
        createTrigger: function () {
            const btn = document.createElement('button');
            btn.className = 'mcp-a11y-trigger';
            btn.setAttribute('aria-label', 'Open accessibility options');
            btn.setAttribute('title', 'Accessibility Options');
            btn.innerHTML = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="4.5" r="2.5"/><path d="M12 7.5c-3.5 0-6.5 1-6.5 1l.5 2s2.2-.7 4.5-.9V12l-3.5 8h2.5l2.5-6 2.5 6h2.5l-3.5-8V9.6c2.3.2 4.5.9 4.5.9l.5-2s-3-1-6.5-1z"/></svg>`;
            btn.addEventListener('click', () => this.toggle());
            document.body.appendChild(btn);
            this.triggerEl = btn;
        },

        // ============= PANEL =============
        createPanel: function () {
            // Overlay
            const overlay = document.createElement('div');
            overlay.className = 'mcp-a11y-overlay';
            overlay.addEventListener('click', () => this.close());
            document.body.appendChild(overlay);
            this.overlayEl = overlay;

            // Panel
            const panel = document.createElement('div');
            panel.className = 'mcp-a11y-panel';
            panel.setAttribute('role', 'dialog');
            panel.setAttribute('aria-label', 'Accessibility Adjustments');

            panel.innerHTML = `
                ${this._headerHTML()}
                ${this._profilesHTML()}
                ${this._contentAdjustmentsHTML()}
                ${this._colorAdjustmentsHTML()}
                ${this._orientationHTML()}
                <div class="mcp-a11y-footer">
                    Web Accessibility Widget &bull; <a href="https://www.w3.org/WAI/standards-guidelines/wcag/" target="_blank" rel="noopener">WCAG 2.1</a>
                </div>
            `;

            document.body.appendChild(panel);
            this.panelEl = panel;
            this.bindPanelEvents();
        },

        _headerHTML: function () {
            return `
                <div class="mcp-a11y-header">
                    <button class="mcp-a11y-close" aria-label="Close accessibility panel">&times;</button>
                    <h2>Accessibility Adjustments</h2>
                    <p>Customize your browsing experience</p>
                    <div class="mcp-a11y-header-actions">
                        <button class="mcp-a11y-header-btn" data-action="reset">&#8634; Reset Settings</button>
                        <button class="mcp-a11y-header-btn" data-action="statement">&#9432; Statement</button>
                        <button class="mcp-a11y-header-btn" data-action="hide">&#10005; Hide Interface</button>
                    </div>
                </div>
            `;
        },

        _profilesHTML: function () {
            const profiles = [
                { id: 'seizure-safe', name: 'Seizure Safe Profile', desc: 'Clear flashes & reduces color', icon: '&#9889;' },
                { id: 'vision-impaired', name: 'Vision Impaired Profile', desc: "Enhances website's visuals", icon: '&#128065;' },
                { id: 'adhd-friendly', name: 'ADHD Friendly Profile', desc: 'More focus & fewer distractions', icon: '&#9635;' },
                { id: 'cognitive', name: 'Cognitive Disability Profile', desc: 'Assists with reading & focusing', icon: '&#9881;' },
                { id: 'keyboard-nav', name: 'Keyboard Navigation', desc: 'Use website with the keyboard', icon: '&#10230;' },
                { id: 'screen-reader', name: 'Screen Reader Adjustments', desc: 'Optimize for screen-readers', icon: '&#9776;' },
            ];
            return `
                <div class="mcp-a11y-section">
                    <div class="mcp-a11y-section-title">Choose the right accessibility profile for you</div>
                    ${profiles.map(p => `
                        <div class="mcp-a11y-profile">
                            <div class="mcp-a11y-toggle" data-profile="${p.id}">
                                <button data-val="off" class="${!this.settings[p.id] ? 'active' : ''}">OFF</button>
                                <button data-val="on" class="${this.settings[p.id] ? 'active' : ''}">ON</button>
                            </div>
                            <div class="mcp-a11y-profile-info">
                                <div class="mcp-a11y-profile-name">${p.name}</div>
                                <div class="mcp-a11y-profile-desc">${p.desc}</div>
                            </div>
                            <div class="mcp-a11y-profile-icon">${p.icon}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        },

        _contentAdjustmentsHTML: function () {
            return `
                <div class="mcp-a11y-section">
                    <div class="mcp-a11y-section-title">Content Adjustments</div>

                    <div class="mcp-a11y-slider-row">
                        <span class="mcp-a11y-slider-label">Text Size</span>
                        <div class="mcp-a11y-slider-controls">
                            <button class="mcp-a11y-slider-btn" data-adjust="text-size" data-dir="-1">&#8722;</button>
                            <span class="mcp-a11y-slider-value" data-display="text-size">${this.settings['text-size'] || 0}%</span>
                            <button class="mcp-a11y-slider-btn" data-adjust="text-size" data-dir="1">+</button>
                        </div>
                    </div>

                    <div class="mcp-a11y-slider-row">
                        <span class="mcp-a11y-slider-label">Line Height</span>
                        <div class="mcp-a11y-slider-controls">
                            <button class="mcp-a11y-slider-btn" data-adjust="line-height" data-dir="-1">&#8722;</button>
                            <span class="mcp-a11y-slider-value" data-display="line-height">${this.settings['line-height'] || 0}</span>
                            <button class="mcp-a11y-slider-btn" data-adjust="line-height" data-dir="1">+</button>
                        </div>
                    </div>

                    <div class="mcp-a11y-slider-row">
                        <span class="mcp-a11y-slider-label">Letter Spacing</span>
                        <div class="mcp-a11y-slider-controls">
                            <button class="mcp-a11y-slider-btn" data-adjust="letter-spacing" data-dir="-1">&#8722;</button>
                            <span class="mcp-a11y-slider-value" data-display="letter-spacing">${this.settings['letter-spacing'] || 0}</span>
                            <button class="mcp-a11y-slider-btn" data-adjust="letter-spacing" data-dir="1">+</button>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile" style="padding-top:8px;">
                        <div class="mcp-a11y-toggle" data-profile="readable-font">
                            <button data-val="off" class="${!this.settings['readable-font'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['readable-font'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Readable Font</div>
                            <div class="mcp-a11y-profile-desc">Swap to a legible, dyslexia-friendly font</div>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="highlight-links">
                            <button data-val="off" class="${!this.settings['highlight-links'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['highlight-links'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Highlight Links</div>
                            <div class="mcp-a11y-profile-desc">Underline & outline all links</div>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="stop-animations">
                            <button data-val="off" class="${!this.settings['stop-animations'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['stop-animations'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Stop Animations</div>
                            <div class="mcp-a11y-profile-desc">Pause all moving elements</div>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="reading-guide">
                            <button data-val="off" class="${!this.settings['reading-guide'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['reading-guide'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Reading Guide</div>
                            <div class="mcp-a11y-profile-desc">Highlight line under cursor</div>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="big-cursor">
                            <button data-val="off" class="${!this.settings['big-cursor'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['big-cursor'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Big Cursor</div>
                            <div class="mcp-a11y-profile-desc">Enlarge the mouse pointer</div>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="text-align-left">
                            <button data-val="off" class="${!this.settings['text-align-left'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['text-align-left'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Align Text Left</div>
                            <div class="mcp-a11y-profile-desc">Force all text to left-align</div>
                        </div>
                    </div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="hide-images">
                            <button data-val="off" class="${!this.settings['hide-images'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['hide-images'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Hide Images</div>
                            <div class="mcp-a11y-profile-desc">Reduce visual clutter</div>
                        </div>
                    </div>
                </div>
            `;
        },

        _colorAdjustmentsHTML: function () {
            const current = this.settings['color-mode'] || 'default';
            const modes = [
                { id: 'default', color: '#fff', border: '#ddd', label: 'Default' },
                { id: 'dark', color: '#1a1a2e', border: '#333', label: 'Dark' },
                { id: 'high-contrast', color: '#000', border: '#ff0', label: 'High Contrast' },
                { id: 'negative', color: '#222', border: '#0ff', label: 'Invert' },
                { id: 'grayscale', color: '#888', border: '#666', label: 'Grayscale' },
            ];
            return `
                <div class="mcp-a11y-section">
                    <div class="mcp-a11y-section-title">Color Adjustments</div>
                    <div class="mcp-a11y-color-row">
                        ${modes.map(m => `
                            <button class="mcp-a11y-color-btn ${current === m.id ? 'active' : ''}"
                                data-color-mode="${m.id}"
                                style="background:${m.color}; border-color: ${current === m.id ? this.options.color : m.border}"
                                aria-label="${m.label}"
                                title="${m.label}"></button>
                        `).join('')}
                    </div>
                </div>
            `;
        },

        _orientationHTML: function () {
            return `
                <div class="mcp-a11y-section">
                    <div class="mcp-a11y-section-title">Orientation Adjustments</div>

                    <div class="mcp-a11y-profile">
                        <div class="mcp-a11y-toggle" data-profile="focus-outline">
                            <button data-val="off" class="${!this.settings['focus-outline'] ? 'active' : ''}">OFF</button>
                            <button data-val="on" class="${this.settings['focus-outline'] ? 'active' : ''}">ON</button>
                        </div>
                        <div class="mcp-a11y-profile-info">
                            <div class="mcp-a11y-profile-name">Enhanced Focus</div>
                            <div class="mcp-a11y-profile-desc">Bold outlines on focused elements</div>
                        </div>
                    </div>
                </div>
            `;
        },

        // ============= EVENTS =============
        bindPanelEvents: function () {
            const panel = this.panelEl;

            // Close button
            panel.querySelector('.mcp-a11y-close').addEventListener('click', () => this.close());

            // Header actions
            panel.querySelectorAll('.mcp-a11y-header-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const action = btn.dataset.action;
                    if (action === 'reset') this.resetSettings();
                    if (action === 'hide') { this.close(); this.triggerEl.style.display = 'none'; }
                    if (action === 'statement') this.showStatement();
                });
            });

            // Profile toggles
            panel.querySelectorAll('.mcp-a11y-toggle').forEach(toggle => {
                toggle.querySelectorAll('button').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const profileId = toggle.dataset.profile;
                        const isOn = btn.dataset.val === 'on';
                        this.settings[profileId] = isOn;
                        toggle.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                        btn.classList.add('active');
                        this.saveSettings();
                        this.applySettings();
                    });
                });
            });

            // Slider controls
            panel.querySelectorAll('.mcp-a11y-slider-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const key = btn.dataset.adjust;
                    const dir = parseInt(btn.dataset.dir);
                    const current = this.settings[key] || 0;
                    const newVal = Math.max(0, Math.min(2, current + dir));
                    this.settings[key] = newVal;
                    const display = panel.querySelector(`[data-display="${key}"]`);
                    if (key === 'text-size') display.textContent = (newVal * 20) + '%';
                    else display.textContent = newVal;
                    this.saveSettings();
                    this.applySettings();
                });
            });

            // Color mode buttons
            panel.querySelectorAll('.mcp-a11y-color-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.settings['color-mode'] = btn.dataset.colorMode;
                    panel.querySelectorAll('.mcp-a11y-color-btn').forEach(b => {
                        b.classList.remove('active');
                        b.style.borderColor = b.dataset.colorMode === btn.dataset.colorMode ? this.options.color : '#ddd';
                    });
                    btn.classList.add('active');
                    this.saveSettings();
                    this.applySettings();
                });
            });

            // ESC key
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.isOpen) this.close();
            });
        },

        // ============= TOGGLE/OPEN/CLOSE =============
        toggle: function () {
            this.isOpen ? this.close() : this.open();
        },

        open: function () {
            this.panelEl.classList.add('open');
            this.overlayEl.classList.add('open');
            this.isOpen = true;
            this.panelEl.querySelector('.mcp-a11y-close').focus();
        },

        close: function () {
            this.panelEl.classList.remove('open');
            this.overlayEl.classList.remove('open');
            this.isOpen = false;
            this.triggerEl.focus();
        },

        // ============= APPLY SETTINGS =============
        applySettings: function () {
            this.removeAllAdjustments();
            const s = this.settings;
            const body = document.body;

            // Profiles — each profile sets multiple CSS classes
            if (s['seizure-safe']) {
                body.classList.add('mcp-a11y-stop-animations');
                this.settings['stop-animations'] = true;
            }
            if (s['vision-impaired']) {
                body.classList.add('mcp-a11y-high-contrast', 'mcp-a11y-biggest-text');
                this.settings['text-size'] = 2;
            }
            if (s['adhd-friendly']) {
                body.classList.add('mcp-a11y-stop-animations', 'mcp-a11y-readable-font');
                this.settings['stop-animations'] = true;
                this.settings['readable-font'] = true;
            }
            if (s['cognitive']) {
                body.classList.add('mcp-a11y-readable-font', 'mcp-a11y-highlight-links');
                this.settings['readable-font'] = true;
                this.settings['highlight-links'] = true;
                this.settings['line-height'] = Math.max(this.settings['line-height'] || 0, 1);
            }
            if (s['keyboard-nav']) {
                body.classList.add('mcp-a11y-highlight-links');
                this.enableKeyboardNav();
            }
            if (s['screen-reader']) {
                // Adds ARIA improvements
                this.enhanceScreenReader();
            }

            // Text size
            const textSize = s['text-size'] || 0;
            if (textSize === 1) body.classList.add('mcp-a11y-bigger-text');
            if (textSize >= 2) body.classList.add('mcp-a11y-biggest-text');

            // Line height
            const lh = s['line-height'] || 0;
            if (lh === 1) body.classList.add('mcp-a11y-line-height-1');
            if (lh >= 2) body.classList.add('mcp-a11y-line-height-2');

            // Letter spacing
            const ls = s['letter-spacing'] || 0;
            if (ls === 1) body.classList.add('mcp-a11y-letter-spacing-1');
            if (ls >= 2) body.classList.add('mcp-a11y-letter-spacing-2');

            // Toggleable features
            if (s['readable-font']) body.classList.add('mcp-a11y-readable-font');
            if (s['highlight-links']) body.classList.add('mcp-a11y-highlight-links');
            if (s['stop-animations']) body.classList.add('mcp-a11y-stop-animations');
            if (s['big-cursor']) body.classList.add('mcp-a11y-big-cursor');
            if (s['text-align-left']) body.classList.add('mcp-a11y-text-align-left');
            if (s['hide-images']) body.classList.add('mcp-a11y-hide-images');

            // Reading guide
            if (s['reading-guide']) {
                this.enableReadingGuide();
                body.classList.add('mcp-a11y-reading-guide');
            }

            // Focus outline
            if (s['focus-outline']) this.enableFocusOutline();

            // Color modes
            const colorMode = s['color-mode'] || 'default';
            if (colorMode === 'dark') body.classList.add('mcp-a11y-dark-bg');
            if (colorMode === 'high-contrast') body.classList.add('mcp-a11y-high-contrast');
            if (colorMode === 'negative') body.classList.add('mcp-a11y-negative-contrast');
            if (colorMode === 'grayscale') body.classList.add('mcp-a11y-grayscale');
        },

        removeAllAdjustments: function () {
            const body = document.body;
            const classes = Array.from(body.classList).filter(c => c.startsWith('mcp-a11y-'));
            classes.forEach(c => body.classList.remove(c));

            // Remove reading guide line
            const line = document.querySelector('.mcp-reading-line');
            if (line) line.remove();

            // Remove focus style
            const focusStyle = document.getElementById('mcp-a11y-focus-style');
            if (focusStyle) focusStyle.remove();
        },

        updateToggles: function () {
            if (!this.panelEl) return;
            this.panelEl.querySelectorAll('.mcp-a11y-toggle').forEach(toggle => {
                const id = toggle.dataset.profile;
                const isOn = !!this.settings[id];
                toggle.querySelectorAll('button').forEach(b => {
                    b.classList.toggle('active', (b.dataset.val === 'on') === isOn);
                });
            });
            // Reset sliders
            ['text-size', 'line-height', 'letter-spacing'].forEach(key => {
                const display = this.panelEl.querySelector(`[data-display="${key}"]`);
                if (display) {
                    const val = this.settings[key] || 0;
                    display.textContent = key === 'text-size' ? (val * 20) + '%' : val;
                }
            });
            // Reset color buttons
            this.panelEl.querySelectorAll('.mcp-a11y-color-btn').forEach(b => {
                const isActive = (b.dataset.colorMode === (this.settings['color-mode'] || 'default'));
                b.classList.toggle('active', isActive);
                b.style.borderColor = isActive ? this.options.color : '#ddd';
            });
        },

        // ============= FEATURE HELPERS =============
        enableReadingGuide: function () {
            if (document.querySelector('.mcp-reading-line')) return;
            const line = document.createElement('div');
            line.className = 'mcp-reading-line';
            document.body.appendChild(line);
            document.addEventListener('mousemove', function handler(e) {
                if (!document.body.classList.contains('mcp-a11y-reading-guide')) {
                    line.remove();
                    document.removeEventListener('mousemove', handler);
                    return;
                }
                line.style.top = (e.clientY + 6) + 'px';
            });
        },

        enableKeyboardNav: function () {
            // Make all clickable elements keyboard focusable
            document.querySelectorAll('div[onclick], span[onclick]').forEach(el => {
                if (!el.getAttribute('tabindex')) el.setAttribute('tabindex', '0');
                if (!el.getAttribute('role')) el.setAttribute('role', 'button');
            });
        },

        enableFocusOutline: function () {
            if (document.getElementById('mcp-a11y-focus-style')) return;
            const style = document.createElement('style');
            style.id = 'mcp-a11y-focus-style';
            style.textContent = `
                *:focus {
                    outline: 3px solid ${this.options.color} !important;
                    outline-offset: 3px !important;
                }
            `;
            document.head.appendChild(style);
        },

        enhanceScreenReader: function () {
            // Add role=img to images without alt
            document.querySelectorAll('img:not([alt])').forEach(img => {
                img.setAttribute('alt', '');
                img.setAttribute('role', 'presentation');
            });
            // Add aria-label to icon-only buttons
            document.querySelectorAll('button, a').forEach(el => {
                if (!el.textContent.trim() && !el.getAttribute('aria-label')) {
                    const title = el.getAttribute('title');
                    if (title) el.setAttribute('aria-label', title);
                }
            });
        },

        showStatement: function () {
            alert('Accessibility Statement\n\nThis website uses an accessibility widget to help visitors customize their browsing experience. We are committed to making our website accessible to all users.\n\nIf you encounter any accessibility barriers, please contact us.');
        }
    };

    window.MCPAccessibility = A11Y;
})();
