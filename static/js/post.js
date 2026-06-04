const postSlug = window.location.pathname.split('/').pop();
let replyParentId = null;
let activeMenuComment = null;
let commentMenuBackdrop = null;
const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

const submitButtonIcons = {
  send: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3.4 20.4l17.45-7.48c.73-.31.73-1.35 0-1.66L3.4 3.78c-.67-.29-1.36.38-1.12 1.08l1.87 5.43a1 1 0 0 0 .95.68h8.16a.75.75 0 0 1 0 1.5H5.1a1 1 0 0 0-.95.68l-1.87 5.43c-.24.7.45 1.37 1.12 1.08z"/></svg>',
  loading: '<span class="loading-dots" aria-hidden="true"><span></span><span></span><span></span></span>',
  success: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9.55 18.2L3.75 12.4l2.12-2.12 3.68 3.68 8.58-8.58 2.12 2.12z"/></svg>',
  error: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M11 7h2v8h-2zm0 10h2v2h-2z"/></svg>'
};
let submitFeedbackTimeout = null;

function isMobileMenuViewport() {
  return window.matchMedia('(max-width: 600px)').matches;
}

function ensureCommentMenuBackdrop() {
  if (commentMenuBackdrop) return;
  commentMenuBackdrop = document.createElement('div');
  commentMenuBackdrop.className = 'comment-menu-backdrop';
  commentMenuBackdrop.addEventListener('click', () => closeAllCommentMenus());
  document.body.appendChild(commentMenuBackdrop);
}

function activateCommentMenuContext(commentEl) {
  if (!isMobileMenuViewport()) return;
  ensureCommentMenuBackdrop();
  if (activeMenuComment) activeMenuComment.classList.remove('menu-active');
  activeMenuComment = commentEl;
  activeMenuComment.classList.add('menu-active');
  document.body.classList.add('comment-menu-open');
  commentMenuBackdrop.classList.add('open');
}

function clearCommentMenuContext() {
  if (activeMenuComment) {
    activeMenuComment.classList.remove('menu-active');
    activeMenuComment = null;
  }
  document.body.classList.remove('comment-menu-open');
  if (commentMenuBackdrop) {
    commentMenuBackdrop.classList.remove('open');
  }
}

function setSubmitButtonState(isReply) {
  const submitBtn = document.getElementById('submit-comment');
  if (!submitBtn) return;
  const label = isReply ? 'Post reply' : 'Post comment';
  submitBtn.setAttribute('aria-label', label);
  submitBtn.setAttribute('title', label);
}

function formatCommentTimestamp(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: localTimeZone
  });
}

function setSubmitButtonVisualState(state) {
  const submitBtn = document.getElementById('submit-comment');
  if (!submitBtn) return;

  submitBtn.classList.remove('is-loading', 'is-success', 'is-error');

  if (state === 'loading') {
    submitBtn.classList.add('is-loading');
    submitBtn.innerHTML = submitButtonIcons.loading;
    submitBtn.setAttribute('aria-label', 'Posting comment');
    submitBtn.setAttribute('title', 'Posting comment');
    return;
  }

  if (state === 'success') {
    submitBtn.classList.add('is-success');
    submitBtn.innerHTML = submitButtonIcons.success;
    submitBtn.setAttribute('aria-label', 'Comment posted');
    submitBtn.setAttribute('title', 'Comment posted');
    return;
  }

  if (state === 'error') {
    submitBtn.classList.add('is-error');
    submitBtn.innerHTML = submitButtonIcons.error;
    submitBtn.setAttribute('aria-label', 'Comment failed');
    submitBtn.setAttribute('title', 'Comment failed');
    return;
  }

  submitBtn.innerHTML = submitButtonIcons.send;
  setSubmitButtonState(replyParentId !== null);
}

function showTransientSubmitFeedback(state, durationMs = 1000) {
  if (submitFeedbackTimeout) {
    clearTimeout(submitFeedbackTimeout);
    submitFeedbackTimeout = null;
  }

  setSubmitButtonVisualState(state);

  return new Promise(resolve => {
    submitFeedbackTimeout = setTimeout(() => {
      setSubmitButtonVisualState('idle');
      submitFeedbackTimeout = null;
      resolve();
    }, durationMs);
  });
}

function closeAllCommentMenus(exceptMenu = null) {
  document.querySelectorAll('.comment-menu.open').forEach(menu => {
    if (menu !== exceptMenu) {
      menu.classList.remove('open');
      const trigger = menu.previousElementSibling;
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    }
  });
  if (!exceptMenu) {
    clearCommentMenuContext();
  }
}

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
  setSubmitButtonState(true);
  document.getElementById('comment-form').scrollIntoView({ behavior: 'smooth' });
}

const cancelReplyBtn = document.getElementById('cancel-reply');
if (cancelReplyBtn) {
    cancelReplyBtn.addEventListener('click', () => {
      replyParentId = null;
      document.getElementById('reply-indicator').style.display = 'none';
      document.getElementById('comment-text').placeholder = 'Leave a comment...';
      setSubmitButtonState(false);
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
  saveBtn.style.width = 'auto';
  saveBtn.style.height = 'auto';
  saveBtn.style.minWidth = '0';
  saveBtn.style.borderRadius = '6px';

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
  date.textContent = formatCommentTimestamp(comment.created_at);

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
    editedSpan.title = formatCommentTimestamp(comment.edited_at);
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

  if (currentUser) {
    const menuTrigger = document.createElement('button');
    menuTrigger.className = 'comment-menu-trigger';
    menuTrigger.type = 'button';
    menuTrigger.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="5" cy="12" r="1.8"></circle><circle cx="12" cy="12" r="1.8"></circle><circle cx="19" cy="12" r="1.8"></circle></svg>';
    menuTrigger.setAttribute('aria-label', 'Comment actions');
    menuTrigger.setAttribute('aria-haspopup', 'true');
    menuTrigger.setAttribute('aria-expanded', 'false');

    const menu = document.createElement('div');
    menu.className = 'comment-menu';

    const replyItem = document.createElement('button');
    replyItem.className = 'comment-menu-item';
    replyItem.type = 'button';
    replyItem.textContent = 'Reply';
    replyItem.onclick = () => {
      replyTo(comment.id, comment.author_name);
      closeAllCommentMenus();
    };
    menu.appendChild(replyItem);

    if ((String(currentUser.id) === String(comment.user_id) || currentUser.is_admin) && !comment.is_deleted) {
      const editItem = document.createElement('button');
      editItem.className = 'comment-menu-item';
      editItem.type = 'button';
      editItem.textContent = 'Edit';
      editItem.onclick = () => {
        startEdit(comment, body);
        closeAllCommentMenus();
      };
      menu.appendChild(editItem);

      const deleteItem = document.createElement('button');
      deleteItem.className = 'comment-menu-item delete';
      deleteItem.type = 'button';
      deleteItem.textContent = 'Delete';
      deleteItem.onclick = () => {
        deleteComment(comment.id);
        closeAllCommentMenus();
      };
      menu.appendChild(deleteItem);
    }

    menuTrigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = menu.classList.contains('open');
      closeAllCommentMenus();
      if (!isOpen) {
        menu.classList.add('open');
        menuTrigger.setAttribute('aria-expanded', 'true');
        activateCommentMenuContext(commentDiv);
      } else {
        menuTrigger.setAttribute('aria-expanded', 'false');
        clearCommentMenuContext();
      }
    });

    menu.addEventListener('click', (e) => e.stopPropagation());

    actions.appendChild(menuTrigger);
    actions.appendChild(menu);
  }

  contentDiv.appendChild(header);
  contentDiv.appendChild(body);
  if (currentUser) {
    contentDiv.appendChild(actions);
  }

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
      const submitBtn = document.getElementById('submit-comment');
      const charCount = document.getElementById('char-count');

      if (submitBtn.classList.contains('is-loading')) {
        return;
      }

      if (!commentText) {
        await showTransientSubmitFeedback('error', 1000);
        return;
      }

      if (commentText.length > 1500) {
        await showTransientSubmitFeedback('error', 1000);
        return;
      }

      setSubmitButtonVisualState('loading');

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
          document.getElementById('comment-text').value = '';
          charCount.textContent = '0 / 1500';

          const newComment = data.comment;
          replyParentId = null;
          document.getElementById('reply-indicator').style.display = 'none';
          document.getElementById('comment-text').placeholder = 'Leave a comment...';
          setSubmitButtonState(false);

          await showTransientSubmitFeedback('success', 1000);

          if (newComment) {
            const container = document.getElementById('comments-list');
            if (container) {
              if (newComment.parent_id) {
                loadComments();
              } else {
                const commentEl = renderComment(newComment, {});
                container.insertBefore(commentEl, container.firstChild);
              }
            }
          } else {
            loadComments();
          }
        } else {
          console.warn(data.error || 'Failed to post comment.');
          await showTransientSubmitFeedback('error', 1000);
        }
      } catch (error) {
        console.error('Error posting comment:', error);
        await showTransientSubmitFeedback('error', 1000);
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

    const thumbSrc = img.getAttribute('src');
    const fullResSrc = img.dataset.fullResSrc || thumbSrc;
    const originalSrc = fullResSrc.split('?')[0] + '?size=full';
    const altText = img.getAttribute('alt') || '';

    // If it's already showing the right image, do nothing
    if (lbImg.src.includes(originalSrc) || lbImg.src.includes(thumbSrc)) return;

    // Fade out first
    lbImg.style.opacity = '0';
    lbCaption.style.opacity = '0';

    setTimeout(() => {
      if (gallery[index] !== img) return;

      // Set thumbnail immediately after fade out
      lbImg.src = thumbSrc;
      lbImg.classList.add('lightbox-loading');
      lbImg.alt = altText;
      lbCaption.textContent = altText;

      // Fade back in with the thumbnail
      lbImg.style.opacity = '1';
      lbCaption.style.opacity = '1';

      // Load high res image
      const highResImg = new Image();
      highResImg.onload = () => {
        if (gallery[index] === img) {
          lbImg.src = originalSrc;
          lbImg.classList.remove('lightbox-loading');
        }
      };
      highResImg.src = originalSrc;
      
    }, 150);

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

  const lightboxImgs = Array.from(content.querySelectorAll('figure > img'));
  lightboxImgs.forEach((img, i) => {
    img.style.cursor = 'zoom-in';
    img.addEventListener('click', () => openLightbox(lightboxImgs, i));
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
  ensureCommentMenuBackdrop();
  document.addEventListener('click', () => closeAllCommentMenus());
  setSubmitButtonVisualState('idle');
  setSubmitButtonState(false);
    loadComments();
    initImageEnhancements();
    initComparisons();
    document.addEventListener('auth-status-changed', () => {
        loadComments();
    });
});
