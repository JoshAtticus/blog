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
