const postSlug = window.location.pathname.split('/').pop();
let replyParentId = null;

async function loadComments() {
  try {
    const response = await fetch(`/api/comments/${postSlug}`);
    const data = await response.json();
    displayComments(data.comments);
  } catch (error) {
    console.error('Error loading comments:', error);
  }
}

function displayComments(comments) {
  const container = document.getElementById('comments-list');
  if (!container) return;
  
  container.textContent = '';

  if (comments.length === 0) {
    const noComments = document.createElement('p');
    noComments.className = 'no-comments';
    noComments.textContent = 'No comments yet. Be the first to comment!';
    container.appendChild(noComments);
    return;
  }

  const topLevel = comments.filter(c => !c.parent_id);

  topLevel.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  const byParent = {};
  comments.forEach(c => {
    if (c.parent_id) {
      if (!byParent[c.parent_id]) byParent[c.parent_id] = [];
      byParent[c.parent_id].push(c);
    }
  });

  for (const parentId in byParent) {
    byParent[parentId].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  }

  topLevel.forEach(comment => {
    container.appendChild(renderComment(comment, byParent));
  });
}

function replyTo(commentId, authorName) {
  replyParentId = commentId;
  document.getElementById('reply-indicator').style.display = 'block';
  document.getElementById('reply-to-name').textContent = authorName;
  document.getElementById('comment-text').focus();
  document.getElementById('comment-text').placeholder = `Replying to ${authorName}...`;
  document.getElementById('submit-comment').textContent = 'Post Reply';
  document.getElementById('comment-form').scrollIntoView({ behavior: 'smooth' });
}

const cancelReplyBtn = document.getElementById('cancel-reply');
if (cancelReplyBtn) {
    cancelReplyBtn.addEventListener('click', () => {
      replyParentId = null;
      document.getElementById('reply-indicator').style.display = 'none';
      document.getElementById('comment-text').placeholder = 'Leave a comment...';
      document.getElementById('submit-comment').textContent = 'Post Comment';
    });
}

function startEdit(comment, bodyEl) {
  const originalText = comment.comment_text;
  bodyEl.innerHTML = '';

  const textarea = document.createElement('textarea');
  textarea.className = 'edit-textarea';
  textarea.value = originalText;
  textarea.style.width = '100%';
  textarea.style.minHeight = '80px';
  textarea.style.marginTop = '0.5rem';
  textarea.style.padding = '0.5rem';
  textarea.style.background = '#121212';
  textarea.style.color = '#e0e0e0';
  textarea.style.border = '1px solid #444';
  textarea.style.borderRadius = '4px';

  const btnGroup = document.createElement('div');
  btnGroup.style.marginTop = '0.5rem';
  btnGroup.style.display = 'flex';
  btnGroup.style.gap = '0.5rem';

  const saveBtn = document.createElement('button');
  saveBtn.textContent = 'Save';
  saveBtn.className = 'submit-comment-btn';
  saveBtn.style.padding = '0.3rem 0.8rem';
  saveBtn.style.fontSize = '0.85rem';

  saveBtn.onclick = async () => {
    const newText = textarea.value.trim();
    if (!newText) return;

    try {
      const res = await fetch(`/api/comments/${comment.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment_text: newText })
      });
      if (res.ok) {
        loadComments();
      } else {
        alert('Failed to update comment');
      }
    } catch (e) {
      console.error(e);
    }
  };

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.style.background = 'none';
  cancelBtn.style.border = 'none';
  cancelBtn.style.color = '#888';
  cancelBtn.style.cursor = 'pointer';
  cancelBtn.onclick = () => loadComments();

  btnGroup.appendChild(saveBtn);
  btnGroup.appendChild(cancelBtn);

  bodyEl.appendChild(textarea);
  bodyEl.appendChild(btnGroup);
  textarea.focus();
}

async function deleteComment(id) {
  if (!confirm('Are you sure you want to delete this comment?')) return;
  try {
    const res = await fetch(`/api/comments/${id}`, { method: 'DELETE' });
    if (res.ok) {
      loadComments();
    } else {
      alert('Failed to delete comment');
    }
  } catch (e) {
    console.error(e);
  }
}

function renderComment(comment, byParent, depth = 0) {
  const commentDiv = document.createElement('div');
  commentDiv.className = 'comment';
  commentDiv.dataset.commentId = comment.id;

  const avatar = document.createElement('img');
  avatar.className = 'comment-avatar';
  avatar.src = comment.author_avatar_url || comment.picture || '/assets/default-avatar.png';
  avatar.alt = comment.author_name;

  const contentDiv = document.createElement('div');
  contentDiv.className = 'comment-content';

  const header = document.createElement('div');
  header.className = 'comment-header';

  const author = document.createElement('strong');
  author.className = 'comment-author';
  author.textContent = comment.author_name;

  const date = document.createElement('span');
  date.className = 'comment-date';
  const dateObj = new Date(comment.created_at);
  date.textContent = dateObj.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });

  header.appendChild(author);
  header.appendChild(date);

  if (comment.source === 'wasteof') {
    const badge = document.createElement('a');
    badge.textContent = 'From wasteof.money';
    badge.href = window.wasteofLink || 'https://wasteof.money';
    badge.target = '_blank';
    badge.className = 'wasteof-badge';
    badge.setAttribute('data-tooltip', 'This comment has been bridged from a third party platform not controlled by JoshAtticus. Replies posted on this blog cannot be seen by users on the third party platform.');
    
    // Handle click for modal
    badge.addEventListener('click', (e) => {
      const isMobile = window.matchMedia('(hover: none)').matches;
      
      if (isMobile) {
        e.preventDefault();
        if (window.uiModal) {
            window.uiModal.show({
                title: 'External Link',
                body: 'This comment has been bridged from a third party platform, wasteof.money.',
                buttons: [
                    {
                        text: 'View on wasteof.money',
                        primary: true,
                        link: badge.href
                    },
                    {
                        text: 'Close',
                        primary: false
                    }
                ]
            });
        } else {
            // Fallback if modal script failed to load
            if (confirm('This comment has been bridged from a third party platform, wasteof.money. Continue to site?')) {
                window.open(badge.href, '_blank');
            }
        }
      }
    });

    header.appendChild(badge);
  }

  if (comment.edited_at) {
    const editedSpan = document.createElement('span');
    editedSpan.className = 'comment-edited';
    editedSpan.textContent = '(Edited)';
    editedSpan.title = new Date(comment.edited_at).toLocaleString();
    header.appendChild(editedSpan);
  }

  const body = document.createElement('div');
  body.className = 'comment-body';

  const cleanText = comment.comment_text.replace(/\n/g, ' ').trim();
  const shouldTruncate = cleanText.length > 300;

  if (shouldTruncate) {
    const truncated = cleanText.substring(0, 300);
    body.textContent = truncated + '... ';

    const seeMore = document.createElement('button');
    seeMore.className = 'see-more-btn';
    seeMore.textContent = 'See more';
    seeMore.onclick = function () {
      body.textContent = cleanText;
    };
    body.appendChild(seeMore);
  } else {
    body.textContent = cleanText;
  }

  const actions = document.createElement('div');
  actions.className = 'comment-actions';

  const replyBtn = document.createElement('button');
  replyBtn.className = 'reply-btn';
  replyBtn.textContent = 'Reply';
  replyBtn.onclick = () => replyTo(comment.id, comment.author_name);

  actions.appendChild(replyBtn);

  if (currentUser && (String(currentUser.id) === String(comment.user_id) || currentUser.is_admin) && !comment.is_deleted) {
    const editBtn = document.createElement('button');
    editBtn.className = 'reply-btn';
    editBtn.textContent = 'Edit';
    editBtn.onclick = () => startEdit(comment, body);
    actions.appendChild(editBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'reply-btn delete-action-btn';
    deleteBtn.textContent = 'Delete';
    deleteBtn.onclick = () => deleteComment(comment.id);
    actions.appendChild(deleteBtn);
  }

  contentDiv.appendChild(header);
  contentDiv.appendChild(body);
  contentDiv.appendChild(actions);

  commentDiv.appendChild(avatar);
  commentDiv.appendChild(contentDiv);

  if (byParent[comment.id]) {
    const repliesDiv = document.createElement('div');
    repliesDiv.className = 'comment-replies';

    if (depth < 1) {
      byParent[comment.id].forEach(reply => {
        repliesDiv.appendChild(renderComment(reply, byParent, depth + 1));
      });
    } else {
      const replyCount = byParent[comment.id].length;
      const showRepliesBtn = document.createElement('button');
      showRepliesBtn.className = 'show-replies-btn';
      showRepliesBtn.textContent = `Show ${replyCount} repl${replyCount === 1 ? 'y' : 'ies'}`;
      showRepliesBtn.onclick = function () {
        showRepliesBtn.remove();
        byParent[comment.id].forEach(reply => {
          repliesDiv.appendChild(renderComment(reply, byParent, depth + 1));
        });
      };
      repliesDiv.appendChild(showRepliesBtn);
    }
    contentDiv.appendChild(repliesDiv);
  }

  return commentDiv;
}

const submitCommentBtn = document.getElementById('submit-comment');
if (submitCommentBtn) {
    submitCommentBtn.addEventListener('click', async () => {
      const commentText = document.getElementById('comment-text').value.trim();
      const statusEl = document.getElementById('comment-status');
      const submitBtn = document.getElementById('submit-comment');
      const charCount = document.getElementById('char-count');

      if (!commentText) {
        statusEl.textContent = 'Please enter a comment.';
        statusEl.className = 'error';
        return;
      }

      if (commentText.length > 1500) {
        statusEl.textContent = 'Comment must be 1500 characters or less.';
        statusEl.className = 'error';
        return;
      }

      submitBtn.disabled = true;
      statusEl.textContent = 'Posting...';
      statusEl.className = '';

      try {
        const response = await fetch(`/api/comments/${postSlug}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            comment_text: commentText,
            parent_id: replyParentId
          })
        });

        const data = await response.json();

        if (response.ok) {
          statusEl.textContent = 'Comment posted successfully!';
          statusEl.className = 'success';
          document.getElementById('comment-text').value = '';
          charCount.textContent = '0 / 1500';

          replyParentId = null;
          document.getElementById('reply-indicator').style.display = 'none';
          document.getElementById('comment-text').placeholder = 'Leave a comment...';
          document.getElementById('submit-comment').textContent = 'Post Comment';

          setTimeout(() => {
            statusEl.textContent = '';
            loadComments();
          }, 2000);
        } else {
          statusEl.textContent = data.error || 'Failed to post comment.';
          statusEl.className = 'error';
        }
      } catch (error) {
        statusEl.textContent = 'Error posting comment. Please try again.';
        statusEl.className = 'error';
      } finally {
        submitBtn.disabled = false;
      }
    });
}

const commentTextInput = document.getElementById('comment-text');
if (commentTextInput) {
    commentTextInput.addEventListener('input', (e) => {
      const count = e.target.value.length;
      document.getElementById('char-count').textContent = `${count} / 1500`;
    });
}

function initImageEnhancements() {
  const content = document.querySelector('.content');
  if (!content) return;

  Array.from(content.querySelectorAll('img')).forEach(img => {
    if (img.closest('figure')) return;
    if (img.closest('.comparison-container')) return;
    const alt = img.getAttribute('alt');
    const figure = document.createElement('figure');
    img.parentNode.insertBefore(figure, img);
    figure.appendChild(img);
    if (alt && alt.trim()) {
      const cap = document.createElement('figcaption');
      cap.textContent = alt.trim();
      figure.appendChild(cap);
    }
  });

  content.querySelectorAll('p').forEach(p => {
    const imgs = Array.from(p.querySelectorAll(':scope > figure > img'));
    if (imgs.length >= 2) {
      const grid = document.createElement('div');
      grid.className = 'image-grid';
      imgs.forEach(img => grid.appendChild(img.closest('figure')));
      p.replaceWith(grid);
    }
  });

  const paragraphs = Array.from(content.querySelectorAll('p'));
  let buffer = [];
  function flushRow() {
    if (buffer.length >= 2) {
      const row = document.createElement('div');
      row.className = 'image-row';
      buffer.forEach(p => {
        const fig = p.querySelector('figure');
        if (fig) row.appendChild(fig);
        p.remove();
      });
      const ref = buffer[0];
      ref.parentNode.insertBefore(row, ref);
    }
    buffer = [];
  }
  paragraphs.forEach(p => {
    const figs = p.querySelectorAll(':scope > figure');
    if (figs.length === 1 && !p.textContent.trim()) {
      buffer.push(p);
    } else {
      flushRow();
    }
  });
  flushRow();

  function classify(img) {
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    if (!w || !h) return; // not loaded yet
    const ratio = w / h;
    img.classList.add('screenshot-frame');
    if (ratio < 0.75) img.classList.add('portrait');
    if (ratio < 0.5) img.classList.add('ultra-tall');
    if (ratio > 2.2) img.classList.add('landscape-wide');
  }
  const allImgs = Array.from(content.querySelectorAll('figure > img'));
  allImgs.forEach(img => {
    if (img.complete) {
      classify(img);
    } else {
      img.addEventListener('load', () => classify(img));
    }
  });

  const lightbox = document.getElementById('lightbox');
  if (!lightbox) return;
  
  const lbImg = lightbox.querySelector('.lightbox-image');
  const lbCaption = lightbox.querySelector('.lightbox-caption');
  const btnClose = lightbox.querySelector('.lightbox-close');
  const btnPrev = lightbox.querySelector('.lightbox-prev');
  const btnNext = lightbox.querySelector('.lightbox-next');

  let gallery = [];
  let index = 0;

  function openLightbox(images, startIndex) {
    gallery = images;
    index = startIndex;
    updateLightbox();
    lightbox.classList.add('open');
    document.body.classList.add('no-scroll');
    lightbox.setAttribute('aria-hidden', 'false');
  }

  function closeLightbox() {
    lightbox.classList.remove('open');
    document.body.classList.remove('no-scroll');
    lightbox.setAttribute('aria-hidden', 'true');
  }

  function updateLightbox() {
    const img = gallery[index];
    if (!img) return;
    const fullResSrc = img.dataset.fullResSrc || img.getAttribute('src');
    const originalSrc = fullResSrc.split('?')[0] + '?size=full';
    lbImg.src = originalSrc;
    lbImg.alt = img.getAttribute('alt') || '';
    lbCaption.textContent = img.getAttribute('alt') || '';
    btnPrev.disabled = index <= 0;
    btnNext.disabled = index >= gallery.length - 1;
  }

  function showNext() {
    if (index < gallery.length - 1) {
      index++;
      updateLightbox();
    }
  }

  function showPrev() {
    if (index > 0) {
      index--;
      updateLightbox();
    }
  }

  content.querySelectorAll('.image-grid').forEach(grid => {
    const imgs = Array.from(grid.querySelectorAll('img'));
    imgs.forEach((img, i) => {
      img.style.cursor = 'zoom-in';
      img.addEventListener('click', () => openLightbox(imgs, i));
    });
  });
  const standaloneImgs = Array.from(content.querySelectorAll('figure > img')).filter(img => !img.closest('.image-grid') && !img.closest('.image-row'));
  standaloneImgs.forEach(img => {
    img.style.cursor = 'zoom-in';
    img.addEventListener('click', () => openLightbox([img], 0));
  });

  content.querySelectorAll('.image-row').forEach(row => {
    const imgs = Array.from(row.querySelectorAll('img'));
    imgs.forEach((img, i) => {
      img.style.cursor = 'zoom-in';
      img.addEventListener('click', () => openLightbox(imgs, i));
    });
  });

  btnClose.addEventListener('click', closeLightbox);
  btnNext.addEventListener('click', showNext);
  btnPrev.addEventListener('click', showPrev);
  lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) closeLightbox();
  });

  document.addEventListener('keydown', (e) => {
    if (!lightbox.classList.contains('open')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowRight') showNext();
    if (e.key === 'ArrowLeft') showPrev();
  });
}

function initComparisons() {
  const containers = document.querySelectorAll('.comparison-container');
  containers.forEach(container => {
    const wrapper = container.querySelector('.comparison-inner') || container;
    const slider = container.querySelector('.comparison-slider');
    const imageOver = container.querySelector('.comparison-image-over');
    
    if (!slider || !imageOver) return;
    
    let active = false;
    
    slider.addEventListener('mousedown', slideReady);
    window.addEventListener('mouseup', slideFinish);
    slider.addEventListener('touchstart', slideReady);
    window.addEventListener('touchend', slideFinish);
    
    function slideReady(e) {
      e.preventDefault();
      active = true;
      window.addEventListener('mousemove', slideMove);
      window.addEventListener('touchmove', slideMove);
    }
    
    function slideFinish() {
      active = false;
      window.removeEventListener('mousemove', slideMove);
      window.removeEventListener('touchmove', slideMove);
    }
    
    function slideMove(e) {
      if (!active) return;
      
      let pos = getCursorPos(e);
      
      if (pos < 0) pos = 0;
      if (pos > wrapper.offsetWidth) pos = wrapper.offsetWidth;
      
      slide(pos);
    }
    
    function getCursorPos(e) {
      const rect = wrapper.getBoundingClientRect();
      const x = (e.changedTouches ? e.changedTouches[0].pageX : e.pageX) - rect.left - window.pageXOffset;
      return x;
    }
    
    function slide(x) {
      imageOver.style.clipPath = `inset(0 ${wrapper.offsetWidth - x}px 0 0)`;
      slider.style.left = x + 'px';
    }
  });

  // Video Comparison Logic
  containers.forEach(container => {
    const videos = Array.from(container.querySelectorAll('video'));
    if (videos.length > 0) {
        const playBtn = container.querySelector('.comp-play-btn');
        const progressBar = container.querySelector('.comp-progress-bar');
        const progressContainer = container.querySelector('.comp-progress-container');
        
        let masterVideo = videos[0];
        
        const setMaster = () => {
             // Find shortest duration
             masterVideo = videos.reduce((prev, curr) => prev.duration < curr.duration ? prev : curr);
        };
        
        // Wait for metadata
        let loaded = 0;
        videos.forEach(v => {
            if (v.readyState >= 1) {
                loaded++;
                if (loaded === videos.length) setMaster();
            } else {
                v.addEventListener('loadedmetadata', () => {
                    loaded++;
                    if (loaded === videos.length) setMaster();
                });
            }
        });
        
        // Sync loop
        const syncLoop = () => {
            if (!masterVideo.duration) return;
            
            // Update progress
            const percent = (masterVideo.currentTime / masterVideo.duration) * 100;
            if (progressBar) progressBar.style.width = `${percent}%`;
            
            // Check for end
            if (masterVideo.ended || masterVideo.currentTime >= masterVideo.duration) {
                videos.forEach(v => {
                    v.currentTime = 0;
                    v.play().catch(() => {});
                });
            }
            
            if (!videos[0].paused) {
                requestAnimationFrame(syncLoop);
            }
        };

        if (playBtn) {
            playBtn.addEventListener('click', () => {
                const isPaused = videos[0].paused;
                if (isPaused) {
                    videos.forEach(v => v.play());
                    playBtn.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
                    syncLoop();
                } else {
                    videos.forEach(v => v.pause());
                    playBtn.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
                }
            });
        }
        
        // Seek
        if (progressContainer) {
            progressContainer.addEventListener('click', (e) => {
                const rect = progressContainer.getBoundingClientRect();
                const pos = (e.clientX - rect.left) / rect.width;
                if (masterVideo.duration) {
                    const targetTime = pos * masterVideo.duration;
                    videos.forEach(v => {
                        v.currentTime = targetTime;
                    });
                    if (progressBar) progressBar.style.width = `${pos * 100}%`;
                }
            });
        }
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
    loadComments();
    initImageEnhancements();
    initComparisons();
    document.addEventListener('auth-status-changed', () => {
        loadComments();
    });
});
