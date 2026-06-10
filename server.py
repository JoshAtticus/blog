import os
import shutil
import sys
from datetime import datetime
from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

NO_CACHE = '--no-cache' in sys.argv
if NO_CACHE:
    cache_dir = 'flask_cache'
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
    os.environ['BLOG_DISABLE_CACHE'] = 'true'
    sys.argv = [arg for arg in sys.argv if arg != '--no-cache']

# Core helpers and extensions
from db_helpers import init_db, get_current_user
from post_helpers import start_wasteof_sync_thread
from extensions import oauth, is_local

# Blueprints
from routes.views import views_bp
from routes.api import api_bp
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.assets import assets_bp
from routes.honeypot import honeypot_bp

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Session configurations
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_NAME'] = 'blog_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = not is_local  # Automatically False locally to make HTTP debugging painless
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize Flask-specific integrations
oauth.init_app(app)

# Register Blueprints
app.register_blueprint(views_bp)
app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(assets_bp)
app.register_blueprint(honeypot_bp)

@app.context_processor
def inject_globals():
    privacy_countries = ['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB', 'UK']
    country = request.headers.get('CF-IPCountry', '').upper() if 'request' in globals() else ''
    is_privacy_region = country in privacy_countries or country == 'US' or os.environ.get('FORCE_PRIVACY_BANNER') == 'true'
    
    return {
        'year': datetime.now().year,
        'is_privacy_region': is_privacy_region,
        'current_user': get_current_user()
    }

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, error_title="Page Not Found", error_description="The page you are looking for might have been removed or changed."), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', error_code=403, error_title="Forbidden", error_description="You do not have permission to access this resource."), 403

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_code=500, error_title="Internal Server Error", error_description="Something went wrong on our end. Please try again later."), 500

@app.errorhandler(401)
def unauthorized(e):
    return render_template('error.html', error_code=401, error_title="Unauthorized", error_description="You need to be logged in to access this page."), 401

@app.errorhandler(405)
def method_not_allowed(e):
    return render_template('error.html', error_code=405, error_title="Method Not Allowed", error_description="The method is not allowed for the requested URL."), 405

if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':  # don't run twice in Flask debug mode reloader
    try:
        init_db()
        start_wasteof_sync_thread()
    except Exception as e:
        print(f"Failed to initialize: {e}")

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(port=5001)