import os
import markdown
import shutil
import re
from datetime import datetime

# Setup directories
os.makedirs("public/posts", exist_ok=True)
if os.path.exists("style.css"):
    shutil.copy("style.css", "public/")

assets_src = os.path.join("posts", "assets")
assets_dest = os.path.join("public", "assets")
if os.path.isdir(assets_src):
    shutil.copytree(assets_src, assets_dest, dirs_exist_ok=True)

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

        # Convert markdown to HTML
        html_content = markdown.markdown(content)
        
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
        # Using the naming convention: [postname]-assets
        post_assets_source = os.path.join("posts", os.path.splitext(filename)[0] + "-assets")
        if os.path.isdir(post_assets_source):
            post_assets_dest = os.path.join("public", "posts", os.path.splitext(filename)[0] + "-assets")
            shutil.copytree(post_assets_source, post_assets_dest, dirs_exist_ok=True)

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

# Sort posts by date (newest first)
posts.sort(key=lambda x: x["date"], reverse=True)

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
        image_html = f'<div class="post-image"><img src="{post["image"]}" alt="{post["title"]} featured image"></div>'

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
