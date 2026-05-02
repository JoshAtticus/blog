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
            <img src="${data.user.picture || '/assets/default-avatar.png'}" alt="${data.user.name}" style="width: 20px; height: 20px; border-radius: 50%; margin-right: 5px;">
            ${data.user.name}
         `;
        accountBtn.href = "/logout";
        accountBtn.title = "Sign Out";
      }

      if (commentForm) commentForm.style.display = 'block';
      if (signinBanner) signinBanner.style.display = 'none';

      if (userInfo) {
        userInfo.innerHTML = `
          <img src="${data.user.picture || '/assets/default-avatar.png'}" alt="${data.user.name}" style="width: 24px; height: 24px; border-radius: 50%;">
          <span>${data.user.name}</span>
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
