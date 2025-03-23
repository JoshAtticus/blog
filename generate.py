import os
import markdown
import shutil
import re
from datetime import datetime
from PIL import Image  # Add this import
import io

# Image compression settings
COMPRESSION_QUALITY = 85  # 0-100, higher is better quality but larger file size
MAX_IMAGE_WIDTH = 1200    # Max width in pixels, height will scale proportionally

def compress_image(input_path, output_path, quality=COMPRESSION_QUALITY, max_width=MAX_IMAGE_WIDTH):
    """Compress an image file and save it to the output path."""
    try:
        # Check if the file is an image
        if not input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            # Not an image, just copy
            shutil.copy2(input_path, output_path)
            return False
            
        # Open the image
        img = Image.open(input_path)
        
        # Resize if larger than max_width
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        
        # Save with compression
        img.save(output_path, optimize=True, quality=quality)
        
        print(f"Compressed: {input_path}")
        return True
    except Exception as e:
        print(f"Error compressing {input_path}: {e}")
        # If compression fails, just copy the original
        if os.path.exists(input_path):
            shutil.copy2(input_path, output_path)
        return False

def copy_with_compression(src_dir, dest_dir):
    """Copy directory tree with image compression."""
    os.makedirs(dest_dir, exist_ok=True)
    
    # Get all files in source directory and subdirectories
    for root, _, files in os.walk(src_dir):
        # Get the corresponding destination directory
        rel_path = os.path.relpath(root, src_dir)
        dest_path = os.path.join(dest_dir, rel_path)
        
        # Create the destination directory if it doesn't exist
        os.makedirs(dest_path, exist_ok=True)
        
        # Copy each file
        for file in files:
            src_file = os.path.join(root, file)
            dest_file = os.path.join(dest_path, file)
            
            # Compress if it's an image, otherwise just copy
            if not compress_image(src_file, dest_file):
                shutil.copy2(src_file, dest_file)

# Setup directories
os.makedirs("public/posts", exist_ok=True)
if os.path.exists("style.css"):
    shutil.copy("style.css", "public/")

assets_src = os.path.join("posts", "assets")
assets_dest = os.path.join("public", "assets")
if os.path.isdir(assets_src):
    copy_with_compression(assets_src, assets_dest)

# Post template with dark mode toggle and comments
POST_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | JoshAtticus Blog</title>
  <link rel="stylesheet" href="../style.css">
  <style>
    /* Image handling in posts */
    .content img {{
      max-width: 100%;
      max-height: 400px; /* Smaller max height */
      height: auto;
      display: block;
      margin: 1rem 0;
    }}
    
    /* Create image gallery for consecutive images */
    .content p:has(img) + p:has(img) {{
      display: inline-block;
      vertical-align: top;
      margin-right: 1rem;
    }}
    
    /* Adjust consecutive images to display side by side */
    .content p:has(img) + p:has(img) img {{
      max-height: 300px;
      display: inline-block;
    }}
  </style>
</head>
<body>
  <header>
    <h1><a href="../index.html">JoshAtticus Blog</a></h1>
    <button class="theme-toggle" id="theme-toggle">🌓</button>
  </header>
  <main>
    <article>
      <h1>{title}</h1>
      <div class="date">{date}</div>
      <div class="content">
        {content}
      </div>
      
      <div class="comments">
        <h2>Comments</h2>
        <script src="https://utteranc.es/client.js"
                repo="JoshAtticus/blog"
                issue-term="title"
                label="comment-thread"
                theme="preferred-color-scheme"
                crossorigin="anonymous"
                async>
        </script>
      </div>
    </article>
  </main>
  <footer>© {year} JoshAtticus</footer>
  
  <script>
    // Dark mode toggle
    const themeToggle = document.getElementById('theme-toggle');
    
    // Check for saved theme preference or use system preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {{
  document.body.classList.add('dark-mode');
  themeToggle.textContent = '☀️';
}} else if (savedTheme === 'light') {{
      document.body.classList.remove('dark-mode');
      themeToggle.textContent = '🌙';
    }}
    
    // Theme toggle button
    themeToggle.addEventListener('click', () => {{
      if (document.body.classList.contains('dark-mode')) {{
        document.body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light');
        themeToggle.textContent = '🌙';
      }} else {{
        document.body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark');
        themeToggle.textContent = '☀️';
      }}
    }});
  </script>
</body>
</html>"""


# Function to clean HTML for summaries
def clean_for_summary(html_content):
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", html_content)
    # Remove leading/trailing whitespace
    text = text.strip()
    return text


# Function to extract the first image from HTML content
def extract_first_image(html_content):
    # Look for the first image tag in the HTML content
    img_match = re.search(r'<img.*?src=["\'](.*?)["\']', html_content)
    if img_match:
        return img_match.group(1)
    return None


# Function to escape curly braces for string formatting
def escape_braces(text):
    return text.replace("{", "{{").replace("}", "}}")

# Function to fix image paths for post HTML (adding "../" to assets/ paths)
def fix_image_paths_for_posts(html_content):
    # Replace references to assets/ with ../assets/ for post pages
    fixed_html = re.sub(r'src=["\']assets/', r'src="../assets/', html_content)
    return fixed_html

def parse_custom_widgets(content):
    # Parse [Review] blocks
    review_pattern = re.compile(r"\[Review\](.*?)\[/Review\]", re.DOTALL)
    content = review_pattern.sub(render_review_widget, content)

    # Parse [Summary] blocks
    summary_pattern = re.compile(r"\[Summary\](.*?)\[/Summary\]", re.DOTALL)
    content = summary_pattern.sub(render_summary_widget, content)

    return content

def render_review_widget(match):
    # Extract review details
    review_data = parse_key_value_block(match.group(1))
    
    # Format rating as stars
    rating = float(review_data['ratingOutOf5'])
    stars = '★' * int(rating) + '☆' * (5 - int(rating))
    
    return f"""
    <div class="review-widget">
        <div class="review-header">
            <h2>{review_data['productName']}</h2>
            <div class="rating">{stars} ({review_data['ratingOutOf5']}/5)</div>
        </div>
        
        <p class="review-summary">{review_data['reviewSummary']}</p>
        
        <div class="review-grid">
            <div class="review-section">
                <h3>Pros</h3>
                <ul>
                    {' '.join(f'<li>{pro}</li>' for pro in review_data['pros'])}
                </ul>
            </div>
            <div class="review-section">
                <h3>Cons</h3>
                <ul>
                    {' '.join(f'<li>{con}</li>' for con in review_data['cons'])}
                </ul>
            </div>
        </div>
        
        <div class="review-grid">
            <div class="review-section">
                <h3>Price</h3>
                <p>{review_data['price']}</p>
            </div>
            <div class="review-section">
                <h3>Recommended</h3>
                <p>{"Yes" if review_data['isRecommended'] else "No"}</p>
            </div>
        </div>
        
        <a href="{review_data['URL']}" target="_blank" class="review-cta">Buy Now</a>
    </div>
    """

def render_summary_widget(match):
    # Extract summary details
    summary_data = parse_key_value_block(match.group(1))
    return f"""
    <div class="summary-widget">
        <h2>Summary</h2>
        <p>{summary_data['content']}</p>
    </div>
    """

def parse_key_value_block(block):
    # Parse key-value pairs from a block
    lines = block.strip().split("\n")
    data = {}
    for line in lines:
        key, value = line.split(":", 1)
        key = key.strip()
        value = eval(value.strip())  # Convert to appropriate type (e.g., list, string)
        data[key] = value
    return data

# Function to process custom widgets after HTML conversion
def process_custom_widgets_in_html(html_content):
    # Look for Summary widget markers in the HTML
    summary_pattern = re.compile(r'<p>\[Summary\](.*?)\[/Summary\]</p>', re.DOTALL)
    html_content = summary_pattern.sub(process_summary_widget, html_content)
    
    # Look for Review widget markers in the HTML
    review_pattern = re.compile(r'<p>\[Review\](.*?)\[/Review\]</p>', re.DOTALL)
    html_content = review_pattern.sub(process_review_widget, html_content)
    
    return html_content

def process_summary_widget(match):
    # Extract the content between the tags
    inner_content = match.group(1).strip()
    
    # Extract the summary content
    content_match = re.search(r'content:\s*"([^"]*)"', inner_content)
    if not content_match:
        return "<div class='error'>Invalid summary format</div>"
    
    summary_content = content_match.group(1)
    
    # Generate HTML for the summary widget
    return f"""
    <div class="summary-widget">
        <h2>Summary</h2>
        <p>{summary_content}</p>
    </div>
    """

def process_review_widget(match):
    # Extract the content between the tags
    inner_content = match.group(1).strip()
    
    # Extract review details with regex
    product_match = re.search(r'productName:\s*"([^"]*)"', inner_content)
    summary_match = re.search(r'reviewSummary:\s*"([^"]*)"', inner_content)
    rating_match = re.search(r'ratingOutOf5:\s*([\d\.]+)', inner_content)
    pros_match = re.search(r'pros:\s*\["([^"]*)"(?:,\s*"([^"]*)")?(?:,\s*"([^"]*)")?\]', inner_content)
    cons_match = re.search(r'cons:\s*\["([^"]*)"(?:,\s*"([^"]*)")?\]', inner_content)
    recommended_match = re.search(r'isRecommended:\s*(true|false)', inner_content)
    price_match = re.search(r'price:\s*"([^"]*)"', inner_content)
    url_match = re.search(r'URL:\s*"([^"]*)"', inner_content)
    
    # Handle missing data
    if not all([product_match, summary_match, rating_match, price_match, url_match]):
        return "<div class='error'>Invalid review format</div>"
    
    # Extract values
    product_name = product_match.group(1)
    summary = summary_match.group(1)
    rating = rating_match.group(1)
    price = price_match.group(1)
    url = url_match.group(1)
    
    # Handle optional arrays
    pros = []
    if pros_match:
        for i in range(1, 4):
            if pros_match.group(i):
                pros.append(pros_match.group(i))
    
    cons = []
    if cons_match:
        for i in range(1, 3):
            if cons_match.group(i):
                cons.append(cons_match.group(i))
    
    recommended = "Yes" if recommended_match and recommended_match.group(1) == "true" else "No"
    
    # Generate HTML for the review widget
    return f"""
    <div class="review-widget">
        <h2>{product_name} Review</h2>
        <p>{summary}</p>
        <p><strong>Rating:</strong> {rating} / 5</p>
        <p><strong>Pros:</strong> {', '.join(pros)}</p>
        <p><strong>Cons:</strong> {', '.join(cons)}</p>
        <p><strong>Price:</strong> {price}</p>
        <p><strong>Recommended:</strong> {recommended}</p>
        <a href="{url}" target="_blank">Buy Now</a>
    </div>
    """

# Process all markdown posts
posts = []
for filename in os.listdir("posts"):
    if filename.endswith(".md"):
        with open(f"posts/{filename}", "r", encoding="utf-8") as f:
            content = f.read()

        # Parse front matter
        title_match = re.search(r"title:\s*(.*)", content)
        date_match = re.search(r"date:\s*(.*)", content)

        title = title_match.group(1).strip() if title_match else "Untitled"
        date_str = (
            date_match.group(1).strip()
            if date_match
            else datetime.now().strftime("%Y-%m-%d")
        )

        # Remove front matter
        content = re.sub(r"---\n.*?\n---\n", "", content, flags=re.DOTALL)

        # Remove Markdown headers that might be at the start
        content_for_summary = re.sub(r"^#+ .*?\n", "", content, flags=re.MULTILINE)

        # Convert markdown to HTML first
        html_content = markdown.markdown(content, extensions=['extra'], output_format='html5')
        
        # Process custom widgets AFTER HTML conversion
        html_content = process_custom_widgets_in_html(html_content)
        
        # Extract the first image URL before fixing paths for preview purposes
        first_image = extract_first_image(html_content)
        
        # Fix image paths for post HTML
        fixed_html_content = fix_image_paths_for_posts(html_content)

        # Clean text for summary (remove HTML tags)
        summary_text = clean_for_summary(markdown.markdown(content_for_summary))

        # Escape curly braces in HTML content to prevent formatting conflicts
        escaped_html_content = escape_braces(fixed_html_content)

        # Generate post HTML file
        post_html = POST_TEMPLATE.format(
            title=title,
            date=date_str,
            content=escaped_html_content,
            year=datetime.now().year,
        )

        # Save HTML file
        post_filename = os.path.splitext(filename)[0] + ".html"
        with open(f"public/posts/{post_filename}", "w", encoding="utf-8") as f:
            f.write(post_html)

        # If an assets folder exists for this post, copy it to the public/posts folder.
        post_assets_source = os.path.join("posts", os.path.splitext(filename)[0] + "-assets")
        if os.path.isdir(post_assets_source):
            post_assets_dest = os.path.join("public", "posts", os.path.splitext(filename)[0] + "-assets")
            copy_with_compression(post_assets_source, post_assets_dest)

        posts.append(
            {
                "title": title,
                "date": date_str,
                "filename": post_filename,
                "summary": (
                    summary_text[:100] + "..."
                    if len(summary_text) > 100
                    else summary_text
                ),
                "image": first_image,
            }
        )
        
def generate_index_page(posts, page_num, has_next_page):
    """Generate HTML for an index page with a list of posts."""
    page_html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JoshAtticus Blog - Page {}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1><a href="index.html">JoshAtticus Blog</a></h1>
    <button class="theme-toggle" id="theme-toggle">🌓</button>
  </header>
  <main>
    <div class="post-list">
""".format(page_num)

    for post in posts:
        image_html = ""
        if post.get("image"):
            image_html = f'<div class="post-image"><img src="{post["image"]}" alt="{post["title"]} featured image"></div>'

        page_html += f"""
      <article class="post-preview">
        <h2><a href="posts/{post['filename']}">{post['title']}</a></h2>
        <div class="date">{post['date']}</div>
        <div class="post-content">
          <div class="summary">{post['summary']}</div>
          {image_html}
        </div>
      </article>
    """

    page_html += """
    </div>
    <nav class="pagination">
    """

    # Add pagination links
    if page_num > 1:
        prev_page = "index.html" if page_num == 2 else f"index-{page_num - 1}.html"
        page_html += f'<a href="{prev_page}" class="prev">Previous</a>'

    if has_next_page:
        next_page = f"index-{page_num + 1}.html"
        page_html += f'<a href="{next_page}" class="next">Next</a>'

    page_html += """
    </nav>
  </main>
  <footer>© {} JoshAtticus</footer>
  
  <script>
    // Dark mode toggle
    const themeToggle = document.getElementById('theme-toggle');
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {{
      document.body.classList.add('dark-mode');
      themeToggle.textContent = '☀️';
    }} else if (savedTheme === 'light') {{
      document.body.classList.remove('dark-mode');
      themeToggle.textContent = '🌙';
    }}
    themeToggle.addEventListener('click', () => {{
      if (document.body.classList.contains('dark-mode')) {{
        document.body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light');
        themeToggle.textContent = '🌙';
      }} else {{
        document.body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark');
        themeToggle.textContent = '☀️';
      }}
    }});
  </script>
</body>
</html>
""".format(datetime.now().year)

    return page_html

# Sort posts by date (newest first)
posts.sort(key=lambda x: x["date"], reverse=True)

POSTS_PER_PAGE = 15

# Generate paginated index pages
for page_num, start_idx in enumerate(range(0, len(posts), POSTS_PER_PAGE), start=1):
    paginated_posts = posts[start_idx:start_idx + POSTS_PER_PAGE]
    page_html = generate_index_page(paginated_posts, page_num, len(posts) > start_idx + POSTS_PER_PAGE)
    with open(f"public/index{'' if page_num == 1 else f'-{page_num}'}.html", "w", encoding="utf-8") as f:
        f.write(page_html)

# Generate index page with CSS for post previews with images
index_html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JoshAtticus Blog</title>
  <link rel="stylesheet" href="style.css">
  <style>
    .post-preview {
      display: flex;
      flex-direction: column;
      margin-bottom: 2rem;
    }
    .post-content {
      display: flex;
      align-items: flex-start;
    }
    .post-image {
      margin-left: 1rem;
      flex-shrink: 0;
      width: 150px;
      height: 150px;
      overflow: hidden;
      border-radius: 5px;
      align-self: flex-start;
      margin-top: -5.5rem; /* Use negative margin to move image up */
    }
    .post-image img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .summary {
      flex-grow: 1;
    }
    @media (max-width: 600px) {
      .post-content {
        flex-direction: column;
      }
      .post-image {
        margin-left: 0;
        margin-top: 1rem; /* Reset margin for mobile layout */
        width: 100%;
        height: auto;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>JoshAtticus Blog</h1>
    <button class="theme-toggle" id="theme-toggle">🌓</button>
  </header>
  <main>
    <div class="post-list">
"""

for post in posts:
    image_html = ""
    if post.get("image"):
        image_html = f'<div class="post-image"><img src="{post["image"]}" alt="{post["title"]}" featured image"></div>'

    index_html += f"""
      <article class="post-preview">
        <h2><a href="posts/{post['filename']}">{post['title']}</a></h2>
        <div class="date">{post['date']}</div>
        <div class="post-content">
          <div class="summary">{post['summary']}</div>
          {image_html}
        </div>
      </article>
    """

index_html += (
    """
    </div>
  </main>
  <footer>© """
    + str(datetime.now().year)
    + """ JoshAtticus</footer>
  
  <script>
    // Dark mode toggle
    const themeToggle = document.getElementById('theme-toggle');
    
    // Check for saved theme preference or use system preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      document.body.classList.add('dark-mode');
      themeToggle.textContent = '☀️';
    } else if (savedTheme === 'light') {
      document.body.classList.remove('dark-mode');
      themeToggle.textContent = '🌙';
    }
    
    // Theme toggle button
    themeToggle.addEventListener('click', () => {
      if (document.body.classList.contains('dark-mode')) {
        document.body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light');
        themeToggle.textContent = '🌙';
      } else {
        document.body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark');
        themeToggle.textContent = '☀️';
      }
    });
  </script>
</body>
</html>"""
)

with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(index_html)
print(f"✅ Blog generated with {len(posts)} posts")
