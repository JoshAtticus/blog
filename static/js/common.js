window.addEventListener('scroll', () => {
  const progressBar = document.getElementById('reading-progress');
  if (progressBar) {
    const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
    const scrolled = (scrollTop / scrollHeight) * 100;
    progressBar.style.width = scrolled + '%';
  }
});

let currentUser = null;

// Escape untrusted strings before inserting into innerHTML templates
function escHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// Only allow remote https avatar URLs; anything else falls back to the local default
function safeAvatar(url) {
  return typeof url === 'string' && url.startsWith('https://') ? url : '/assets/default-avatar.png';
}

async function checkAuthStatus() {
  try {
    const response = await fetch('/api/auth/status');
    const data = await response.json();

    const accountBtn = document.getElementById('account-btn');
    const commentForm = document.getElementById('comment-form');
    const signinBanner = document.getElementById('signin-banner');
    const userInfo = document.getElementById('user-info');

    if (data.authenticated) {
      currentUser = data.user;
      
      if (accountBtn) {
        accountBtn.innerHTML = `
            <img src="${escHtml(safeAvatar(data.user.picture))}" alt="${escHtml(data.user.name)}" style="width: 20px; height: 20px; border-radius: 50%; margin-right: 5px;">
            ${escHtml(data.user.name)}
         `;
        // Logout is a POST action now; the click handler below intercepts this
        accountBtn.href = "#";
        accountBtn.dataset.authAction = "logout";
        accountBtn.title = "Sign Out";
      }

      if (commentForm) commentForm.style.display = 'block';
      if (signinBanner) signinBanner.style.display = 'none';

      if (userInfo) {
        userInfo.innerHTML = `
          <img src="${escHtml(safeAvatar(data.user.picture))}" alt="${escHtml(data.user.name)}" style="width: 24px; height: 24px; border-radius: 50%;">
          <span>${escHtml(data.user.name)}</span>
        `;
      }
      
      document.dispatchEvent(new CustomEvent('auth-status-changed', { detail: { authenticated: true, user: data.user } }));

    } else {
      currentUser = null;
      
      if (accountBtn) {
        accountBtn.innerHTML = `
            <svg class="nav-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
            </svg>
            Sign In
         `;
        accountBtn.href = "/login";
        accountBtn.dataset.authAction = "login";
      }

      if (commentForm) commentForm.style.display = 'none';
      if (signinBanner) signinBanner.style.display = 'block';
      
      document.dispatchEvent(new CustomEvent('auth-status-changed', { detail: { authenticated: false } }));
    }
  } catch (error) {
    console.error('Error checking auth status:', error);
  }
}

document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();

    // Logout via POST /logout (the GET route was removed to prevent CSRF logout)
    const accountBtn = document.getElementById('account-btn');
    if (accountBtn) {
      accountBtn.addEventListener('click', async (e) => {
        if (accountBtn.dataset.authAction !== 'logout') return; // fall through to /login href
        e.preventDefault();
        try {
          await fetch('/logout', { method: 'POST' });
        } catch (err) {
          console.error('Logout failed:', err);
        }
        window.location.href = '/';
      });
    }
});

// External Link Interceptor
document.addEventListener('click', (e) => {
  if (e.defaultPrevented) return;

  const link = e.target.closest('a');
  if (!link) return;

  // Ignore links inside the modal itself to prevent infinite loops
  if (link.closest('.modal-content')) return;

  // Ignore if target is not _blank (optional, but usually external links are _blank)
  // Actually, we want to catch all external links regardless of target
  
  const href = link.getAttribute('href');
  if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:')) return;

  let url;
  try {
    url = new URL(href, window.location.origin);
  } catch (err) {
    return;
  }

  if (url.hostname !== window.location.hostname) {
    e.preventDefault();
    
    if (window.uiModal) {
        window.uiModal.show({
            title: 'Leaving Site',
            body: `You are about to visit an external site:<br><br><strong style="color: #1a73e8; font-size: 1.1em;">${url.hostname}</strong><br><br>We are not responsible for the content of external sites.`,
            buttons: [
                {
                    text: 'Continue',
                    primary: true,
                    link: href
                },
                {
                    text: 'Cancel',
                    primary: false
                }
            ]
        });
    } else {
        if (confirm(`You are about to visit ${url.hostname}. Continue?`)) {
            window.open(href, '_blank');
        }
    }
  }
});

// Privacy Notice (Cookie Consent)
document.addEventListener('DOMContentLoaded', function() {
    const banner = document.getElementById('privacy-notice');
    const acceptBtn = document.getElementById('privacy-accept');
    
    if (!banner) return;

    if (!localStorage.getItem('privacyConsent')) {
        // Use server-side detection (Cloudflare Header) via injected global variable
        if (window.isPrivacyRegion) {
             banner.style.display = 'flex';
        }
    }
    
    if (acceptBtn) {
        acceptBtn.addEventListener('click', function() {
            localStorage.setItem('privacyConsent', 'true');
            banner.style.display = 'none';
        });
    }
});
