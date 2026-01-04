import os
import re
import json
import markdown
import time
import sqlite3
import uuid
import hashlib
import threading
import requests
import fcntl
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, jsonify, make_response, session
from cachelib import SimpleCache
from PIL import Image
import io
from feedgen.feed import FeedGenerator
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
# Fix for HTTPS behind reverse proxy (Coolify/Docker)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_NAME'] = 'blog_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True # Should be True in production
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# OAuth Configuration
oauth = OAuth(app)

# Google OAuth
oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# GitHub OAuth
oauth.register(
    name='github',
    client_id=os.environ.get('GITHUB_CLIENT_ID'),
    client_secret=os.environ.get('GITHUB_CLIENT_SECRET'),
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'}
)

# JoshAtticusID OAuth
oauth.register(
    name='joshatticus',
    client_id=os.environ.get('JOSHATTICUS_CLIENT_ID'),
    client_secret=os.environ.get('JOSHATTICUS_CLIENT_SECRET'),
    access_token_url='https://id.joshattic.us/oauth/token',
    authorize_url='https://id.joshattic.us/oauth/authorize',
    userinfo_endpoint='https://id.joshattic.us/oauth/userinfo',
    client_kwargs={'scope': 'name email profile_picture'}
)

cache = SimpleCache()
CACHE_TIMEOUT = 60 * 60 
POSTS_DIR = "posts"
DB_PATH = os.environ.get('DB_PATH', 'blog.db')

COMPRESSION_QUALITY = 85
MAX_IMAGE_WIDTH = 1200 
processed_images = set()

# Security / Rate Limiting
SUSPICIOUS_ERROR_LIMIT = 10
SUSPICIOUS_ERROR_WINDOW = 60  # 1 minute
SUSPICIOUS_BLOCK_DURATION = 3600  # 1 hour

@app.context_processor
def inject_year():
    return {'year': datetime.now().year}

# Database initialization
def init_db():
    """Initialize the database with required tables"""
    # Ensure the directory for the database exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_views (
            slug TEXT PRIMARY KEY,
            view_count INTEGER DEFAULT 0,
            shares_count INTEGER DEFAULT 0,
            last_viewed TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            user_id TEXT,
            ip_hash TEXT,
            viewed_at TEXT NOT NULL,
            UNIQUE(slug, user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analytics_pageviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            user_id TEXT, -- Cookie UUID or Logged in User ID
            ip_hash TEXT,
            user_agent TEXT,
            referrer TEXT,
            event_type TEXT DEFAULT 'view', -- 'view' or 'share'
            platform TEXT, -- e.g. 'twitter', 'facebook', 'copy', etc
            viewed_at TEXT NOT NULL
        )
    ''')

    # Migration: Add event_type column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE analytics_pageviews ADD COLUMN event_type TEXT DEFAULT "view"')
    except sqlite3.OperationalError:
        pass # Column likely exists
    # Migration: Add platform column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE analytics_pageviews ADD COLUMN platform TEXT')
    except sqlite3.OperationalError:
        pass
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            user_id TEXT NOT NULL,
            author_name TEXT NOT NULL,
            comment_text TEXT NOT NULL,
            parent_id INTEGER,
            created_at TEXT NOT NULL,
            ip_hash TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES comments (id)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_views_slug_user 
        ON user_views(slug, user_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_views_slug_ip_time 
        ON user_views(slug, ip_hash, viewed_at)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_comments_slug 
        ON comments(slug, created_at)
    ''')
    
    # Users table for authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            oauth_provider TEXT NOT NULL,
            oauth_id TEXT NOT NULL,
            email TEXT,
            email_verified BOOLEAN DEFAULT 0,
            name TEXT,
            picture TEXT,
            is_admin BOOLEAN DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(oauth_provider, oauth_id)
        )
    ''')
    
    # Migration: Add email_verified column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    # Migration: Add is_deleted and edited_at to comments
    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN is_deleted BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN edited_at TEXT')
    except sqlite3.OperationalError:
        pass

    # Migration: Add wasteof.money integration columns
    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN source TEXT DEFAULT "local"')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN external_id TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN author_avatar_url TEXT')
    except sqlite3.OperationalError:
        pass

    # Comment history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INTEGER NOT NULL,
            old_text TEXT NOT NULL,
            edited_at TEXT NOT NULL,
            FOREIGN KEY (comment_id) REFERENCES comments (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize the database when the module is loaded
init_db()

@app.before_request
def check_suspicious_block():
    # Get client IP (ProxyFix middleware handles X-Forwarded-For)
    ip = request.remote_addr
        
    # Check if IP is blocked
    if cache.get(f'blocked_{ip}'):
        return render_template('suspicious.html'), 403

@app.after_request
def monitor_suspicious_activity(response):
    # Monitor 4xx and 5xx errors, excluding 401/403 (auth issues)
    if response.status_code >= 400 and response.status_code not in [401, 403]:
        # Get client IP
        ip = request.remote_addr
        
        # Increment error count
        error_key = f'errors_{ip}'
        errors = cache.get(error_key) or 0
        errors += 1
        cache.set(error_key, errors, timeout=SUSPICIOUS_ERROR_WINDOW)
        
        # Check if limit exceeded
        if errors >= SUSPICIOUS_ERROR_LIMIT:
            cache.set(f'blocked_{ip}', True, timeout=SUSPICIOUS_BLOCK_DURATION)
            
    return response

# Authentication Helpers and Routes
def get_current_user():
    """Get the currently logged in user from session"""
    if 'user_id' not in session:
        return None
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return dict(user)
    return None

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/login/<provider>')
def login(provider):
    if provider not in ['google', 'github', 'joshatticus']:
        return "Provider not supported", 400
    
    redirect_uri = url_for('auth_callback', provider=provider, _external=True)
    return oauth.create_client(provider).authorize_redirect(redirect_uri)

@app.route('/auth/callback/<provider>')
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
        # GitHub email might be private
        email_resp = client.get('user/emails')
        if email_resp.status_code == 200:
            emails = email_resp.json()
            for e in emails:
                if e.get('primary') and e.get('verified'):
                    email = e.get('email')
                    email_verified = True
                    break
                    
    elif provider == 'joshatticus':
        # Don't use OpenID claims (id_token), use OAuth2 claims (userinfo endpoint)
        user_info = client.userinfo()
        
        oauth_id = user_info.get('sub')
        email = user_info.get('email')
        email_verified = user_info.get('email_verified', False)
        name = user_info.get('name')
        if not name:
            name = user_info.get('preferred_username')
        if not name:
            name = user_info.get('nickname')
        if not name and email:
            name = email.split('@')[0]
            
        picture = user_info.get('picture') or user_info.get('profile_picture')

    if not oauth_id:
        return "Could not retrieve user information", 400
        
    # Save or update user in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE oauth_provider = ? AND oauth_id = ?', (provider, oauth_id))
    existing_user = cursor.fetchone()
    
    if existing_user:
        user_id = existing_user[0]
        cursor.execute('''
            UPDATE users 
            SET email = ?, email_verified = ?, name = ?, picture = ? 
            WHERE id = ?
        ''', (email, email_verified, name, picture, user_id))
    else:
        # Check if this is the first user (make admin)
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

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/')

@app.route('/api/auth/status')
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

def get_share_platform_from_user_agent(user_agent):
    """Return platform name if user agent matches a known share bot, else None"""
    if not user_agent:
        return None
    bot_map = {
        'discordbot': 'discord',
        'twitterbot': 'twitter',
        'facebookexternalhit': 'facebook',
        'facebookbot': 'facebook',
        'whatsapp': 'whatsapp',
        'telegrambot': 'telegram',
        'slackbot': 'slack',
        'linkedinbot': 'linkedin',
        'pinterestbot': 'pinterest',
        'redditbot': 'reddit',
        'tumblr': 'tumblr',
        'mastodon': 'mastodon',
        'skypebot': 'skype',
        'slackbot-linkexpanding': 'slack',
        'slack-imgproxy': 'slack',
        'iframely': 'iframely',
        'bitlybot': 'bitly',
        'embedly': 'embedly',
        'snapchat': 'snapchat',
        'instagrambot': 'instagram',
        'signal': 'signal',
        'imessage': 'imessage',
    }
    user_agent_lower = user_agent.lower()
    for sig, platform in bot_map.items():
        if sig in user_agent_lower:
            return platform
    return None

def hash_ip(ip_address):
    """Hash IP address for privacy"""
    return hashlib.sha256(ip_address.encode()).hexdigest()

def get_client_ip():
    """Get client IP address, considering X-Forwarded-For header"""
    if 'X-Forwarded-For' in request.headers:
        # Get the first IP in the chain (original client)
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr or ''

def check_ip_rate_limit(slug, ip_hash):
    """Check if IP has exceeded rate limit (5 views per post per month)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get views from this IP in the last 30 days
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM analytics_pageviews 
        WHERE slug = ? AND ip_hash = ? AND viewed_at > ? AND event_type = 'view'
    ''', (slug, ip_hash, thirty_days_ago))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count < 5

def has_user_viewed(slug, user_id):
    """Check if user has already viewed this post"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM analytics_pageviews WHERE slug = ? AND user_id = ? AND event_type = 'view'
    ''', (slug, user_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# record_user_view is no longer needed as log_analytics_view handles it

def get_view_count(slug):
    """Get the view count for a post"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT view_count FROM post_views WHERE slug = ?', (slug,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_shares_count(slug):
    """Get the shares count for a post"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT shares_count FROM post_views WHERE slug = ?', (slug,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def increment_view_count(slug):
    """Increment the view count for a post"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO post_views (slug, view_count, last_viewed)
        VALUES (?, 1, ?)
        ON CONFLICT(slug) DO UPDATE SET
            view_count = view_count + 1,
            last_viewed = ?
    ''', (slug, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def increment_shares_count(slug):
    """Increment the shares count for a post"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO post_views (slug, shares_count, last_viewed)
        VALUES (?, 1, ?)
        ON CONFLICT(slug) DO UPDATE SET
            shares_count = shares_count + 1,
            last_viewed = ?
    ''', (slug, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Log analytics event
    # We might not have request context here if called from background, but usually it is from request
    try:
        user_id = request.cookies.get('blog_user_id') or 'unknown'
        ip_hash = hash_ip(get_client_ip())
        platform = request.args.get('platform') or request.form.get('platform') or request.json.get('platform') if request.is_json else None
        log_analytics_view(slug, user_id, ip_hash, request.user_agent.string, request.referrer, 'share', platform)
    except Exception:
        pass # Fail silently if outside request context

def log_analytics_view(slug, user_id, ip_hash, user_agent, referrer, event_type='view', platform=None):
    """Log a page view or event for analytics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO analytics_pageviews (slug, user_id, ip_hash, user_agent, referrer, event_type, platform, viewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (slug, user_id, ip_hash, user_agent, referrer, event_type, platform, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# --- Share analytics via bot user agent detection ---
@app.before_request
def auto_log_share_from_bot():
    # Only log for GET requests to post pages
    if request.method != 'GET':
        return
    path = request.path
    # crude check for post URL, adjust if needed
    if path.startswith('/posts/') and not path.endswith('-assets') and '.' not in path.split('/')[-1]:
        user_agent = request.user_agent.string
        platform = get_share_platform_from_user_agent(user_agent)
        if platform:
            slug = path.split('/posts/')[-1]
            user_id = request.cookies.get('blog_user_id') or 'unknown'
            ip_hash = hash_ip(get_client_ip())
            # Only log if not already logged in this session for this slug/platform
            key = f'sharebot_{slug}_{platform}'
            if not cache.get(key):
                log_analytics_view(slug, user_id, ip_hash, user_agent, request.referrer, 'share', platform)
                cache.set(key, True, timeout=60)  # avoid duplicate logs for same session

MD_EXTENSIONS = [
    'tables',
    'fenced_code',
]

def compress_image(image_path, max_width=MAX_IMAGE_WIDTH, quality=COMPRESSION_QUALITY):
    """Compress an image and return it as bytes"""
    MAX_HEIGHT = 1600
    cache_key = f'img_{image_path}_{max_width}_{quality}'
    cached_image = cache.get(cache_key)
    
    if cached_image is not None:
        return cached_image
    
    try:
        if not image_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            with open(image_path, 'rb') as f:
                file_data = f.read()
            cache.set(cache_key, file_data, CACHE_TIMEOUT)
            return file_data
            
        img = Image.open(image_path)
        
        needs_resize = False
        ratio = 1.0
        
        if img.width > max_width:
            ratio = max_width / img.width
            needs_resize = True
            
        if img.height > MAX_HEIGHT:
            height_ratio = MAX_HEIGHT / img.height
            ratio = min(ratio, height_ratio)
            needs_resize = True
            
        if needs_resize:
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
        
        output = io.BytesIO()
        format = image_path.lower().split('.')[-1]
        if format == 'jpg':
            format = 'jpeg'
        
        final_quality = quality
        if img.width * img.height > 2000000:
            final_quality = min(quality, 75)
        
        img.save(output, format=format, optimize=True, quality=final_quality)
        output.seek(0)
        compressed_data = output.getvalue()
        
        cache.set(cache_key, compressed_data, CACHE_TIMEOUT)
        return compressed_data
    except Exception as e:
        print(f"Error compressing {image_path}: {e}")
        with open(image_path, 'rb') as f:
            file_data = f.read()
        cache.set(cache_key, file_data, CACHE_TIMEOUT)
        return file_data

def generate_image_sizes(image_path):
    """Generate three sizes of an image: placeholder (blur), thumbnail, and full"""
    sizes = {
        'placeholder': (50, 20),  # Very small, low quality for instant load
        'thumbnail': (800, 70),    # Medium size for main display
        'full': (1200, 85)         # Full quality
    }
    
    results = {}
    for size_name, (width, quality) in sizes.items():
        cache_key = f'img_{image_path}_{size_name}_{width}_{quality}'
        cached_data = cache.get(cache_key)
        
        if cached_data is not None:
            results[size_name] = cached_data
            continue
        
        try:
            if not image_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                with open(image_path, 'rb') as f:
                    file_data = f.read()
                results[size_name] = file_data
                cache.set(cache_key, file_data, CACHE_TIMEOUT)
                continue
            
            img = Image.open(image_path)
            
            # Calculate resize ratio
            ratio = min(width / img.width, 1.0)
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            
            if ratio < 1.0:
                resized_img = img.resize((new_width, new_height), Image.LANCZOS)
            else:
                resized_img = img
            
            output = io.BytesIO()
            format = image_path.lower().split('.')[-1]
            if format == 'jpg':
                format = 'jpeg'
            
            resized_img.save(output, format=format, optimize=True, quality=quality)
            output.seek(0)
            compressed_data = output.getvalue()
            
            results[size_name] = compressed_data
            cache.set(cache_key, compressed_data, CACHE_TIMEOUT)
            
        except Exception as e:
            print(f"Error generating {size_name} for {image_path}: {e}")
            with open(image_path, 'rb') as f:
                file_data = f.read()
            results[size_name] = file_data
            cache.set(cache_key, file_data, CACHE_TIMEOUT)
    
    return results

def parse_front_matter(content):
    """Parse front matter from Markdown content"""
    front_matter = {}
    
    front_matter_match = re.match(r"---\n(.*?)\n---", content, re.DOTALL)
    if front_matter_match:
        front_matter_text = front_matter_match.group(1)
        
        title_match = re.search(r"title:\s*(.*)", front_matter_text)
        if title_match:
            front_matter['title'] = title_match.group(1).strip()
        
        date_match = re.search(r"date:\s*(.*)", front_matter_text)
        if date_match:
            front_matter['date'] = date_match.group(1).strip()
        
        # Parse custom summary if provided
        summary_match = re.search(r"summary:\s*(.*)", front_matter_text)
        if summary_match:
            front_matter['summary'] = summary_match.group(1).strip()
        
        # Parse wasteof.money link
        wasteof_match = re.search(r"wasteof_link:\s*(.*)", front_matter_text)
        if wasteof_match:
            front_matter['wasteof_link'] = wasteof_match.group(1).strip()

        tags_match = re.search(r"tags:\s*\[(.*?)\]", front_matter_text, re.DOTALL)
        if tags_match:
            tags_text = tags_match.group(1)
            tags = [tag.strip().strip('"\'') for tag in tags_text.split(',')]
            front_matter['tags'] = [tag for tag in tags if tag]
        else:
            tags_match = re.search(r"tags:\s*(.*)", front_matter_text)
            if tags_match:
                tags_text = tags_match.group(1)
                tags = [tag.strip().strip('"\'') for tag in tags_text.split(',')]
                front_matter['tags'] = [tag for tag in tags if tag]
            else:
                front_matter['tags'] = []
    
    return front_matter

def extract_and_remove_first_image(html_content):
    img_match = re.search(r'<p><img.*?src=["\'](?:\.\./)?(.*?)["\'].*?></p>', html_content)
    first_image = ""
    content_without_first_image = html_content
    
    if img_match:
        first_image = img_match.group(1)
        content_without_first_image = re.sub(r'<p><img.*?src=["\'](?:\.\./)?' + 
                                           re.escape(first_image) + 
                                           r'["\'].*?></p>', '', html_content, count=1)
    
    return first_image, content_without_first_image

def enforce_link_target_blank(html_content: str) -> str:
    """Ensure all <a> tags open in a new tab with safe rel attributes.
    - Adds target="_blank" and rel="noopener noreferrer" to all anchor tags.
    - Replaces existing target/rel if present.
    """
    if not html_content:
        return html_content

    def repl(match: re.Match) -> str:
        attrs = match.group(1) or ""
        attrs = re.sub(r"\s*target\s*=\s*\"[^\"]*\"", "", attrs, flags=re.IGNORECASE)
        attrs = re.sub(r"\s*target\s*=\s*'[^']*'", "", attrs, flags=re.IGNORECASE)
        attrs = re.sub(r"\s*rel\s*=\s*\"[^\"]*\"", "", attrs, flags=re.IGNORECASE)
        attrs = re.sub(r"\s*rel\s*=\s*'[^']*'", "", attrs, flags=re.IGNORECASE)
        attrs = re.sub(r"\s+", " ", attrs).strip()
        if attrs:
            attrs = " " + attrs
        return f"<a{attrs} target=\"_blank\" rel=\"noopener noreferrer\">"

    return re.sub(r"<a\s+([^>]*)>", repl, html_content, flags=re.IGNORECASE)

def clean_for_summary(html_content):
    text = re.sub(r"<[^>]+>", "", html_content)
    return text.strip()

def process_image_comparison(html_content):
    """
    Replaces [[compare: left_image | right_image | caption]] with HTML for comparison slider.
    Caption is optional.
    Handles potential <p> wrappers added by Markdown.
    """
    pattern = r'(?:<p>\s*)?\[\[compare:\s*(.*?)\s*\|\s*(.*?)(?:\s*\|\s*(.*?))?\]\](?:\s*</p>)?'
    
    def repl(match):
        left_img = match.group(1)
        right_img = match.group(2)
        caption = match.group(3) if match.group(3) else ""
        
        html = f'''
        <div class="comparison-container">
          <div class="comparison-inner">
            <img class="comparison-image-under" src="{left_img}" alt="">
            <img class="comparison-image-over" src="{right_img}" alt="">
            <div class="comparison-slider">
              <div class="comparison-handle"></div>
            </div>
          </div>
          <div class="comparison-caption">{caption}</div>
        </div>
        '''
        return html

    return re.sub(pattern, repl, html_content)

def process_twitter_embed(html_content):
    """
    Replaces [[twitter: url]] with Twitter embed HTML.
    """
    pattern = r'(?:<p>\s*)?\[\[twitter:\s*(.*?)\]\](?:\s*</p>)?'
    
    def repl(match):
        url = match.group(1).strip()
        
        html = f'''
        <blockquote class="twitter-tweet" data-dnt="true" data-theme="dark">
          <a href="{url}">Loading Twitter embed, if it's not loading, click here to open the post in a new tab</a>
        </blockquote>
        <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
        '''
        return html

    return re.sub(pattern, repl, html_content)

def process_wasteof_comment(cursor, post_slug, comment_data, parent_external_id):
    external_id = comment_data['_id']
    user_id = comment_data['poster']['id']
    author_name = comment_data['poster']['name']
    content = comment_data['content'] # HTML content
    
    # Strip HTML
    content = re.sub(r'<br\s*/?>', '\n', content)
    content = re.sub(r'</p>', '\n\n', content)
    content = re.sub(r'<[^>]+>', '', content)
    content = content.strip()
    
    created_at = datetime.fromtimestamp(comment_data['time'] / 1000, timezone.utc).isoformat()
    
    # Get avatar
    avatar_url = f"https://api.wasteof.money/users/{author_name}/picture"
    
    # Check if exists
    cursor.execute('SELECT id FROM comments WHERE external_id = ?', (external_id,))
    existing = cursor.fetchone()
    
    # Resolve parent_id
    parent_db_id = None
    if parent_external_id:
        cursor.execute('SELECT id FROM comments WHERE external_id = ?', (parent_external_id,))
        parent_row = cursor.fetchone()
        if parent_row:
            parent_db_id = parent_row[0]
    
    if existing:
        # Update
        cursor.execute('''
            UPDATE comments 
            SET comment_text = ?, author_name = ?, author_avatar_url = ?, parent_id = ?
            WHERE id = ?
        ''', (content, author_name, avatar_url, parent_db_id, existing[0]))
    else:
        # Insert
        cursor.execute('''
            INSERT INTO comments (slug, user_id, author_name, comment_text, parent_id, created_at, ip_hash, source, external_id, author_avatar_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (post_slug, user_id, author_name, content, parent_db_id, created_at, 'wasteof', 'wasteof', external_id, avatar_url))

def fetch_wasteof_replies(cursor, post_slug, comment_id):
    page = 1
    headers = {
        'User-Agent': 'JoshAtticusBlog/1.0 +https://blog.joshattic.us/bot'
    }
    while True:
        try:
            resp = requests.get(f"https://api.wasteof.money/comments/{comment_id}/replies?page={page}", headers=headers, timeout=10)
            if resp.status_code != 200:
                break
            data = resp.json()
            for reply in data.get('comments', []):
                process_wasteof_comment(cursor, post_slug, reply, comment_id)
                # Recursively fetch replies to replies
                if reply.get('hasReplies'):
                    fetch_wasteof_replies(cursor, post_slug, reply['_id'])
            
            if data.get('last', True):
                break
            page += 1
        except Exception as e:
            print(f"Error fetching wasteof replies: {e}")
            break

def sync_wasteof_comments(post_slug, wasteof_link):
    """Sync comments from wasteof.money"""
    try:
        # Extract post ID
        match = re.search(r'wasteof\.money/posts/([a-f0-9]+)', wasteof_link)
        if not match:
            print(f"Invalid wasteof link for {post_slug}: {wasteof_link}")
            return
        
        post_id = match.group(1)
        
        # Fetch comments
        comments = []
        page = 1
        headers = {
            'User-Agent': 'JoshAtticusBlog/1.0 +https://blog.joshattic.us/bot'
        }
        while True:
            try:
                resp = requests.get(f"https://api.wasteof.money/posts/{post_id}/comments?page={page}", headers=headers, timeout=10)
                if resp.status_code != 200:
                    break
                data = resp.json()
                comments.extend(data.get('comments', []))
                if data.get('last', True):
                    break
                page += 1
            except Exception as e:
                print(f"Error fetching wasteof comments page {page}: {e}")
                break
        
        # Process comments
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for comment in comments:
            process_wasteof_comment(cursor, post_slug, comment, None)
            
            # Handle replies
            if comment.get('hasReplies'):
                fetch_wasteof_replies(cursor, post_slug, comment['_id'])
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error syncing wasteof comments for {post_slug}: {e}")

def run_wasteof_sync():
    # Use a lock file to ensure only one worker runs the sync
    lock_file_path = '/tmp/wasteof_sync.lock'
    try:
        f = open(lock_file_path, 'w')
    except IOError:
        print("Could not open lock file for sync")
        return

    while True:
        try:
            # Try to acquire an exclusive non-blocking lock
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # If we are here, we have the lock
            try:
                print("Starting wasteof.money sync...")
                posts = get_all_posts()
                cutoff_date = datetime.now() - timedelta(days=90)
                for post in posts:
                    if post.get('wasteof_link'):
                        should_sync = False
                        try:
                            # Parse post date (YYYY-MM-DD)
                            post_date = datetime.strptime(post['date'], "%Y-%m-%d")
                            if post_date > cutoff_date:
                                should_sync = True
                        except (ValueError, TypeError):
                            # If date parsing fails, default to syncing to be safe
                            should_sync = True
                            
                        if should_sync:
                            sync_wasteof_comments(post['slug'], post['wasteof_link'])
                print("Wasteof.money sync completed.")
            except Exception as e:
                print(f"Error in wasteof sync loop: {e}")
            
            # Sleep for 15 minutes while holding the lock
            # This prevents other workers from taking over
            time.sleep(900) 
            
        except IOError:
            # Could not acquire lock, another worker is syncing
            # Sleep a bit and try again later
            time.sleep(60)
        except Exception as e:
            print(f"Unexpected error in sync thread: {e}")
            time.sleep(60)

def start_wasteof_sync_thread():
    thread = threading.Thread(target=run_wasteof_sync, daemon=True)
    thread.start()

def get_all_posts():
    """Get all posts with their metadata"""
    posts = cache.get('all_posts')
    if posts is not None:
        return posts
    
    posts = []
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            with open(os.path.join(POSTS_DIR, filename), "r", encoding="utf-8") as f:
                content = f.read()
            
            front_matter = parse_front_matter(content)
            
            content_without_front_matter = re.sub(r"---\n.*?\n---\n", "", content, flags=re.DOTALL)
            
            html_content = markdown.markdown(content_without_front_matter, extensions=MD_EXTENSIONS)
            html_content = enforce_link_target_blank(html_content)
            html_content = process_image_comparison(html_content)
            html_content = process_twitter_embed(html_content)
            
            first_image, content_without_first_image = extract_and_remove_first_image(html_content)
            
            if not first_image:
                first_image = "assets/default-banner.jpg" # there is no default banner I put this here so python doesn't shit itself but it probably still will so I haven't tested it
            
            # Use custom summary from front matter if available, otherwise auto-generate
            if 'summary' in front_matter:
                summary_text = front_matter['summary']
            else:
                summary_text = clean_for_summary(html_content)
                summary_text = summary_text[:150] + "..." if len(summary_text) > 150 else summary_text
            
            post_filename = os.path.splitext(filename)[0] + ".html"
            
            posts.append({
                "title": front_matter.get('title', "Untitled"),
                "date": front_matter.get('date', datetime.now().strftime("%Y-%m-%d")),
                "filename": post_filename,
                "slug": os.path.splitext(filename)[0],
                "summary": summary_text,
                "image": first_image,
                "tags": front_matter.get('tags', []),
                "content": content_without_first_image,
                "wasteof_link": front_matter.get('wasteof_link')
            })
    
    posts.sort(key=lambda x: x["date"], reverse=True)
    
    cache.set('all_posts', posts, CACHE_TIMEOUT)
    
    return posts

def get_post_by_slug(slug):
    """Get a specific post by its slug"""
    cache_key = f'post_{slug}'
    cached_post = cache.get(cache_key)
    if cached_post is not None:
        return cached_post
    
    posts = get_all_posts()
    for post in posts:
        if post['slug'] == slug:
            cache.set(cache_key, post, CACHE_TIMEOUT)
            return post
    
    return None

def get_tags():
    """Get all tags with count of posts"""
    cache_key = 'all_tags'
    cached_tags = cache.get(cache_key)
    if cached_tags is not None:
        return cached_tags
    
    posts = get_all_posts()
    tags = {}
    
    for post in posts:
        for tag in post.get('tags', []):
            if tag not in tags:
                tags[tag] = {
                    'name': tag,
                    'count': 0,
                    'slug': tag.lower().replace(' ', '-')
                }
            tags[tag]['count'] += 1
    
    tags_list = list(tags.values())
    tags_list.sort(key=lambda x: x['name'])
    
    cache.set(cache_key, tags_list, CACHE_TIMEOUT)
    return tags_list

def get_posts_by_tag(tag):
    """Get all posts with a specific tag"""
    cache_key = f'tag_{tag}'
    cached_posts = cache.get(cache_key)
    if cached_posts is not None:
        return cached_posts
    
    posts = get_all_posts()
    tag_lower = tag.lower()
    
    tagged_posts = [post for post in posts if any(t.lower().replace(' ', '-') == tag_lower for t in post.get('tags', []))]
    
    if not tagged_posts:
        tag_name = tag_lower.replace('-', ' ')
        tagged_posts = [post for post in posts if any(t.lower() == tag_name for t in post.get('tags', []))]
    
    cache.set(cache_key, tagged_posts, CACHE_TIMEOUT)
    return tagged_posts

def get_comments_for_post(slug, page=None, per_page=20):
    """Get comments for a post, optionally paginated by top-level threads"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if page:
        # Count top-level comments
        cursor.execute('SELECT COUNT(*) FROM comments WHERE slug = ? AND parent_id IS NULL', (slug,))
        total_top_level = cursor.fetchone()[0]
        total_pages = (total_top_level + per_page - 1) // per_page if total_top_level > 0 else 1
        
        offset = (page - 1) * per_page
        
        # Get top-level comments for this page
        cursor.execute('''
            SELECT id
            FROM comments
            WHERE slug = ? AND parent_id IS NULL
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (slug, per_page, offset))
        
        top_level_rows = cursor.fetchall()
        top_level_ids = [row['id'] for row in top_level_rows]
        
        if not top_level_ids:
             conn.close()
             return [], 1, 0
             
        # Get full tree for these top-level comments using Recursive CTE
        placeholders = ','.join(['?'] * len(top_level_ids))
        query = f'''
            WITH RECURSIVE comment_tree AS (
                SELECT id, user_id, author_name, comment_text, parent_id, created_at, is_deleted, edited_at, source, external_id, author_avatar_url
                FROM comments 
                WHERE id IN ({placeholders})
                UNION ALL
                SELECT c.id, c.user_id, c.author_name, c.comment_text, c.parent_id, c.created_at, c.is_deleted, c.edited_at, c.source, c.external_id, c.author_avatar_url
                FROM comments c
                JOIN comment_tree ct ON c.parent_id = ct.id
            )
            SELECT ct.*, u.picture 
            FROM comment_tree ct
            LEFT JOIN users u ON ct.user_id = CAST(u.id AS TEXT)
            ORDER BY ct.created_at ASC
        '''
        cursor.execute(query, top_level_ids)
        rows = cursor.fetchall()
        comments = [dict(row) for row in rows]
        conn.close()
        return comments, total_pages, total_top_level
        
    else:
        cursor.execute('''
            SELECT c.id, c.user_id, c.author_name, c.comment_text, c.parent_id, c.created_at, c.is_deleted, c.edited_at, u.picture
            FROM comments c
            LEFT JOIN users u ON c.user_id = CAST(u.id AS TEXT)
            WHERE c.slug = ?
            ORDER BY c.created_at ASC
        ''', (slug,))
        
        rows = cursor.fetchall()
        conn.close()
        
        comments = [dict(row) for row in rows]
        return comments, 1, len(comments)

def edit_comment(comment_id, user_id, new_text):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Verify ownership
    cursor.execute('SELECT user_id, comment_text FROM comments WHERE id = ?', (comment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Comment not found"
    
    if str(row[0]) != str(user_id):
        conn.close()
        return False, "Unauthorized"
        
    old_text = row[1]
    now = datetime.now().isoformat()
    
    # Save history
    cursor.execute('INSERT INTO comment_history (comment_id, old_text, edited_at) VALUES (?, ?, ?)', 
                  (comment_id, old_text, now))
                  
    # Update comment
    cursor.execute('UPDATE comments SET comment_text = ?, edited_at = ? WHERE id = ?', 
                  (new_text, now, comment_id))
                  
    conn.commit()
    conn.close()
    return True, None

def delete_comment(comment_id, user_id, is_admin=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Verify ownership
    cursor.execute('SELECT user_id FROM comments WHERE id = ?', (comment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Comment not found"
    
    if str(row[0]) != str(user_id) and not is_admin:
        conn.close()
        return False, "Unauthorized"
        
    cursor.execute('UPDATE comments SET is_deleted = 1 WHERE id = ?', (comment_id,))
    
    conn.commit()
    conn.close()
    return True, None

def add_comment(slug, user_id, author_name, comment_text, parent_id, ip_hash):
    """Add a new comment"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO comments (slug, user_id, author_name, comment_text, parent_id, created_at, ip_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (slug, user_id, author_name, comment_text, parent_id, datetime.now().isoformat(), ip_hash))
    
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return comment_id

def check_comment_rate_limit(user_id, ip_hash):
    """Check if user/IP can post comment (max 10 per hour)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM comments
        WHERE (user_id = ? OR ip_hash = ?) AND created_at > ?
    ''', (user_id, ip_hash, one_hour_ago))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count < 10

def check_reply_rate_limit(user_id, ip_hash):
    """Check if user/IP can post reply (max 5 per 10 minutes)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    ten_minutes_ago = (datetime.now() - timedelta(minutes=10)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM comments
        WHERE (user_id = ? OR ip_hash = ?) AND created_at > ? AND parent_id IS NOT NULL
    ''', (user_id, ip_hash, ten_minutes_ago))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count < 5

# api endpoints
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    all_posts = get_all_posts()
    total_posts = len(all_posts)
    total_pages = (total_posts + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    end = start + per_page
    posts = all_posts[start:end]
    
    return render_template('index.html', 
                          posts=posts, 
                          year=datetime.now().year,
                          page=page,
                          total_pages=total_pages)

@app.route('/posts/<slug>')
def post(slug):
    post = get_post_by_slug(slug)
    if not post:
        return redirect(url_for('index'))
    
    user_agent = request.headers.get('User-Agent', '')
    platform = get_share_platform_from_user_agent(user_agent)
    # If it's a bot, increment shares count with platform
    if platform:
        increment_shares_count(slug)  # Optionally pass platform if you update increment_shares_count
    else:
        # Get or create user ID from cookie
        user_id = request.cookies.get('blog_user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
        # Get client IP and hash it
        client_ip = get_client_ip()
        ip_hash = hash_ip(client_ip)
        
        # Check if this user has viewed this post (before logging current view)
        has_viewed = has_user_viewed(slug, user_id)
        
        # Check IP rate limit
        within_rate_limit = check_ip_rate_limit(slug, ip_hash)
        
        # Log analytics view (every hit)
        log_analytics_view(slug, user_id, ip_hash, user_agent, request.referrer)
        
        # Only count view if user hasn't viewed AND IP is within rate limit
        if not has_viewed and within_rate_limit:
            increment_view_count(slug)
            # record_user_view is handled by log_analytics_view now
    
    # Get counts
    view_count = get_view_count(slug)
    shares_count = get_shares_count(slug)
    
    post_url = f"https://blog.joshattic.us/posts/{post['filename']}"
    absolute_image_url = f"https://blog.joshattic.us/{post['image']}"
    
    response = make_response(render_template('post.html', 
                          post=post, 
                          year=datetime.now().year,
                          url=post_url,
                          absolute_image_url=absolute_image_url,
                          view_count=view_count,
                          shares_count=shares_count))
    
    # Set user ID cookie if it doesn't exist (expires in 1 year)
    if not platform and not request.cookies.get('blog_user_id'):
        expires = datetime.now() + timedelta(days=365)
        response.set_cookie('blog_user_id', user_id, expires=expires, httponly=True, samesite='Lax')
    
    return response

@app.route('/bot')
def bot_page():
    return render_template('bot.html', year=datetime.now().year)

@app.route('/tags')
def tags():
    all_tags = get_tags()
    return render_template('tags.html', tags=all_tags, year=datetime.now().year)

@app.route('/tags/<tag_slug>')
def tag(tag_slug):
    tagged_posts = get_posts_by_tag(tag_slug)
    
    tag_name = tag_slug.replace('-', ' ')
    
    return render_template('tag.html', 
                          tag=tag_name, 
                          posts=tagged_posts, 
                          year=datetime.now().year)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 12
    results = []
    
    if query:
        posts = get_all_posts()
        query_lower = query.lower()
        
        for post in posts:
            if (query_lower in post['title'].lower() or 
                query_lower in post['summary'].lower() or 
                any(query_lower in tag.lower() for tag in post['tags'])):
                results.append(post)
    
    total_results = len(results)
    total_pages = (total_results + per_page - 1) // per_page if total_results > 0 else 1
    
    start = (page - 1) * per_page
    end = start + per_page
    paginated_results = results[start:end]
    
    return render_template('search.html', 
                          results=paginated_results, 
                          query=query, 
                          year=datetime.now().year,
                          page=page,
                          total_pages=total_pages,
                          total_results=total_results)

@app.route('/api/search')
def api_search():
    """API endpoint for search to support instant search"""
    query = request.args.get('q', '').lower()
    results = []
    
    if query:
        posts = get_all_posts()
        
        for post in posts:
            if (query in post['title'].lower() or 
                query in post['summary'].lower() or 
                any(query in tag.lower() for tag in post['tags'])):
                results.append(post)
    
    return jsonify({"results": results})

@app.route('/api/comments/<slug>', methods=['GET', 'POST'])
def comments_api(slug):
    if request.method == 'GET':
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        comments, total_pages, total_comments = get_comments_for_post(slug, page, per_page)
        user = get_current_user()
        is_admin = user and user.get('is_admin')
        
        # Process comments to mask deleted ones
        for comment in comments:
            if comment['is_deleted']:
                if not is_admin:
                    comment['author_name'] = '[Deleted by user]'
                    comment['comment_text'] = '[Deleted by user]'
                    comment['picture'] = None 
                else:
                    comment['comment_text'] = f"[DELETED] {comment['comment_text']}"
        
        return jsonify({
            "comments": comments,
            "page": page,
            "total_pages": total_pages,
            "total_comments": total_comments
        })
    
    elif request.method == 'POST':
        # Check authentication
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
            
        # Check email verification
        if not user.get('email_verified'):
            return jsonify({"error": "Verified email required to comment"}), 403
            
        data = request.get_json()
        
        # Use authenticated user info
        user_id = str(user['id'])
        author_name = user['name']
        
        # Get IP and hash it
        client_ip = get_client_ip()
        ip_hash = hash_ip(client_ip)
        
        # Rate limiting
        if not check_comment_rate_limit(user_id, ip_hash):
            return jsonify({"error": "Rate limit exceeded. Please wait before posting again."}), 429
            
        # Reply rate limiting
        parent_id = data.get('parent_id')
        if parent_id and not check_reply_rate_limit(user_id, ip_hash):
             return jsonify({"error": "Reply rate limit exceeded. Please wait before replying again."}), 429
        
        comment_text = data.get('comment_text', '').strip()
        
        # Validation
        if not comment_text:
            return jsonify({"error": "Comment text is required"}), 400
            
        if len(comment_text) > 1500:
            return jsonify({"error": "Comment exceeds 1500 characters"}), 400
            
        # Security: Escape HTML and strip newlines
        import html
        comment_text = html.escape(comment_text)
        comment_text = comment_text.replace('\n', ' ').replace('\r', '')
        
        add_comment(slug, user_id, author_name, comment_text, parent_id, ip_hash)
        
        return jsonify({"success": True})

@app.route('/api/comments/<int:comment_id>', methods=['PUT', 'DELETE'])
def comment_action_api(comment_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
        
    user_id = str(user['id'])
    
    if request.method == 'PUT':
        data = request.get_json()
        new_text = data.get('comment_text', '').strip()
        
        if not new_text:
            return jsonify({"error": "Comment text is required"}), 400
            
        if len(new_text) > 1500:
            return jsonify({"error": "Comment exceeds 1500 characters"}), 400
            
        import html
        new_text = html.escape(new_text)
        new_text = new_text.replace('\n', ' ').replace('\r', '')
        
        success, error = edit_comment(comment_id, user_id, new_text)
        if not success:
            return jsonify({"error": error}), 403
            
        return jsonify({"success": True})
        
    elif request.method == 'DELETE':
        is_admin = user.get('is_admin', False)
        success, error = delete_comment(comment_id, user_id, is_admin)
        if not success:
            return jsonify({"error": error}), 403
            
        return jsonify({"success": True})

@app.route('/admin')
def admin_panel():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return redirect(url_for('index'))
    return render_template('admin.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/api/admin/users')
def admin_users():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
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
    
    return jsonify({
        "users": users,
        "page": page,
        "total_pages": total_pages,
        "total_users": total_users
    })

@app.route('/api/admin/comments')
def admin_comments():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    slug_filter = request.args.get('slug')
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if slug_filter:
        cursor.execute('SELECT COUNT(*) FROM comments WHERE slug = ?', (slug_filter,))
    else:
        cursor.execute('SELECT COUNT(*) FROM comments')
        
    total_comments = cursor.fetchone()[0]
    total_pages = (total_comments + per_page - 1) // per_page if total_comments > 0 else 1
    
    if slug_filter:
        cursor.execute('''
            SELECT c.*, u.name as author_name, u.email, u.picture
            FROM comments c 
            LEFT JOIN users u ON c.user_id = CAST(u.id AS TEXT)
            WHERE c.slug = ?
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        ''', (slug_filter, per_page, offset))
    else:
        cursor.execute('''
            SELECT c.*, u.name as author_name, u.email, u.picture
            FROM comments c 
            LEFT JOIN users u ON c.user_id = CAST(u.id AS TEXT)
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset))
        
    comments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Enrich comments with post info
    all_posts = get_all_posts()
    posts_map = {post['slug']: post for post in all_posts}
    
    for comment in comments:
        post = posts_map.get(comment['slug'])
        if post:
            comment['post_title'] = post['title']
            # Get first image or default
            if post.get('image'):
                comment['post_image'] = post['image']
            else:
                comment['post_image'] = None
        else:
            comment['post_title'] = comment['slug']
            comment['post_image'] = None
    
    return jsonify({
        "comments": comments,
        "page": page,
        "total_pages": total_pages,
        "total_comments": total_comments
    })

@app.route('/api/analytics/overview')
def analytics_overview():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total views (all time)
    cursor.execute("SELECT COUNT(*) FROM analytics_pageviews WHERE event_type = 'view'")
    total_views = cursor.fetchone()[0]
    
    # Total unique views (all time) - approximate by ip_hash
    cursor.execute("SELECT COUNT(DISTINCT ip_hash) FROM analytics_pageviews WHERE event_type = 'view'")
    total_unique_views = cursor.fetchone()[0]
    
    # Total shares (all time)
    cursor.execute("SELECT COUNT(*) FROM analytics_pageviews WHERE event_type = 'share'")
    total_shares = cursor.fetchone()[0]
    
    # Views last 30 days
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM analytics_pageviews WHERE event_type = 'view' AND viewed_at > ?", (thirty_days_ago,))
    views_30d = cursor.fetchone()[0]
    
    # Unique visitors (last 30 days) - approximate by ip_hash
    cursor.execute("SELECT COUNT(DISTINCT ip_hash) FROM analytics_pageviews WHERE event_type = 'view' AND viewed_at > ?", (thirty_days_ago,))
    visitors_30d = cursor.fetchone()[0]
    
    # Top posts (last 30 days)
    cursor.execute('''
        SELECT slug, COUNT(*) as count 
        FROM analytics_pageviews 
        WHERE event_type = 'view' AND viewed_at > ? 
        GROUP BY slug 
        ORDER BY count DESC 
        LIMIT 5
    ''', (thirty_days_ago,))
    top_posts = [{"slug": row[0], "views": row[1]} for row in cursor.fetchall()]
    
    conn.close()
    
    # Enrich top posts with titles
    all_posts = get_all_posts()
    posts_map = {post['slug']: post for post in all_posts}
    for p in top_posts:
        post = posts_map.get(p['slug'])
        if post:
            p['title'] = post['title']
        else:
            p['title'] = p['slug']
            
    return jsonify({
        "total_views": total_views,
        "total_unique_views": total_unique_views,
        "total_shares": total_shares,
        "views_30d": views_30d,
        "visitors_30d": visitors_30d,
        "top_posts": top_posts
    })

@app.route('/api/analytics/chart')
def analytics_chart():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('''
        SELECT substr(viewed_at, 1, 10) as day, COUNT(*) 
        FROM analytics_pageviews 
        WHERE event_type = 'view' AND viewed_at > ?
        GROUP BY day
        ORDER BY day
    ''', (thirty_days_ago,))
    daily_views = [{"date": row[0], "views": row[1]} for row in cursor.fetchall()]
    
    conn.close()
    return jsonify(daily_views)

@app.route('/api/analytics/posts')
def analytics_posts_list():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get view counts per post
    cursor.execute('''
        SELECT slug, COUNT(*) as count 
        FROM analytics_pageviews 
        GROUP BY slug
    ''')
    view_counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    all_posts = get_all_posts()
    result = []
    for post in all_posts:
        result.append({
            "slug": post['slug'],
            "title": post['title'],
            "date": post['date'],
            "image": post.get('image'),
            "views": view_counts.get(post['slug'], 0)
        })
        
    # Sort by date desc
    result.sort(key=lambda x: x['date'], reverse=True)
    
    return jsonify(result)

@app.route('/api/analytics/posts/<slug>')
def analytics_post_detail(slug):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total views for this post
    cursor.execute('SELECT COUNT(*) FROM analytics_pageviews WHERE slug = ?', (slug,))
    total_views = cursor.fetchone()[0]
    
    # Views over time (last 30 days)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('''
        SELECT substr(viewed_at, 1, 10) as day, COUNT(*) 
        FROM analytics_pageviews 
        WHERE slug = ? AND viewed_at > ?
        GROUP BY day
        ORDER BY day
    ''', (slug, thirty_days_ago))
    daily_views = [{"date": row[0], "views": row[1]} for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        "slug": slug,
        "total_views": total_views,
        "daily_views": daily_views
    })
    
@app.route('/api/analytics/shares_by_platform')
def analytics_shares_by_platform():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(platform, 'unknown') as platform, COUNT(*) as count
        FROM analytics_pageviews
        WHERE event_type = 'share'
        GROUP BY platform
        ORDER BY count DESC
    ''')
    data = [{"platform": row[0], "count": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/admin/comments/reply', methods=['POST'])
def admin_reply_to_comment():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    parent_id = data.get('parent_id')
    slug = data.get('slug')
    comment_text = data.get('comment_text', '').strip()
    if not (parent_id and slug and comment_text):
        return jsonify({"error": "Missing required fields"}), 400
    # Use admin's user_id and name
    user_id = str(user['id'])
    author_name = user['name']
    client_ip = get_client_ip()
    ip_hash = hash_ip(client_ip)
    # No rate limit for admin
    import html
    comment_text = html.escape(comment_text).replace('\n', ' ').replace('\r', '')
    comment_id = add_comment(slug, user_id, author_name, comment_text, parent_id, ip_hash)
    return jsonify({"success": True, "comment_id": comment_id})

@app.route('/style.css')
def style():
    return send_from_directory('.', 'style.css')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/assets/<path:filename>')
def serve_asset(filename):
    size = request.args.get('size', 'full')
    filepath = os.path.join('posts/assets', filename)
    
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        if size in ['placeholder', 'thumbnail', 'full']:
            sizes = generate_image_sizes(filepath)
            image_data = sizes.get(size, sizes['full'])
        else:
            image_data = compress_image(filepath)
        
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        return app.response_class(image_data, mimetype=mimetype)
    return send_from_directory('posts/assets', filename)

@app.route('/posts/assets/<path:filename>')
def serve_post_asset(filename):
    size = request.args.get('size', 'full')
    filepath = os.path.join('posts/assets', filename)
    
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        if size in ['placeholder', 'thumbnail', 'full']:
            sizes = generate_image_sizes(filepath)
            image_data = sizes.get(size, sizes['full'])
        else:
            image_data = compress_image(filepath)
        
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        return app.response_class(image_data, mimetype=mimetype)
    return send_from_directory('posts/assets', filename)

@app.route('/posts/<post_slug>-assets/<path:filename>')
def serve_post_specific_asset(post_slug, filename):
    size = request.args.get('size', 'full')
    dir_path = f'posts/{post_slug}-assets'
    filepath = os.path.join(dir_path, filename)
    
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        if size in ['placeholder', 'thumbnail', 'full']:
            sizes = generate_image_sizes(filepath)
            image_data = sizes.get(size, sizes['full'])
        else:
            image_data = compress_image(filepath)
        
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        return app.response_class(image_data, mimetype=mimetype)
    return send_from_directory(dir_path, filename)

@app.route('/feed.rss')
def rss_feed():
    """Generate an RSS feed of blog posts"""
    fg = FeedGenerator()
    fg.title('JoshAtticus Blog')
    fg.description('Personal blog')
    fg.link(href='https://blog.joshattic.us')
    fg.language('en')
    
    posts = get_all_posts()
    posts = posts[::-1]
    
    for post in posts:
        fe = fg.add_entry()
        fe.title(post['title'])
        fe.link(href=f"https://blog.joshattic.us/posts/{post['slug']}")
        try:
            post_date = datetime.strptime(post['date'], '%Y-%m-%d')
            post_date = post_date.replace(tzinfo=timezone.utc)
            fe.published(post_date)
        except ValueError:
            fe.published(datetime.now(timezone.utc))
        
        content = ""
        if post['image']:
            image_url = f"https://blog.joshattic.us/{post['image']}"
            content += f'<p><img src="{image_url}" alt="{post["title"]}"></p>'
        
        content += post['content']
        fe.content(content, type='html')
        
        for tag in post['tags']:
            fe.category(term=tag)
    
    return app.response_class(fg.rss_str(), mimetype='application/rss+xml')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', 
        error_code=404,
        error_title="Page Not Found",
        error_description="The page you are looking for might have been removed, had its name changed, or is temporarily unavailable."
    ), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', 
        error_code=403,
        error_title="Forbidden",
        error_description="You do not have permission to access this resource."
    ), 403

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
        error_code=500,
        error_title="Internal Server Error",
        error_description="Something went wrong on our end. Please try again later."
    ), 500

@app.errorhandler(401)
def unauthorized(e):
    return render_template('error.html', 
        error_code=401,
        error_title="Unauthorized",
        error_description="You need to be logged in to access this page."
    ), 401

@app.errorhandler(405)
def method_not_allowed(e):
    return render_template('error.html', 
        error_code=405,
        error_title="Method Not Allowed",
        error_description="The method is not allowed for the requested URL."
    ), 405

# Initialize DB and start sync thread when imported (e.g. by Gunicorn)
# We use a lock in run_wasteof_sync to ensure only one worker runs the sync
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true': # Avoid running twice in Flask debug mode reloader
    try:
        init_db()
        start_wasteof_sync_thread()
    except Exception as e:
        print(f"Failed to init: {e}")

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    # init_db and start_wasteof_sync_thread are already called above
    app.run(port=5001)
