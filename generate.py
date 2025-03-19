import os
import markdown
import shutil
import re
from datetime import datetime

# Setup directories
os.makedirs('public/posts', exist_ok=True)
if os.path.exists('style.css'):
    shutil.copy('style.css', 'public/')

# Post template
POST_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | JoshAtticus Blog</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header>
    <h1><a href="../index.html">JoshAtticus Blog</a></h1>
  </header>
  <main>
    <article>
      <h1>{title}</h1>
      <div class="date">{date}</div>
      <div class="content">
        {content}
      </div>
    </article>
  </main>
  <footer>© {year} </footer>
</body>
</html>'''

# Function to clean HTML for summaries
def clean_for_summary(html_content):
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', html_content)
    # Remove leading/trailing whitespace
    text = text.strip()
    return text

# Process all markdown posts
posts = []
for filename in os.listdir('posts'):
    if filename.endswith('.md'):
        with open(f'posts/{filename}', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse front matter
        title_match = re.search(r'title:\s*(.*)', content)
        date_match = re.search(r'date:\s*(.*)', content)
        
        title = title_match.group(1).strip() if title_match else "Untitled"
        date_str = date_match.group(1).strip() if date_match else datetime.now().strftime("%Y-%m-%d")
        
        # Remove front matter
        content = re.sub(r'---\n.*?\n---\n', '', content, flags=re.DOTALL)
        
        # Remove Markdown headers that might be at the start
        content_for_summary = re.sub(r'^#+ .*?\n', '', content, flags=re.MULTILINE)
        
        # Convert markdown to HTML
        html_content = markdown.markdown(content)
        
        # Clean text for summary (remove HTML tags)
        summary_text = clean_for_summary(markdown.markdown(content_for_summary))
        
        # Generate post HTML file
        post_html = POST_TEMPLATE.format(
            title=title,
            date=date_str,
            content=html_content,
            year=datetime.now().year
        )
        
        # Save HTML file
        post_filename = os.path.splitext(filename)[0] + '.html'
        with open(f'public/posts/{post_filename}', 'w', encoding='utf-8') as f:
            f.write(post_html)
        
        posts.append({
            'title': title,
            'date': date_str,
            'filename': post_filename,
            'summary': summary_text[:100] + '...' if len(summary_text) > 100 else summary_text
        })

# Sort posts by date (newest first)
posts.sort(key=lambda x: x['date'], reverse=True)

# Generate index page
index_html = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JoshAtticus Blog</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>JoshAtticus Blog</h1>
  </header>
  <main>
    <div class="post-list">
'''

for post in posts:
    index_html += f'''
      <article class="post-preview">
        <h2><a href="posts/{post['filename']}">{post['title']}</a></h2>
        <div class="date">{post['date']}</div>
        <div class="summary">{post['summary']}</div>
      </article>
    '''

index_html += '''
    </div>
  </main>
  <footer>© ''' + str(datetime.now().year) + ''' JoshAtticus Blog</footer>
</body>
</html>'''

with open('public/index.html', 'w', encoding='utf-8') as f:
    f.write(index_html)

print(f"✅ Blog generated with {len(posts)} posts")