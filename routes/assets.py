import os
import io
import requests
from flask import Blueprint, send_from_directory, request, app, Response
from PIL import Image
from extensions import cache, CACHE_TIMEOUT, COMPRESSION_QUALITY, MAX_IMAGE_WIDTH

assets_bp = Blueprint('assets', __name__)

def compress_image(image_path, max_width=MAX_IMAGE_WIDTH, quality=COMPRESSION_QUALITY):
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
            needs_resize = True
            ratio = min(ratio, MAX_HEIGHT / img.height)
            
        if needs_resize:
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
        
        output = io.BytesIO()
        fmt = image_path.lower().split('.')[-1]
        if fmt == 'jpg':
            fmt = 'jpeg'
        
        final_quality = min(quality, 75) if img.width * img.height > 2000000 else quality
        save_kwargs = {'format': fmt, 'optimize': True, 'quality': final_quality}
        if fmt == 'jpeg':
            save_kwargs['subsampling'] = 0
        img.save(output, **save_kwargs)
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
    sizes = {'placeholder': (50, 20), 'thumbnail': (800, 70), 'full': (2000, 90)}
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
            if ratio < 1.0:
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            
            output = io.BytesIO()
            fmt = image_path.lower().split('.')[-1]
            if fmt == 'jpg':
                fmt = 'jpeg'
            
            save_kwargs = {'format': fmt, 'optimize': True, 'quality': quality}
            if fmt == 'jpeg':
                save_kwargs['subsampling'] = 0
            img.save(output, **save_kwargs)
            compressed_data = output.getvalue()
            results[size_name] = compressed_data
            cache.set(cache_key, compressed_data, CACHE_TIMEOUT)
        except Exception as e:
            print(f"Size gen error for {image_path}: {e}")
            with open(image_path, 'rb') as f:
                file_data = f.read()
            results[size_name] = file_data
            cache.set(cache_key, file_data, CACHE_TIMEOUT)
    return results

@assets_bp.route('/style.css')
def style():
    return send_from_directory('.', 'style.css')

@assets_bp.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

def respond_image(filepath, filename):
    size = request.args.get('size', 'full')
    if os.path.exists(filepath) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        if size in ['placeholder', 'thumbnail', 'full']:
            image_data = generate_image_sizes(filepath).get(size)
        elif size == 'original':
            with open(filepath, 'rb') as f:
                image_data = f.read()
        else:
            image_data = compress_image(filepath)
        
        mimetype = f"image/{filename.lower().split('.')[-1]}"
        if mimetype == "image/jpg":
            mimetype = "image/jpeg"
        # Access original response class
        from flask import current_app
        return current_app.response_class(image_data, mimetype=mimetype)
    return send_from_directory(os.path.dirname(filepath), filename)



@assets_bp.route('/assets/<path:filename>')
def serve_asset(filename):
    return respond_image(os.path.join('posts/assets', filename), filename)

@assets_bp.route('/posts/assets/<path:filename>')
def serve_post_asset(filename):
    return respond_image(os.path.join('posts/assets', filename), filename)

@assets_bp.route('/posts/<post_slug>-assets/<path:filename>')
def serve_post_specific_asset(post_slug, filename):
    return respond_image(os.path.join(f'posts/{post_slug}-assets', filename), filename)