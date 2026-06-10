import os
import hashlib
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from cachelib import FileSystemCache, NullCache
from flask import request

# Load the .env file immediately on startup
load_dotenv()

IPHUB_KEY = os.environ.get('IPHUB_KEY')
DB_PATH = os.environ.get('DB_PATH', 'blog.db')
COMPRESSION_QUALITY = 85
MAX_IMAGE_WIDTH = 1200 
PHOENIX_TZ = ZoneInfo('America/Phoenix')

CACHE_TIMEOUT = 60 * 60
is_local = (
    os.environ.get('FLASK_ENV') == 'development' 
    or os.environ.get('FLASK_DEBUG') == '1' 
    or os.environ.get('LOCAL_DEV') == 'true'
)
disable_cache = os.environ.get('BLOG_DISABLE_CACHE') == 'true'

if is_local or disable_cache:
    cache = NullCache()
    if is_local:
        print("[Extensions] Local development detected: Caching is disabled (NullCache).")
    else:
        print("[Extensions] --no-cache detected: Caching is disabled (NullCache).")
else:
    cache = FileSystemCache('flask_cache', threshold=500, default_timeout=CACHE_TIMEOUT)

oauth = OAuth()

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

def get_client_ip():
    if 'X-Forwarded-For' in request.headers:
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr or ''

def hash_ip(ip_address):
    return hashlib.sha256(ip_address.encode()).hexdigest()