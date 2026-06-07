import sqlite3
import os
from datetime import datetime, timezone, timedelta
from extensions import DB_PATH, PHOENIX_TZ, hash_ip, get_client_ip
from flask import session

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
            user_id TEXT,
            ip_hash TEXT,
            user_agent TEXT,
            referrer TEXT,
            event_type TEXT DEFAULT 'view',
            platform TEXT,
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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_views_slug_user ON user_views(slug, user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_views_slug_ip_time ON user_views(slug, ip_hash, viewed_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_slug ON comments(slug, created_at)')
    
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

def get_current_user():
    if 'user_id' not in session:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def check_ip_rate_limit(slug, ip_hash):
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM analytics_pageviews WHERE slug = ? AND user_id = ? AND event_type = 'view'
    ''', (slug, user_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_view_count(slug):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT view_count FROM post_views WHERE slug = ?', (slug,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_shares_count(slug):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT shares_count FROM post_views WHERE slug = ?', (slug,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def increment_view_count(slug):
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

def log_analytics_view(slug, user_id, ip_hash, user_agent, referrer, event_type='view', platform=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO analytics_pageviews (slug, user_id, ip_hash, user_agent, referrer, event_type, platform, viewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (slug, user_id, ip_hash, user_agent, referrer, event_type, platform, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def normalize_comment_timestamp(raw_value):
    if not raw_value:
        return None
    timestamp_text = str(raw_value).replace('Z', '+00:00')
    timestamp = datetime.fromisoformat(timestamp_text)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=PHOENIX_TZ)
    return timestamp.astimezone(timezone.utc)

def normalize_comment_row(row):
    comment = dict(row)
    created_at = normalize_comment_timestamp(comment.get('created_at'))
    if created_at:
        comment['created_at'] = created_at.isoformat()

    edited_at = comment.get('edited_at')
    if edited_at:
        edited_timestamp = normalize_comment_timestamp(edited_at)
        if edited_timestamp:
            comment['edited_at'] = edited_timestamp.isoformat()
    return comment

def get_comment_by_id(comment_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.user_id, c.author_name, c.comment_text, c.parent_id, c.created_at, c.is_deleted, c.edited_at, c.source, c.external_id, c.author_avatar_url, u.picture
        FROM comments c
        LEFT JOIN users u ON c.user_id = CAST(u.id AS TEXT)
        WHERE c.id = ?
    ''', (comment_id,))
    row = cursor.fetchone()
    conn.close()
    return normalize_comment_row(row) if row else None

def get_comments_for_post(slug, page=None, per_page=20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if page:
        cursor.execute('SELECT COUNT(*) FROM comments WHERE slug = ? AND parent_id IS NULL', (slug,))
        total_top_level = cursor.fetchone()[0]
        total_pages = (total_top_level + per_page - 1) // per_page if total_top_level > 0 else 1

        cursor.execute('SELECT id, created_at FROM comments WHERE slug = ? AND parent_id IS NULL', (slug,))
        top_level_rows = [dict(row) for row in cursor.fetchall()]
        top_level_rows.sort(key=lambda row: normalize_comment_timestamp(row['created_at']) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        offset = (page - 1) * per_page
        top_level_ids = [row['id'] for row in top_level_rows[offset:offset + per_page]]
        
        if not top_level_ids:
             conn.close()
             return [], 1, 0
             
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
        comments = [normalize_comment_row(row) for row in rows]
        conn.close()
        return comments, total_pages, total_top_level
    else:
        cursor.execute('''
            SELECT c.id, c.user_id, c.author_name, c.comment_text, c.parent_id, c.created_at, c.is_deleted, c.edited_at, u.picture
            FROM comments c
            LEFT JOIN users u ON c.user_id = CAST(u.id AS TEXT)
            WHERE c.slug = ?
        ''', (slug,))
        rows = cursor.fetchall()
        conn.close()
        comments = [normalize_comment_row(row) for row in rows]
        comments.sort(key=lambda comment: normalize_comment_timestamp(comment['created_at']) or datetime.min.replace(tzinfo=timezone.utc))
        return comments, 1, len(comments)

def edit_comment(comment_id, user_id, new_text):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, comment_text FROM comments WHERE id = ?', (comment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Comment not found"
    
    if str(row[0]) != str(user_id):
        conn.close()
        return False, "Unauthorized"
        
    old_text = row[1]
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute('INSERT INTO comment_history (comment_id, old_text, edited_at) VALUES (?, ?, ?)', (comment_id, old_text, now))
    cursor.execute('UPDATE comments SET comment_text = ?, edited_at = ? WHERE id = ?', (new_text, now, comment_id))
    conn.commit()
    conn.close()
    return True, None

def delete_comment(comment_id, user_id, is_admin=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO comments (slug, user_id, author_name, comment_text, parent_id, created_at, ip_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (slug, user_id, author_name, comment_text, parent_id, datetime.now(timezone.utc).isoformat(), ip_hash))
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return comment_id

def check_comment_rate_limit(user_id, ip_hash):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM comments WHERE (user_id = ? OR ip_hash = ?) AND created_at > ?
    ''', (user_id, ip_hash, one_hour_ago))
    count = cursor.fetchone()[0]
    conn.close()
    return count < 10

def check_reply_rate_limit(user_id, ip_hash):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ten_minutes_ago = (datetime.now() - timedelta(minutes=10)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM comments WHERE (user_id = ? OR ip_hash = ?) AND created_at > ? AND parent_id IS NOT NULL
    ''', (user_id, ip_hash, ten_minutes_ago))
    count = cursor.fetchone()[0]
    conn.close()
    return count < 5