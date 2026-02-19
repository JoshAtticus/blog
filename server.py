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
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, jsonify, make_response, session, Response
from cachelib import FileSystemCache
from PIL import Image
import io
from feedgen.feed import FeedGenerator
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
import html
import random

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

IPHUB_KEY = os.environ.get('IPHUB_KEY')

def get_ip_type(ip):
    # Returns: 0 (Residential), 1 (Hosting/Block), -1 (Unknown/Error)
    if not IPHUB_KEY:
        return -1
    try:
        resp = requests.get(f'http://v2.api.iphub.info/ip/{ip}', headers={'X-Key': IPHUB_KEY}, timeout=3)
        if resp.status_code == 200:
            return resp.json().get('block', -1)
    except:
        pass
    return -1

def generate_heavy_payload(ip_id):
    yield b"<!DOCTYPE html><html><head><title>Loading...</title></head><body><h1>Please wait...</h1><div style='display:none;'>"
    total_bytes = 0
    chunk_size = 1024 * 1024 # 1MB chunks
    
    # Target: 5GB
    
    path_template = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><path d='M10 10 H 90 V 90 H 10 L 10 10 " + "L {} {} ".format
    
    while total_bytes < 5 * 1024 * 1024 * 1024:
        # Generate random garbage SVG data
        chunk = ""
        for _ in range(1000): # Batch per chunk
            points = " ".join([f"L {random.randint(0,100)} {random.randint(0,100)}" for _ in range(50)])
            chunk += f"<svg><path d='M0 0 {points} Z'/></svg>"
            
        encoded_chunk = chunk.encode('utf-8')
        len_chunk = len(encoded_chunk)
        total_bytes += len_chunk
        yield encoded_chunk
        
        # Update DB every ~10MB to avoid too many writes
        if total_bytes % (10 * 1024 * 1024) < len_chunk:
            try:
                conn_log = sqlite3.connect(DB_PATH)
                cursor_log = conn_log.cursor()
                cursor_log.execute('UPDATE blocked_ips SET data_sent = data_sent + ? WHERE id = ?', (total_bytes, ip_id))
                conn_log.commit()
                conn_log.close()
                total_bytes = 0 
            except:
                pass

    yield b"</div></body></html>"

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_NAME'] = 'blog_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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

CACHE_TIMEOUT = 60 * 60 
cache = FileSystemCache('flask_cache', threshold=500, default_timeout=CACHE_TIMEOUT)
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
def inject_globals():
    # GDPR (EU + UK) list
    privacy_countries = ['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB', 'UK']
    
    # Get country from Cloudflare header
    country = request.headers.get('CF-IPCountry', '').upper()
    
    # Show in EU/UK or US (for California)
    # If header is missing (e.g. local dev), default to False or maybe True depending on preference.
    # Here defaulting to False to avoid annoyance during dev, can be forced for testing.
    is_privacy_region = country in privacy_countries or country == 'US' or os.environ.get('FORCE_PRIVACY_BANNER') == 'true'
    
    return {
        'year': datetime.now().year,
        'is_privacy_region': is_privacy_region,
        'current_user': get_current_user()
    }

def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
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

    try:
        cursor.execute('ALTER TABLE analytics_pageviews ADD COLUMN event_type TEXT DEFAULT "view"')
    except sqlite3.OperationalError:
        pass
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
    
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN is_deleted BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE comments ADD COLUMN edited_at TEXT')
    except sqlite3.OperationalError:
        pass

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INTEGER NOT NULL,
            old_text TEXT NOT NULL,
            edited_at TEXT NOT NULL,
            FOREIGN KEY (comment_id) REFERENCES comments (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            user_agent TEXT,
            country TEXT,
            reason TEXT,
            blocked_until TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    try:
        cursor.execute('ALTER TABLE blocked_ips ADD COLUMN extra_info TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE blocked_ips ADD COLUMN data_sent INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE blocked_ips ADD COLUMN ip_type INTEGER DEFAULT -1')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE blocked_ips ADD COLUMN tracking_id TEXT')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_blocked_ips_tracking_id ON blocked_ips(tracking_id)')
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint_hash TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blocked_fingerprints_hash ON blocked_fingerprints(fingerprint_hash)')
    
    conn.commit()
    conn.close()

init_db()

@app.route('/robots.txt')
def robots_txt():
    response = make_response("User-agent: *\nDisallow: /wp-admin-login\n")
    response.headers["Content-Type"] = "text/plain"
    return response

from flask import Response

def stream_heavy_block(ip, db_id):
    # Determine IP Type (Residential/Hosting)
    current_type = -1
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT ip_type FROM blocked_ips WHERE id = ?', (db_id,))
        row = cursor.fetchone()
        current_type = row[0] if row else -1
        
        # Check IPHub if not already checked
        if (current_type == -1 or current_type is None) and IPHUB_KEY:
            try:
                r = requests.get(f"http://v2.api.iphub.info/ip/{ip}", headers={"X-Key": IPHUB_KEY}, timeout=3)
                if r.status_code == 200:
                    ctype = r.json().get('block')
                    cursor.execute('UPDATE blocked_ips SET ip_type = ? WHERE id = ?', (ctype, db_id))
                    conn.commit()
                    current_type = ctype
            except Exception as e:
                print(f"IPHub Error: {e}")
        conn.close()
    except Exception:
        pass

    # Generator for Massive Data
    def generate():
        total_streamed = 0
        limit = 5 * 1024 * 1024 * 1024 # 5GB
        chunk_size = 100 * 1024 * 1024 # 100MB for DB updates (reduce write frequency)
        
        # Pre-calculate a LARGER chunk to maximize throughput on 4Gbps link
        # 100KB chunks might be too small for 4Gbps (requires too many context switches)
        # Let's aim for ~1MB chunks to reduce Python loop overhead
        complex_path = "M 0 0 " + " ".join([f"Q {i%500} {(i*2)%500} {(i*3)%500} {(i*4)%500}" for i in range(100)])
        svg_template = f"<svg width='500' height='500'><path d='{complex_path}' fill='none' stroke='black'/></svg>"
        heavy_chunk = (svg_template * 500).encode('utf-8') # Approx 1MB per yield
        chunk_len = len(heavy_chunk)
        
        yield b"<!DOCTYPE html><html><head><title>Admin Panel Loading...</title></head><body><h1>Loading Assets...</h1><div style='display:none;'>"
        
        chunk_accum = 0
        
        try:
            while total_streamed < limit:
                yield heavy_chunk
                total_streamed += chunk_len
                chunk_accum += chunk_len
            
            yield b"</div></body></html>"
            
        finally:
            # Update DB only ONCE at the end of the connection (whether complete or aborted)
            if chunk_accum > 0:
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute('UPDATE blocked_ips SET data_sent = COALESCE(data_sent, 0) + ? WHERE id = ?', (chunk_accum, db_id))
                except:
                    pass

    return Response(generate(), mimetype='text/html')

@app.before_request
def check_suspicious_block():
    ip = request.remote_addr
    path = request.path
    
    # Allow finalizing the honeypot block
    if path.startswith('/api/honeypot/finalize'):
        return

    is_blocked = False
    
    # 1. Check Cookie Block (Validate against DB)
    tracking_id = request.cookies.get('wpadm_session')
    db_id = None
    
    if tracking_id:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT id FROM blocked_ips WHERE tracking_id = ?', (tracking_id,))
            row = c.fetchone()
            if row:
                is_blocked = True
                db_id = row[0]
            conn.close()
        except:
             pass

    # 2. Check IP Cache Block OR DB Block
    if not is_blocked:
        # Check Cache first (fast)
        if cache.get(f'honeypot_blocked_{ip}'):
            is_blocked = True
        else:
            # Check DB
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute('SELECT id FROM blocked_ips WHERE ip_address = ?', (ip,))
                row = c.fetchone()
                if row:
                    is_blocked = True
                    # Refresh cache for speed
                    cache.set(f'honeypot_blocked_{ip}', True, timeout=60 * 60 * 24 * 365 * 10)
                conn.close()
            except: pass

            
    if is_blocked:
        # If accessing the Honeypot AGAIN, serve the heavy payload
        if path == '/wp-admin-login':
             # Find existing record if we don't have it from cookie
            if not db_id:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM blocked_ips WHERE ip_address = ? AND reason LIKE "%Honeypot%" ORDER BY id DESC LIMIT 1', (ip,))
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        db_id = row[0]
                except: pass
            
            if db_id:
                return stream_heavy_block(ip, db_id)
            
        return render_template('blocked.html'), 403

    if cache.get(f'blocked_{ip}'):
        return render_template('suspicious.html'), 403

@app.route('/wp-admin-login')
def honeypot():
    # 1. Log Initial Access (Server-side Only)
    ip = request.remote_addr
    user_agent = request.user_agent.string
    country = request.headers.get('CF-IPCountry', 'Unknown')
    headers_dict = dict(request.headers)
    
    # Check if already blocked (IP or Cookie)
    cookie_blocked = False
    tracking_id = request.cookies.get('wpadm_session')
    
    if tracking_id:
        # Validate if this cookie actually corresponds to an ACTIVE block
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT id FROM blocked_ips WHERE tracking_id = ?', (tracking_id,))
            if c.fetchone():
                cookie_blocked = True
            conn.close()
        except: pass
        
    if cache.get(f'honeypot_blocked_{ip}') or cookie_blocked:
         return render_template('blocked.html'), 403

    # Generate a tracking ID
    tracking_id = str(uuid.uuid4())
    
    # Store temporary context in cache to link with JS data later
    cache.set(f'honeypot_pending_{tracking_id}', {
        'ip': ip,
        'ua': user_agent,
        'country': country,
        'headers': headers_dict,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }, timeout=300)
    
    resp = make_response(render_template('honeypot_loading.html'))
    resp.set_cookie('wpadm_session', tracking_id, max_age=60*60*24*365*10, httponly=True, samesite='Lax')
    
    # 3. Log "Initial Hit" to DB immediately (for non-JS bots)
    block_duration = 60 * 60 * 24 * 7 
    blocked_until = datetime.now(timezone.utc) + timedelta(seconds=block_duration)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Check if already blocked to avoid duplicates
        cursor.execute('SELECT id FROM blocked_ips WHERE ip_address = ? AND reason LIKE "%Honeypot%"', (ip,))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute('''
                INSERT INTO blocked_ips (ip_address, user_agent, country, reason, blocked_until, extra_info, tracking_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ip, user_agent, country, 'Accessing /wp-admin-login (Honeypot - Initial)', blocked_until.isoformat(), json.dumps({'headers': headers_dict, 'initial_hit': True}), tracking_id))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging honeypot access: {e}")
        
    # 4. Set Cache Block (Effective immediately for next request)
    cache.set(f'honeypot_blocked_{ip}', True, timeout=block_duration)
    
    return resp

@app.route('/api/honeypot/finalize', methods=['POST'])
def honeypot_finalize():
    # 2. Receive JS Fingerprint Data and Finalize Block
    tracking_id = request.cookies.get('wpadm_session')
    client_data = request.json or {}
    fingerprint_hash = client_data.get('fingerprint_hash')
    
    ip = request.remote_addr
    
    # Create Full Fingerprint Record
    full_log = {
        'client_fingerprint': client_data,
        'cookies': dict(request.cookies),
        'server_timestamp': datetime.now(timezone.utc).isoformat(),
        'tracking_id': tracking_id
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check and store fingerprint block
        if fingerprint_hash:
            # Is this fingerprint already blocked?
            cursor.execute('SELECT id FROM blocked_fingerprints WHERE fingerprint_hash = ?', (fingerprint_hash,))
            if cursor.fetchone():
                # BLOCK THIS IP because fingerprint is banned
                # But we are already blocking this IP because it hit the honeypot.
                # However, user says "If another IP with the same canvas fingerprint then tries to access the site..."
                pass
            else:
                # Store new fingerprint
                cursor.execute('INSERT INTO blocked_fingerprints (fingerprint_hash, reason) VALUES (?, ?)', (fingerprint_hash, 'Associated with Honeypot Hit'))
        
        cursor.execute('''
            UPDATE blocked_ips 
            SET extra_info = ?, reason = ?, tracking_id = ?
            WHERE ip_address = ? AND reason LIKE "Accessing /wp-admin-login (Honeypot - Initial)"
        ''', (json.dumps(full_log), 'Accessing /wp-admin-login (Honeypot - Fingerprinted)', tracking_id, ip))
        
        if cursor.rowcount == 0:
            # Fallback insert if not found
            # Indefinite block (100 years from now)
            blocked_until = datetime.now(timezone.utc) + timedelta(days=365*100)
            country = request.headers.get('CF-IPCountry', 'Unknown')
            user_agent = request.user_agent.string
            cursor.execute('''
                INSERT INTO blocked_ips (ip_address, user_agent, country, reason, blocked_until, extra_info, tracking_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ip, user_agent, country, 'Accessing /wp-admin-login (Honeypot - Fingerprinted)', blocked_until.isoformat(), json.dumps(full_log), tracking_id))
            
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging blocked IP to DB: {e}")
        
    # Ensure cache block is set (limit to max cache int, approx 30 days is fine for now, or just huge)
    # Flask-Cache doesn't guarantee indefinite but we can set a large number.
    cache.set(f'honeypot_blocked_{ip}', True, timeout=60 * 60 * 24 * 365 * 10)
    
    return jsonify({"status": "blocked"})


@app.after_request
def monitor_suspicious_activity(response):
    if response.status_code >= 400 and response.status_code not in [401, 403]:
        ip = request.remote_addr
        
        error_key = f'errors_{ip}'
        errors = cache.get(error_key) or 0
        errors += 1
        cache.set(error_key, errors, timeout=SUSPICIOUS_ERROR_WINDOW)
        
        # kill spammers with hammers (looking at you fucking seo bots)
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
            name = user_info.get('preferred_username')
        if not name:
            name = user_info.get('nickname')
        if not name and email:
            name = email.split('@')[0]
            
        picture = user_info.get('picture') or user_info.get('profile_picture')

    if not oauth_id:
        return "Could not retrieve user information", 400
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # do you exist?
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
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr or ''

def check_ip_rate_limit(slug, ip_hash):
    """Check if IP has exceeded rate limit (5 views per post per month)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    # idfk why we wouldn't have it tho
    try:
        user_id = request.cookies.get('blog_user_id') or 'unknown'
        ip_hash = hash_ip(get_client_ip())
        platform = request.args.get('platform') or request.form.get('platform') or request.json.get('platform') if request.is_json else None
        log_analytics_view(slug, user_id, ip_hash, request.user_agent.string, request.referrer, 'share', platform)
    except Exception:
        pass

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


@app.before_request
def auto_log_share_from_bot():
    if request.method != 'GET':
        return
    path = request.path
    if path.startswith('/posts/') and not path.endswith('-assets') and '.' not in path.split('/')[-1]:
        user_agent = request.user_agent.string
        platform = get_share_platform_from_user_agent(user_agent)
        if platform:
            slug = path.split('/posts/')[-1]
            user_id = request.cookies.get('blog_user_id') or 'unknown'
            ip_hash = hash_ip(get_client_ip())
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
        
        summary_match = re.search(r"summary:\s*(.*)", front_matter_text)
        if summary_match:
            front_matter['summary'] = summary_match.group(1).strip()
        
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
    Replaces [[compare: left_source | right_source | caption]] with HTML for comparison slider.
    Supports images and videos.
    Caption is optional.
    Handles potential <p> wrappers added by Markdown.
    """
    pattern = r'(?:<p>\s*)?\[\[compare:\s*(.*?)\s*\|\s*(.*?)(?:\s*\|\s*(.*?))?\]\](?:\s*</p>)?'
    
    def get_media_tag(src, class_name):
        src = src.strip()
        is_video = src.lower().endswith(('.mp4', '.webm', '.mov', '.ogg'))
        if is_video:
            return f'<video class="{class_name}" src="{src}" preload="metadata" muted playsinline></video>'
        else:
            return f'<img class="{class_name}" src="{src}" alt="">'

    def repl(match):
        left_src = match.group(1)
        right_src = match.group(2)
        caption = match.group(3) if match.group(3) else ""
        left_tag = get_media_tag(left_src, "comparison-image-under")
        right_tag = get_media_tag(right_src, "comparison-image-over")
        has_video = any(src.strip().lower().endswith(('.mp4', '.webm', '.mov', '.ogg')) for src in [left_src, right_src])
        
        controls_html = ""
        if has_video:
            controls_html = '''
            <div class="comparison-controls">
                <button class="comp-play-btn" aria-label="Play">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                </button>
                <div class="comp-progress-container">
                    <div class="comp-progress-bar"></div>
                </div>
            </div>
            '''
        
        html = f'''
        <div class="comparison-container">
          <div class="comparison-inner">
            {left_tag}
            {right_tag}
            <div class="comparison-slider">
              <div class="comparison-handle"></div>
            </div>
          </div>
          {controls_html}
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
    content = comment_data['content']
    
    # xss is bad actually
    content = re.sub(r'<br\s*/?>', '\n', content)
    content = re.sub(r'</p>', '\n\n', content)
    content = re.sub(r'<[^>]+>', '', content)
    content = content.strip()
    created_at = datetime.fromtimestamp(comment_data['time'] / 1000, timezone.utc).isoformat()
    avatar_url = f"https://api.wasteof.money/users/{author_name}/picture"
    
    cursor.execute('SELECT id FROM comments WHERE external_id = ?', (external_id,))
    existing = cursor.fetchone()
    
    parent_db_id = None
    if parent_external_id:
        cursor.execute('SELECT id FROM comments WHERE external_id = ?', (parent_external_id,))
        parent_row = cursor.fetchone()
        if parent_row:
            parent_db_id = parent_row[0]
    
    if existing:
        cursor.execute('''
            UPDATE comments 
            SET comment_text = ?, author_name = ?, author_avatar_url = ?, parent_id = ?
            WHERE id = ?
        ''', (content, author_name, avatar_url, parent_db_id, existing[0]))
    else:
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
        match = re.search(r'wasteof\.money/posts/([a-f0-9]+)', wasteof_link)
        if not match:
            print(f"Invalid wasteof link for {post_slug}: {wasteof_link}")
            return
        
        post_id = match.group(1)
        
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
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for comment in comments:
            process_wasteof_comment(cursor, post_slug, comment, None)
            
            if comment.get('hasReplies'):
                fetch_wasteof_replies(cursor, post_slug, comment['_id'])
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error syncing wasteof comments for {post_slug}: {e}")

def run_wasteof_sync():
    lock_file_path = '/tmp/wasteof_sync.lock'
    try:
        f = open(lock_file_path, 'w')
    except IOError:
        print("Could not open lock file for sync")
        return

    while True:
        try:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            try:
                print("Starting wasteof.money sync...")
                posts = get_all_posts()
                cutoff_date = datetime.now() - timedelta(days=90)
                for post in posts:
                    if post.get('wasteof_link'):
                        should_sync = False
                        try:
                            post_date = datetime.strptime(post['date'], "%Y-%m-%d")
                            if post_date > cutoff_date:
                                should_sync = True
                        except (ValueError, TypeError):
                            should_sync = True
                            
                        if should_sync:
                            sync_wasteof_comments(post['slug'], post['wasteof_link'])
                print("Wasteof.money sync completed.")
            except Exception as e:
                print(f"Error in wasteof sync loop: {e}")
            time.sleep(900) 
            
        except IOError:

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
        # count top-level comments
        cursor.execute('SELECT COUNT(*) FROM comments WHERE slug = ? AND parent_id IS NULL', (slug,))
        total_top_level = cursor.fetchone()[0]
        total_pages = (total_top_level + per_page - 1) // per_page if total_top_level > 0 else 1
        
        offset = (page - 1) * per_page
        
        # get top-level comments for this page
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
             
        # get full tree for these top-level comments using Recursive CTE
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
    
    # you shall not edit other people's comments
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
    
    cursor.execute('INSERT INTO comment_history (comment_id, old_text, edited_at) VALUES (?, ?, ?)', 
                  (comment_id, old_text, now))
                  
    cursor.execute('UPDATE comments SET comment_text = ?, edited_at = ? WHERE id = ?', 
                  (new_text, now, comment_id))
                  
    conn.commit()
    conn.close()
    return True, None

def delete_comment(comment_id, user_id, is_admin=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # you shall not delete other people's comments unless admin
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
    # if it's a bot, increment shares count with platform
    if platform:
        increment_shares_count(slug)
    else:
        user_id = request.cookies.get('blog_user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
        client_ip = get_client_ip()
        ip_hash = hash_ip(client_ip)
        has_viewed = has_user_viewed(slug, user_id)
        within_rate_limit = check_ip_rate_limit(slug, ip_hash)
        log_analytics_view(slug, user_id, ip_hash, user_agent, request.referrer)
        if not has_viewed and within_rate_limit:
            increment_view_count(slug)
    
    # views & shares
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
    
    # user id cookie
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
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = 12

    tagged_posts = get_posts_by_tag(tag_slug)
    total_posts = len(tagged_posts)
    total_pages = (total_posts + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    end = start + per_page
    posts = tagged_posts[start:end]
    
    tag_name = tag_slug.replace('-', ' ')
    
    return render_template('tag.html', 
                          tag=tag_name, 
                          posts=posts, 
                          total_posts=total_posts,
                          year=datetime.now().year,
                          page=page,
                          total_pages=total_pages)

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
        
        # hide deleted comments to normies
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
        # are you logged in?
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
            
        # check if email is verified (we can get this from joshatticusid and google, assume verified for github)
        if not user.get('email_verified'):
            return jsonify({"error": "Verified email required to comment"}), 403
            
        # check if banned
        if user.get('is_banned'):
            return jsonify({"error": "You are banned from commenting."}), 403

        data = request.get_json()
        
        # user info
        user_id = str(user['id'])
        author_name = user['name']
        
        # ip hashes
        client_ip = get_client_ip()
        ip_hash = hash_ip(client_ip)
        
        # no spamming
        if not check_comment_rate_limit(user_id, ip_hash):
            return jsonify({"error": "Rate limit exceeded. Please wait before posting again."}), 429
            
        parent_id = data.get('parent_id')
        if parent_id and not check_reply_rate_limit(user_id, ip_hash):
             return jsonify({"error": "Reply rate limit exceeded. Please wait before replying again."}), 429
        
        comment_text = data.get('comment_text', '').strip()
        
        # no empty comments or word bombs
        if not comment_text:
            return jsonify({"error": "Comment text is required"}), 400
            
        if len(comment_text) > 1500:
            return jsonify({"error": "Comment exceeds 1500 characters"}), 400
            
        # Security: kill html with hammers
        comment_text = html.escape(comment_text)
        comment_text = comment_text.replace('\n', ' ').replace('\r', '')
        
        add_comment(slug, user_id, author_name, comment_text, parent_id, ip_hash)
        
        return jsonify({"success": True})

@app.route('/api/comments/<int:comment_id>', methods=['PUT', 'DELETE'])
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

@app.route('/api/admin/users/<int:user_id>/ban', methods=['POST'])
def admin_ban_user(user_id):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/users/<int:user_id>/unban', methods=['POST'])
def admin_unban_user(user_id):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/blocked_ips')
def admin_blocked_ips():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
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
    
    return jsonify({
        "blocked_ips": blocked_ips,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records
    })

@app.route('/api/admin/blocked_ips/<int:id>/analysis')
def admin_blocked_ip_analysis(id):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
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
    analysis = {
        "id": ip_data['id'],
        "ip": ip_data['ip_address'],
        "country": ip_data['country'],
        "fingerprint_hash": None,
        "fingerprint_shared_count": 0,
        "related_ips": [],
        "details": {}
    }

    if extra_info_str:
        try:
            extra = json.loads(extra_info_str)
            client_fp = extra.get('client_fingerprint', {})
            
            # Extract basic details if available (client_fp structure depends on JS implementation)
            # Assuming typical fingerprintjs structure or similar flat structure from JS
            analysis['details']['screen_res'] = f"{client_fp.get('screen_width', '?')}x{client_fp.get('screen_height', '?')}"
            analysis['details']['timezone'] = client_fp.get('timezone', 'Unknown')
            analysis['details']['platform'] = client_fp.get('platform', 'Unknown')
            analysis['details']['renderer'] = client_fp.get('webgl_renderer', 'Unknown')
            
            # Extract Hash
            fp_hash = client_fp.get('fingerprint_hash')
            if fp_hash:
                analysis['fingerprint_hash'] = fp_hash
                
                # Check for other IPs with this hash
                # Since extra_info is JSON string, checking exact match is hard but we can check if string contains hash
                # A more robust way would be needed for production, but strict hash check inside JSON string is decent proxy
                
                # Or query the blocked_fingerprints table? No, that just lists banned hashes.
                # We need to know WHICH IPs share it.
                # We have to fetch all blocked IPs with extra_info and parse... which is slow for many records.
                # ALTERNATIVE: checking `tracking_id` which might be cleaner if cookies persists.
                
                # Let's try to find by string matching the hash in extra_info column.
                # extra_info LIKE '%"fingerprint_hash": "THE_HASH"%'
                
                search_pattern = f'%"{fp_hash}"%'
                cursor.execute('SELECT ip_address, created_at FROM blocked_ips WHERE extra_info LIKE ? AND id != ? ORDER BY created_at DESC LIMIT 50', (search_pattern, id))
                related_rows = cursor.fetchall()
                
                analysis['fingerprint_shared_count'] = len(related_rows)
                analysis['related_ips'] = [{"ip": r['ip_address'], "date": r['created_at']} for r in related_rows[:10]]
                
        except Exception as e:
            print(f"Error parsing extra info: {e}")
            pass
            
    conn.close()
    return jsonify(analysis)

@app.route('/api/admin/invoicing')
def admin_invoicing():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Get Totals for Summary (Global)
    # We want total cost across ALL blocked IPs, not just current page
    cursor.execute('''
        SELECT 
            SUM(data_sent) as total_bytes,
            COUNT(CASE WHEN ip_type = 0 THEN 1 END) as residential_count,
            COUNT(*) as total_records
        FROM blocked_ips 
        WHERE data_sent > 0
    ''')
    summary_row = cursor.fetchone()
    total_bytes = summary_row['total_bytes'] or 0
    residential_count = summary_row['residential_count'] or 0
    total_records = summary_row['total_records']
    
    # Calculate global costs based on total bytes (approximate, since per-IP calculation is more correct)
    # But for "Est Cost", summing up (2 * specific_ip_gb) is same as 2 * (sum_gb) IF we assume all residential.
    # Actually, we only charge for residential.
    
    # Let's do it properly: Sum data_sent for residential IPs only for cost calculation
    cursor.execute('''
        SELECT SUM(data_sent) FROM blocked_ips WHERE data_sent > 0 AND ip_type = 0
    ''')
    res_bytes = cursor.fetchone()[0] or 0
    res_gb = res_bytes / (1024 * 1024 * 1024)
    
    total_cost_low = 2 * res_gb
    total_cost_high = 15 * res_gb
    
    # 2. Get Paginated Rows
    # Fetch data for invoicing table
    cursor.execute('''
        SELECT id, ip_address, ip_type, data_sent, created_at 
        FROM blocked_ips 
        WHERE data_sent > 0 
        ORDER BY data_sent DESC
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    rows = cursor.fetchall()
    
    conn.close()
    
    total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
    
    invoices = []
    
    for row in rows:
        r = dict(row)
        data_b = r['data_sent'] or 0
        data_gb = data_b / (1024 * 1024 * 1024)
        
        # User formula: (2*d) and (15*d)
        cost_l = 2 * data_gb
        cost_h = 15 * data_gb
        
        is_res = r['ip_type'] == 0
        
        invoices.append({
            "ip": r['ip_address'],
            "type": "Residential" if r['ip_type'] == 0 else ("Hosting" if r['ip_type'] == 1 else "Unknown"),
            "data_gb": data_gb,
            "cost_low": cost_l if is_res else 0,
            "cost_high": cost_h if is_res else 0,
            "is_residential": is_res
        })
        
    return jsonify({
        "invoices": invoices,
        "page": page,
        "total_pages": total_pages,
        "summary": {
            "total_cost_low": total_cost_low,
            "total_cost_high": total_cost_high,
            "total_data_gb": total_bytes / (1024 * 1024 * 1024),
            "residential_ips": residential_count
        }
    })

@app.route('/api/admin/blocked_ips/<int:id>/unblock', methods=['POST'])
def admin_unblock_ip(id):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT ip_address, extra_info FROM blocked_ips WHERE id = ?', (id,))
    row = cursor.fetchone()
    if row:
        ip = row['ip_address']
        extra_info_str = row['extra_info']
        
        # Check for fingerprint and remove from blocked_fingerprints
        if extra_info_str:
            try:
                extra = json.loads(extra_info_str)
                client_fp = extra.get('client_fingerprint')
                # Try getting hash from client_fingerprint dict OR directly if structured differently
                fp_hash = None
                if isinstance(client_fp, dict):
                    fp_hash = client_fp.get('fingerprint_hash')
                
                if fp_hash:
                    cursor.execute('DELETE FROM blocked_fingerprints WHERE fingerprint_hash = ?', (fp_hash,))
            except: pass

        # Remove from DB (delete all records for this IP to ensure full unblock)
        cursor.execute('DELETE FROM blocked_ips WHERE ip_address = ?', (ip,))
        conn.commit()
        
        # Remove from cache
        cache.delete(f'honeypot_blocked_{ip}')
        cache.delete(f'blocked_{ip}')
        
    conn.close()
    return jsonify({"success": True})

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
    
    all_posts = get_all_posts()
    posts_map = {post['slug']: post for post in all_posts}
    
    for comment in comments:
        post = posts_map.get(comment['slug'])
        if post:
            comment['post_title'] = post['title']
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
    
    cursor.execute('''
        SELECT substr(viewed_at, 1, 10) as day, COUNT(*) 
        FROM analytics_pageviews 
        WHERE event_type = 'share' AND viewed_at > ?
        GROUP BY day
        ORDER BY day
    ''', (thirty_days_ago,))
    daily_shares = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    final_data = {}
    for item in daily_views:
        final_data[item['date']] = {"date": item['date'], "views": item['views'], "shares": 0, "new_posts": []}
        
    for date, count in daily_shares.items():
        if date not in final_data:
            final_data[date] = {"date": date, "views": 0, "shares": count, "new_posts": []}
        else:
            final_data[date]["shares"] = count
            
    all_posts = get_all_posts()
    for post in all_posts:
        post_date = post['date']
        if post_date in final_data:
            final_data[post_date]['new_posts'].append(post['title'])
        elif post_date >= thirty_days_ago[:10]:
             final_data[post_date] = {"date": post_date, "views": 0, "shares": 0, "new_posts": [post['title']]}
             
    sorted_data = sorted(final_data.values(), key=lambda x: x['date'])
    return jsonify(sorted_data)

@app.route('/api/analytics/posts')
def analytics_posts_list():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    page = request.args.get('page', 1, type=int)
    per_page = 20
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
        
    result.sort(key=lambda x: x['date'], reverse=True)
    
    total_posts = len(result)
    total_pages = (total_posts + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    end = start + per_page
    
    paginated_result = result[start:end]
    
    return jsonify({
        "posts": paginated_result,
        "page": page,
        "total_pages": total_pages
    })

@app.route('/api/analytics/posts/<slug>')
def analytics_post_detail(slug):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM analytics_pageviews WHERE slug = ?', (slug,))
    total_views = cursor.fetchone()[0]
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('''
        SELECT substr(viewed_at, 1, 10) as day, COUNT(*) 
        FROM analytics_pageviews 
        WHERE slug = ? AND viewed_at > ? AND event_type = 'view'
        GROUP BY day
        ORDER BY day
    ''', (slug, thirty_days_ago))
    daily_views = [{"date": row[0], "views": row[1]} for row in cursor.fetchall()]

    cursor.execute('''
        SELECT substr(viewed_at, 1, 10) as day, COUNT(*) 
        FROM analytics_pageviews 
        WHERE slug = ? AND viewed_at > ? AND event_type = 'share'
        GROUP BY day
        ORDER BY day
    ''', (slug, thirty_days_ago))
    daily_shares = [{"date": row[0], "shares": row[1]} for row in cursor.fetchall()]
    
    cursor.execute('''
        SELECT platform, COUNT(*) as count
        FROM analytics_pageviews
        WHERE slug = ? AND event_type = 'share' AND platform IS NOT NULL AND platform != 'unknown'
        GROUP BY platform
        ORDER BY count DESC
    ''', (slug,))
    shares_platform = [{"platform": row[0], "count": row[1]} for row in cursor.fetchall()]

    conn.close()

    # Get post metadata
    all_posts = get_all_posts()
    post_meta = next((p for p in all_posts if p['slug'] == slug), {})
    
    return jsonify({
        "slug": slug,
        "title": post_meta.get('title', slug),
        "date": post_meta.get('date', '-'),
        "image": post_meta.get('image'),
        "total_views": total_views,
        "daily_views": daily_views,
        "daily_shares": daily_shares,
        "shares_platform": shares_platform
    })
    
@app.route('/api/analytics/shares_by_platform')
def analytics_shares_by_platform():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT platform, COUNT(*) as count
        FROM analytics_pageviews
        WHERE event_type = 'share' AND platform IS NOT NULL AND platform != 'unknown'
        GROUP BY platform
        ORDER BY count DESC
    ''')
    data = [{"platform": row[0], "count": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/analytics/daily_shares_platform')
def analytics_daily_shares_platform():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('''
        SELECT substr(viewed_at, 1, 10) as day, platform, COUNT(*) as count
        FROM analytics_pageviews 
        WHERE event_type = 'share' AND viewed_at > ? AND platform IS NOT NULL AND platform != 'unknown'
        GROUP BY day, platform
        ORDER BY day
    ''', (thirty_days_ago,))
    
    data = []
    for row in cursor.fetchall():
        data.append({"date": row[0], "platform": row[1], "count": row[2]})
        
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
    user_id = str(user['id'])
    author_name = user['name']
    client_ip = get_client_ip()
    ip_hash = hash_ip(client_ip)
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

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/crazy')
def crazy():
    return render_template('crazy.html')

@app.route('/sitemap.xml')
# istg I made this fucking sitemap for google search console and it keeps saying it couldn't fetch it so I fucking give up
def sitemap():
    posts = get_all_posts()
    base_url = "https://blog.joshattic.us"
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    static_pages = [
        {'loc': '/', 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': '/tags', 'changefreq': 'weekly', 'priority': '0.8'},
        {'loc': '/search', 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': '/privacy', 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': '/terms', 'changefreq': 'yearly', 'priority': '0.3'},
    ]
    
    for page in static_pages:
        xml += '  <url>\n'
        xml += f'    <loc>{base_url}{page["loc"]}</loc>\n'
        xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        xml += '  </url>\n'
    
    for post in posts:
        xml += '  <url>\n'
        xml += f'    <loc>{base_url}/posts/{post["slug"]}</loc>\n'
        xml += f'    <lastmod>{post["date"]}</lastmod>\n'
        xml += '    <changefreq>monthly</changefreq>\n'
        xml += '    <priority>0.7</priority>\n'
        xml += '  </url>\n'
        
    xml += '</urlset>'
    
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response

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
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true': # don't run twice in Flask debug mode reloader
    try:
        init_db()
        start_wasteof_sync_thread()
    except Exception as e:
        print(f"Failed to init: {e}")

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    # init_db and start_wasteof_sync_thread are already called above
    app.run(port=5001)
