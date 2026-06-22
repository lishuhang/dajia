/* dajia archive - client-side title-only search
   Fetches /dajia/search.json (built by Jekyll from search.md)
   No external libs.
*/
(function() {
  'use strict';
  var input = document.getElementById('title-search');
  var results = document.getElementById('search-results');
  if (!input || !results) return;

  var POSTS = null;
  var idx = null;
  var baseurl = '';

  // Detect baseurl from a known asset path
  var scripts = document.getElementsByTagName('script');
  for (var i = 0; i < scripts.length; i++) {
    var src = scripts[i].src || '';
    var m = src.match(/^(.*)\/assets\/search\.js$/);
    if (m) { baseurl = m[1]; break; }
  }

  function ensureLoaded(cb) {
    if (POSTS !== null) { cb(); return; }
    fetch(baseurl + '/search.json').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(data) {
      POSTS = data || [];
      idx = POSTS.map(function(p, i) {
        return {
          i: i,
          title_lc: (p.title || '').toLowerCase(),
          author_lc: (p.author || '').toLowerCase(),
        };
      });
      cb();
    }).catch(function(e) {
      console.warn('search.json load failed:', e);
    });
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, function(c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

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

  var debounceTimer = null;
  input.addEventListener('input', function() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function() {
      ensureLoaded(function() { search(input.value); });
    }, 200);
  });
  input.addEventListener('focus', function() {
    if (input.value.trim()) {
      ensureLoaded(function() { search(input.value); });
    }
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
