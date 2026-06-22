/* dajia archive - client-side title-only search
   Posts data is embedded in the page (window.DAJIA_POSTS).
   No external libs, no network requests.
*/
(function() {
  'use strict';
  var POSTS = window.DAJIA_POSTS || [];
  var input = document.getElementById('title-search');
  var results = document.getElementById('search-results');
  if (!input || !results) return;

  // Pre-build lowercase title index for fast substring search
  var idx = POSTS.map(function(p, i) {
    return {
      i: i,
      title_lc: (p.title || '').toLowerCase(),
      author_lc: (p.author || '').toLowerCase(),
    };
  });

  var debounceTimer = null;

  function search(q) {
    q = (q || '').trim().toLowerCase();
    if (!q) {
      results.classList.remove('visible');
      results.innerHTML = '';
      return;
    }
    var matches = [];
    for (var j = 0; j < idx.length; j++) {
      var e = idx[j];
      if (e.title_lc.indexOf(q) !== -1 || e.author_lc.indexOf(q) !== -1) {
        matches.push(POSTS[e.i]);
        if (matches.length >= 50) break;
      }
    }
    if (matches.length === 0) {
      results.innerHTML = '<div class="no-results">未找到含 "' + escapeHtml(q) + '" 的标题</div>';
    } else {
      results.innerHTML = matches.map(function(p) {
        return '<a class="result-item" href="' + p.url + '">' +
          '<div class="result-title">' + escapeHtml(p.title) + '</div>' +
          '<div class="result-meta">' + escapeHtml(p.date) + ' · ' + escapeHtml(p.author) + '</div>' +
          '</a>';
      }).join('') +
      (matches.length >= 50 ? '<div class="no-results">仅显示前 50 条结果</div>' : '');
    }
    results.classList.add('visible');
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, function(c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  input.addEventListener('input', function() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function() { search(input.value); }, 200);
  });
  input.addEventListener('focus', function() {
    if (input.value.trim()) search(input.value);
  });
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      input.value = '';
      results.classList.remove('visible');
      input.blur();
    } else if (e.key === 'Enter') {
      var firstLink = results.querySelector('a.result-item');
      if (firstLink) window.location.href = firstLink.href;
    }
  });
  document.addEventListener('click', function(e) {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.remove('visible');
    }
  });
})();
