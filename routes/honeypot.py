import sqlite3
import requests
import json
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, render_template, make_response, jsonify, Response
from extensions import IPHUB_KEY, DB_PATH, cache

honeypot_bp = Blueprint('honeypot', __name__)

def get_ip_type(ip):
    if not IPHUB_KEY:
        return -1
    try:
        resp = requests.get(f'http://v2.api.iphub.info/ip/{ip}', headers={'X-Key': IPHUB_KEY}, timeout=3)
        if resp.status_code == 200:
            return resp.json().get('block', -1)
    except:
        pass
    return -1

def stream_heavy_block(ip, db_id):
    current_type = -1
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT ip_type FROM blocked_ips WHERE id = ?', (db_id,))
        row = cursor.fetchone()
        current_type = row[0] if row else -1
        
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
    except:
        pass

    def generate():
        total_streamed = 0
        limit = 5 * 1024 * 1024 * 1024
        complex_path = "M 0 0 " + " ".join([f"Q {i%500} {(i*2)%500} {(i*3)%500} {(i*4)%500}" for i in range(100)])
        svg_template = f"<svg width='500' height='500'><path d='{complex_path}' fill='none' stroke='black'/></svg>"
        heavy_chunk = (svg_template * 500).encode('utf-8')
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
            if chunk_accum > 0:
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute('UPDATE blocked_ips SET data_sent = COALESCE(data_sent, 0) + ? WHERE id = ?', (chunk_accum, db_id))
                except:
                    pass

    return Response(generate(), mimetype='text/html')

@honeypot_bp.before_app_request
def check_suspicious_block():
    ip = request.remote_addr
    path = request.path
    
    if path.startswith('/api/honeypot/finalize'):
        return

    is_blocked = False
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

    if not is_blocked:
        if cache.get(f'honeypot_blocked_{ip}'):
            is_blocked = True
        else:
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute('SELECT id FROM blocked_ips WHERE ip_address = ?', (ip,))
                row = c.fetchone()
                if row:
                    is_blocked = True
                    cache.set(f'honeypot_blocked_{ip}', True, timeout=60 * 60 * 24 * 365 * 10)
                conn.close()
            except: pass

    if is_blocked:
        if path == '/wp-admin-login':
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

@honeypot_bp.route('/wp-admin-login')
def honeypot():
    ip = request.remote_addr
    user_agent = request.user_agent.string
    country = request.headers.get('CF-IPCountry', 'Unknown')
    headers_dict = dict(request.headers)
    
    cookie_blocked = False
    tracking_id = request.cookies.get('wpadm_session')
    
    if tracking_id:
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

    tracking_id = str(uuid.uuid4())
    cache.set(f'honeypot_pending_{tracking_id}', {
        'ip': ip,
        'ua': user_agent,
        'country': country,
        'headers': headers_dict,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }, timeout=300)
    
    resp = make_response(render_template('honeypot_loading.html'))
    resp.set_cookie('wpadm_session', tracking_id, max_age=60*60*24*365*10, httponly=True, samesite='Lax')
    
    block_duration = 60 * 60 * 24 * 7 
    blocked_until = datetime.now(timezone.utc) + timedelta(seconds=block_duration)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
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
        
    cache.set(f'honeypot_blocked_{ip}', True, timeout=block_duration)
    return resp

@honeypot_bp.route('/api/honeypot/finalize', methods=['POST'])
def honeypot_finalize():
    tracking_id = request.cookies.get('wpadm_session')
    client_data = request.json or {}
    fingerprint_hash = client_data.get('fingerprint_hash')
    ip = request.remote_addr
    
    full_log = {
        'client_fingerprint': client_data,
        'cookies': dict(request.cookies),
        'server_timestamp': datetime.now(timezone.utc).isoformat(),
        'tracking_id': tracking_id
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if fingerprint_hash:
            cursor.execute('SELECT id FROM blocked_fingerprints WHERE fingerprint_hash = ?', (fingerprint_hash,))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO blocked_fingerprints (fingerprint_hash, reason) VALUES (?, ?)', (fingerprint_hash, 'Associated with Honeypot Hit'))
        
        cursor.execute('''
            UPDATE blocked_ips SET extra_info = ?, reason = ?, tracking_id = ?
            WHERE ip_address = ? AND reason LIKE "Accessing /wp-admin-login (Honeypot - Initial)"
        ''', (json.dumps(full_log), 'Accessing /wp-admin-login (Honeypot - Fingerprinted)', tracking_id, ip))
        
        if cursor.rowcount == 0:
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
        print(f"Error logging blocked IP: {e}")
        
    cache.set(f'honeypot_blocked_{ip}', True, timeout=60 * 60 * 24 * 365 * 10)
    return jsonify({"status": "blocked"})

@honeypot_bp.after_app_request
def monitor_suspicious_activity(response):
    if response.status_code >= 400 and response.status_code not in [401, 403]:
        ip = request.remote_addr
        error_key = f'errors_{ip}'
        errors = cache.get(error_key) or 0
        errors += 1
        cache.set(error_key, errors, timeout=60)
        
        # kill spammers with hammers (looking at you fucking seo bots)
        if errors >= 10:
            cache.set(f'blocked_{ip}', True, timeout=3600)
    return response