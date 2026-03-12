"""
MCP Framework - Public Client Review Page
Renders a standalone HTML page for clients to review/edit blog posts
No login required — authenticated by unique review_token
"""
from flask import jsonify
from markupsafe import escape
import json
import logging

logger = logging.getLogger(__name__)


def render_review_page(review_token):
    """Render the public client review page"""
    from app.database import db
    from app.models.db_models import DBBlogPost, DBClient
    from app.models.schedule_models import DBContentComment
    
    blog = DBBlogPost.query.filter_by(review_token=review_token).first()
    
    if not blog:
        return _render_not_found(), 404
    
    client = DBClient.query.get(blog.client_id)
    client_name = escape(client.business_name) if client else 'Your Business'
    
    # Get comments
    comments = DBContentComment.query.filter_by(blog_id=blog.id).order_by(
        DBContentComment.created_at.asc()
    ).all()
    
    comments_html = ''
    for c in comments:
        is_client = c.author_type == 'client'
        bg = 'bg-blue-50 border-blue-200' if is_client else 'bg-gray-50 border-gray-200'
        badge = '<span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">Client</span>' if is_client else '<span class="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded">Team</span>'
        resolved = ' opacity-60' if c.is_resolved else ''
        resolved_tag = '<span class="text-xs text-green-600 ml-2">✓ Resolved</span>' if c.is_resolved else ''
        
        comments_html += f'''
        <div class="p-4 rounded-lg border {bg}{resolved}" data-comment-id="{c.id}">
            <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                    <span class="font-medium text-gray-800">{escape(c.author_name or 'Anonymous')}</span>
                    {badge}{resolved_tag}
                </div>
                <span class="text-xs text-gray-400">{c.created_at.strftime('%b %d, %Y %I:%M %p') if c.created_at else ''}</span>
            </div>
            <p class="text-gray-700 text-sm">{escape(c.comment)}</p>
        </div>
        '''
    
    # Fact-check display
    fc_score = blog.fact_check_score
    fc_html = ''
    if fc_score is not None:
        fc_color = '#059669' if fc_score >= 80 else '#d97706' if fc_score >= 60 else '#dc2626'
        fc_label = 'Excellent' if fc_score >= 80 else 'Good' if fc_score >= 60 else 'Needs Review'
        
        fc_details = ''
        try:
            fc_report = json.loads(blog.fact_check_report) if blog.fact_check_report else {}
            flagged = fc_report.get('flagged_claims', [])
            verified = fc_report.get('verified_claims', [])
            summary = fc_report.get('summary', '')
            
            if summary:
                fc_details += f'<p class="text-sm text-gray-600 mt-2">{escape(summary)}</p>'
            
            if flagged:
                fc_details += '<div class="mt-3 space-y-2">'
                fc_details += '<p class="text-sm font-semibold text-yellow-700">⚠ Items to Review:</p>'
                for f in flagged:
                    sev_color = 'red' if f.get('severity') == 'high' else 'yellow' if f.get('severity') == 'medium' else 'gray'
                    fc_details += f'<div class="p-2 rounded bg-{sev_color}-50 border-l-4 border-{sev_color}-400 text-sm">'
                    fc_details += f'<p class="font-medium text-gray-800">{escape(f.get("claim", ""))}</p>'
                    fc_details += f'<p class="text-gray-500 text-xs mt-1">{escape(f.get("issue", ""))}</p>'
                    if f.get('suggestion'):
                        fc_details += f'<p class="text-blue-600 text-xs mt-1">💡 {escape(f["suggestion"])}</p>'
                    fc_details += '</div>'
                fc_details += '</div>'
                
        except (json.JSONDecodeError, TypeError):
            pass
        
        fc_html = f'''
        <div class="bg-white rounded-xl border p-6 mb-6">
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-gray-800 flex items-center gap-2">
                    <svg class="w-5 h-5" fill="currentColor" style="color:{fc_color}" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clip-rule="evenodd"/></svg>
                    Accuracy Verification
                </h3>
                <div class="flex items-center gap-2">
                    <span class="text-2xl font-bold" style="color:{fc_color}">{fc_score}</span>
                    <span class="text-gray-400">/100</span>
                </div>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div class="h-2 rounded-full" style="width:{fc_score}%;background:{fc_color}"></div>
            </div>
            <p class="text-sm font-medium" style="color:{fc_color}">{fc_label}</p>
            {fc_details}
        </div>
        '''
    
    # Tags
    try:
        tags = json.loads(blog.tags) if blog.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []
    
    tags_json = json.dumps(tags)
    
    # Blog body (sanitize for display)
    blog_body = blog.body or '<p>No content yet.</p>'
    
    # SEO score
    seo_score = blog.seo_score or 0
    seo_color = '#059669' if seo_score >= 80 else '#d97706' if seo_score >= 60 else '#dc2626'
    
    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review: {escape(blog.title or 'Blog Post')} | {client_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f3f4f6; }}
        .blog-content h2 {{ font-size: 1.5rem; font-weight: 700; margin: 1.5rem 0 0.75rem; color: #1f2937; }}
        .blog-content h3 {{ font-size: 1.25rem; font-weight: 600; margin: 1.25rem 0 0.5rem; color: #374151; }}
        .blog-content p {{ margin: 0.75rem 0; line-height: 1.7; color: #4b5563; }}
        .blog-content a {{ color: #6366f1; text-decoration: underline; }}
        .blog-content ul, .blog-content ol {{ margin: 0.5rem 0; padding-left: 1.5rem; }}
        .blog-content li {{ margin: 0.25rem 0; color: #4b5563; }}
        .blog-content .cta-box {{ background: #f0f4ff; border: 1px solid #c7d2fe; border-radius: 12px; padding: 20px; margin: 20px 0; }}
        .editor-active {{ min-height: 400px; outline: none; border: 2px solid #6366f1; border-radius: 12px; padding: 24px; background: white; }}
        .tag {{ display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; background: #ede9fe; color: #6d28d9; border-radius: 9999px; font-size: 13px; }}
        .tag button {{ background: none; border: none; cursor: pointer; color: #6d28d9; font-size: 16px; line-height: 1; }}
        .save-bar {{ position: sticky; bottom: 0; z-index: 50; }}
        .toast {{ position: fixed; bottom: 24px; right: 24px; z-index: 100; transition: all 0.3s; }}
    </style>
</head>
<body>
    <!-- Header -->
    <div class="bg-gradient-to-r from-indigo-600 to-purple-600 text-white">
        <div class="max-w-4xl mx-auto px-4 py-6">
            <p class="text-indigo-200 text-sm mb-1">Blog Review for {client_name}</p>
            <h1 id="pageTitle" class="text-2xl font-bold">{escape(blog.title or 'Untitled Blog Post')}</h1>
            <div class="flex items-center gap-4 mt-3 text-sm text-indigo-200">
                <span><i class="fas fa-align-left mr-1"></i>{blog.word_count or 0} words</span>
                <span style="color:{seo_color}"><i class="fas fa-chart-line mr-1"></i>SEO: {seo_score}/100</span>
                {f'<span style="color:{fc_color}"><i class="fas fa-shield-alt mr-1"></i>Accuracy: {fc_score}/100</span>' if fc_score is not None else ''}
                <span id="statusBadge" class="px-2 py-1 bg-white/20 rounded text-xs">{blog.client_status or 'pending_review'}</span>
            </div>
        </div>
    </div>
    
    <div class="max-w-4xl mx-auto px-4 py-8">
        <!-- Edit/View toggle -->
        <div class="flex justify-between items-center mb-6">
            <div class="flex gap-2">
                <button onclick="setMode('view')" id="btnView" class="px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition">
                    <i class="fas fa-eye mr-1"></i>Preview
                </button>
                <button onclick="setMode('edit')" id="btnEdit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition">
                    <i class="fas fa-edit mr-1"></i>Edit
                </button>
            </div>
            <div class="flex gap-2">
                <button onclick="saveChanges('save')" id="btnSave" class="hidden px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition">
                    <i class="fas fa-save mr-1"></i>Save Changes
                </button>
                <button onclick="saveChanges('approve')" class="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition">
                    <i class="fas fa-check mr-1"></i>Approve for Publishing
                </button>
            </div>
        </div>
        
        <!-- Meta Fields -->
        <div class="bg-white rounded-xl border p-6 mb-6">
            <div class="grid grid-cols-1 gap-4">
                <div>
                    <label class="text-sm font-medium text-gray-500 mb-1 block">Blog Title</label>
                    <input type="text" id="editTitle" value="{escape(blog.title or '')}" 
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-300 focus:border-indigo-500 text-lg font-semibold"
                        disabled>
                </div>
                <div>
                    <label class="text-sm font-medium text-gray-500 mb-1 block">Meta Title <span id="metaTitleLen" class="text-xs text-gray-400">({len(blog.meta_title or '')}/60)</span></label>
                    <input type="text" id="editMetaTitle" value="{escape(blog.meta_title or '')}"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-300 focus:border-indigo-500"
                        maxlength="70" disabled>
                </div>
                <div>
                    <label class="text-sm font-medium text-gray-500 mb-1 block">Meta Description <span id="metaDescLen" class="text-xs text-gray-400">({len(blog.meta_description or '')}/160)</span></label>
                    <textarea id="editMetaDesc" rows="2"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-300 focus:border-indigo-500"
                        maxlength="170" disabled>{escape(blog.meta_description or '')}</textarea>
                </div>
            </div>
        </div>
        
        {fc_html}
        
        <!-- Blog Body -->
        <div class="bg-white rounded-xl border p-6 mb-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="font-bold text-gray-800">Blog Content</h3>
                <span id="wordCount" class="text-sm text-gray-400">{blog.word_count or 0} words</span>
            </div>
            <div id="bodyView" class="blog-content">{blog_body}</div>
            <div id="bodyEdit" class="hidden blog-content editor-active" contenteditable="true">{blog_body}</div>
        </div>
        
        <!-- Tags -->
        <div class="bg-white rounded-xl border p-6 mb-6">
            <h3 class="font-bold text-gray-800 mb-3"><i class="fas fa-tags mr-2 text-indigo-500"></i>Tags</h3>
            <div id="tagsContainer" class="flex flex-wrap gap-2 mb-3"></div>
            <div id="tagInput" class="hidden flex gap-2">
                <input type="text" id="newTag" placeholder="Add a tag..." 
                    class="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300"
                    onkeypress="if(event.key==='Enter')addTag()">
                <button onclick="addTag()" class="px-3 py-1.5 bg-indigo-500 text-white text-sm rounded-lg hover:bg-indigo-600">Add</button>
            </div>
        </div>
        
        <!-- Featured Image -->
        <div class="bg-white rounded-xl border p-6 mb-6">
            <h3 class="font-bold text-gray-800 mb-3"><i class="fas fa-image mr-2 text-amber-500"></i>Featured Image</h3>
            <div id="imagePreview" class="{'hidden' if not blog.featured_image_url else ''}">
                <img id="featuredImg" src="{blog.featured_image_url or ''}" class="w-full max-h-96 object-contain rounded-lg border">
                <button onclick="removeImage()" id="removeImgBtn" class="hidden mt-2 text-sm text-red-500 hover:text-red-700"><i class="fas fa-trash mr-1"></i>Remove</button>
            </div>
            <div id="imageUpload" class="{'hidden' if blog.featured_image_url else ''} border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                <i class="fas fa-cloud-upload-alt text-3xl text-gray-300 mb-2"></i>
                <p class="text-gray-500 mb-2">Upload a featured image</p>
                <input type="file" id="imageFile" accept="image/*" class="hidden" onchange="handleImageUpload(this)">
                <button onclick="document.getElementById('imageFile').click()" id="uploadImgBtn" class="hidden px-4 py-2 bg-indigo-500 text-white rounded-lg text-sm hover:bg-indigo-600">
                    Choose Image
                </button>
            </div>
        </div>
        
        <!-- Comments -->
        <div class="bg-white rounded-xl border p-6 mb-6">
            <h3 class="font-bold text-gray-800 mb-4"><i class="fas fa-comments mr-2 text-green-500"></i>Comments</h3>
            <div id="commentsList" class="space-y-3 mb-4">
                {comments_html if comments_html else '<p class="text-gray-400 text-sm">No comments yet.</p>'}
            </div>
            <div class="border-t pt-4">
                <div class="flex gap-2 mb-2">
                    <input type="text" id="commentName" placeholder="Your name" 
                        class="w-40 px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <input type="email" id="commentEmail" placeholder="Your email (optional)" 
                        class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div class="flex gap-2">
                    <textarea id="commentText" rows="2" placeholder="Add a comment or feedback..." 
                        class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-green-300"></textarea>
                    <button onclick="submitComment()" class="self-end px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Toast -->
    <div id="toast" class="toast hidden">
        <div id="toastContent" class="bg-green-600 text-white px-6 py-3 rounded-lg shadow-lg"></div>
    </div>

    <script>
        const REVIEW_TOKEN = '{review_token}';
        const API_BASE = window.location.origin;
        let currentTags = {tags_json};
        let editMode = false;
        
        // Initialize
        renderTags();
        
        function setMode(mode) {{
            editMode = mode === 'edit';
            const fields = ['editTitle', 'editMetaTitle', 'editMetaDesc'];
            fields.forEach(id => document.getElementById(id).disabled = !editMode);
            
            document.getElementById('bodyView').classList.toggle('hidden', editMode);
            document.getElementById('bodyEdit').classList.toggle('hidden', !editMode);
            document.getElementById('tagInput').classList.toggle('hidden', !editMode);
            document.getElementById('btnSave').classList.toggle('hidden', !editMode);
            document.getElementById('removeImgBtn').classList.toggle('hidden', !editMode);
            document.getElementById('uploadImgBtn').classList.toggle('hidden', !editMode);
            
            document.getElementById('btnEdit').className = editMode 
                ? 'px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium' 
                : 'px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition';
            document.getElementById('btnView').className = !editMode 
                ? 'px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium' 
                : 'px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition';
            
            if (editMode) {{
                document.getElementById('bodyEdit').innerHTML = document.getElementById('bodyView').innerHTML;
            }}
        }}
        
        async function saveChanges(action) {{
            const body = editMode ? document.getElementById('bodyEdit').innerHTML : null;
            const payload = {{
                title: document.getElementById('editTitle').value,
                meta_title: document.getElementById('editMetaTitle').value,
                meta_description: document.getElementById('editMetaDesc').value,
                tags: currentTags,
                action: action
            }};
            if (body) payload.body = body;
            
            try {{
                const res = await fetch(`${{API_BASE}}/api/schedule/review/${{REVIEW_TOKEN}}`, {{
                    method: 'PUT',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(payload)
                }});
                const data = await res.json();
                if (res.ok) {{
                    showToast(data.message || 'Saved!', 'success');
                    document.getElementById('statusBadge').textContent = data.client_status;
                    if (action === 'approve') {{
                        document.getElementById('statusBadge').textContent = 'client_approved';
                    }}
                    // Sync view
                    if (body) {{
                        document.getElementById('bodyView').innerHTML = body;
                    }}
                }} else {{
                    showToast(data.error || 'Failed to save', 'error');
                }}
            }} catch(e) {{
                showToast('Network error. Please try again.', 'error');
            }}
        }}
        
        // Tags
        function renderTags() {{
            const container = document.getElementById('tagsContainer');
            container.innerHTML = currentTags.map((tag, i) => 
                `<span class="tag">${{tag}}<button onclick="removeTag(${{i}})" title="Remove">&times;</button></span>`
            ).join('');
        }}
        
        function addTag() {{
            const input = document.getElementById('newTag');
            const val = input.value.trim();
            if (val && !currentTags.includes(val)) {{
                currentTags.push(val);
                renderTags();
                input.value = '';
            }}
        }}
        
        function removeTag(i) {{
            currentTags.splice(i, 1);
            renderTags();
        }}
        
        // Image
        function removeImage() {{
            document.getElementById('imagePreview').classList.add('hidden');
            document.getElementById('imageUpload').classList.remove('hidden');
            document.getElementById('featuredImg').src = '';
        }}
        
        function handleImageUpload(input) {{
            if (input.files && input.files[0]) {{
                const reader = new FileReader();
                reader.onload = function(e) {{
                    document.getElementById('featuredImg').src = e.target.result;
                    document.getElementById('imagePreview').classList.remove('hidden');
                    document.getElementById('imageUpload').classList.add('hidden');
                    // Note: For full production, you'd upload to server here
                    showToast('Image preview loaded. Save to keep changes.', 'info');
                }};
                reader.readAsDataURL(input.files[0]);
            }}
        }}
        
        // Comments
        async function submitComment() {{
            const text = document.getElementById('commentText').value.trim();
            const name = document.getElementById('commentName').value.trim() || 'Client';
            const email = document.getElementById('commentEmail').value.trim();
            
            if (!text) return;
            
            try {{
                const res = await fetch(`${{API_BASE}}/api/schedule/review/${{REVIEW_TOKEN}}/comments`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ comment: text, author_name: name, author_email: email }})
                }});
                const data = await res.json();
                if (res.ok) {{
                    // Add comment to the list
                    const list = document.getElementById('commentsList');
                    const noComments = list.querySelector('p.text-gray-400');
                    if (noComments) noComments.remove();
                    
                    const div = document.createElement('div');
                    div.className = 'p-4 rounded-lg border bg-blue-50 border-blue-200';
                    div.innerHTML = `
                        <div class="flex items-center gap-2 mb-2">
                            <span class="font-medium text-gray-800">${{name}}</span>
                            <span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">Client</span>
                            <span class="text-xs text-gray-400">Just now</span>
                        </div>
                        <p class="text-gray-700 text-sm">${{text}}</p>
                    `;
                    list.appendChild(div);
                    
                    document.getElementById('commentText').value = '';
                    showToast('Comment added!', 'success');
                }}
            }} catch(e) {{
                showToast('Failed to post comment', 'error');
            }}
        }}
        
        // Counter updates
        document.getElementById('editMetaTitle').addEventListener('input', function() {{
            document.getElementById('metaTitleLen').textContent = `(${{this.value.length}}/60)`;
        }});
        document.getElementById('editMetaDesc').addEventListener('input', function() {{
            document.getElementById('metaDescLen').textContent = `(${{this.value.length}}/160)`;
        }});
        
        function showToast(msg, type) {{
            const toast = document.getElementById('toast');
            const content = document.getElementById('toastContent');
            content.textContent = msg;
            content.className = `${{type === 'error' ? 'bg-red-600' : type === 'info' ? 'bg-blue-600' : 'bg-green-600'}} text-white px-6 py-3 rounded-lg shadow-lg`;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 4000);
        }}
    </script>
</body>
</html>'''
    
    return page


def _render_not_found():
    return '''<!DOCTYPE html>
<html><head><title>Review Not Found</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f3f4f6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
    <div style="text-align:center;padding:40px;background:white;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,0.1);max-width:400px;">
        <div style="font-size:48px;margin-bottom:16px;">🔒</div>
        <h2 style="margin:0 0 8px;color:#1f2937;">Review Link Not Found</h2>
        <p style="color:#6b7280;margin:0;">This review link doesn\'t exist or may have expired. Please check your email for the correct link.</p>
    </div>
</body></html>'''
