import os
import re
import json
import markdown
import time
from datetime import datetime
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, jsonify
from cachelib import SimpleCache
from PIL import Image
import io
from feedgen.feed import FeedGenerator

app = Flask(__name__, template_folder='templates')

cache = SimpleCache()
CACHE_TIMEOUT = 60 * 60 
POSTS_DIR = "posts"

COMPRESSION_QUALITY = 85
MAX_IMAGE_WIDTH = 1200 
processed_images = set()

# helper functions for compression, site rendering etc

def compress_image(image_path, max_width=MAX_IMAGE_WIDTH, quality=COMPRESSION_QUALITY):
    """Compress an image and return it as bytes"""
    MAX_HEIGHT = 1600  # Maximum height for any image
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
        
        # Check if image needs resizing based on width or height
        needs_resize = False
        ratio = 1.0
        
        if img.width > max_width:
            ratio = max_width / img.width
            needs_resize = True
            
        if img.height > MAX_HEIGHT:
            height_ratio = MAX_HEIGHT / img.height
            ratio = min(ratio, height_ratio)  # Use the smaller ratio
            needs_resize = True
            
        if needs_resize:
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
        
        # Adjust quality based on file size
        output = io.BytesIO()
        format = image_path.lower().split('.')[-1]
        if format == 'jpg':
            format = 'jpeg'
        
        # Lower quality for very large images
        final_quality = quality
        if img.width * img.height > 2000000:  # For images larger than 2MP
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

def clean_for_summary(html_content):
    text = re.sub(r"<[^>]+>", "", html_content)
    return text.strip()

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
            
            html_content = markdown.markdown(content_without_front_matter)
            
            first_image, content_without_first_image = extract_and_remove_first_image(html_content)
            
            if not first_image:
                first_image = "assets/default-banner.jpg" # there is no default banner I put this here so python doesn't shit itself but it probably still will so I haven't tested it
            
            summary_text = clean_for_summary(html_content)
            
            post_filename = os.path.splitext(filename)[0] + ".html"
            
            posts.append({
                "title": front_matter.get('title', "Untitled"),
                "date": front_matter.get('date', datetime.now().strftime("%Y-%m-%d")),
                "filename": post_filename,
                "slug": os.path.splitext(filename)[0],
                "summary": summary_text[:150] + "..." if len(summary_text) > 150 else summary_text,
                "image": first_image,
                "tags": front_matter.get('tags', []),
                "content": content_without_first_image
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

# api endpoints
@app.route('/')
def index():
    posts = get_all_posts()
    return render_template('index.html', posts=posts, year=datetime.now().year)

@app.route('/posts/<slug>')
def post(slug):
    post = get_post_by_slug(slug)
    if not post:
        return redirect(url_for('index'))
    
    post_url = f"https://blog.joshatticus.site/posts/{post['filename']}"
    absolute_image_url = f"https://blog.joshatticus.site/{post['image']}"
    
    return render_template('post.html', 
                          post=post, 
                          year=datetime.now().year,
                          url=post_url,
                          absolute_image_url=absolute_image_url)

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
    results = []
    
    if query:
        posts = get_all_posts()
        query = query.lower()
        
        for post in posts:
            if (query in post['title'].lower() or 
                query in post['summary'].lower() or 
                any(query in tag.lower() for tag in post['tags'])):
                results.append(post)
    
    return render_template('search.html', 
                          results=results, 
                          query=query, 
                          year=datetime.now().year)

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

@app.route('/style.css')
def style():
    return send_from_directory('.', 'style.css')

@app.route('/assets/<path:filename>')
def serve_asset(filename):
    filepath = os.path.join('posts/assets', filename)
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        compressed_image = compress_image(filepath)
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        return app.response_class(compressed_image, mimetype=mimetype)
    return send_from_directory('posts/assets', filename)

@app.route('/posts/assets/<path:filename>')
def serve_post_asset(filename):
    filepath = os.path.join('posts/assets', filename)
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        compressed_image = compress_image(filepath)
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        return app.response_class(compressed_image, mimetype=mimetype)
    return send_from_directory('posts/assets', filename)

@app.route('/posts/<post_slug>-assets/<path:filename>')
def serve_post_specific_asset(post_slug, filename):
    dir_path = f'posts/{post_slug}-assets'
    filepath = os.path.join(dir_path, filename)
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        compressed_image = compress_image(filepath)
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        return app.response_class(compressed_image, mimetype=mimetype)
    return send_from_directory(dir_path, filename)

@app.route('/feed.rss')
def rss_feed():
    """Generate an RSS feed of blog posts"""
    fg = FeedGenerator()
    fg.title('Josh\'s Blog')
    fg.description('Personal blog')
    fg.link(href='https://blog.joshatticus.site')
    fg.language('en')
    
    posts = get_all_posts()
    
    for post in posts:
        fe = fg.add_entry()
        fe.title(post['title'])
        fe.link(href=f"https://blog.joshatticus.site/posts/{post['slug']}")
        
        # Format the date properly for RSS
        try:
            post_date = datetime.strptime(post['date'], '%Y-%m-%d')
            fe.published(post_date)
        except ValueError:
            # If date format is different, use current time
            fe.published(datetime.now())
        
        # Include the image in content if available
        content = ""
        if post['image']:
            image_url = f"https://blog.joshatticus.site/{post['image']}"
            content += f'<p><img src="{image_url}" alt="{post["title"]}"></p>'
        
        content += post['content']
        fe.content(content, type='html')
        
        # Add tags as categories
        for tag in post['tags']:
            fe.category(term=tag)
    
    return app.response_class(fg.rss_str(), mimetype='application/rss+xml')

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(port=5001)