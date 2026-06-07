import os
import re
import markdown
import sqlite3
import requests
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, urlparse
from extensions import cache, CACHE_TIMEOUT, DB_PATH

try:
    import fcntl
except ImportError:
    fcntl = None

MD_EXTENSIONS = ['tables', 'fenced_code']

def get_share_platform_from_user_agent(user_agent):
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

def parse_front_matter(content):
    front_matter = {}
    front_matter_match = re.match(r"---\n(.*?)\n---", content, re.DOTALL)
    if front_matter_match:
        front_matter_text = front_matter_match.group(1)
        
        for key in ['title', 'date', 'summary', 'wasteof_link']:
            match = re.search(fr"{key}:\s*(.*)", front_matter_text)
            if match:
                front_matter[key] = match.group(1).strip()

        tags_match = re.search(r"tags:\s*\[(.*?)\]", front_matter_text, re.DOTALL) or re.search(r"tags:\s*(.*)", front_matter_text)
        if tags_match:
            tags_text = tags_match.group(1)
            tags = [tag.strip().strip('"\'') for tag in tags_text.split(',')]
            front_matter['tags'] = [t for t in tags if t]
        else:
            front_matter['tags'] = []
    return front_matter

def extract_and_remove_first_image(html_content):
    img_match = re.search(r'<p><img.*?src=["\'](?:\.\./)?(.*?)["\'].*?></p>', html_content)
    first_image = ""
    content_without_first_image = html_content
    
    if img_match:
        first_image = img_match.group(1)
        content_without_first_image = re.sub(r'<p><img.*?src=["\'](?:\.\./)?' + re.escape(first_image) + r'["\'].*?></p>', '', html_content, count=1)
    return first_image, content_without_first_image

def enforce_link_target_blank(html_content: str) -> str:
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
    return re.sub(r"<[^>]+>", "", html_content).strip()

def process_image_comparison(html_content):
    pattern = r'(?:<p>\s*)?\[\[compare:\s*(.*?)\s*\|\s*(.*?)(?:\s*\|\s*(.*?))?\]\](?:\s*</p>)?'
    
    def get_media_tag(src, class_name):
        src = src.strip()
        if src.lower().endswith(('.mp4', '.webm', '.mov', '.ogg')):
            return f'<video class="{class_name}" src="{src}" preload="metadata" muted playsinline></video>'
        return f'<img class="{class_name}" src="{src}" alt="">'

    def repl(match):
        left_src, right_src = match.group(1), match.group(2)
        caption = match.group(3) if match.group(3) else ""
        left_tag = get_media_tag(left_src, "comparison-image-under")
        right_tag = get_media_tag(right_src, "comparison-image-over")
        has_video = any(s.strip().lower().endswith(('.mp4', '.webm', '.mov', '.ogg')) for s in [left_src, right_src])
        
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
        return f'''
        <div class="comparison-container">
          <div class="comparison-inner">
            {left_tag}
            {right_tag}
            <div class="comparison-slider"><div class="comparison-handle"></div></div>
          </div>
          {controls_html}
          <div class="comparison-caption">{caption}</div>
        </div>
        '''
    return re.sub(pattern, repl, html_content)

def process_twitter_embed(html_content):
    pattern = r'(?:<p>\s*)?\[\[twitter:\s*(.*?)\]\](?:\s*</p>)?'
    def repl(match):
        url = match.group(1).strip()
        return f'''
        <blockquote class="twitter-tweet" data-dnt="true" data-theme="dark">
          <a href="{url}">Loading Twitter embed...</a>
        </blockquote>
        <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
        '''
    return re.sub(pattern, repl, html_content)

def process_youtube_embed(html_content):
    pattern = r'(?:<p>\s*)?\[\[youtube:\s*(.*?)\]\](?:\s*</p>)?'
    def repl(match):
        value = match.group(1).strip()
        video_id = value
        if 'youtube.com' in value or 'youtu.be' in value:
            parsed = urlparse(value)
            if 'youtu.be' in parsed.netloc:
                video_id = parsed.path.lstrip('/')
            else:
                query_params = parse_qs(parsed.query)
                video_id = query_params.get('v', [''])[0]
                if not video_id and '/embed/' in parsed.path:
                    video_id = parsed.path.split('/embed/')[-1].split('/')[0]

        video_id = re.sub(r'[^A-Za-z0-9_-]', '', video_id)
        if not video_id:
            return match.group(0)

        embed_url = f'https://www.youtube-nocookie.com/embed/{video_id}'
        return f'''
        <div class="youtube-embed">
            <iframe src="{embed_url}" title="YouTube video player" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
        '''
    return re.sub(pattern, repl, html_content)

def process_wasteof_comment(cursor, post_slug, comment_data, parent_external_id):
    external_id = comment_data['_id']
    user_id = comment_data['poster']['id']
    author_name = comment_data['poster']['name']
    content = comment_data['content']
    
    content = re.sub(r'<br\s*/?>', '\n', content)
    content = re.sub(r'</p>', '\n\n', content)
    content = re.sub(r'<[^>]+>', '', content).strip()
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
            UPDATE comments SET comment_text = ?, author_name = ?, author_avatar_url = ?, parent_id = ? WHERE id = ?
        ''', (content, author_name, avatar_url, parent_db_id, existing[0]))
    else:
        cursor.execute('''
            INSERT INTO comments (slug, user_id, author_name, comment_text, parent_id, created_at, ip_hash, source, external_id, author_avatar_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (post_slug, user_id, author_name, content, parent_db_id, created_at, 'wasteof', 'wasteof', external_id, avatar_url))

def fetch_wasteof_replies(cursor, post_slug, comment_id):
    page = 1
    headers = {'User-Agent': 'JoshAtticusBlog/1.0 +https://blog.joshattic.us/bot'}
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
        except:
            break

def sync_wasteof_comments(post_slug, wasteof_link):
    try:
        match = re.search(r'wasteof\.money/posts/([a-f0-9]+)', wasteof_link)
        if not match:
            return
        
        post_id = match.group(1)
        comments = []
        page = 1
        headers = {'User-Agent': 'JoshAtticusBlog/1.0 +https://blog.joshattic.us/bot'}
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
            except:
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
        print(f"Error syncing comments for {post_slug}: {e}")

def run_wasteof_sync():
    import tempfile
    lock_file_path = os.path.join(tempfile.gettempdir(), 'wasteof_sync.lock')
    try:
        f = open(lock_file_path, 'w')
    except IOError:
        return

    while True:
        try:
            if fcntl:
                fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            
            try:
                posts = get_all_posts()
                cutoff_date = datetime.now() - timedelta(days=90)
                for post in posts:
                    if post.get('wasteof_link'):
                        should_sync = False
                        try:
                            post_date = datetime.strptime(post['date'], "%Y-%m-%d")
                            if post_date > cutoff_date:
                                should_sync = True
                        except:
                            should_sync = True
                        if should_sync:
                            sync_wasteof_comments(post['slug'], post['wasteof_link'])
            except Exception as e:
                print(f"Error in wasteof sync loop: {e}")
            time.sleep(900)
        except IOError:
            time.sleep(60)
        except Exception as e:
            print(f"Unexpected sync error: {e}")
            time.sleep(60)

def start_wasteof_sync_thread():
    thread = threading.Thread(target=run_wasteof_sync, daemon=True)
    thread.start()

def get_all_posts():
    posts = cache.get('all_posts')
    if posts is not None:
        return posts
    
    posts = []
    if not os.path.exists("posts"):
        os.makedirs("posts", exist_ok=True)
        
    for filename in os.listdir("posts"):
        if filename.endswith(".md"):
            with open(os.path.join("posts", filename), "r", encoding="utf-8") as f:
                content = f.read()
            
            front_matter = parse_front_matter(content)
            content_without_front_matter = re.sub(r"---\n.*?\n---\n", "", content, flags=re.DOTALL)
            
            html_content = markdown.markdown(content_without_front_matter, extensions=MD_EXTENSIONS)
            html_content = enforce_link_target_blank(html_content)
            html_content = process_image_comparison(html_content)
            html_content = process_twitter_embed(html_content)
            html_content = process_youtube_embed(html_content)
            
            first_image, content_without_first_image = extract_and_remove_first_image(html_content)
            if not first_image:
                first_image = "assets/default-banner.jpg"
            
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