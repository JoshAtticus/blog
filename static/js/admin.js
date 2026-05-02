let charts = {};
let currentPostSlug = null;
let showPlatformShares = false;
let pollingInterval = null;
let state = {
    users: { page: 1 },
    community: { page: 1 },
    detailComments: { page: 1 },
    content: { page: 1 },
    userComments: { page: 1, userId: null },
    blockedIPs: { page: 1 },
    invoicing: { page: 1 }
};

// --- Navigation ---
function nav(viewId) {
    // Hide all sections
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    // Show target section
    const target = document.getElementById(`view-${viewId}`);
    if(target) target.classList.add('active');
    else if(viewId === 'post-details') document.getElementById('view-post-details').classList.add('active');
    else if(viewId === 'user-comments') document.getElementById('view-user-comments').classList.add('active');

    // Update Menu Active State
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const navItem = Array.from(document.querySelectorAll('.nav-item')).find(el => {
        const onClick = el.getAttribute('onclick');
        return onClick && onClick.includes(`'${viewId}'`);
    });
    if (navItem) navItem.classList.add('active');
    
    // Trigger Load Functions
    if (viewId === 'dashboard') loadDashboard();
    if (viewId === 'content') loadContent(state.content.page);
    if (viewId === 'community') loadCommunity(state.community.page);
    if (viewId === 'users') loadUsers(state.users.page);
    if (viewId === 'blocked-ips') loadBlockedIPs(state.blockedIPs.page);
    if (viewId === 'invoicing') loadInvoicing(state.invoicing.page);
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
        
        // 2. Main Chart
        if (showPlatformShares) {
             const res = await fetch('/api/analytics/daily_shares_platform');
             const data = await res.json();
             
             const dates = [...new Set(data.map(d => d.date))].sort();
             const platforms = [...new Set(data.map(d => d.platform))];
             
             const datasets = platforms.map(platform => {
                 return {
                     label: platform,
                     data: dates.map(date => {
                         const match = data.find(d => d.date === date && d.platform === platform);
                         return match ? match.count : 0;
                     }),
                     stack: 'stack0'
                 };
             });
             
             renderComplexChart('mainChart', 'bar', dates, datasets);
        } else {
            const chartRes = await fetch('/api/analytics/chart');
            const chartData = await chartRes.json();
            
            // Views Dataset
            const viewsDataset = {
                label: 'Views',
                data: chartData.map(d => d.views),
                borderColor: '#1a73e8',
                backgroundColor: 'rgba(26, 115, 232, 0.1)',
                fill: true,
                tension: 0.4,
                pointStyle: chartData.map(d => d.new_posts.length > 0 ? 'rectRot' : 'circle'),
                pointRadius: chartData.map(d => d.new_posts.length > 0 ? 8 : 3),
                pointBackgroundColor: chartData.map(d => d.new_posts.length > 0 ? '#fff' : '#1a73e8'),
                pointBorderColor: '#1a73e8',
                yAxisID: 'y'
            };
            
            // Shares Dataset
            const sharesDataset = {
                label: 'Shares',
                data: chartData.map(d => d.shares),
                borderColor: '#e8453c',
                backgroundColor: 'rgba(232, 69, 60, 0.1)',
                borderDash: [5, 5],
                fill: false,
                tension: 0.4,
                yAxisID: 'y' 
            };
            
            // Custom helper to inject post titles into chart instance for tooltips
            const canvas = document.getElementById('mainChart');
            if(canvas) {
                canvas.chartDataRaw = chartData;
            }

            renderComplexChart('mainChart', 'line', chartData.map(d => d.date), [viewsDataset, sharesDataset]);
        }

        // 3. Shares Chart (Bar)
        const sharesRes = await fetch('/api/analytics/shares_by_platform');
        const sharesData = await sharesRes.json();
        renderBarChart('sharesPlatformChart', sharesData.map(d => d.platform), sharesData.map(d => d.count), 'Shares');
    } catch (err) {
        console.error("Error loading dashboard:", err);
    }
}

function togglePlatformShares() {
    showPlatformShares = !showPlatformShares;
    const btn = document.getElementById('btn-toggle-shares');
    if(btn) btn.innerText = showPlatformShares ? "Show General View" : "Show Platform Shares";
    loadDashboard();
}

// --- Content Logic ---
async function loadContent(page) {
    try {
        const res = await fetch(`/api/analytics/posts?page=${page}`);
        const data = await res.json();
        state.content.page = data.page;
        
        document.getElementById('content-list').innerHTML = data.posts.map(p => `
            <tr onclick="openPost('${p.slug}')">
                <td>
                    <div style="display:flex;align-items:center;gap:1rem">
                        <img src="${p.image || 'https://placehold.co/600x400'}" style="width:60px;height:34px;object-fit:cover;border-radius:4px" onerror="this.src='https://placehold.co/60x34'">
                        ${p.title}
                    </div>
                </td>
                <td>${p.date}</td>
                <td>${p.views}</td>
            </tr>
        `).join('');
        
        renderPagination('content', data.page, data.total_pages, 'loadContent');
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
            // Merge views and shares data by date
            const allDates = [...new Set([
                ...data.daily_views.map(d => d.date),
                ...(data.daily_shares || []).map(d => d.date)
            ])].sort();

            const viewsDataset = {
                label: 'Views',
                data: allDates.map(date => {
                    const match = data.daily_views.find(d => d.date === date);
                    return match ? match.views : 0;
                }),
                borderColor: '#1a73e8',
                backgroundColor: 'rgba(26, 115, 232, 0.1)',
                fill: true,
                tension: 0.4
            };

            const sharesDataset = {
                label: 'Shares',
                data: allDates.map(date => {
                    const match = (data.daily_shares || []).find(d => d.date === date);
                    return match ? match.shares : 0;
                }),
                borderColor: '#e8453c',
                backgroundColor: 'rgba(232, 69, 60, 0.1)',
                borderDash: [5, 5],
                fill: false,
                tension: 0.4
            };
            
            renderComplexChart('detailChart', 'line', allDates, [viewsDataset, sharesDataset]);
        }

        const sharesContainer = document.getElementById('detail-shares-container');
        const sharesList = document.getElementById('detail-shares-list');
        if(data.shares_platform && data.shares_platform.length > 0) {
            sharesContainer.style.display = 'block';
            sharesList.innerHTML = data.shares_platform.map(s => `
                <div style="background:#252525;padding:0.5rem 1rem;border-radius:4px;border:1px solid #333">
                    <span style="color:#aaa">${s.platform}</span>: <strong style="color:#fff">${s.count}</strong>
                </div>
            `).join('');
        } else {
            sharesContainer.style.display = 'none';
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
                <td>
                    <div style="display:flex;align-items:center;gap:0.5rem">
                        ${!user.is_admin ? `
                        <button onclick="${user.is_banned ? 'unbanUser' : 'banUser'}(${user.id})" style="padding:4px 8px;cursor:pointer;background:${user.is_banned ? '#4caf50' : '#ff5252'};color:#fff;border:none;border-radius:4px; margin-right:5px;">
                            ${user.is_banned ? 'Unban' : 'Ban'}
                        </button>
                        ` : ''}
                        <button onclick="openUserComments(${user.id}, 1)" style="padding:4px 8px;cursor:pointer;background:#1a73e8;color:#fff;border:none;border-radius:4px;">
                            Comments
                        </button>
                    </div>
                </td>
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
                    <img src="${comment.post_image || 'https://placehold.co/600x400'}" class="comment-post-thumb" onerror="this.src='https://placehold.co/120x68'">
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
    pollingInterval = setInterval(() => {
        if(document.getElementById('view-dashboard').classList.contains('active')) {
            loadDashboard();
        }
    }, 30000);
});

function renderComplexChart(canvasId, type, labels, datasets) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (charts[canvasId]) charts[canvasId].destroy();
    
    // Auto colors for stacked bar 
    if (type === 'bar' && datasets.length > 1) {
        const colors = ['#1a73e8', '#e8453c', '#f9bc00', '#34a853', '#ab47bc', '#00acc1', '#ff7043'];
        datasets.forEach((ds, i) => {
            if(!ds.backgroundColor) ds.backgroundColor = colors[i % colors.length];
        });
    }

    const ctx = canvas.getContext('2d');
    charts[canvasId] = new Chart(ctx, {
        type: type,
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            stacked: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    callbacks: {
                        afterBody: function(tooltipItems) {
                             if(canvas.chartDataRaw) {
                                 const index = tooltipItems[0].dataIndex;
                                 const item = canvas.chartDataRaw[index];
                                 if(item && item.new_posts && item.new_posts.length > 0) {
                                     return ['New Posts:', ...item.new_posts.map(p => '- ' + p)];
                                 }
                             }
                             return []; 
                        }
                    }
                }
            },
            scales: {
                y: { beginAtZero: true, grid: { color: '#333' } },
                x: { grid: { display: false } }
            }
        }
    });
}

async function banUser(id) {
    if(!confirm('Ban this user?')) return;
    try {
        await fetch(`/api/admin/users/${id}/ban`, { method: 'POST' });
        loadUsers(state.users.page);
    } catch(e) { alert('Error banning user'); }
}

async function unbanUser(id) {
    if(!confirm('Unban this user?')) return;
    try {
        await fetch(`/api/admin/users/${id}/unban`, { method: 'POST' });
        loadUsers(state.users.page);
    } catch(e) { alert('Error unbanning user'); }
}

// --- User Comments Logic ---
async function openUserComments(userId, page = 1) {
    state.userComments.userId = userId;
    state.userComments.page = page;
    nav('user-comments');
    
    try {
        const res = await fetch(`/api/admin/users/${userId}/comments?page=${page}`);
        const data = await res.json();
        
        document.getElementById('user-comments-name').innerText = data.user_name || 'User ' + userId;
        renderComments(data.comments, 'user-comments-list');
        renderPagination('user-comments', data.page, data.total_pages, 'reloadUserComments');
    } catch(err) { console.error("Error loading user comments", err); }
}

function reloadUserComments(page) {
    if(state.userComments.userId) {
        openUserComments(state.userComments.userId, page);
    }
}

async function deleteAllUserComments() {
    const userId = state.userComments.userId;
    if(!userId) return;
    if(!confirm("Are you sure you want to delete ALL comments from this user? This cannot be undone.")) return;
    
    try {
        await fetch(`/api/admin/users/${userId}/comments/delete_all`, { method: 'POST' });
        reloadUserComments(1);
        alert("All comments marked as deleted.");
    } catch(err) { alert("Error deleting comments."); }
}

// --- Blocked IPs ---
async function loadBlockedIPs(page) {
    state.blockedIPs.page = page;
    try {
        const res = await fetch(`/api/admin/blocked_ips?page=${page}`);
        if(!res.ok) throw new Error("Failed to fetch");
        const data = await res.json();
        
        document.getElementById('blocked-total').innerText = data.total_records;
        
    state.blockedIPs.data = data.blocked_ips; // Store for modal access
        
        const tbody = document.getElementById('blocked-ips-list');
        tbody.innerHTML = data.blocked_ips.map(ip => `
            <tr onclick="showBlockedDetails(${ip.id})">
                <td>${ip.id}</td>
                <td title="${ip.user_agent || ''}">${ip.ip_address}</td>
                <td>${ip.country || '-'}</td>
                <td>${ip.reason}</td>
                <td>${new Date(ip.blocked_until).toLocaleString()}</td>
                <td>${new Date(ip.created_at).toLocaleString()}</td>
                <td>
                    <button onclick="event.stopPropagation(); unblockIP(${ip.id})" style="background:#ff5252;color:#fff;border:none;padding:4px 8px;border-radius:4px;cursor:pointer;">Unblock</button>
                </td>
            </tr>
        `).join('');
        
        // Custom simple pagination for now, or reuse common if available
        if(typeof renderPagination === 'function') {
             renderPagination('blocked-ips', page, data.total_pages, 'loadBlockedIPs');
        } else {
             // Fallback
             const pDiv = document.getElementById('blocked-ips-pagination');
             pDiv.innerHTML = `
                <button ${page <= 1 ? 'disabled' : ''} onclick="loadBlockedIPs(${page-1})">Prev</button>
                <span>Page ${page} of ${data.total_pages}</span>
                <button ${page >= data.total_pages ? 'disabled' : ''} onclick="loadBlockedIPs(${page+1})">Next</button>
             `;
        }
    } catch(e) { console.error(e); }
}

async function showBlockedDetails(id) {
    const ip = state.blockedIPs.data.find(i => i.id === id);
    if (!ip) return;
    
    // Fetch deeper analysis
    let analysis = {};
    const modalContent = document.getElementById('blocked-details-content');
    modalContent.innerHTML = `<div style="text-align:center;padding:2rem;">Loading analysis...</div>`;
    
    try {
        const res = await fetch(`/api/admin/blocked_ips/${id}/analysis`);
        analysis = await res.json();
    } catch(e) {
        console.error("Analysis Failed:", e);
        analysis = { details: {}, related_ips: [] };
    }
    
    // Fallback if basic parsing failed
    let extra = {};
    try { extra = JSON.parse(ip.extra_info); } catch(e) {}
    
    const details = analysis.details || {};
    const related = analysis.related_ips || [];
    
    modalContent.innerHTML = `
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
            <div>
                <h3>Network Info</h3>
                <p><strong>IP:</strong> ${ip.ip_address}</p>
                <p><strong>User Agent:</strong> <span style="font-family:monospace;font-size:0.8rem;color:#aaa;">${ip.user_agent || 'N/A'}</span></p>
                <p><strong>Country:</strong> ${ip.country || 'N/A'}</p>
                <p><strong>Blocked Util:</strong> ${new Date(ip.blocked_until).toLocaleDateString()}</p>
                <p><strong>Reason:</strong> ${ip.reason}</p>
            </div>
            <div>
                <h3>Device Fingerprint</h3>
                ${analysis.fingerprint_hash ? `
                    <div style="background:#252525; padding:1rem; border-radius:4px; margin-bottom:1rem;">
                        <div style="font-size:0.8rem;color:#aaa;margin-bottom:0.5rem;">FINGERPRINT HASH</div>
                        <div style="font-family:monospace;word-break:break-all;color:#4caf50;">${analysis.fingerprint_hash}</div>
                    </div>
                    <p><strong>Screen:</strong> ${details.screen_res || 'Unknown'}</p>
                    <p><strong>Timezone:</strong> ${details.timezone || 'Unknown'}</p>
                    <p><strong>Shared Count:</strong> <strong style="color:${related.length > 0 ? '#ff5252' : '#4caf50'}">${related.length + 1} IPs</strong> with this fingerprint</p>
                ` : `<p style="color:#aaa;">No fingerprint data captured.</p>`}
            </div>
        </div>
        
        ${related.length > 0 ? `
            <hr style="border-color:#333; margin: 2rem 0;">
            <h3>Related IPs (Same Fingerprint)</h3>
            <table style="font-size:0.9rem;">
                <thead><tr><th>IP Address</th><th>First Seen</th></tr></thead>
                <tbody>
                    ${related.map(r => `
                        <tr>
                            <td style="font-family:monospace;">${r.ip}</td>
                            <td>${new Date(r.date || r.created_at).toLocaleString()}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        ` : ''}

        <hr style="border-color:#333; margin: 2rem 0;">
        <details>
            <summary style="cursor:pointer;color:#aaa;">Raw Data Payload</summary>
            <pre style="background:#000; padding:1rem; border-radius:4px; overflow-x:auto; color:#4a9eff; margin-top:1rem;">${JSON.stringify(extra, null, 2)}</pre>
        </details>
    `;
    
    const modal = document.getElementById('modal-blocked-details');
    modal.style.display = 'flex';
}

function closeBlockedDetails() {
    document.getElementById('modal-blocked-details').style.display = 'none';
}

async function unblockIP(id) {
    if(!confirm('Are you sure you want to unblock this IP?')) return;
    
    await fetch(`/api/admin/blocked_ips/${id}/unblock`, { method: 'POST' });
    loadBlockedIPs(state.blockedIPs.page);
}

// --- Invoicing Logic ---
async function loadInvoicing(page = 1) {
    try {
        const res = await fetch(`/api/admin/invoicing?page=${page}`);
        if (!res.ok) throw new Error("Failed to fetch invoicing data");
        const data = await res.json();
        
        state.invoicing.page = data.page;
        const summary = data.summary;
        
        const cEst = document.getElementById('invoice-est-cost');
        if(cEst) cEst.innerText = `$${summary.total_cost_low.toFixed(2)} - $${summary.total_cost_high.toFixed(2)}`;
        
        const cTotal = document.getElementById('invoice-total-data');
        if(cTotal) cTotal.innerText = `${summary.total_data_gb.toFixed(4)} GB`;
        
        const cRes = document.getElementById('invoice-res-ips');
        if(cRes) cRes.innerText = summary.residential_ips;
        
        const tbody = document.getElementById('invoice-table-body');
        if (tbody) {
            tbody.innerHTML = data.invoices.map(inv => `
                <tr>
                    <td style="font-family:monospace;">${inv.ip}</td>
                    <td><span class="status-badge ${inv.is_residential ? 'status-verified' : 'status-unverified'}">${inv.type}</span></td>
                    <td>${inv.data_gb.toFixed(4)} GB</td>
                    <td>$${inv.cost_low.toFixed(4)}</td>
                    <td>$${inv.cost_high.toFixed(4)}</td>
                </tr>
            `).join('');
        }
        
        if (typeof renderPagination === 'function') {
            renderPagination('invoicing', data.page, data.total_pages, 'loadInvoicing');
        }

        if (document.getElementById('invoiceChart')) {
             const ctx = document.getElementById('invoiceChart').getContext('2d');
             if(charts['invoiceChart']) charts['invoiceChart'].destroy();

             charts['invoiceChart'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['Estimated Cost'],
                    datasets: [
                        { label: 'Low Estimate ($2/GB)', data: [summary.total_cost_low], backgroundColor: '#4caf50' },
                        { label: 'High Estimate ($15/GB)', data: [summary.total_cost_high], backgroundColor: '#ff9800' }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true } }
                }
             });
        }

    } catch (e) {
        console.error("Error loading invoicing:", e);
    }
}

// --- NEW LOGIC FOR MANUAL IP LOOKUP AND ACTIONS ---

async function lookupIp() {
    const ip = document.getElementById('blocked-ip-search').value.trim();
    if (!ip) return;
    
    const resultDiv = document.getElementById('ip-lookup-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = 'Searching...';
    
    try {
        const res = await fetch(`/api/admin/blocked_ips/lookup?ip=${encodeURIComponent(ip)}`);
        const data = await res.json();
        
        if (data.is_blocked) {
            let historyHtml = '';
            if (data.history && data.history.length > 0) {
                 historyHtml = `
                    <div style="margin-top:1rem; font-size:0.9rem; border-top:1px solid #333; padding-top:1rem;">
                        <strong>History:</strong>
                        <ul style="padding-left:1.2rem; color:#aaa;">
                            ${data.history.map(h => `
                                <li>
                                    ${new Date(h.created_at).toLocaleDateString()} - 
                                    ${h.reason} 
                                    ( until ${new Date(h.blocked_until).toLocaleDateString()} )
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                 `;
            }
            
            resultDiv.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <h3 style="color:var(--danger); margin:0;">🚫 BLOCKED</h3>
                        <p style="margin:0.5rem 0;">This IP is currently blocked.</p>
                        ${data.cache_status ? '<span style="font-size:0.8rem; background:#444; padding:2px 6px; border-radius:4px;">In Cache</span>' : ''}
                    </div>
                    <div>
                        <button onclick="manageIp('${ip}', 'unblock')" style="background:var(--success);">Unblock & Purge</button>
                    </div>
                </div>
                ${historyHtml}
            `;
        } else {
            resultDiv.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <h3 style="color:var(--success); margin:0;">✅ Not Blocked</h3>
                        <p style="margin:0.5rem 0;">This IP is not currently blocked.</p>
                    </div>
                    <div>
                        <button onclick="manageIp('${ip}', 'block')" style="background:var(--danger);">Block Permanently</button>
                    </div>
                </div>
            `;
        }
    } catch(err) {
        resultDiv.innerHTML = `<span style="color:red">Error searching IP: ${err.message}</span>`;
    }
}

async function manageIp(ip, action) {
    if (!confirm(`Are you sure you want to ${action} ${ip}?`)) return;
    
    try {
        const res = await fetch('/api/admin/blocked_ips/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ip, action })
        });
        const data = await res.json();
        
        if (data.success) {
            alert(action === 'block' ? 'IP Blocked Successfully' : 'IP Unblocked & Purged Successfully');
            lookupIp(); // Refresh status
            loadBlockedIPs(1); // Refresh list
        } else {
            alert('Action failed: ' + (data.error || 'Unknown error'));
        }
    } catch(err) {
        alert('Action failed: ' + err.message);
    }
}
