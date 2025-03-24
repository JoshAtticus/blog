import os
import markdown
import shutil
import re
from datetime import datetime
from PIL import Image

# Image compression settings
COMPRESSION_QUALITY = 85
MAX_IMAGE_WIDTH = 1200

# Constants
TEMPLATES_DIR = "templates"
PUBLIC_DIR = "public"
POSTS_DIR = "posts"
ASSETS_DIR = os.path.join(POSTS_DIR, "assets")

# Helper Functions
def load_template(template_name):
    """Load an HTML template from the templates folder."""
    with open(os.path.join(TEMPLATES_DIR, template_name), "r", encoding="utf-8") as f:
        return f.read()

def compress_image(input_path, output_path, quality=COMPRESSION_QUALITY, max_width=MAX_IMAGE_WIDTH):
    """Compress an image file and save it to the output path."""
    try:
        if not input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            shutil.copy2(input_path, output_path)
            return False
        img = Image.open(input_path)
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        img.save(output_path, optimize=True, quality=quality)
        return True
    except Exception as e:
        print(f"Error compressing {input_path}: {e}")
        shutil.copy2(input_path, output_path)
        return False

def copy_with_compression(src_dir, dest_dir):
    """Copy directory tree with image compression."""
    os.makedirs(dest_dir, exist_ok=True)
    for root, _, files in os.walk(src_dir):
        rel_path = os.path.relpath(root, src_dir)
        dest_path = os.path.join(dest_dir, rel_path)
        os.makedirs(dest_path, exist_ok=True)
        for file in files:
            src_file = os.path.join(root, file)
            dest_file = os.path.join(dest_path, file)
            if not compress_image(src_file, dest_file):
                shutil.copy2(src_file, dest_file)

def extract_first_image(html_content):
    """Extract the first image URL from HTML content."""
    img_match = re.search(r'<img.*?src=["\'](.*?)["\']', html_content)
    return img_match.group(1) if img_match else None

def clean_html_for_summary(html_content):
    """Strip HTML tags and clean text for summaries."""
    text = re.sub(r"<[^>]+>", "", html_content).strip()
    return text

def parse_custom_widgets(content):
    """Parse and render custom widgets in the content."""
    # Parse [Review] blocks
    review_pattern = re.compile(r"\[Review\](.*?)\[/Review\]", re.DOTALL)
    content = review_pattern.sub(render_review_widget, content)

    # Parse [Summary] blocks
    summary_pattern = re.compile(r"\[Summary\](.*?)\[/Summary\]", re.DOTALL)
    content = summary_pattern.sub(render_summary_widget, content)

    return content

def render_review_widget(match):
    """Render a review widget."""
    review_data = parse_key_value_block(match.group(1))
    rating = float(review_data['ratingOutOf5'])
    stars = '★' * int(rating) + '☆' * (5 - int(rating))
    return f"""
    <div class="review-widget">
        <h2>{review_data['productName']}</h2>
        <div class="rating">{stars} ({review_data['ratingOutOf5']}/5)</div>
        <p>{review_data['reviewSummary']}</p>
        <div class="pros-cons">
            <div class="pros"><strong>Pros:</strong> {', '.join(review_data['pros'])}</div>
            <div class="cons"><strong>Cons:</strong> {', '.join(review_data['cons'])}</div>
        </div>
        <p><strong>Price:</strong> {review_data['price']}</p>
        <p><strong>Recommended:</strong> {"Yes" if review_data['isRecommended'] else "No"}</p>
        <a href="{review_data['URL']}" target="_blank" class="buy-now">Buy Now</a>
    </div>
    """

def render_summary_widget(match):
    """Render a summary widget."""
    summary_data = parse_key_value_block(match.group(1))
    return f"""
    <div class="summary-widget">
        <h2>Summary</h2>
        <p>{summary_data['content']}</p>
    </div>
    """

def parse_key_value_block(block):
    """Parse key-value pairs from a block."""
    lines = block.strip().split("\n")
    data = {}
    for line in lines:
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        # Replace JSON-like booleans with Python booleans
        value = value.replace("true", "True").replace("false", "False")
        data[key] = eval(value)  # Convert to appropriate type
    return data

# Main Functions
def process_posts():
    """Process all markdown posts and generate HTML."""
    posts = []
    os.makedirs(os.path.join(PUBLIC_DIR, "posts"), exist_ok=True)
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            with open(os.path.join(POSTS_DIR, filename), "r", encoding="utf-8") as f:
                content = f.read()

            # Parse front matter
            title = re.search(r"title:\s*(.*)", content).group(1).strip()
            date_str = re.search(r"date:\s*(.*)", content).group(1).strip()
            content = re.sub(r"---\n.*?\n---\n", "", content, flags=re.DOTALL)

            # Convert markdown to HTML
            html_content = markdown.markdown(content, extensions=["extra"], output_format="html5")
            html_content = parse_custom_widgets(html_content)

            # Extract first image
            first_image = extract_first_image(html_content)

            # Generate summary
            summary = clean_html_for_summary(html_content)[:100] + "..."

            # Save post HTML
            post_filename = os.path.splitext(filename)[0] + ".html"
            post_html = load_template("post_template.html").format(
                title=title,
                date=date_str,
                content=html_content,
                year=datetime.now().year
            )
            with open(os.path.join(PUBLIC_DIR, "posts", post_filename), "w", encoding="utf-8") as f:
                f.write(post_html)

            posts.append({
                "title": title,
                "date": date_str,
                "filename": post_filename,
                "summary": summary,
                "image": first_image
            })
    return posts

def generate_index(posts):
    """Generate the index page with pagination."""
    POSTS_PER_PAGE = 15
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    for page_num, start_idx in enumerate(range(0, len(posts), POSTS_PER_PAGE), start=1):
        paginated_posts = posts[start_idx:start_idx + POSTS_PER_PAGE]
        has_next_page = len(posts) > start_idx + POSTS_PER_PAGE

        # Generate post previews
        post_previews = ""
        for post in paginated_posts:
            image_html = f'<img src="posts/{post["image"]}" alt="{post["title"]}">' if post["image"] else ""
            post_previews += f"""
            <article>
                <h2><a href="posts/{post['filename']}">{post['title']}</a></h2>
                <p>{post['summary']}</p>
                {image_html}
            </article>
            """

        # Generate pagination
        pagination = ""
        if page_num > 1:
            pagination += f'<a href="index-{page_num - 1}.html">Previous</a>'
        if has_next_page:
            pagination += f'<a href="index-{page_num + 1}.html">Next</a>'

        # Save index page
        index_html = load_template("index_template.html").format(
            posts=post_previews,
            pagination=pagination,
            year=datetime.now().year
        )
        index_filename = f"index{'' if page_num == 1 else f'-{page_num}'}.html"
        with open(os.path.join(PUBLIC_DIR, index_filename), "w", encoding="utf-8") as f:
            f.write(index_html)

# Main Script
if __name__ == "__main__":
    # Copy assets
    if os.path.exists(ASSETS_DIR):
        copy_with_compression(ASSETS_DIR, os.path.join(PUBLIC_DIR, "assets"))

    # Process posts and generate pages
    posts = process_posts()
    posts.sort(key=lambda x: x["date"], reverse=True)
    generate_index(posts)

    print(f"✅ Blog generated with {len(posts)} posts")