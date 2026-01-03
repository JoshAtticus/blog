let charts = {};
let currentPostSlug = null;
let state = {
    users: { page: 1 },
    community: { page: 1 },
    detailComments: { page: 1 }
};

// --- Navigation ---
function nav(viewId) {
    // Hide all sections
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    // Show target section
    const target = document.getElementById(`view-${viewId}`);
    if(target) target.classList.add('active');
    else if(viewId === 'post-details') document.getElementById('view-post-details').classList.add('active');

    // Update Menu Active State
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const navItem = Array.from(document.querySelectorAll('.nav-item')).find(el => {
        const onClick = el.getAttribute('onclick');
        return onClick && onClick.includes(`'${viewId}'`);
    });
    if (navItem) navItem.classList.add('active');
    
    // Trigger Load Functions
    if (viewId === 'dashboard') loadDashboard();
    if (viewId === 'content') loadContent();
    if (viewId === 'community') loadCommunity(1);
    if (viewId === 'users') loadUsers(1);
}

function switchSubTab(tab) {
    document.querySelectorAll('.sub-tab').forEach(el => el.classList.remove('active'));
    if(event && event.target) event.target.classList.add('active');
    
    if (tab === 'analytics') {
        document.getElementById('sub-view-analytics').style.display = 'block';
        document.getElementById('sub-view-community').style.display = 'none';
    } else {
        document.getElementById('sub-view-analytics').style.display = 'none';
        document.getElementById('sub-view-community').style.display = 'block';
        if(currentPostSlug) loadPostComments(currentPostSlug, 1);
    }
}

// --- Dashboard Logic ---
async function loadDashboard() {
    try {
        // 1. Overview Stats
        const res = await fetch('/api/analytics/overview');
        const data = await res.json();
        
        document.getElementById('dash-total-unique-views').innerText = data.total_unique_views || 0;
        document.getElementById('dash-total-views').innerText = data.total_views || 0;
        document.getElementById('dash-total-shares').innerText = data.total_shares || 0;
        document.getElementById('dash-visitors-30d').innerText = data.visitors_30d || 0;
        
        document.getElementById('dash-top-posts').innerHTML = (data.top_posts || []).map(p => `
            <tr onclick="openPost('${p.slug}')">
                <td>${p.title}</td>
                <td>${p.views}</td>
            </tr>
        `).join('');
        
        // 2. Main Chart (Line)
        const chartRes = await fetch('/api/analytics/chart');
        const chartData = await chartRes.json();
        renderChart('mainChart', chartData.map(d => d.date), chartData.map(d => d.views), 'Views');

        // 3. Shares Chart (Bar)
        const sharesRes = await fetch('/api/analytics/shares_by_platform');
        const sharesData = await sharesRes.json();
        renderBarChart('sharesPlatformChart', sharesData.map(d => d.platform), sharesData.map(d => d.count), 'Shares');
    } catch (err) {
        console.error("Error loading dashboard:", err);
    }
}

// --- Content Logic ---
async function loadContent() {
    try {
        const res = await fetch('/api/analytics/posts');
        const data = await res.json();
        
        document.getElementById('content-list').innerHTML = data.map(p => `
            <tr onclick="openPost('${p.slug}')">
                <td>
                    <div style="display:flex;align-items:center;gap:1rem">
                        <img src="${p.image || '/assets/default-post.jpg'}" style="width:60px;height:34px;object-fit:cover;border-radius:4px" onerror="this.src='https://placehold.co/60x34'">
                        ${p.title}
                    </div>
                </td>
                <td>${p.date}</td>
                <td>${p.views}</td>
            </tr>
        `).join('');
    } catch (err) {
        console.error("Error loading content:", err);
    }
}

// --- Post Details Logic ---
async function openPost(slug) {
    currentPostSlug = slug;
    nav('post-details'); 
    
    try {
        const res = await fetch(`/api/analytics/posts/${slug}`);
        const data = await res.json();
        
        document.getElementById('detail-title').innerText = data.title || slug;
        document.getElementById('detail-date').innerText = data.date || '-';
        document.getElementById('detail-total-views').innerText = data.total_views;
        
        if(data.daily_views) {
            renderChart('detailChart', data.daily_views.map(d => d.date), data.daily_views.map(d => d.views), 'Views');
        }
        
        // Reset sub-tab to Analytics by default
        document.querySelectorAll('.sub-tab').forEach(el => el.classList.remove('active'));
        document.querySelector('.sub-tab').classList.add('active'); // First one
        document.getElementById('sub-view-analytics').style.display = 'block';
        document.getElementById('sub-view-community').style.display = 'none';
    } catch (err) {
        console.error("Error loading post details:", err);
    }
}

// --- Community (Global) ---
async function loadCommunity(page) {
    try {
        const res = await fetch(`/api/admin/comments?page=${page}`);
        const data = await res.json();
        state.community.page = data.page;
        renderComments(data.comments, 'community-list');
        renderPagination('community', data.page, data.total_pages, 'loadCommunity');
    } catch (err) { console.error(err); }
}

// --- Post Comments (Specific) ---
async function loadPostComments(slug, page) {
    try {
        const res = await fetch(`/api/admin/comments?slug=${slug}&page=${page}`);
        const data = await res.json();
        state.detailComments.page = data.page;
        renderComments(data.comments, 'detail-comments-list');
        renderPagination('detail-comments', data.page, data.total_pages, 'loadPostCommentsWrapper');
    } catch (err) { console.error(err); }
}

function loadPostCommentsWrapper(page) {
    loadPostComments(currentPostSlug, page);
}

// --- Users Logic ---
async function loadUsers(page) {
    try {
        const res = await fetch(`/api/admin/users?page=${page}`);
        const data = await res.json();
        state.users.page = data.page;
        
        document.getElementById('users-list').innerHTML = data.users.map(user => `
            <tr>
                <td>${user.id}</td>
                <td>
                    <div style="display:flex;align-items:center;gap:0.5rem">
                        <img src="${user.picture || '/assets/default-avatar.png'}" style="width:24px;height:24px;border-radius:50%" onerror="this.src='https://placehold.co/24'">
                        ${user.name}
                    </div>
                </td>
                <td>${user.email || '-'}</td>
                <td>${user.oauth_provider}</td>
                <td>
                    <span class="status-badge ${user.email_verified ? 'status-verified' : 'status-unverified'}">
                        ${user.email_verified ? 'Verified' : 'Unverified'}
                    </span>
                </td>
                <td>${user.is_admin ? 'Yes' : 'No'}</td>
                <td>${new Date(user.created_at).toLocaleDateString()}</td>
            </tr>
        `).join('');
        renderPagination('users', data.page, data.total_pages, 'loadUsers');
    } catch (err) { console.error(err); }
}

// --- Helper Functions ---
function renderComments(comments, containerId) {
    const container = document.getElementById(containerId);
    if(!comments || comments.length === 0) {
        container.innerHTML = '<div style="padding:1rem;color:#aaa">No comments found.</div>';
        return;
    }
    container.innerHTML = comments.map(comment => `
        <div class="comment-card">
            <div class="comment-main">
                <img src="${comment.picture || '/assets/default-avatar.png'}" class="comment-avatar-img" onerror="this.src='https://placehold.co/40'">
                <div class="comment-content-area">
                    <div class="comment-meta">
                        <span class="comment-author-name">${comment.author_name}</span>
                        <span>•</span>
                        <span>${new Date(comment.created_at).toLocaleDateString()}</span>
                        ${comment.is_deleted ? '<span class="status-deleted">Deleted</span>' : ''}
                    </div>
                    <div class="comment-text">${comment.comment_text}</div>
                    <div class="comment-actions-row">
                        ${!comment.is_deleted ? `<button class="comment-action-link" onclick="deleteComment(${comment.id})">DELETE</button>` : ''}
                        ${!comment.is_deleted ? `<button class="comment-action-link" onclick="showReplyBox(${comment.id}, '${comment.slug}')">REPLY</button>` : ''}
                    </div>
                    <div class="reply-box" id="reply-box-${comment.id}" style="display:none;margin-top:0.5rem;">
                        <textarea id="reply-text-${comment.id}" rows="2" style="width:100%;resize:vertical;"></textarea>
                        <button onclick="submitReply(${comment.id}, '${comment.slug}')" style="margin-top:0.5rem;">Send Reply</button>
                        <button onclick="hideReplyBox(${comment.id})" style="margin-top:0.5rem;">Cancel</button>
                    </div>
                </div>
            </div>
            <div class="comment-post-info">
                <a href="/posts/${comment.slug}" target="_blank">
                    <img src="${comment.post_image || '/assets/default-post.jpg'}" class="comment-post-thumb" onerror="this.src='https://placehold.co/120x68'">
                </a>
                <a href="/posts/${comment.slug}" target="_blank" class="comment-post-title">
                    ${comment.post_title || comment.slug}
                </a>
            </div>
        </div>
    `).join('');
}

function showReplyBox(commentId, slug) {
    document.getElementById(`reply-box-${commentId}`).style.display = 'block';
}
function hideReplyBox(commentId) {
    document.getElementById(`reply-box-${commentId}`).style.display = 'none';
}

async function submitReply(parentId, slug) {
    const textField = document.getElementById(`reply-text-${parentId}`);
    const text = textField.value.trim();
    if (!text) return alert('Reply cannot be empty.');
    
    try {
        await fetch('/api/admin/comments/reply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parent_id: parentId, slug: slug, comment_text: text })
        });
        hideReplyBox(parentId);
        textField.value = ''; // clear
        // Reload current view
        if (document.getElementById('view-community').classList.contains('active')) loadCommunity(state.community.page);
        else loadPostComments(currentPostSlug, state.detailComments.page);
    } catch (err) { alert('Error sending reply'); }
}

function renderPagination(type, page, totalPages, funcName) {
    const container = document.getElementById(`${type}-pagination`);
    if(!container) return;
    
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <button onclick="${funcName}(${page - 1})" ${page <= 1 ? 'disabled' : ''}>Previous</button>
        <span style="color:#aaa">Page ${page} of ${totalPages}</span>
        <button onclick="${funcName}(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>Next</button>
    `;
}

async function deleteComment(id) {
    if (!confirm('Delete comment?')) return;
    try {
        await fetch(`/api/comments/${id}`, { method: 'DELETE' });
        // Reload current view
        if (document.getElementById('view-community').classList.contains('active')) loadCommunity(state.community.page);
        else loadPostComments(currentPostSlug, state.detailComments.page);
    } catch (err) { alert('Error deleting comment'); }
}

function renderChart(canvasId, labels, data, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    if (charts[canvasId]) charts[canvasId].destroy();
    const ctx = canvas.getContext('2d');
    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                borderColor: '#1a73e8',
                backgroundColor: 'rgba(26, 115, 232, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: '#333' } },
                x: { grid: { display: false } }
            }
        }
    });
}

function renderBarChart(canvasId, labels, data, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    if (charts[canvasId]) charts[canvasId].destroy();
    const ctx = canvas.getContext('2d');
    charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                backgroundColor: '#1a73e8',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: '#333' } },
                x: { grid: { display: false } }
            }
        }
    });
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
});
