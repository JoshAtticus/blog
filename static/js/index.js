document.addEventListener('DOMContentLoaded', () => {
  const images = document.querySelectorAll('.card-image img');

  images.forEach((img, index) => {
    const originalSrc = img.getAttribute('src');

    if (!originalSrc || !originalSrc.includes('/assets/')) {
      return;
    }

    img.classList.add('progressive-image-loading');
    const baseUrl = originalSrc.split('?')[0];
    const placeholderUrl = baseUrl + '?size=placeholder';
    
    // The first card is the large featured post, so it deserves the full high-res image.
    // Other smaller cards are fine with the thumbnail resolution.
    const isFeatured = index === 0;
    const targetUrl = isFeatured ? (baseUrl + '?size=full') : (baseUrl + '?size=thumbnail');
    
    img.src = placeholderUrl;
    img.style.filter = 'blur(10px)';
    img.style.transition = 'filter 0.3s ease';

    if (isFeatured) {
      // For the featured post, load the thumbnail first so a clean image is visible quickly,
      // then swap in the full high-res image.
      const thumbnailUrl = baseUrl + '?size=thumbnail';
      const thumbnailImg = new Image();
      thumbnailImg.onload = function () {
        img.src = thumbnailUrl;
        img.style.filter = 'blur(0px)';
        
        const fullImg = new Image();
        fullImg.onload = function () {
          img.src = targetUrl;
          img.classList.remove('progressive-image-loading');
          img.classList.add('progressive-image-loaded');
        };
        fullImg.src = targetUrl;
      };
      thumbnailImg.src = thumbnailUrl;
    } else {
      const thumbnailImg = new Image();
      thumbnailImg.onload = function () {
        img.src = targetUrl;
        img.style.filter = 'blur(0px)';
        img.classList.remove('progressive-image-loading');
        img.classList.add('progressive-image-loaded');
      };
      thumbnailImg.src = targetUrl;
    }
  });
});
