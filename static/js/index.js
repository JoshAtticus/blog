document.addEventListener('DOMContentLoaded', () => {
  const images = document.querySelectorAll('.card-image img');

  images.forEach(img => {
    const originalSrc = img.getAttribute('src');

    if (!originalSrc || !originalSrc.includes('/assets/')) {
      return;
    }

    img.classList.add('progressive-image-loading');
    const baseUrl = originalSrc.split('?')[0];
    const placeholderUrl = baseUrl + '?size=placeholder';
    const thumbnailUrl = baseUrl + '?size=thumbnail';
    img.src = placeholderUrl;
    img.style.filter = 'blur(10px)';
    img.style.transition = 'filter 0.3s ease';

    const thumbnailImg = new Image();
    thumbnailImg.onload = function () {
      img.src = thumbnailUrl;
      img.style.filter = 'blur(0px)';
      img.classList.remove('progressive-image-loading');
      img.classList.add('progressive-image-loaded');
    };
    thumbnailImg.src = thumbnailUrl;
  });
});
