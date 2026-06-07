import sqlite3
from datetime import datetime, timezone
from flask import Blueprint, redirect, url_for, request, session, jsonify, render_template
from extensions import oauth, DB_PATH
from db_helpers import get_current_user

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login_page():
    return render_template('login.html')

@auth_bp.route('/login/<provider>')
def login(provider):
    if provider not in ['google', 'github', 'joshatticus']:
        return "Provider not supported", 400
    redirect_uri = url_for('auth.auth_callback', provider=provider, _external=True)
    return oauth.create_client(provider).authorize_redirect(redirect_uri)

@auth_bp.route('/auth/callback/<provider>')
def auth_callback(provider):
    if provider not in ['google', 'github', 'joshatticus']:
        return "Provider not supported", 400
    
    client = oauth.create_client(provider)
    try:
        token = client.authorize_access_token()
    except Exception as e:
        return f"Authentication failed: {str(e)}", 400
        
    user_info = None
    oauth_id = None
    email = None
    email_verified = False
    name = None
    picture = None
    
    if provider == 'google':
        user_info = token.get('userinfo')
        if not user_info:
            user_info = client.get('https://openidconnect.googleapis.com/v1/userinfo').json()
        oauth_id = user_info.get('sub')
        email = user_info.get('email')
        email_verified = user_info.get('email_verified', False)
        name = user_info.get('name')
        picture = user_info.get('picture')
        
    elif provider == 'github':
        user_info = client.get('user').json()
        oauth_id = str(user_info.get('id'))
        name = user_info.get('name') or user_info.get('login')
        picture = user_info.get('avatar_url')
        
        # guthib email might be private, if so explode /j
        email_resp = client.get('user/emails')
        if email_resp.status_code == 200:
            emails = email_resp.json()
            for e in emails:
                if e.get('primary') and e.get('verified'):
                    email = e.get('email')
                    email_verified = True
                    break
                    
    elif provider == 'joshatticus':
        # i HATE openid so much it's a scam i wasted 30 minutes on ts
        user_info = client.userinfo()
        oauth_id = user_info.get('sub')
        email = user_info.get('email')
        email_verified = user_info.get('email_verified', False)
        name = user_info.get('name')
        if not name:
            name = user_info.get('preferred_username') or user_info.get('nickname')
        if not name and email:
            name = email.split('@')[0]
        picture = user_info.get('picture') or user_info.get('profile_picture')

    if not oauth_id:
        return "Could not retrieve user information", 400
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE oauth_provider = ? AND oauth_id = ?', (provider, oauth_id))
    existing_user = cursor.fetchone()
    
    if existing_user:
        user_id = existing_user[0]
        cursor.execute('''
            UPDATE users SET email = ?, email_verified = ?, name = ?, picture = ? WHERE id = ?
        ''', (email, email_verified, name, picture, user_id))
    else:
        # Check if this is the first user (make admin) (yes horribly insecure womp womp cry about it if anyone signs up before me i would just delete the database)
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        is_admin = 1 if count == 0 else 0
        
        cursor.execute('''
            INSERT INTO users (oauth_provider, oauth_id, email, email_verified, name, picture, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (provider, oauth_id, email, email_verified, name, picture, is_admin, datetime.now(timezone.utc).isoformat()))
        user_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    
    session['user_id'] = user_id
    return redirect('/')

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/')

@auth_bp.route('/api/auth/status')
def auth_status():
    user = get_current_user()
    if user:
        return jsonify({
            'authenticated': True,
            'user': {
                'name': user['name'],
                'picture': user['picture'],
                'is_admin': bool(user['is_admin'])
            }
        })
    return jsonify({'authenticated': False})