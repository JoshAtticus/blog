import html
import requests
from flask import Blueprint, request, jsonify, Response
from extensions import get_client_ip, hash_ip
from db_helpers import (
    get_current_user, get_comments_for_post, check_comment_rate_limit,
    check_reply_rate_limit, add_comment, get_comment_by_id, edit_comment, delete_comment
)
from post_helpers import get_all_posts

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/search')
def api_search():
    query = request.args.get('q', '').lower()
    results = []
    if query:
        for p in get_all_posts():
            if query in p['title'].lower() or query in p['summary'].lower() or any(query in t.lower() for t in p['tags']):
                results.append(p)
    return jsonify({"results": results})

@api_bp.route('/api/comments/<slug>', methods=['GET', 'POST'])
def comments_api(slug):
    if request.method == 'GET':
        page, per_page = request.args.get('page', 1, type=int), request.args.get('per_page', 20, type=int)
        comments, total_pages, total_comments = get_comments_for_post(slug, page, per_page)
        user = get_current_user()
        is_admin = user and user.get('is_admin')
        
        for c in comments:
            if c['is_deleted']:
                if not is_admin:
                    c['author_name'], c['comment_text'], c['picture'] = '[Deleted by user]', '[Deleted by user]', None
                else:
                    c['comment_text'] = f"[DELETED] {c['comment_text']}"
        return jsonify({"comments": comments, "page": page, "total_pages": total_pages, "total_comments": total_comments})
    
    elif request.method == 'POST':
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        if not user.get('email_verified'):
            return jsonify({"error": "Verified email required to comment"}), 403
        if user.get('is_banned'):
            return jsonify({"error": "You are banned from commenting."}), 403

        data = request.get_json()
        user_id, author_name = str(user['id']), user['name']
        client_ip = get_client_ip()
        ip_hash = hash_ip(client_ip)
        
        if not check_comment_rate_limit(user_id, ip_hash):
            return jsonify({"error": "Rate limit exceeded. Please wait before posting again."}), 429
            
        parent_id = data.get('parent_id')
        if parent_id and not check_reply_rate_limit(user_id, ip_hash):
             return jsonify({"error": "Reply rate limit exceeded. Please wait before replying again."}), 429
        
        comment_text = data.get('comment_text', '').strip()
        if not comment_text:
            return jsonify({"error": "Comment text is required"}), 400
        if len(comment_text) > 1500:
            return jsonify({"error": "Comment exceeds 1500 characters"}), 400
            
        comment_text = html.escape(comment_text).replace('\n', ' ').replace('\r', '')
        comment_id = add_comment(slug, user_id, author_name, comment_text, parent_id, ip_hash)
        return jsonify({"success": True, "comment": get_comment_by_id(comment_id)})

@api_bp.route('/api/comments/<int:comment_id>', methods=['PUT', 'DELETE'])
def comment_action_api(comment_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    if user.get('is_banned'):
        return jsonify({"error": "You are banned."}), 403
        
    user_id = str(user['id'])
    if request.method == 'PUT':
        data = request.get_json()
        new_text = data.get('comment_text', '').strip()
        if not new_text:
            return jsonify({"error": "Comment text is required"}), 400
        if len(new_text) > 1500:
            return jsonify({"error": "Comment exceeds 1500 characters"}), 400
            
        new_text = html.escape(new_text).replace('\n', ' ').replace('\r', '')
        success, error = edit_comment(comment_id, user_id, new_text)
        return jsonify({"success": True}) if success else (jsonify({"error": error}), 403)
        
    elif request.method == 'DELETE':
        success, error = delete_comment(comment_id, user_id, user.get('is_admin', False))
        return jsonify({"success": True}) if success else (jsonify({"error": error}), 403)