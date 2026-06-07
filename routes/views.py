import os
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, render_template, make_response, redirect, url_for
from feedgen.feed import FeedGenerator
from extensions import get_client_ip, hash_ip, cache
from db_helpers import (
    get_view_count, get_shares_count, check_ip_rate_limit, 
    has_user_viewed, increment_view_count, increment_shares_count, log_analytics_view,
    get_current_user
)
from post_helpers import (
    get_all_posts, get_post_by_slug, get_tags, get_posts_by_tag, 
    get_share_platform_from_user_agent
)

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    all_posts = get_all_posts()
    total_posts = len(all_posts)
    total_pages = (total_posts + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    posts = all_posts[start:start+per_page]
    return render_template('index.html', posts=posts, year=datetime.now().year, page=page, total_pages=total_pages)

@views_bp.route('/posts/<slug>')
def post(slug):
    post_item = get_post_by_slug(slug)
    if not post_item:
        return redirect(url_for('views.index'))
    
    user_agent = request.headers.get('User-Agent', '')
    platform = get_share_platform_from_user_agent(user_agent)
    
    if platform:
        increment_shares_count(slug)
    else:
        user_id = request.cookies.get('blog_user_id') or str(uuid.uuid4())
        client_ip = get_client_ip()
        ip_hash = hash_ip(client_ip)
        
        has_viewed = has_user_viewed(slug, user_id)
        within_rate_limit = check_ip_rate_limit(slug, ip_hash)
        log_analytics_view(slug, user_id, ip_hash, user_agent, request.referrer)
        
        if not has_viewed and within_rate_limit:
            increment_view_count(slug)
            
    view_count = get_view_count(slug)
    shares_count = get_shares_count(slug)
    
    post_url = f"https://blog.joshattic.us/posts/{post_item['filename']}"
    absolute_image_url = f"https://blog.joshattic.us/{post_item['image']}"
    
    response = make_response(render_template('post.html', post=post_item, year=datetime.now().year, url=post_url, absolute_image_url=absolute_image_url, view_count=view_count, shares_count=shares_count))
    if not platform and not request.cookies.get('blog_user_id'):
        response.set_cookie('blog_user_id', user_id, expires=datetime.now() + timedelta(days=365), httponly=True, samesite='Lax')
    return response

@views_bp.route('/bot')
def bot_page():
    return render_template('bot.html', year=datetime.now().year)

@views_bp.route('/tags')
def tags():
    return render_template('tags.html', tags=get_tags(), year=datetime.now().year)

@views_bp.route('/tags/<tag_slug>')
def tag(tag_slug):
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = 12

    tagged_posts = get_posts_by_tag(tag_slug)
    total_posts = len(tagged_posts)
    total_pages = (total_posts + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    posts = tagged_posts[start:start+per_page]
    return render_template('tag.html', tag=tag_slug.replace('-', ' '), posts=posts, total_posts=total_posts, year=datetime.now().year, page=page, total_pages=total_pages)

@views_bp.route('/search')
def search():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 12
    results = []
    
    if query:
        query_lower = query.lower()
        for p in get_all_posts():
            if query_lower in p['title'].lower() or query_lower in p['summary'].lower() or any(query_lower in t.lower() for t in p['tags']):
                results.append(p)
    
    total_results = len(results)
    total_pages = (total_results + per_page - 1) // per_page if total_results > 0 else 1
    
    start = (page - 1) * per_page
    return render_template('search.html', results=results[start:start+per_page], query=query, year=datetime.now().year, page=page, total_pages=total_pages, total_results=total_results)

@views_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

@views_bp.route('/terms')
def terms():
    return render_template('terms.html')

@views_bp.route('/crazy')
def crazy():
    return render_template('crazy.html')

@views_bp.route('/contact')
def contact():
    return render_template('contact.html')

@views_bp.route('/sitemap.xml')
def sitemap():
    posts = get_all_posts()
    base_url = "https://blog.joshattic.us"
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    static_pages = [
        {'loc': '/', 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': '/tags', 'changefreq': 'weekly', 'priority': '0.8'},
        {'loc': '/search', 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': '/privacy', 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': '/terms', 'changefreq': 'yearly', 'priority': '0.3'},
    ]
    for page in static_pages:
        xml += f'  <url>\n    <loc>{base_url}{page["loc"]}</loc>\n    <changefreq>{page["changefreq"]}</changefreq>\n    <priority>{page["priority"]}</priority>\n  </url>\n'
    
    for p in posts:
        xml += f'  <url>\n    <loc>{base_url}/posts/{p["slug"]}</loc>\n    <lastmod>{p["date"]}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n  </url>\n'
    xml += '</urlset>'
    
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response

@views_bp.route('/feed.rss')
def rss_feed():
    fg = FeedGenerator()
    fg.title('JoshAtticus Blog')
    fg.description('Personal blog')
    fg.link(href='https://blog.joshattic.us')
    fg.language('en')
    
    for p in get_all_posts()[::-1]:
        fe = fg.add_entry()
        fe.title(p['title'])
        fe.link(href=f"https://blog.joshattic.us/posts/{p['slug']}")
        try:
            fe.published(datetime.strptime(p['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc))
        except:
            fe.published(datetime.now(timezone.utc))
        
        content = f'<p><img src="https://blog.joshattic.us/{p["image"]}" alt="{p["title"]}"></p>' if p['image'] else ""
        fe.content(content + p['content'], type='html')
        for tag in p['tags']:
            fe.category(term=tag)
            
    from flask import current_app
    return current_app.response_class(fg.rss_str(), mimetype='application/rss+xml')