/* dajia archive - frontend JS
   - Load search-index.json (built by build-search-index.py)
   - Year/Month filtering
   - Lunr.js full-text search (Chinese support via lunr.zh)
   - Pagination (50 posts per page)
*/

(function() {
  'use strict';

  const BASE = window.DAJIA_BASEURL || '';
  let ALL_POSTS = [];      // [{title, author, date, url, body}]
  let IDX = null;           // lunr index
  let INDEX_LOADED = false;
  let INDEX_LOADING = false;
  let INDEX_FAILED = false;

  // ===== state =====
  let selectedYear = null;
  let selectedMonth = null;
  let currentPage = 0;
  const PAGE_SIZE = 50;

  // ===== DOM helpers =====
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ===== Load search index (lazy) =====
  async function loadIndex() {
    if (INDEX_LOADED || INDEX_LOADING || INDEX_FAILED) return;
    INDEX_LOADING = true;
    try {
      const res = await fetch(BASE + '/search-index.json');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      ALL_POSTS = await res.json();
      // Build lunr index with Chinese support
      if (typeof lunr !== 'undefined') {
        IDX = lunr(function() {
          this.use(lunr.zh);
          this.ref('id');
          this.field('title', { boost: 10 });
          this.field('author', { boost: 5 });
          this.field('body');
          this.field('date');
          ALL_POSTS.forEach((p, i) => {
            this.add({
              id: i,
              title: p.title || '',
              author: p.author || '',
              body: (p.body || '').slice(0, 5000), // limit body length for index
              date: p.date || ''
            });
          });
        });
      }
      INDEX_LOADED = true;
      // If on home page, render the list
      renderArticleList();
      renderYearMonthFilters();
    } catch (e) {
      console.error('Failed to load search index:', e);
      INDEX_FAILED = true;
      const loadingEl = $('#article-list .loading');
      if (loadingEl) loadingEl.textContent = '加载失败，请刷新重试';
    } finally {
      INDEX_LOADING = false;
    }
  }

  // ===== Format helpers =====
  function pad2(n) { return String(n).padStart(2, '0'); }

  function getYearMonth(post) {
    const m = /^(\d{4})-(\d{2})-\d{2}/.exec(post.date || '');
    if (!m) return { year: null, month: null };
    return { year: m[1], month: m[2] };
  }

  // ===== Filtered posts =====
  function getFilteredPosts() {
    if (!selectedYear && !selectedMonth) return ALL_POSTS;
    return ALL_POSTS.filter(p => {
      const { year, month } = getYearMonth(p);
      if (selectedYear && year !== selectedYear) return false;
      if (selectedMonth && month !== selectedMonth) return false;
      return true;
    });
  }

  // ===== Render article list (home page) =====
  function renderArticleList() {
    const listEl = $('#article-list');
    if (!listEl) return;
    if (!INDEX_LOADED) {
      listEl.innerHTML = '<div class="loading">加载中…</div>';
      return;
    }
    const filtered = getFilteredPosts();
    currentPage = 0;
    const slice = filtered.slice(0, PAGE_SIZE);
    if (filtered.length === 0) {
      listEl.innerHTML = '<div class="loading">没有符合条件的文章</div>';
      $('#load-more').style.display = 'none';
      return;
    }
    listEl.innerHTML = slice.map(p => `
      <div class="post-list-item">
        <span class="post-date">${escapeHtml(p.date)}</span>
        <span class="post-author">${escapeHtml(p.author || '')}</span>
        <a class="post-link" href="${BASE + p.url}">${escapeHtml(p.title)}</a>
      </div>
    `).join('');
    const loadMore = $('#load-more');
    if (loadMore) {
      loadMore.style.display = filtered.length > PAGE_SIZE ? 'block' : 'none';
      loadMore.disabled = false;
      loadMore.textContent = `加载更多（剩余 ${filtered.length - PAGE_SIZE} 篇）`;
    }
    // Update post count
    const countEl = $('#post-count');
    if (countEl) countEl.textContent = ALL_POSTS.length;
  }

  function loadMore() {
    const filtered = getFilteredPosts();
    currentPage += 1;
    const start = currentPage * PAGE_SIZE;
    const slice = filtered.slice(start, start + PAGE_SIZE);
    const listEl = $('#article-list');
    if (listEl) {
      const html = slice.map(p => `
        <div class="post-list-item">
          <span class="post-date">${escapeHtml(p.date)}</span>
          <span class="post-author">${escapeHtml(p.author || '')}</span>
          <a class="post-link" href="${BASE + p.url}">${escapeHtml(p.title)}</a>
        </div>
      `).join('');
      listEl.insertAdjacentHTML('beforeend', html);
    }
    const loadMore = $('#load-more');
    const remaining = filtered.length - (start + PAGE_SIZE);
    if (remaining <= 0) {
      loadMore.style.display = 'none';
    } else {
      loadMore.textContent = `加载更多（剩余 ${remaining} 篇）`;
    }
  }

  // ===== Year/Month filters =====
  function renderYearMonthFilters() {
    if (!INDEX_LOADED) return;

    // Build counts
    const yearCounts = {};
    const monthCounts = {}; // {year: {month: count}}
    ALL_POSTS.forEach(p => {
      const { year, month } = getYearMonth(p);
      if (!year) return;
      yearCounts[year] = (yearCounts[year] || 0) + 1;
      if (!monthCounts[year]) monthCounts[year] = {};
      monthCounts[year][month] = (monthCounts[year][month] || 0) + 1;
    });
    const years = Object.keys(yearCounts).sort();

    // Sidebar (landscape)
    const yearList = $('#year-list');
    if (yearList) {
      yearList.innerHTML = years.map(y => `
        <div class="year-item ${y === selectedYear ? 'active' : ''}" data-year="${y}">
          <span>${y}年</span>
          <span class="count">${yearCounts[y]}</span>
        </div>
      `).join('');
      $$('.year-item', yearList).forEach(el => {
        el.addEventListener('click', () => {
          const y = el.dataset.year;
          selectedYear = (selectedYear === y) ? null : y;
          selectedMonth = null;
          renderYearMonthFilters();
          renderArticleList();
        });
      });
    }

    // Month list (sidebar)
    const monthList = $('#month-list');
    if (monthList) {
      let html = '';
      if (selectedYear && monthCounts[selectedYear]) {
        const months = Object.keys(monthCounts[selectedYear]).sort();
        html = months.map(m => `
          <div class="month-item ${m === selectedMonth ? 'active' : ''}" data-month="${m}">
            <span>${parseInt(m, 10)}月</span>
            <span class="count">${monthCounts[selectedYear][m]}</span>
          </div>
        `).join('');
      } else {
        html = '<div style="color:#999;font-size:0.85em;padding:0.4em 0.6em;">请先选择年份</div>';
      }
      monthList.innerHTML = html;
      $$('.month-item', monthList).forEach(el => {
        el.addEventListener('click', () => {
          const m = el.dataset.month;
          selectedMonth = (selectedMonth === m) ? null : m;
          renderYearMonthFilters();
          renderArticleList();
        });
      });
    }

    // Mobile: top year strip
    const yearStrip = $('#year-strip');
    if (yearStrip) {
      yearStrip.innerHTML = '<div class="year-chip" data-year="">全部</div>' +
        years.map(y => `<div class="year-chip ${y === selectedYear ? 'active' : ''}" data-year="${y}">${y}</div>`).join('');
      $$('.year-chip', yearStrip).forEach(el => {
        el.addEventListener('click', () => {
          const y = el.dataset.year;
          selectedYear = y || null;
          selectedMonth = null;
          renderYearMonthFilters();
          renderArticleList();
          // scroll selected into view
          el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
        });
      });
    }

    // Mobile: top month strip
    const monthStrip = $('#month-strip');
    if (monthStrip) {
      let html = '<div class="month-chip" data-month="">全部月份</div>';
      if (selectedYear && monthCounts[selectedYear]) {
        const months = Object.keys(monthCounts[selectedYear]).sort();
        html += months.map(m => `<div class="month-chip ${m === selectedMonth ? 'active' : ''}" data-month="${m}">${parseInt(m,10)}月</div>`).join('');
      } else {
        html += '<div class="month-chip disabled">请先选年</div>';
      }
      monthStrip.innerHTML = html;
      $$('.month-chip:not(.disabled)', monthStrip).forEach(el => {
        el.addEventListener('click', () => {
          const m = el.dataset.month;
          selectedMonth = m || null;
          renderYearMonthFilters();
          renderArticleList();
          el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
        });
      });
    }
  }

  // ===== Search =====
  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  function highlight(text, query) {
    if (!text || !query) return escapeHtml(text);
    const esc = escapeHtml(text);
    // For each character in query, wrap in mark (逐字匹配)
    // Use a single combined regex
    const chars = Array.from(query).map(c => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    if (!chars) return esc;
    const re = new RegExp(chars, 'g');
    return esc.replace(re, m => `<mark>${m}</mark>`);
  }

  function makeExcerpt(body, query, maxLen = 200) {
    if (!body) return '';
    if (!query) return body.slice(0, maxLen) + (body.length > maxLen ? '…' : '');
    // Find first match position
    const chars = Array.from(query).map(c => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    let minIdx = -1;
    for (const c of chars) {
      const idx = body.indexOf(c);
      if (idx >= 0 && (minIdx === -1 || idx < minIdx)) minIdx = idx;
    }
    if (minIdx === -1) return body.slice(0, maxLen) + (body.length > maxLen ? '…' : '');
    const start = Math.max(0, minIdx - 60);
    const end = Math.min(body.length, start + maxLen);
    let snippet = body.slice(start, end);
    if (start > 0) snippet = '…' + snippet;
    if (end < body.length) snippet = snippet + '…';
    return highlight(snippet, query);
  }

  function doSearch(query) {
    if (!INDEX_LOADED || !IDX) return [];
    if (!query || query.trim().length === 0) return [];
    try {
      const results = IDX.search(query);
      return results.slice(0, 50).map(r => {
        const post = ALL_POSTS[parseInt(r.ref, 10)];
        return { post, score: r.score };
      });
    } catch (e) {
      console.warn('search error:', e);
      return [];
    }
  }

  function renderSearchResults(query, results, container) {
    if (!query) {
      container.innerHTML = '';
      container.classList.remove('visible');
      return;
    }
    if (results.length === 0) {
      container.innerHTML = `<div class="no-results">未找到含 "<strong>${escapeHtml(query)}</strong>" 的文章</div>`;
      container.classList.add('visible');
      return;
    }
    container.innerHTML = results.slice(0, 20).map(({ post }) => `
      <a class="result-item" href="${BASE + post.url}">
        <span class="result-title">${highlight(post.title, query)}</span>
        <span class="result-meta">${escapeHtml(post.date)} · ${escapeHtml(post.author || '')} · 评分 ${post.score ? post.score.toFixed(2) : ''}</span>
        <div class="result-excerpt">${makeExcerpt(post.body, query)}</div>
      </a>
    `).join('');
    if (results.length > 20) {
      container.innerHTML += `<div class="no-results">共 ${results.length} 条结果，仅显示前 20 条。请使用<a href="${BASE}/search/">搜索页</a>查看全部。</div>`;
    }
    container.classList.add('visible');
  }

  // ===== Header search box (global) =====
  function setupHeaderSearch() {
    const input = $('#global-search');
    const results = $('#search-results');
    if (!input || !results) return;

    let debounceTimer = null;
    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const query = input.value.trim();
        if (!query) {
          results.innerHTML = '';
          results.classList.remove('visible');
          return;
        }
        if (!INDEX_LOADED) {
          results.innerHTML = '<div class="no-results">搜索索引加载中，请稍候…</div>';
          results.classList.add('visible');
          loadIndex();
          return;
        }
        const r = doSearch(query);
        renderSearchResults(query, r, results);
      }, 250);
    });

    // Hide on outside click
    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && !results.contains(e.target)) {
        results.classList.remove('visible');
      }
    });
    input.addEventListener('focus', () => {
      if (input.value.trim()) {
        results.classList.add('visible');
      }
    });
    // Enter to go to search page
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const query = input.value.trim();
        if (query) {
          window.location.href = BASE + '/search/?q=' + encodeURIComponent(query);
        }
      }
    });
  }

  // ===== Search page =====
  function setupSearchPage() {
    const input = $('#page-search-input');
    const results = $('#page-search-results');
    if (!input || !results) return;

    // Read query param
    const params = new URLSearchParams(window.location.search);
    const initialQuery = params.get('q') || '';
    if (initialQuery) input.value = initialQuery;

    let debounceTimer = null;
    function performSearch() {
      const query = input.value.trim();
      if (!query) {
        results.innerHTML = '<div class="no-results">输入关键字进行全文搜索</div>';
        return;
      }
      if (!INDEX_LOADED) {
        results.innerHTML = '<div class="no-results">搜索索引加载中…</div>';
        return;
      }
      const r = doSearch(query);
      if (r.length === 0) {
        results.innerHTML = `<div class="no-results">未找到含 "${escapeHtml(query)}" 的文章</div>`;
        return;
      }
      results.innerHTML = `<div class="no-results" style="text-align:left;">共找到 <strong>${r.length}</strong> 条结果（按相关度排序）</div>` +
        r.map(({ post, score }) => `
          <div class="result-item">
            <a class="result-title" href="${BASE + post.url}">${highlight(post.title, query)}</a>
            <div class="result-meta">${escapeHtml(post.date)} · ${escapeHtml(post.author || '')} · 评分 ${score.toFixed(3)}</div>
            <div class="result-excerpt">${makeExcerpt(post.body, query, 300)}</div>
          </div>
        `).join('');
    }

    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(performSearch, 300);
    });

    // Wait for index
    if (INDEX_LOADED) {
      performSearch();
    } else {
      loadIndex().then(performSearch);
    }
  }

  // ===== Init =====
  function init() {
    setupHeaderSearch();
    // Trigger lazy load if home page
    const articleList = $('#article-list');
    const searchPage = $('#page-search-input');
    if (articleList || searchPage) {
      loadIndex();
    }
    // Load more button
    const loadMoreBtn = $('#load-more');
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener('click', loadMore);
    }
    // Search page setup
    setupSearchPage();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
