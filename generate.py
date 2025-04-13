import os
import markdown
import shutil
import re
import json
from datetime import datetime
from PIL import Image
import io

# Image compression settings
COMPRESSION_QUALITY = 85  # 0-100, higher is better quality but larger file size
MAX_IMAGE_WIDTH = 1200    # Max width in pixels, height will scale proportionally

# Track processed images to avoid re-compressing
processed_images = set()

def compress_image(input_path, output_path, quality=COMPRESSION_QUALITY, max_width=MAX_IMAGE_WIDTH):
    """Compress an image file and save it to the output path."""
    # Skip if already processed this exact output path
    if output_path in processed_images:
        return True
        
    try:
        # Check if the file is an image
        if not input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            # Not an image, just copy
            shutil.copy2(input_path, output_path)
            processed_images.add(output_path)
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
        processed_images.add(output_path)
        return True
    except Exception as e:
        print(f"Error compressing {input_path}: {e}")
        # If compression fails, just copy the original
        if os.path.exists(input_path):
            shutil.copy2(input_path, output_path)
            processed_images.add(output_path)
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

# Post template
POST_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | JoshAtticus Blog</title>
  <link rel="stylesheet" href="../style.css">
  
  <!-- Open Graph / Facebook Meta Tags -->
  <meta property="og:type" content="article">
  <meta property="og:url" content="{url}">
  <meta property="og:title" content="{title} | JoshAtticus Blog">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{absolute_image_url}">
  
  <!-- Twitter Meta Tags -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title} | JoshAtticus Blog">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{absolute_image_url}">
  
  <script defer data-domain="blog.joshatticus.site" src="https://plausible.joshatticus.site/js/script.file-downloads.outbound-links.js"></script>
</head>
<body>
  <div class="reading-progress-container">
    <div class="reading-progress" id="reading-progress"></div>
  </div>
  
  <header>
    <h1><a href="../index.html">JoshAtticus Blog</a></h1>

    <nav class="nav">
      <a href="tags.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 2v6h6V2H3zm2 2h2v2H5V4zm8-2v6h6V2h-6zm2 2h2v2h-2V4zM3 12v6h6v-6H3zm2 2h2v2H5v-2zm13-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-4zm0 2h4v2h-4v-2z"/></svg>
        Tags
      </a>
      <a href="search.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm-8 6a8 8 0 1 1 14.32 4.906l5.387 5.387a1 1 0 0 1-1.414 1.414l-5.387-5.387A8 8 0 0 1 2 10z"/></svg>
        Search
      </a>
    </nav>
  </header>
  
  <main>
    <article>
      <!-- Banner image with title overlay -->
      <div class="post-header">
        <img alt="{title}" src="../{first_image}" />
        <div class="title-overlay">
          <h1>{title}</h1>
          <div class="date">{date}</div>
        </div>
      </div>
      
      <!-- Main content container -->
      <div class="post-container">
        <div class="content">
          {content_without_first_image}
        </div>
        
        <!-- Share buttons -->
        <div class="share-buttons">
          <a href="https://twitter.com/intent/tweet?text={title} by JoshAtticus&url={url}" target="_blank" rel="noopener noreferrer" class="share-twitter">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"></path></svg>
            Post on X
          </a>
          <a href="https://www.facebook.com/sharer/sharer.php?u={url}&quote={title} by JoshAtticus" target="_blank" rel="noopener noreferrer" class="share-facebook">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"></path></svg>
            Share on Facebook
          </a>
          <a href="mailto:?subject={title}&body=Check out this blog post by JoshAtticus: {url}" class="share-email">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"></path></svg>
            Share via Email
          </a>
        </div>
        
        <div class="comments">
          <h2>Comments</h2>
          <script src="https://utteranc.es/client.js"
                  repo="JoshAtticus/blog"
                  issue-term="title"
                  label="comment-thread"
                  theme="github-dark"
                  crossorigin="anonymous"
                  async>
          </script>
        </div>
      </div>
    </article>
  </main>
  <footer>© {year} JoshAtticus</footer>
  
  <script>
    // Reading progress tracker
    window.addEventListener('scroll', () => {{
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = (scrollTop / scrollHeight) * 100;
      document.getElementById('reading-progress').style.width = scrolled + '%';
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

def extract_and_remove_first_image(html_content):
    # Extract the first image path
    img_match = re.search(r'<p><img.*?src=["\'](?:\.\./)?(.*?)["\'].*?></p>', html_content)
    first_image = ""
    content_without_first_image = html_content
    
    if (img_match):
        first_image = img_match.group(1)
        # Remove the first image paragraph from content
        content_without_first_image = re.sub(r'<p><img.*?src=["\'](?:\.\./)?' + re.escape(first_image) + r'["\'].*?></p>', '', html_content, count=1)
    
    return first_image, content_without_first_image

# Update the front matter parsing to extract tags
def parse_front_matter(content):
    """Parse front matter from Markdown content"""
    front_matter = {}
    
    # Extract the front matter section
    front_matter_match = re.match(r"---\n(.*?)\n---", content, re.DOTALL)
    if (front_matter_match):
        front_matter_text = front_matter_match.group(1)
        
        # Extract title
        title_match = re.search(r"title:\s*(.*)", front_matter_text)
        if title_match:
            front_matter['title'] = title_match.group(1).strip()
        
        # Extract date
        date_match = re.search(r"date:\s*(.*)", front_matter_text)
        if date_match:
            front_matter['date'] = date_match.group(1).strip()
        
        # Extract tags - can be in array format or comma-separated
        tags_match = re.search(r"tags:\s*\[(.*?)\]", front_matter_text, re.DOTALL)
        if tags_match:
            # Array format: tags: [tag1, tag2, tag3]
            tags_text = tags_match.group(1)
            tags = [tag.strip().strip('"\'') for tag in tags_text.split(',')]
            front_matter['tags'] = [tag for tag in tags if tag]  # Remove empty tags
        else:
            # Look for simple format: tags: tag1, tag2, tag3
            tags_match = re.search(r"tags:\s*(.*)", front_matter_text)
            if tags_match:
                tags_text = tags_match.group(1)
                tags = [tag.strip().strip('"\'') for tag in tags_text.split(',')]
                front_matter['tags'] = [tag for tag in tags if tag]
            else:
                front_matter['tags'] = []
    
    return front_matter

# Create search index data structure
def create_search_index(posts):
    """Create a search index for client-side searching"""
    search_data = []
    for post in posts:
        search_data.append({
            'title': post['title'],
            'date': post['date'],
            'filename': post['filename'],
            'summary': post['summary'],
            'tags': post.get('tags', []),
            'image': post.get('image', '')
        })
    return search_data

# Generate tag pages
def generate_tag_pages(posts, output_dir):
    """Generate HTML pages for each tag"""
    # Collect all tags and the posts that have them
    tags = {}
    for post in posts:
        for tag in post.get('tags', []):
            if tag not in tags:
                tags[tag] = []
            tags[tag].append(post)
    
    # Create a tags directory
    tags_dir = os.path.join(output_dir, "tags")
    os.makedirs(tags_dir, exist_ok=True)
    
    # Create an index of all tags
    tags_index = []
    
    # Generate a page for each tag
    for tag, tag_posts in tags.items():
        # Sort posts by date
        tag_posts.sort(key=lambda x: x['date'], reverse=True)
        
        # Add to tags index
        tags_index.append({
            'name': tag,
            'count': len(tag_posts),
            'slug': tag.lower().replace(' ', '-')
        })
        
        # Generate HTML file for this tag
        tag_filename = os.path.join(tags_dir, f"{tag.lower().replace(' ', '-')}.html")
        
        with open(tag_filename, "w", encoding="utf-8") as f:
            f.write(generate_tag_page_html(tag, tag_posts))
    
    # Sort tags by name
    tags_index.sort(key=lambda x: x['name'])
    
    # Create tags index page
    with open(os.path.join(output_dir, "tags.html"), "w", encoding="utf-8") as f:
        f.write(generate_tags_index_html(tags_index))
    
    return tags_index

# Generate HTML for a tag page
def generate_tag_page_html(tag, posts):
    """Generate HTML for a specific tag page"""
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Posts tagged "{tag}" | JoshAtticus Blog</title>
  <link rel="stylesheet" href="../style.css">
  <script defer data-domain="blog.joshatticus.site" src="https://plausible.joshatticus.site/js/script.file-downloads.outbound-links.js"></script>
</head>
<body>
  <div class="reading-progress-container">
    <div class="reading-progress" id="reading-progress"></div>
  </div>
  
    <header>
        <h1><a href="../index.html">JoshAtticus Blog</a></h1>

    <nav class="nav">
      <a href="tags.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 2v6h6V2H3zm2 2h2v2H5V4zm8-2v6h6V2h-6zm2 2h2v2h-2V4zM3 12v6h6v-6H3zm2 2h2v2H5v-2zm13-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-4zm0 2h4v2h-4v-2z"/></svg>
        Tags
      </a>
      <a href="search.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm-8 6a8 8 0 1 1 14.32 4.906l5.387 5.387a1 1 0 0 1-1.414 1.414l-5.387-5.387A8 8 0 0 1 2 10z"/></svg>
        Search
      </a>
    </nav>
  </header>
  
  <main>
    <div class="breadcrumb">
      <a href="../index.html">Home</a> > <a href="../tags.html">Tags</a> > {tag}
    </div>
    
    <h2 class="tag-header">
      Posts tagged "{tag}" <span class="tag-count">({len(posts)})</span>
    </h2>
    
    <div class="post-list">
"""

    # Add posts to the HTML
    for post in posts:
        # Generate tags HTML
        tags_html = ''
        if post.get('tags'):
            tags_html = '<div class="tags">'
            for post_tag in post.get('tags'):
                tag_slug = post_tag.lower().replace(' ', '-')
                tags_html += f'<a href="../tags/{tag_slug}.html" class="tag">{post_tag}</a>'
            tags_html += '</div>'
        
        # Generate image HTML
        image_html = ""
        if post.get('image'):
            image_html = f'<div class="post-image"><img src="../{post["image"]}" alt="{post["title"]} featured image"></div>'

        html += f"""
      <article class="post-preview">
        <h2><a href="../posts/{post['filename']}">{post['title']}</a></h2>
        <div class="date">{post['date']}</div>
        <div class="post-content">
          <div class="summary">
            {post['summary']}
            {tags_html}
          </div>
          {image_html}
        </div>
      </article>
    """

    html += """
    </div>
  </main>
  <footer>© """ + str(datetime.now().year) + """ JoshAtticus</footer>
  
  <script>
    // Reading progress tracker
    window.addEventListener('scroll', () => {
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = (scrollTop / scrollHeight) * 100;
      document.getElementById('reading-progress').style.width = scrolled + '%';
    });
  </script>
</body>
</html>"""

    return html

# Generate HTML for tags index page
def generate_tags_index_html(tags):
    """Generate HTML for the tags index page"""
    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>All Tags | JoshAtticus Blog</title>
  <link rel="stylesheet" href="style.css">
  <script defer data-domain="blog.joshatticus.site" src="https://plausible.joshatticus.site/js/script.file-downloads.outbound-links.js"></script>
</head>
<body>
  <div class="reading-progress-container">
    <div class="reading-progress" id="reading-progress"></div>
  </div>
  
    <header>
        <h1><a href="index.html">JoshAtticus Blog</a></h1>

    <nav class="nav">
      <a href="tags.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 2v6h6V2H3zm2 2h2v2H5V4zm8-2v6h6V2h-6zm2 2h2v2h-2V4zM3 12v6h6v-6H3zm2 2h2v2H5v-2zm13-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-4zm0 2h4v2h-4v-2z"/></svg>
        Tags
      </a>
      <a href="search.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm-8 6a8 8 0 1 1 14.32 4.906l5.387 5.387a1 1 0 0 1-1.414 1.414l-5.387-5.387A8 8 0 0 1 2 10z"/></svg>
        Search
      </a>
    </nav>
  </header>
  
  <main>
    <div class="breadcrumb">
      <a href="index.html">Home</a> > Tags
    </div>
    
    <h2>All Tags</h2>
    
    <div class="tag-cloud">
"""

    # Add tags to the HTML
    for tag in tags:
        html += f"""
      <a href="tags/{tag['slug']}.html" class="tag-item">
        <span class="tag-name">{tag['name']}</span>
        <span class="tag-count">{tag['count']}</span>
      </a>
    """

    html += """
    </div>
  </main>
  <footer>© """ + str(datetime.now().year) + """ JoshAtticus</footer>
  
  <script>
    // Reading progress tracker
    window.addEventListener('scroll', () => {
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollHeight = document.document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = (scrollTop / scrollHeight) * 100;
      document.getElementById('reading-progress').style.width = scrolled + '%';
    });
  </script>
</body>
</html>"""

    return html

def generate_search_page_html():
    """Generate HTML for the search page"""
    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Search | JoshAtticus Blog</title>
  <link rel="stylesheet" href="style.css">
  <script defer data-domain="blog.joshatticus.site" src="https://plausible.joshatticus.site/js/script.file-downloads.outbound-links.js"></script>
</head>
<body>
  <div class="reading-progress-container">
    <div class="reading-progress" id="reading-progress"></div>
  </div>

  
<header>
        <h1><a href="index.html">JoshAtticus Blog</a></h1>

    <nav class="nav">
      <a href="tags.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 2v6h6V2H3zm2 2h2v2H5V4zm8-2v6h6V2h-6zm2 2h2v2h-2V4zM3 12v6h6v-6H3zm2 2h2v2H5v-2zm13-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-4zm0 2h4v2h-4v-2z"/></svg>
        Tags
      </a>
      <a href="search.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm-8 6a8 8 0 1 1 14.32 4.906l5.387 5.387a1 1 0 0 1-1.414 1.414l-5.387-5.387A8 8 0 0 1 2 10z"/></svg>
        Search
      </a>
    </nav>
  </header>
  
  <main>
    <div class="breadcrumb">
      <a href="index.html">Home</a> > Search
    </div>
    
    <h2>Search</h2>
    
    <div class="search-container">
      <input type="text" id="search-input" class="search-input" placeholder="Search posts..." autofocus>
      
      <div id="search-results" class="search-results">
        <p class="no-results">Start typing to search...</p>
      </div>
    </div>
  </main>
  <footer>© """ + str(datetime.now().year) + """ JoshAtticus</footer>
  
  <script>
    // Reading progress tracker
    window.addEventListener('scroll', () => {
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = (scrollTop / scrollHeight) * 100;
      document.getElementById('reading-progress').style.width = scrolled + '%';
    });
    
    // Search functionality
    (async function() {
      const searchInput = document.getElementById('search-input');
      const searchResults = document.getElementById('search-results');
      
      // Load search index
      let searchData = [];
      
      try {
        const response = await fetch('search-index.json');
        searchData = await response.json();
      } catch (error) {
        console.error('Error loading search index:', error);
        searchResults.innerHTML = '<p class="no-results">Error loading search data.</p>';
        return;
      }
      
      // Search function
      function search(query) {
        if (!query) {
          searchResults.innerHTML = '<p class="no-results">Start typing to search...</p>';
          return;
        }
        
        // Convert query to lowercase for case-insensitive search
        query = query.toLowerCase();
        
        // Filter posts that match the query
        const results = searchData.filter(post => {
          const titleMatch = post.title.toLowerCase().includes(query);
          const summaryMatch = post.summary.toLowerCase().includes(query);
          const tagMatch = post.tags.some(tag => tag.toLowerCase().includes(query));
          
          return titleMatch || summaryMatch || tagMatch;
        });
        
        // Display results
        if (results.length === 0) {
          searchResults.innerHTML = '<p class="no-results">No results found.</p>';
          return;
        }
        
        // Function to highlight matching text - FIXED by adding extra backslashes
        function highlightText(text, query) {
          if (!text) return '';
          // Escape special regex characters in the query
          const escapedQuery = query.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
          const regex = new RegExp(`(${escapedQuery})`, 'gi');
          return text.replace(regex, '<span class="highlight">$1</span>');
        }
        
        // Generate HTML for results
        let resultsHTML = '';
        
        results.forEach(post => {
          // Highlight matching text
          const highlightedTitle = highlightText(post.title, query);
          const highlightedSummary = highlightText(post.summary, query);
          
          // Generate tags HTML
          let tagsHTML = '';
          if (post.tags && post.tags.length > 0) {
            tagsHTML = '<div class="tags">';
            post.tags.forEach(tag => {
              const tagSlug = tag.toLowerCase().replace(/ /g, '-');
              const highlightedTag = highlightText(tag, query);
              tagsHTML += `<a href="tags/${tagSlug}.html" class="tag">${highlightedTag}</a>`;
            });
            tagsHTML += '</div>';
          }
          
          // Generate image HTML
          let imageHTML = '';
          if (post.image) {
            imageHTML = `<div class="post-image"><img src="${post.image}" alt="${post.title} featured image"></div>`;
          }
          
          resultsHTML += `
            <article class="post-preview">
              <h2><a href="posts/${post.filename}">${highlightedTitle}</a></h2>
              <div class="date">${post.date}</div>
              <div class="post-content">
                <div class="summary">
                  ${highlightedSummary}
                  ${tagsHTML}
                </div>
                ${imageHTML}
              </div>
            </article>
          `;
        });
        
        searchResults.innerHTML = resultsHTML;
      }
      
      // Listen for input changes
      let debounceTimeout;
      searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
          search(searchInput.value.trim());
        }, 300); // Debounce to avoid searching on every keystroke
      });
      
      // Check if URL has search parameter
      const urlParams = new URLSearchParams(window.location.search);
      const queryParam = urlParams.get('q');
      if (queryParam) {
        searchInput.value = queryParam;
        search(queryParam);
      }
    })();
  </script>
</body>
</html>"""

    return html

def process_markdown_posts():
    posts = []
    for filename in os.listdir("posts"):
        if filename.endswith(".md"):
            with open(f"posts/{filename}", "r", encoding="utf-8") as f:
                content = f.read()

            # Parse front matter including tags
            front_matter = parse_front_matter(content)
            
            title = front_matter.get('title', "Untitled")
            date_str = front_matter.get('date', datetime.now().strftime("%Y-%m-%d"))
            tags = front_matter.get('tags', [])

            # Remove front matter
            content = re.sub(r"---\n.*?\n---\n", "", content, flags=re.DOTALL)

            # Remove Markdown headers that might be at the start
            content_for_summary = re.sub(r"^#+ .*?\n", "", content, flags=re.MULTILINE)

            # Convert markdown to HTML
            html_content = markdown.markdown(content)
            
            # Fix image paths for post HTML
            fixed_html_content = fix_image_paths_for_posts(html_content)
            
            # Extract and remove the first image for the banner
            first_image, content_without_first_image = extract_and_remove_first_image(fixed_html_content)
            
            # If no image was found, use a default image
            if not first_image:
                first_image = "assets/default-banner.jpg"  # Create a default banner image
            
            # Escape curly braces in the content
            escaped_content = escape_braces(content_without_first_image)

            # Clean text for summary (remove HTML tags)
            summary_text = clean_for_summary(markdown.markdown(content_for_summary))

            # Escape curly braces in HTML content to prevent formatting conflicts
            escaped_html_content = escape_braces(fixed_html_content)

            # Post filename
            post_filename = os.path.splitext(filename)[0] + ".html"
            
            # Create URL for sharing
            post_url = f"https://blog.joshatticus.site/posts/{post_filename}"

            # Create absolute image URL (important for social media previews)
            absolute_image_url = f"https://blog.joshatticus.site/{first_image}"

            # Use summary as description for meta tags
            description = summary_text[:160] + "..." if len(summary_text) > 160 else summary_text

            # Add tags to the post HTML content
            tags_html = ''
            if tags:
                tags_html = '<div class="tags" style="margin-top: 1.5rem;">'
                for tag in tags:
                    tag_slug = tag.lower().replace(' ', '-')
                    tags_html += f'<a href="../tags/{tag_slug}.html" class="tag">{tag}</a>'
                tags_html += '</div>'

            # Modify POST_TEMPLATE to include tags
            post_html = POST_TEMPLATE.format(
                title=title,
                date=date_str,
                first_image=first_image,
                absolute_image_url=absolute_image_url,
                description=description,
                content_without_first_image=escaped_content + tags_html,  # Add tags after content
                year=datetime.now().year,
                url=post_url
            )
            
            # Save HTML file
            with open(f"public/posts/{post_filename}", "w", encoding="utf-8") as f:
                f.write(post_html)

            # If an assets folder exists for this post, copy it
            post_assets_source = os.path.join("posts", os.path.splitext(filename)[0] + "-assets")
            if os.path.isdir(post_assets_source):
                post_assets_dest = os.path.join("public", "posts", os.path.splitext(filename)[0] + "-assets")
                copy_with_compression(post_assets_source, post_assets_dest)

            posts.append({
                "title": title,
                "date": date_str,
                "filename": post_filename,
                "summary": summary_text[:100] + "..." if len(summary_text) > 100 else summary_text,
                "image": first_image,
                "tags": tags
            })

    return posts

if __name__ == "__main__":
    # Setup directories
    os.makedirs("public/posts", exist_ok=True)
    os.makedirs("public/tags", exist_ok=True)
    
    if os.path.exists("style.css"):
        shutil.copy("style.css", "public/")

    assets_src = os.path.join("posts", "assets")
    assets_dest = os.path.join("public", "assets")
    if os.path.isdir(assets_src):
        copy_with_compression(assets_src, assets_dest)
    
    # Process markdown posts
    posts = process_markdown_posts()
    
    # Sort posts by date (newest first)
    posts.sort(key=lambda x: x["date"], reverse=True)
    
    # Generate search index
    search_index = create_search_index(posts)
    with open("public/search-index.json", "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False)
    
    # Generate tag pages
    tags_index = generate_tag_pages(posts, "public")
    
    # Generate search page
    with open("public/search.html", "w", encoding="utf-8") as f:
        f.write(generate_search_page_html())
    
    # Update the index.html template
    index_html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JoshAtticus Blog</title>
  <link rel="stylesheet" href="style.css">
  
  <!-- Open Graph / Facebook Meta Tags -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://blog.joshatticus.site/">
  <meta property="og:title" content="JoshAtticus Blog">
  <meta property="og:description" content="Personal blog of JoshAtticus featuring tech, programming, and more.">
  <meta property="og:image" content="https://blog.joshatticus.site/assets/default-banner.jpg">
  
  <!-- Twitter Meta Tags -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="JoshAtticus Blog">
  <meta name="twitter:description" content="Personal blog of JoshAtticus featuring tech, programming, and more.">
  <meta name="twitter:image" content="https://blog.joshatticus.site/assets/default-banner.jpg">
  
  <script defer data-domain="blog.joshatticus.site" src="https://plausible.joshatticus.site/js/script.file-downloads.outbound-links.js"></script>
</head>
<body>
  <div class="reading-progress-container">
    <div class="reading-progress" id="reading-progress"></div>
  </div>
  
  <header>
    <h1><a href="index.html">JoshAtticus Blog</a></h1>

    <nav class="nav">
      <a href="tags.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 2v6h6V2H3zm2 2h2v2H5V4zm8-2v6h6V2h-6zm2 2h2v2h-2V4zM3 12v6h6v-6H3zm2 2h2v2H5v-2zm13-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1h-4zm0 2h4v2h-4v-2z"/></svg>
        Tags
      </a>
      <a href="search.html">
        <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm-8 6a8 8 0 1 1 14.32 4.906l5.387 5.387a1 1 0 0 1-1.414 1.414l-5.387-5.387A8 8 0 0 1 2 10z"/></svg>
        Search
      </a>
    </nav>
  </header>
  
  <main>
    <div class="post-grid">
"""

    for post in posts:
        # Generate tags HTML
        tags_html = ''
        if post.get('tags'):
            tags_html = '<div class="tags">'
            for tag in post.get('tags'):
                tag_slug = tag.lower().replace(' ', '-')
                tags_html += f'<a href="tags/{tag_slug}.html" class="tag">{tag}</a>'
            tags_html += '</div>'
        
        # Generate image HTML (fallback to default if no image)
        image_path = post.get('image') or 'assets/default-banner.jpg'

        index_html += f"""
      <article>
        <div class="post-card">
          <div class="card-image">
            <img src="{image_path}" alt="{post['title']} featured image">
            <div class="card-title-overlay">
              <h2><a href="posts/{post['filename']}">{post['title']}</a></h2>
              <div class="date">{post['date']}</div>
            </div>
          </div>
          <div class="card-content">
            <div class="card-summary">
              {post['summary']}
            </div>
            {tags_html}
          </div>
        </div>
      </article>
    """

    index_html += """
    </div>
  </main>
  <footer>© """ + str(datetime.now().year) + """ JoshAtticus</footer>
  
  <script>
    // Reading progress tracker
    window.addEventListener('scroll', () => {
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = (scrollTop / scrollHeight) * 100;
      document.getElementById('reading-progress').style.width = scrolled + '%';
    });
  </script>
</body>
</html>"""

    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"✅ Blog generated with {len(posts)} posts, {len(tags_index)} tags, and search functionality")
