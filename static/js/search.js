(function () {
  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');
  const loadingIndicator = document.getElementById('loading-indicator');
  let debounceTimer;

  function updateUrl(query) {
    const url = new URL(window.location);
    if (query) {
      url.searchParams.set('q', query);
    } else {
      url.searchParams.delete('q');
    }
    history.pushState({}, '', url);
  }

  async function performSearch(query) {
    loadingIndicator.style.display = 'inline-block';

    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
      const data = await response.json();

      updateUrl(query);

      if (data.results.length === 0) {
        searchResults.innerHTML = `<p class="no-results">No results found for "${query}".</p>`;
        return;
      }

      let resultsHTML = '';

      data.results.forEach(post => {
        let tagsHTML = '';
        if (post.tags && post.tags.length > 0) {
          tagsHTML = '<div class="tags">';
          post.tags.forEach(tag => {
            const tagSlug = tag.toLowerCase().replace(/ /g, '-');
            tagsHTML += `<a href="/tags/${tagSlug}" class="tag">${tag}</a>`;
          });
          tagsHTML += '</div>';
        }

        resultsHTML += `
          <article class="post-preview">
            <h2><a href="/posts/${post.slug}">${post.title}</a></h2>
            <div class="date">${post.date}</div>
            <div class="post-content">
              <div class="summary">
                ${post.summary}
                ${tagsHTML}
              </div>
              <div class="post-image">
                <img src="/${post.image}" alt="${post.title} featured image">
              </div>
            </div>
          </article>
        `;
      });

      searchResults.innerHTML = resultsHTML;
    } catch (error) {
      console.error('Search error:', error);
      searchResults.innerHTML = '<p class="no-results">Error performing search. Please try again.</p>';
    } finally {
      loadingIndicator.style.display = 'none';
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      const query = this.value.trim();

      clearTimeout(debounceTimer);

      if (query.length === 0) {
        searchResults.innerHTML = '<p class="no-results">Enter a search term above.</p>';
        updateUrl('');
        return;
      }

      if (query.length < 2) {
        return;
      }

      debounceTimer = setTimeout(() => {
        performSearch(query);
      }, 500);
    });
  }

  window.addEventListener('popstate', () => {
    const url = new URL(window.location);
    const query = url.searchParams.get('q') || '';
    if (searchInput) {
      searchInput.value = query;
    }

    if (query) {
      performSearch(query);
    } else {
      if (searchResults) {
        searchResults.innerHTML = '<p class="no-results">Enter a search term above.</p>';
      }
    }
  });
})();
