import sqlite3
import json
import html
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, render_template
from extensions import DB_PATH, get_client_ip, hash_ip, cache
from db_helpers import get_current_user, add_comment
from post_helpers import get_all_posts

admin_bp = Blueprint('admin', __name__)

@admin_bp.before_request
def check_admin():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403

@admin_bp.route('/admin')
def admin_panel():
    return render_template('admin.html')

@admin_bp.route('/api/admin/users')
def admin_users():
    page, per_page = request.args.get('page', 1, type=int), request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
    
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?', (per_page, offset))
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"users": users, "page": page, "total_pages": total_pages, "total_users": total_users})

@admin_bp.route('/api/admin/users/<int:user_id>/ban', methods=['POST'])
def admin_ban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET is_banned = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@admin_bp.route('/api/admin/users/<int:user_id>/unban', methods=['POST'])
def admin_unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET is_banned = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@admin_bp.route('/api/admin/blocked_ips')
def admin_blocked_ips():
    page, per_page = request.args.get('page', 1, type=int), request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM blocked_ips')
    total_records = cursor.fetchone()[0]
    total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
    
    cursor.execute('SELECT * FROM blocked_ips ORDER BY created_at DESC LIMIT ? OFFSET ?', (per_page, offset))
    blocked_ips = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"blocked_ips": blocked_ips, "page": page, "total_pages": total_pages, "total_records": total_records})

@admin_bp.route('/api/admin/blocked_ips/<int:id>/analysis')
def admin_blocked_ip_analysis(id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM blocked_ips WHERE id = ?', (id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
        
    ip_data = dict(row)
    extra_info_str = ip_data.get('extra_info')
    analysis = {"id": ip_data['id'], "ip": ip_data['ip_address'], "country": ip_data['country'], "fingerprint_hash": None, "fingerprint_shared_count": 0, "related_ips": [], "details": {}}

    if extra_info_str:
        try:
            extra = json.loads(extra_info_str)
            client_fp = extra.get('client_fingerprint', {})
            analysis['details']['screen_res'] = f"{client_fp.get('screen_width', '?')}x{client_fp.get('screen_height', '?')}"
            analysis['details']['timezone'] = client_fp.get('timezone', 'Unknown')
            analysis['details']['platform'] = client_fp.get('platform', 'Unknown')
            analysis['details']['renderer'] = client_fp.get('webgl_renderer', 'Unknown')
            
            fp_hash = client_fp.get('fingerprint_hash')
            if fp_hash:
                analysis['fingerprint_hash'] = fp_hash
                search_pattern = f'%"{fp_hash}"%'
                cursor.execute('SELECT ip_address, created_at FROM blocked_ips WHERE extra_info LIKE ? AND id != ? ORDER BY created_at DESC LIMIT 50', (search_pattern, id))
                related_rows = cursor.fetchall()
                analysis['fingerprint_shared_count'] = len(related_rows)
                analysis['related_ips'] = [{"ip": r['ip_address'], "date": r['created_at']} for r in related_rows[:10]]
        except Exception as e:
            print(f"Error parsing extra info: {e}")
            
    conn.close()
    return jsonify(analysis)

@admin_bp.route('/api/admin/invoicing')
def admin_invoicing():
    page, per_page = request.args.get('page', 1, type=int), request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(data_sent) as total_bytes, COUNT(CASE WHEN ip_type = 0 THEN 1 END) as residential_count, COUNT(*) as total_records FROM blocked_ips WHERE data_sent > 0')
    summary_row = cursor.fetchone()
    total_bytes = summary_row['total_bytes'] or 0
    residential_count = summary_row['residential_count'] or 0
    total_records = summary_row['total_records']
    
    cursor.execute('SELECT SUM(data_sent) FROM blocked_ips WHERE data_sent > 0 AND ip_type = 0')
    res_bytes = cursor.fetchone()[0] or 0
    res_gb = res_bytes / (1024 * 1024 * 1024)
    total_cost_low, total_cost_high = 2 * res_gb, 15 * res_gb
    
    cursor.execute('SELECT id, ip_address, ip_type, data_sent, created_at FROM blocked_ips WHERE data_sent > 0 ORDER BY data_sent DESC LIMIT ? OFFSET ?', (per_page, offset))
    rows = cursor.fetchall()
    conn.close()
    
    total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
    invoices = []
    
    for r in [dict(row) for row in rows]:
        data_gb = (r['data_sent'] or 0) / (1024 * 1024 * 1024)
        is_res = r['ip_type'] == 0
        invoices.append({
            "ip": r['ip_address'],
            "type": "Residential" if r['ip_type'] == 0 else ("Hosting" if r['ip_type'] == 1 else "Unknown"),
            "data_gb": data_gb,
            "cost_low": 2 * data_gb if is_res else 0,
            "cost_high": 15 * data_gb if is_res else 0,
            "is_residential": is_res
        })
        
    return jsonify({"invoices": invoices, "page": page, "total_pages": total_pages, "summary": {"total_cost_low": total_cost_low, "total_cost_high": total_cost_high, "total_data_gb": total_bytes / (1024 * 1024 * 1024), "residential_ips": residential_count}})

@admin_bp.route('/api/admin/blocked_ips/<int:id>/unblock', methods=['POST'])
def admin_unblock_ip(id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT ip_address, extra_info FROM blocked_ips WHERE id = ?', (id,))
    row = cursor.fetchone()
    if row:
        ip, extra_info_str = row['ip_address'], row['extra_info']
        if extra_info_str:
            try:
                client_fp = json.loads(extra_info_str).get('client_fingerprint')
                if isinstance(client_fp, dict) and client_fp.get('fingerprint_hash'):
                    cursor.execute('DELETE FROM blocked_fingerprints WHERE fingerprint_hash = ?', (client_fp['fingerprint_hash'],))
            except: pass
        cursor.execute('DELETE FROM blocked_ips WHERE ip_address = ?', (ip,))
        conn.commit()
        cache.delete(f'honeypot_blocked_{ip}')
        cache.delete(f'blocked_{ip}')
    conn.close()
    return jsonify({"success": True})

@admin_bp.route('/api/admin/blocked_ips/lookup')
def admin_lookup_ip():
    ip = request.args.get('ip')
    if not ip:
        return jsonify({"error": "Missing IP"}), 400
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM blocked_ips WHERE ip_address = ? ORDER BY created_at DESC', (ip,))
    rows = cursor.fetchall()
    history = [dict(row) for row in rows]
    conn.close()
    
    is_blocked_cache = cache.get(f'honeypot_blocked_{ip}') or cache.get(f'blocked_{ip}')
    return jsonify({"ip": ip, "is_blocked": bool(rows) or bool(is_blocked_cache), "history": history, "cache_status": bool(is_blocked_cache)})

@admin_bp.route('/api/admin/blocked_ips/action', methods=['POST'])
def admin_blocked_ip_action():
    data = request.json
    ip, action = data.get('ip'), data.get('action')
    if not ip or not action:
        return jsonify({"error": "Missing params"}), 400
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if action == 'unblock':
        cursor.execute('SELECT extra_info FROM blocked_ips WHERE ip_address = ?', (ip,))
        for row in cursor.fetchall():
            if row[0]:
                try:
                    fp_hash = json.loads(row[0]).get('client_fingerprint', {}).get('fingerprint_hash')
                    if fp_hash:
                        cursor.execute('DELETE FROM blocked_fingerprints WHERE fingerprint_hash = ?', (fp_hash,))
                except: pass
        cursor.execute('DELETE FROM blocked_ips WHERE ip_address = ?', (ip,))
        cache.delete(f'honeypot_blocked_{ip}')
        cache.delete(f'blocked_{ip}')
    elif action == 'block':
        blocked_until = (datetime.now(timezone.utc) + timedelta(days=365 * 100)).isoformat()
        cursor.execute('INSERT INTO blocked_ips (ip_address, reason, blocked_until, country, user_agent, created_at) VALUES (?, ?, ?, ?, ?, datetime("now"))', (ip, data.get('reason', 'Manual Admin Block'), blocked_until, 'Manual', 'Manual Admin Block'))
        cache.set(f'honeypot_blocked_{ip}', True, timeout=60 * 60 * 24 * 365 * 100)
    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@admin_bp.route('/api/admin/comments')
def admin_comments():
    page, per_page = request.args.get('page', 1, type=int), request.args.get('per_page', 20, type=int)
    slug_filter, offset = request.args.get('slug'), (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if slug_filter:
        cursor.execute('SELECT COUNT(*) FROM comments WHERE slug = ?', (slug_filter,))
    else:
        cursor.execute('SELECT COUNT(*) FROM comments')
        
    total_comments = cursor.fetchone()[0]
    total_pages = (total_comments + per_page - 1) // per_page if total_comments > 0 else 1
    
    query_str = 'SELECT c.*, u.name as author_name, u.email, u.picture FROM comments c LEFT JOIN users u ON c.user_id = CAST(u.id AS TEXT)'
    if slug_filter:
        cursor.execute(f'{query_str} WHERE c.slug = ? ORDER BY c.created_at DESC LIMIT ? OFFSET ?', (slug_filter, per_page, offset))
    else:
        cursor.execute(f'{query_str} ORDER BY c.created_at DESC LIMIT ? OFFSET ?', (per_page, offset))
        
    comments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    posts_map = {post['slug']: post for post in get_all_posts()}
    for c in comments:
        post = posts_map.get(c['slug'])
        c['post_title'] = post['title'] if post else c['slug']
        c['post_image'] = post.get('image') if post else None
    return jsonify({"comments": comments, "page": page, "total_pages": total_pages, "total_comments": total_comments})

@admin_bp.route('/api/analytics/overview')
def analytics_overview():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM analytics_pageviews WHERE event_type = 'view'")
    total_views = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT ip_hash) FROM analytics_pageviews WHERE event_type = 'view'")
    total_unique_views = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM analytics_pageviews WHERE event_type = 'share'")
    total_shares = cursor.fetchone()[0]
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM analytics_pageviews WHERE event_type = 'view' AND viewed_at > ?", (thirty_days_ago,))
    views_30d = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT ip_hash) FROM analytics_pageviews WHERE event_type = 'view' AND viewed_at > ?", (thirty_days_ago,))
    visitors_30d = cursor.fetchone()[0]
    
    cursor.execute('SELECT slug, COUNT(*) as count FROM analytics_pageviews WHERE event_type = "view" AND viewed_at > ? GROUP BY slug ORDER BY count DESC LIMIT 5', (thirty_days_ago,))
    top_posts = [{"slug": r[0], "views": r[1]} for r in cursor.fetchall()]
    conn.close()
    
    posts_map = {post['slug']: post for post in get_all_posts()}
    for p in top_posts:
        p['title'] = posts_map[p['slug']]['title'] if p['slug'] in posts_map else p['slug']
    return jsonify({"total_views": total_views, "total_unique_views": total_unique_views, "total_shares": total_shares, "views_30d": views_30d, "visitors_30d": visitors_30d, "top_posts": top_posts})

@admin_bp.route('/api/analytics/chart')
def analytics_chart():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('SELECT substr(viewed_at, 1, 10) as day, COUNT(*) FROM analytics_pageviews WHERE event_type = "view" AND viewed_at > ? GROUP BY day ORDER BY day', (thirty_days_ago,))
    daily_views = [{"date": r[0], "views": r[1]} for r in cursor.fetchall()]
    
    cursor.execute('SELECT substr(viewed_at, 1, 10) as day, COUNT(*) FROM analytics_pageviews WHERE event_type = "share" AND viewed_at > ? GROUP BY day ORDER BY day', (thirty_days_ago,))
    daily_shares = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    
    final_data = {v['date']: {"date": v['date'], "views": v['views'], "shares": 0, "new_posts": []} for v in daily_views}
    for date, count in daily_shares.items():
        if date not in final_data:
            final_data[date] = {"date": date, "views": 0, "shares": count, "new_posts": []}
        else:
            final_data[date]["shares"] = count
            
    for p in get_all_posts():
        if p['date'] in final_data:
            final_data[p['date']]['new_posts'].append(p['title'])
        elif p['date'] >= thirty_days_ago[:10]:
             final_data[p['date']] = {"date": p['date'], "views": 0, "shares": 0, "new_posts": [p['title']]}
             
    return jsonify(sorted(final_data.values(), key=lambda x: x['date']))

@admin_bp.route('/api/analytics/posts')
def analytics_posts_list():
    page, per_page = request.args.get('page', 1, type=int), 20
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT slug, COUNT(*) as count FROM analytics_pageviews GROUP BY slug')
    view_counts = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    
    result = [{"slug": p['slug'], "title": p['title'], "date": p['date'], "image": p.get('image'), "views": view_counts.get(p['slug'], 0)} for p in get_all_posts()]
    result.sort(key=lambda x: x['date'], reverse=True)
    
    start = (page - 1) * per_page
    return jsonify({"posts": result[start:start+per_page], "page": page, "total_pages": (len(result) + per_page - 1) // per_page})

@admin_bp.route('/api/analytics/posts/<slug>')
def analytics_post_detail(slug):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM analytics_pageviews WHERE slug = ?', (slug,))
    total_views = cursor.fetchone()[0]
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('SELECT substr(viewed_at, 1, 10) as day, COUNT(*) FROM analytics_pageviews WHERE slug = ? AND viewed_at > ? AND event_type = "view" GROUP BY day ORDER BY day', (slug, thirty_days_ago))
    daily_views = [{"date": r[0], "views": r[1]} for r in cursor.fetchall()]

    cursor.execute('SELECT substr(viewed_at, 1, 10) as day, COUNT(*) FROM analytics_pageviews WHERE slug = ? AND viewed_at > ? AND event_type = "share" GROUP BY day ORDER BY day', (slug, thirty_days_ago))
    daily_shares = [{"date": r[0], "shares": r[1]} for r in cursor.fetchall()]
    
    cursor.execute('SELECT platform, COUNT(*) as count FROM analytics_pageviews WHERE slug = ? AND event_type = "share" AND platform IS NOT NULL AND platform != "unknown" GROUP BY platform ORDER BY count DESC', (slug,))
    shares_platform = [{"platform": r[0], "count": r[1]} for r in cursor.fetchall()]
    conn.close()

    post_meta = next((p for p in get_all_posts() if p['slug'] == slug), {})
    return jsonify({"slug": slug, "title": post_meta.get('title', slug), "date": post_meta.get('date', '-'), "image": post_meta.get('image'), "total_views": total_views, "daily_views": daily_views, "daily_shares": daily_shares, "shares_platform": shares_platform})

@admin_bp.route('/api/analytics/shares_by_platform')
def analytics_shares_by_platform():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT platform, COUNT(*) as count FROM analytics_pageviews WHERE event_type = "share" AND platform IS NOT NULL AND platform != "unknown" GROUP BY platform ORDER BY count DESC')
    data = [{"platform": r[0], "count": r[1]} for r in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@admin_bp.route('/api/analytics/daily_shares_platform')
def analytics_daily_shares_platform():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('SELECT substr(viewed_at, 1, 10) as day, platform, COUNT(*) as count FROM analytics_pageviews WHERE event_type = "share" AND viewed_at > ? AND platform IS NOT NULL AND platform != "unknown" GROUP BY day, platform ORDER BY day', (thirty_days_ago,))
    data = [{"date": r[0], "platform": r[1], "count": r[2]} for r in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@admin_bp.route('/api/admin/comments/reply', methods=['POST'])
def admin_reply_to_comment():
    data = request.get_json()
    parent_id, slug, comment_text = data.get('parent_id'), data.get('slug'), data.get('comment_text', '').strip()
    if not (parent_id and slug and comment_text):
        return jsonify({"error": "Missing required fields"}), 400
        
    user = get_current_user()
    user_id, author_name = str(user['id']), user['name']
    comment_text = html.escape(comment_text).replace('\n', ' ').replace('\r', '')
    comment_id = add_comment(slug, user_id, author_name, comment_text, parent_id, hash_ip(get_client_ip()))
    return jsonify({"success": True, "comment_id": comment_id})