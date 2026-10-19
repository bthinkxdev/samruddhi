(function () {
  'use strict';

  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
  var progressEl = document.getElementById('htmx-progress');
  var pageLoader = document.getElementById('jm-loader');
  var pendingGlobalProgress = 0;

  function hidePageLoader() {
    if (!pageLoader || pageLoader.classList.contains('is-done')) {
      return;
    }
    pageLoader.classList.add('is-done');
    window.setTimeout(function () {
      if (pageLoader) {
        pageLoader.setAttribute('hidden', '');
      }
    }, 450);
  }

  function triggeringElementHasIndicator(elt) {
    if (!elt) {
      return false;
    }
    if (elt.getAttribute && elt.getAttribute('hx-indicator')) {
      return true;
    }
    return !!elt.closest('[hx-indicator]');
  }

  function showGlobalProgress() {
    if (!progressEl) {
      return;
    }
    progressEl.hidden = false;
    progressEl.setAttribute('aria-hidden', 'false');
    progressEl.classList.add('is-active');
  }

  function hideGlobalProgress() {
    if (!progressEl || pendingGlobalProgress > 0) {
      return;
    }
    progressEl.classList.remove('is-active');
    progressEl.hidden = true;
    progressEl.setAttribute('aria-hidden', 'true');
  }

  function showHtmxToast() {
    var root = document.getElementById('htmx-toast-root');
    if (!root) {
      return;
    }
    root.hidden = false;
    root.innerHTML =
      '<div class="htmx-toast" role="alert">' +
      '<span class="htmx-toast__message">Something went wrong, please try again.</span>' +
      '<button type="button" class="htmx-toast__close btn-ghost" aria-label="Dismiss">&times;</button>' +
      '</div>';
    var closeBtn = root.querySelector('.htmx-toast__close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        root.hidden = true;
        root.innerHTML = '';
      });
    }
    window.setTimeout(function () {
      if (!root.hidden) {
        root.hidden = true;
        root.innerHTML = '';
      }
    }, 6000);
  }

  document.body.addEventListener('htmx:configRequest', function (event) {
    if (csrfToken) {
      event.detail.headers['X-CSRFToken'] = csrfToken;
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (triggeringElementHasIndicator(event.detail.elt)) {
      return;
    }
    pendingGlobalProgress += 1;
    showGlobalProgress();
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (triggeringElementHasIndicator(event.detail.elt)) {
      return;
    }
    pendingGlobalProgress = Math.max(0, pendingGlobalProgress - 1);
    hideGlobalProgress();
  });

  document.body.addEventListener('htmx:responseError', function (event) {
    console.error('[HTMX] responseError', event.detail);
    showHtmxToast();
  });

  document.body.addEventListener('htmx:sendError', function (event) {
    console.error('[HTMX] sendError', event.detail);
    showHtmxToast();
  });

  window.addEventListener('load', function () {
    window.setTimeout(hidePageLoader, 320);
  });
  // Fallback if load already fired or assets cached
  if (document.readyState === 'complete') {
    window.setTimeout(hidePageLoader, 320);
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      window.setTimeout(function () {
        if (document.readyState === 'complete') {
          hidePageLoader();
        }
      }, 1200);
    });
  }

  function loadCartDrawerIfNeeded() {
    var body = document.getElementById('cart-drawer-body');
    if (!body || body.dataset.drawerHydrated === 'true' || !window.htmx) {
      return;
    }
    var url = body.getAttribute('hx-get');
    if (!url) {
      return;
    }
    htmx.ajax('GET', url, { target: '#cart-drawer-body', swap: 'innerHTML' });
    body.dataset.drawerHydrated = 'true';
  }

  var cartOffcanvas = document.getElementById('cartOffcanvas');
  if (cartOffcanvas) {
    cartOffcanvas.addEventListener('shown.bs.offcanvas', function () {
      loadCartDrawerIfNeeded();
    });
  }

  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.id === 'cart-drawer-body') {
      event.detail.target.dataset.drawerHydrated = 'true';
    }
    if (event.detail.target && event.detail.target.id === 'search-suggestions') {
      initSearchSuggestionsKeyboard();
      updateSearchDropdownState();
    }
  });

  function updateSearchDropdownState() {
    var input = document.getElementById('site-search-input');
    var panel = document.getElementById('search-suggestions-dropdown');
    var results = document.getElementById('search-suggestions');
    if (!input || !panel || !results) {
      return;
    }
    var isOpen = results.innerHTML.trim().length > 0 || panel.querySelector('.htmx-request');
    input.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }

  function closeSearchSuggestions() {
    var input = document.getElementById('site-search-input');
    var results = document.getElementById('search-suggestions');
    if (!input || !results) {
      return;
    }
    results.innerHTML = '';
    input.setAttribute('aria-expanded', 'false');
    input.focus();
  }

  function initSearchSuggestionsKeyboard() {
    var input = document.getElementById('site-search-input');
    var results = document.getElementById('search-suggestions');
    if (!input || !results) {
      return;
    }
    var links = results.querySelectorAll('.search-suggestion-link');
    links.forEach(function (link, index) {
      link.setAttribute('data-suggestion-index', String(index));
    });
    if (links.length) {
      input.dataset.activeSuggestion = '0';
      links[0].classList.add('is-active');
    } else {
      delete input.dataset.activeSuggestion;
    }
  }

  function setActiveSearchSuggestion(input, links, index) {
    links.forEach(function (link) { link.classList.remove('is-active'); });
    if (index < 0 || index >= links.length) {
      delete input.dataset.activeSuggestion;
      return;
    }
    input.dataset.activeSuggestion = String(index);
    links[index].classList.add('is-active');
    links[index].scrollIntoView({ block: 'nearest' });
  }

  var searchInput = document.getElementById('site-search-input');
  if (searchInput) {
    searchInput.addEventListener('keydown', function (event) {
      var results = document.getElementById('search-suggestions');
      if (!results) {
        return;
      }
      var links = results.querySelectorAll('.search-suggestion-link');
      var activeIndex = parseInt(searchInput.dataset.activeSuggestion || '-1', 10);

      if (event.key === 'Escape') {
        event.preventDefault();
        closeSearchSuggestions();
        return;
      }

      if (!links.length) {
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        var next = activeIndex < links.length - 1 ? activeIndex + 1 : 0;
        setActiveSearchSuggestion(searchInput, links, next);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        var prev = activeIndex > 0 ? activeIndex - 1 : links.length - 1;
        setActiveSearchSuggestion(searchInput, links, prev);
      } else if (event.key === 'Enter' && activeIndex >= 0 && links[activeIndex]) {
        event.preventDefault();
        window.location.href = links[activeIndex].href;
      }
    });

    searchInput.addEventListener('input', function () {
      if (!searchInput.value.trim()) {
        closeSearchSuggestions();
      }
    });

    searchInput.addEventListener('blur', function () {
      window.setTimeout(function () {
        var results = document.getElementById('search-suggestions');
        if (!results || document.activeElement === searchInput) {
          return;
        }
        if (!results.contains(document.activeElement)) {
          results.innerHTML = '';
          searchInput.setAttribute('aria-expanded', 'false');
        }
      }, 150);
    });
  }

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (event.detail.elt && event.detail.elt.id === 'site-search-input') {
      var results = document.getElementById('search-suggestions');
      if (results) {
        results.innerHTML = '';
      }
      updateSearchDropdownState();
    }
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail.elt && event.detail.elt.id === 'site-search-input') {
      updateSearchDropdownState();
    }
  });

  function updatePlpSidebarScroll() {
    // Disabled to prevent scroll glitching: max-height is handled purely via CSS calc()
    /*
    var sidebar = document.querySelector('.plp-filters-desktop');
    if (!sidebar) return;
    var rect = sidebar.getBoundingClientRect();
    var availableHeight = window.innerHeight - rect.top - 24;
    sidebar.style.maxHeight = Math.max(300, availableHeight) + 'px';
    */
  }

  // window.addEventListener('scroll', updatePlpSidebarScroll, { passive: true });
  // window.addEventListener('resize', updatePlpSidebarScroll, { passive: true });
  // document.addEventListener('DOMContentLoaded', updatePlpSidebarScroll);
  // updatePlpSidebarScroll();

  function reinitPageScripts() {
    // updatePlpSidebarScroll();
    document.querySelectorAll('.thumb-btn').forEach(function (btn) {
      if (btn.dataset.boundThumb) return;
      btn.dataset.boundThumb = '1';
      btn.addEventListener('click', function () {
        var main = document.getElementById('main-pdp-image');
        if (main) main.src = this.getAttribute('data-full');
        document.querySelectorAll('.thumb-btn').forEach(function (b) {
          b.classList.remove('active', 'is-active');
        });
        this.classList.add('active', 'is-active');
      });
    });
  }

  function applyDocumentLocale(detail) {
    if (!detail || !detail.lang) {
      return;
    }
    document.documentElement.lang = detail.lang;
    document.documentElement.dir = detail.dir || 'ltr';
    var rtlHref = document.body.getAttribute('data-rtl-stylesheet');
    var rtlLink = document.getElementById('rtl-stylesheet');
    if (detail.dir === 'rtl') {
      if (!rtlLink && rtlHref) {
        rtlLink = document.createElement('link');
        rtlLink.id = 'rtl-stylesheet';
        rtlLink.rel = 'stylesheet';
        rtlLink.href = rtlHref;
        document.head.appendChild(rtlLink);
      }
    } else if (rtlLink) {
      rtlLink.remove();
    }
  }

  document.body.addEventListener('preferencesUpdated', function (event) {
    applyDocumentLocale(event.detail);
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (event.detail.elt && event.detail.elt.classList.contains('preference-switcher')) {
      sessionStorage.setItem('themeScrollY', String(window.scrollY));
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (event) {
    if (event.detail.target && event.detail.target.id === 'theme-app-shell') {
      var saved = sessionStorage.getItem('themeScrollY');
      if (saved !== null) {
        window.scrollTo(0, parseInt(saved, 10));
        sessionStorage.removeItem('themeScrollY');
      }
      reinitPageScripts();
    }
    if (event.detail.target && event.detail.target.id === 'product-grid') {
      
      var grid = event.detail.target;
      var header = document.querySelector('.site-header.sticky-top');
      var toolbar = document.querySelector('.plp-toolbar');
      var offset = 16;
      if (header) offset += header.getBoundingClientRect().height;
      if (toolbar && getComputedStyle(toolbar).position === 'sticky') {
        offset += toolbar.getBoundingClientRect().height;
      }
      var gridTop = grid.getBoundingClientRect().top + window.scrollY;
      var offsetPosition = Math.max(0, gridTop - offset);
      if (window.scrollY > offsetPosition) {
        window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
      }
      reinitPageScripts();
    }
  });

  reinitPageScripts();


  /*
   * Attention coordinator — search nudge pulses on a fixed schedule.
   * Timing plan (page load = 0):
   *   Search preferred: 15s, 55s, 95s (max 3, then stop / stop on search use)
   *   Each effect lasts 8s; after any effect, channel locked for 8s + 30s gap
   *   If a preferred time is busy, it waits until the channel is free
   */
  (function initAttentionEffects() {
    var SHOW_MS = 8000;
    var MIN_GAP_MS = 30000;
    var SEARCH_FIRST_MS = 15000;
    var SEARCH_GAP_MS = 40000;
    var SEARCH_MAX = 3;

    var freeAt = 0;
    var queue = Promise.resolve();
    var searchStopped = false;
    var timers = [];

    var openBtn = document.getElementById('mobile-search-open');
    var nudge = openBtn ? openBtn.closest('.jm-search-nudge') : null;
    var overlay = document.getElementById('mobile-search-overlay');
    var input = document.getElementById('mobile-search-input');
    var clearBtn = document.getElementById('mobile-search-clear');
    var results = document.getElementById('mobile-search-results');

    var NUDGE_STORAGE_DONE = 'jm_search_nudge_done';
    var NUDGE_STORAGE_COUNT = 'jm_search_nudge_count';

    function readSearchCount() {
      try {
        return parseInt(localStorage.getItem(NUDGE_STORAGE_COUNT) || '0', 10) || 0;
      } catch (e) {
        return 0;
      }
    }

    function writeSearchCount(count) {
      try {
        localStorage.setItem(NUDGE_STORAGE_COUNT, String(count));
      } catch (e) { }
    }

    function isSearchDone() {
      try {
        return localStorage.getItem(NUDGE_STORAGE_DONE) === '1'
          || localStorage.getItem('jm_search_nudge_seen') === '1';
      } catch (e) {
        return false;
      }
    }

    function markSearchDone() {
      searchStopped = true;
      if (nudge) {
        nudge.classList.remove('is-active');
        nudge.classList.add('is-done');
      }
      try {
        localStorage.setItem(NUDGE_STORAGE_DONE, '1');
      } catch (e) { }
    }

    function schedule(fn, delay) {
      var id = window.setTimeout(fn, Math.max(0, delay));
      timers.push(id);
      return id;
    }

    function runExclusive(activate, deactivate) {
      queue = queue.then(function () {
        return new Promise(function (resolve) {
          function start() {
            var now = Date.now();
            var wait = Math.max(0, freeAt - now);
            schedule(function () {
              freeAt = Date.now() + SHOW_MS + MIN_GAP_MS;
              activate();
              schedule(function () {
                deactivate();
                resolve();
              }, SHOW_MS);
            }, wait);
          }
          start();
        });
      });
      return queue;
    }

    function requestSearchPulse() {
      if (searchStopped || !nudge || isSearchDone()) return;
      var count = readSearchCount();
      if (count >= SEARCH_MAX) {
        markSearchDone();
        return;
      }
      runExclusive(
        function () {
          if (searchStopped || isSearchDone()) return;
          var next = readSearchCount() + 1;
          writeSearchCount(next);
          nudge.classList.add('is-active');
          if (next >= SEARCH_MAX) {
            schedule(markSearchDone, SHOW_MS + 40);
          }
        },
        function () {
          if (nudge) nudge.classList.remove('is-active');
        }
      );
    }

    function scheduleSearchPulses() {
      if (!nudge || isSearchDone()) {
        if (nudge) nudge.classList.add('is-done');
        searchStopped = true;
        return;
      }
      var count = readSearchCount();
      if (count >= SEARCH_MAX) {
        markSearchDone();
        return;
      }
      var remaining = SEARCH_MAX - count;
      for (var i = 0; i < remaining; i += 1) {
        schedule(requestSearchPulse, SEARCH_FIRST_MS + (i * SEARCH_GAP_MS));
      }
    }

    // Mobile search open/close wiring (kept with attention effects)
    if (overlay && openBtn && input) {
      function openSearch() {
        overlay.classList.add('is-open');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('mobile-search-open');
        openBtn.setAttribute('aria-expanded', 'true');
        markSearchDone();
        window.setTimeout(function () {
          input.focus({ preventScroll: true });
        }, 120);
      }

      function closeSearch() {
        overlay.classList.remove('is-open');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('mobile-search-open');
        openBtn.setAttribute('aria-expanded', 'false');
        input.blur();
      }

      function syncClearButton() {
        if (!clearBtn) return;
        clearBtn.hidden = !input.value.trim();
      }

      openBtn.addEventListener('click', openSearch);
      overlay.querySelectorAll('[data-search-dismiss]').forEach(function (el) {
        el.addEventListener('click', closeSearch);
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && overlay.classList.contains('is-open')) {
          closeSearch();
        }
      });
      input.addEventListener('input', function () {
        syncClearButton();
        if (!input.value.trim() && results) results.innerHTML = '';
      });
      if (clearBtn) {
        clearBtn.addEventListener('click', function () {
          input.value = '';
          if (results) results.innerHTML = '';
          syncClearButton();
          input.focus({ preventScroll: true });
        });
      }
      document.body.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target && event.detail.target.id === 'mobile-search-results') {
          syncClearButton();
        }
      });
    }

    scheduleSearchPulses();
  })();

  document.querySelectorAll('.product-rail-scroll, .chip-scroll').forEach(function (rail) {
    var isDown = false;
    var startX;
    var scrollLeft;
    rail.addEventListener('mousedown', function (e) {
      isDown = true;
      startX = e.pageX - rail.offsetLeft;
      scrollLeft = rail.scrollLeft;
      rail.style.cursor = 'grabbing';
    });
    rail.addEventListener('mouseleave', function () { isDown = false; rail.style.cursor = ''; });
    rail.addEventListener('mouseup', function () { isDown = false; rail.style.cursor = ''; });
    rail.addEventListener('mousemove', function (e) {
      if (!isDown) return;
      e.preventDefault();
      var x = e.pageX - rail.offsetLeft;
      rail.scrollLeft = scrollLeft - (x - startX) * 1.5;
    });
  });
})();

// Featured brands rail: arrow scrolling + auto-hide disabled state
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.brand-rail').forEach((rail) => {
    const track = rail.querySelector('[data-brand-track]');
    const prevBtn = rail.querySelector('[data-brand-scroll="prev"]');
    const nextBtn = rail.querySelector('[data-brand-scroll="next"]');
    if (!track || !prevBtn || !nextBtn) return;

    const scrollByCard = (dir) => {
      const card = track.querySelector('.brand-card');
      const gap = 20;
      const distance = card ? card.offsetWidth + gap : 220;
      track.scrollBy({ left: dir * distance * 2, behavior: 'smooth' });
    };

    prevBtn.addEventListener('click', () => scrollByCard(-1));
    nextBtn.addEventListener('click', () => scrollByCard(1));

    const updateArrowState = () => {
      const maxScroll = track.scrollWidth - track.clientWidth - 1;
      prevBtn.disabled = track.scrollLeft <= 0;
      nextBtn.disabled = track.scrollLeft >= maxScroll || maxScroll <= 0;
    };

    track.addEventListener('scroll', updateArrowState, { passive: true });
    window.addEventListener('resize', updateArrowState);
    updateArrowState();
  });
});
/* Desert Star: product rail arrows, quick view, wishlist, search category */
(function () {
  'use strict';

  function initRailArrows(root) {
    (root || document).querySelectorAll('.jm-featured__rail').forEach(function (rail) {
      if (rail.dataset.jmRailReady === '1') return;
      var track = rail.querySelector('[data-rail-track]');
      var prevBtn = rail.querySelector('[data-rail-scroll="prev"]');
      var nextBtn = rail.querySelector('[data-rail-scroll="next"]');
      if (!track || !prevBtn || !nextBtn) return;
      rail.dataset.jmRailReady = '1';

      function scrollByDir(dir) {
        var styles = window.getComputedStyle(track);
        var gap = parseFloat(styles.columnGap || styles.gap) || 16;
        var item = track.querySelector('.product-rail-item');
        var colWidth = item ? item.getBoundingClientRect().width : 240;
        track.scrollBy({ left: dir * (colWidth + gap) * 2, behavior: 'smooth' });
      }

      function updateState() {
        var maxScroll = track.scrollWidth - track.clientWidth - 1;
        prevBtn.disabled = track.scrollLeft <= 0;
        nextBtn.disabled = track.scrollLeft >= maxScroll || maxScroll <= 0;
      }

      prevBtn.addEventListener('click', function () { scrollByDir(-1); });
      nextBtn.addEventListener('click', function () { scrollByDir(1); });
      track.addEventListener('scroll', updateState, { passive: true });
      window.addEventListener('resize', updateState);
      updateState();
    });
  }

  function resetQvQty() {
    var qtyInput = document.getElementById('jm-qv-qty');
    var formQty = document.getElementById('jm-qv-form-qty');
    var errorMsg = document.getElementById('jm-qv-stock-error-msg');
    if (qtyInput) qtyInput.value = '1';
    if (formQty) formQty.value = '1';
    if (errorMsg) {
      errorMsg.textContent = '';
      errorMsg.classList.add('d-none');
    }
  }

  window.handleQvQtyChange = function (delta) {
    var qtyInput = document.getElementById('jm-qv-qty');
    if (!qtyInput) return;
    var maxStock = parseInt(qtyInput.getAttribute('data-max-stock'), 10);
    var currQty = parseInt(qtyInput.value, 10) || 1;
    var errorMsg = document.getElementById('jm-qv-stock-error-msg');

    if (delta > 0 && !isNaN(maxStock) && currQty >= maxStock) {
      if (errorMsg) {
        errorMsg.textContent = maxStock <= 0 ? 'Out of stock' : 'Only ' + maxStock + ' items available in stock.';
        errorMsg.classList.remove('d-none');
      }
      return;
    }

    var newQty = currQty + delta;
    if (newQty < 1) newQty = 1;
    qtyInput.value = newQty;
    var formQty = document.getElementById('jm-qv-form-qty');
    if (formQty) formQty.value = newQty;

    if (errorMsg) {
      errorMsg.classList.add('d-none');
      errorMsg.textContent = '';
    }
  };

  function applyQvButtons(inCart, isOut) {
    var qvCartForm = document.getElementById('jm-qv-cart');
    var qvViewCart = document.getElementById('jm-qv-view-cart');
    var qvAddBtn = document.getElementById('jm-qv-add-btn');
    var qvQtyGroup = document.getElementById('jm-qv-qty-group');

    if (qvCartForm && qvViewCart) {
      if (inCart) {
        qvCartForm.classList.add('d-none');
        if (qvQtyGroup) qvQtyGroup.classList.add('d-none');
        qvViewCart.classList.remove('d-none');
      } else {
        qvCartForm.classList.remove('d-none');
        if (qvQtyGroup) qvQtyGroup.classList.remove('d-none');
        qvViewCart.classList.add('d-none');
      }
    }
    if (qvQtyGroup) {
      qvQtyGroup.style.opacity = isOut ? '0.5' : '1';
      qvQtyGroup.style.pointerEvents = isOut ? 'none' : 'auto';
    }
    if (qvAddBtn) {
      if (isOut) {
        qvAddBtn.type = 'button';
        qvAddBtn.disabled = true;
        qvAddBtn.classList.add('disabled');
        qvAddBtn.textContent = 'Sold out';
        qvAddBtn.style.cursor = 'not-allowed';
        qvAddBtn.style.opacity = '0.6';
        qvAddBtn.style.pointerEvents = 'auto';
        qvAddBtn.onclick = function (e) { e.preventDefault(); return false; };
      } else {
        qvAddBtn.type = 'submit';
        qvAddBtn.disabled = false;
        qvAddBtn.classList.remove('disabled');
        qvAddBtn.textContent = 'Add to Cart';
        qvAddBtn.style.cursor = 'pointer';
        qvAddBtn.style.opacity = '1';
        qvAddBtn.style.pointerEvents = 'auto';
        qvAddBtn.onclick = null;
      }
    }
  }

  function updateQvState(pid, vid, card) {
    if (!pid) return;
    var itemKey = vid ? (pid + '_' + vid) : pid;
    var inCart = false;
    if (window.jmCartItemKeys && window.jmCartItemKeys.size > 0) {
      inCart = window.jmCartItemKeys.has(itemKey);
    } else if (card) {
      inCart = card.dataset.inCart === 'true';
    }
    var isOut = card ? (card.dataset.isOutOfStock === 'true') : false;
    var checkedRadio = document.querySelector('.qv-variant-radio:checked');
    var stockEl = document.getElementById('jm-qv-stock');
    var qvQtyInput = document.getElementById('jm-qv-qty');
    var qvFormQty = document.getElementById('jm-qv-form-qty');
    var qvErrorMsg = document.getElementById('jm-qv-stock-error-msg');

    if (checkedRadio && checkedRadio.dataset.stock !== undefined && checkedRadio.dataset.stock !== '') {
      var st = parseInt(checkedRadio.dataset.stock, 10);
      var th = parseInt(checkedRadio.dataset.thresh || '5', 10);
      isOut = st <= 0;
      if (qvQtyInput) {
        qvQtyInput.setAttribute('data-max-stock', String(st));
        if (parseInt(qvQtyInput.value, 10) > st && st > 0) {
          qvQtyInput.value = String(st);
          if (qvFormQty) qvFormQty.value = String(st);
        }
      }
      if (qvErrorMsg) {
        qvErrorMsg.textContent = '';
        qvErrorMsg.classList.add('d-none');
      }
      if (stockEl) {
        if (isOut) {
          stockEl.textContent = 'Out of Stock';
          stockEl.className = 'jm-qv__stock is-out';
        } else if (st <= th) {
          stockEl.textContent = 'Only ' + st + ' left';
          stockEl.className = 'jm-qv__stock is-low';
        } else {
          stockEl.innerHTML = 'In Stock';
          stockEl.className = 'jm-qv__stock is-in';
        }
      }
    }
    applyQvButtons(inCart, isOut);

    var url = '/catalog/' + pid + '/variant-price/' + (vid ? '?variant_id=' + vid : '');
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var priceEl = document.getElementById('jm-qv-price');
        var stockEl = document.getElementById('jm-qv-stock');

        if (priceEl && (data.formatted_price || data.price)) {
          if (data.formatted_price) {
            priceEl.textContent = data.formatted_price;
          } else {
            var curSymbol = '';
            if (priceEl.textContent) {
              var match = priceEl.textContent.match(/^[^\d.,]+/);
              if (match) curSymbol = match[0].trim() + ' ';
            }
            priceEl.textContent = curSymbol + parseFloat(data.price).toFixed(2).replace(/\.00$/, '');
          }
        }

        if (data.stock_quantity !== undefined && qvQtyInput) {
          qvQtyInput.setAttribute('data-max-stock', String(data.stock_quantity));
          if (parseInt(qvQtyInput.value, 10) > data.stock_quantity && data.stock_quantity > 0) {
            qvQtyInput.value = String(data.stock_quantity);
            var fQty = document.getElementById('jm-qv-form-qty');
            if (fQty) fQty.value = String(data.stock_quantity);
          }
        }

        if (qvErrorMsg) {
          qvErrorMsg.textContent = '';
          qvErrorMsg.classList.add('d-none');
        }

        if (stockEl) {
          if (outOfStock) {
            stockEl.textContent = 'Out of Stock';
            stockEl.className = 'jm-qv__stock is-out';
          } else if (data.stock_quantity !== undefined && data.low_stock_threshold !== undefined && data.stock_quantity <= data.low_stock_threshold) {
            stockEl.textContent = 'Only ' + data.stock_quantity + ' left';
            stockEl.className = 'jm-qv__stock is-low';
          } else {
            stockEl.innerHTML = 'In Stock';
            stockEl.className = 'jm-qv__stock is-in';
          }
        }

        if (window.jmCartItemKeys && data.is_in_cart) {
          window.jmCartItemKeys.add(itemKey);
        } else if (window.jmCartItemKeys && !data.is_in_cart) {
          window.jmCartItemKeys.delete(itemKey);
        }

        applyQvButtons(data.is_in_cart, outOfStock);
      }).catch(function () { });
  }

  function openQuickView(card) {
    var modalEl = document.getElementById('jmQuickViewModal');
    if (!modalEl || !window.bootstrap) return;
    var img = document.getElementById('jm-qv-image');
    var title = document.getElementById('jmQuickViewTitle');
    var price = document.getElementById('jm-qv-price');
    var mrp = document.getElementById('jm-qv-mrp');
    var discount = document.getElementById('jm-qv-discount');
    var stock = document.getElementById('jm-qv-stock');
    var badge = document.getElementById('jm-qv-badge');
    var pdp = document.getElementById('jm-qv-pdp');
    var productId = document.getElementById('jm-qv-product-id');
    var variantId = document.getElementById('jm-qv-variant-id');
    var isOut = card.dataset.isOutOfStock === 'true';

    var qvQtyInput = document.getElementById('jm-qv-qty');
    var qvFormQty = document.getElementById('jm-qv-form-qty');
    var qvErrorMsg = document.getElementById('jm-qv-stock-error-msg');
    if (qvQtyInput) {
      qvQtyInput.value = '1';
      qvQtyInput.setAttribute('data-max-stock', card.dataset.stockQuantity || '0');
    }
    if (qvFormQty) qvFormQty.value = '1';
    if (qvErrorMsg) {
      qvErrorMsg.textContent = '';
      qvErrorMsg.classList.add('d-none');
    }

    if (img) {
      img.src = card.dataset.productImage || '';
      img.alt = card.dataset.productName || '';
    }
    if (title) title.textContent = card.dataset.productName || '';
    if (price) price.textContent = card.dataset.productPrice || '';
    if (mrp) mrp.classList.add('d-none');
    if (discount) discount.classList.add('d-none');
    if (stock) {
      stock.innerHTML = card.dataset.productStock || '';
      var cardStockEl = card.querySelector('.jm-product-card__stock');
      if (cardStockEl && cardStockEl.classList.contains('is-low')) {
        stock.className = 'jm-qv__stock is-low';
      } else if (isOut || (cardStockEl && cardStockEl.classList.contains('is-out'))) {
        stock.className = 'jm-qv__stock is-out';
      } else {
        stock.className = 'jm-qv__stock is-in';
      }
    }
    if (badge) {
      if (card.dataset.productBadge) {
        badge.hidden = false;
        badge.textContent = card.dataset.productBadge;
      } else {
        badge.hidden = true;
      }
    }
    if (pdp) pdp.href = card.dataset.productUrl || '#';
    if (productId) productId.value = card.dataset.productId || '';

    if (modalEl.dataset.cartItemKeys !== undefined && !window.jmCartItemKeys) {
      window.jmCartItemKeys = new Set(modalEl.dataset.cartItemKeys.split(',').filter(Boolean));
    }
    if (!window.jmCartItemKeys) window.jmCartItemKeys = new Set();

    var variantsWrap = document.getElementById('jm-qv-variants-wrap');
    var variantsGroup = document.getElementById('jm-qv-variants-group');
    var variantsData = [];
    try {
      if (card.dataset.productVariants) {
        variantsData = JSON.parse(card.dataset.productVariants);
      }
    } catch (e) { }

    var selectedVid = card.dataset.variantId || '';

    if (variantsWrap && variantsGroup) {
      if (!variantsData || !variantsData.length) {
        variantsWrap.classList.add('d-none');
        variantsGroup.innerHTML = '';
        if (variantId) variantId.value = selectedVid;
        updateQvState(productId ? productId.value : '', selectedVid, card);
      } else {
        variantsWrap.classList.remove('d-none');
        variantsGroup.innerHTML = '';

        if (!selectedVid && variantsData.length > 0) {
          selectedVid = String(variantsData[0].id);
        }

        variantsData.forEach(function (v) {
          var vidStr = String(v.id);
          var isOutVariant = v.stock <= 0;
          var inputId = 'qv_variant_' + vidStr;

          var radio = document.createElement('input');
          radio.type = 'radio';
          radio.className = 'btn-check qv-variant-radio';
          radio.name = 'qv_variant_option';
          radio.id = inputId;
          radio.value = vidStr;
          radio.autocomplete = 'off';
          radio.dataset.price = v.price || '';
          radio.dataset.mrp = v.mrp || '';
          radio.dataset.discount = v.discount || '0';
          radio.dataset.stock = String(v.stock !== undefined ? v.stock : 0);
          radio.dataset.thresh = String(v.thresh !== undefined ? v.thresh : 5);
          if (vidStr === selectedVid) {
            radio.checked = true;
          }

          var label = document.createElement('label');
          label.className = 'btn btn-outline-dark rounded-pill px-3 py-1 position-relative overflow-hidden';
          label.setAttribute('for', inputId);
          label.style.fontSize = '0.85rem';
          if (isOutVariant) {
            label.style.color = '#adb5bd';
            label.style.borderColor = '#dee2e6';
          }
          label.textContent = v.name;
          if (isOutVariant) {
            var span = document.createElement('span');
            span.style.cssText = 'position: absolute; width: 150%; height: 1px; background: currentColor; top: 50%; left: -25%; transform: rotate(-20deg); opacity: 0.5;';
            label.appendChild(span);
          }

          radio.addEventListener('change', function () {
            if (variantId) variantId.value = this.value;
            var curSymbol = '';
            if (price && price.textContent) {
              var match = price.textContent.match(/^[^\d.,]+/);
              if (match) curSymbol = match[0].trim() + ' ';
            }
            if (this.dataset.price && price) {
              price.textContent = curSymbol + parseFloat(this.dataset.price).toFixed(2).replace(/\.00$/, '');
            }
            if (mrp && this.dataset.mrp) {
              mrp.textContent = curSymbol + parseFloat(this.dataset.mrp).toFixed(2).replace(/\.00$/, '');
              mrp.classList.remove('d-none');
            } else if (mrp) {
              mrp.classList.add('d-none');
            }
            if (discount && parseInt(this.dataset.discount) > 0) {
              discount.textContent = this.dataset.discount + '% OFF';
              discount.classList.remove('d-none');
            } else if (discount) {
              discount.classList.add('d-none');
            }

            resetQvQty();
            updateQvState(productId ? productId.value : '', this.value, null);
          });

          variantsGroup.appendChild(radio);
          variantsGroup.appendChild(label);
        });

        var checked = variantsGroup.querySelector('.qv-variant-radio:checked');
        var initVid = checked ? checked.value : selectedVid;
        if (variantId) variantId.value = initVid;
        if (checked) {
          checked.dispatchEvent(new Event('change'));
        }
        updateQvState(productId ? productId.value : '', initVid, card);
      }
    } else {
      if (variantId) variantId.value = selectedVid;
      updateQvState(productId ? productId.value : '', selectedVid, card);
    }

    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function setWishFilled(svg, filled) {
    if (!svg) return;
    svg.setAttribute('fill', filled ? 'currentColor' : 'none');
  }

  function syncWishlistChrome(detail) {
    var added = !!(detail && detail.added);
    var productId = detail && detail.product_id != null ? String(detail.product_id) : '';
    if (!productId) return;

    document.querySelectorAll('.jm-product-card__wish').forEach(function (btn) {
      var form = btn.closest('form');
      var input = form ? form.querySelector('input[name="product_id"]') : null;
      if (!input || String(input.value) !== productId) return;
      btn.classList.toggle('is-active', added);
      btn.setAttribute('aria-pressed', added ? 'true' : 'false');
      setWishFilled(btn.querySelector('svg'), added);
    });

    document.querySelectorAll('[data-jm-wish-btn]').forEach(function (btn) {
      if (String(btn.getAttribute('data-product-id') || '') !== productId) return;
      btn.classList.toggle('is-active', added);
      btn.setAttribute('aria-pressed', added ? 'true' : 'false');
      setWishFilled(btn.querySelector('svg'), added);
    });
  }

  document.addEventListener('click', function (event) {
    var qvBtn = event.target.closest('[data-jm-quick-view]');
    if (qvBtn) {
      event.preventDefault();
      event.stopPropagation();
      var card = qvBtn.closest('.jm-product-card');
      if (card) openQuickView(card);
    }

    var atcBtn = event.target.closest('[data-jm-add-to-cart]');
    if (atcBtn) {
      event.preventDefault();
      event.stopPropagation();
      var card = atcBtn.closest('.jm-product-card');
      if (card) openAddToCartModal(card);
    }
  });

  function resetAtcQty() {
    var qtyInput = document.getElementById('jm-atc-qty');
    var errorMsg = document.getElementById('jm-atc-stock-error-msg');
    if (qtyInput) qtyInput.value = '1';
    if (errorMsg) {
      errorMsg.textContent = '';
      errorMsg.classList.add('d-none');
    }
  }

  window.handleAtcQtyChange = function (delta) {
    var qtyInput = document.getElementById('jm-atc-qty');
    if (!qtyInput) return;
    var maxStock = parseInt(qtyInput.getAttribute('data-max-stock'), 10);
    var currQty = parseInt(qtyInput.value, 10) || 1;
    var errorMsg = document.getElementById('jm-atc-stock-error-msg');

    if (delta > 0 && !isNaN(maxStock) && currQty >= maxStock) {
      if (errorMsg) {
        errorMsg.textContent = maxStock <= 0 ? 'Out of stock' : 'Only ' + maxStock + ' items available in stock.';
        errorMsg.classList.remove('d-none');
      }
      return;
    }

    var newQty = currQty + delta;
    if (newQty < 1) newQty = 1;
    qtyInput.value = newQty;

    if (errorMsg) {
      errorMsg.classList.add('d-none');
      errorMsg.textContent = '';
    }
  };

  function updateAtcState(pid, vid, card) {
    if (!pid) return;
    var itemKey = vid ? (pid + '_' + vid) : pid;
    var inCart = false;
    if (window.jmCartItemKeys && window.jmCartItemKeys.size > 0) {
      inCart = window.jmCartItemKeys.has(itemKey);
    } else if (card) {
      inCart = card.dataset.inCart === 'true';
    }
    var isOut = card ? (card.dataset.isOutOfStock === 'true') : false;
    var checkedRadio = document.querySelector('.atc-variant-radio:checked');
    var stockEl = document.getElementById('jm-atc-stock');
    var qtyInput = document.getElementById('jm-atc-qty');
    var errorMsg = document.getElementById('jm-atc-stock-error-msg');
    
    if (checkedRadio && checkedRadio.dataset.stock !== undefined && checkedRadio.dataset.stock !== '') {
      var st = parseInt(checkedRadio.dataset.stock, 10);
      var th = parseInt(checkedRadio.dataset.thresh || '5', 10);
      isOut = st <= 0;
      if (qtyInput) {
        qtyInput.setAttribute('data-max-stock', String(st));
        if (parseInt(qtyInput.value, 10) > st && st > 0) {
          qtyInput.value = String(st);
        }
      }
      if (errorMsg) {
        errorMsg.textContent = '';
        errorMsg.classList.add('d-none');
      }
      if (stockEl) {
        if (isOut) {
          stockEl.textContent = 'Out of Stock';
          stockEl.className = 'jm-atc__stock is-out text-danger';
        } else if (st <= th) {
          stockEl.textContent = 'Only ' + st + ' left';
          stockEl.className = 'jm-atc__stock is-low text-warning';
        } else {
          stockEl.innerHTML = 'In Stock';
          stockEl.className = 'jm-atc__stock is-in text-success';
        }
      }
    }
    
    var atcCartForm = document.getElementById('jm-atc-cart');
    var atcViewCart = document.getElementById('jm-atc-view-cart');
    var atcAddBtn = document.getElementById('jm-atc-add-btn');
    var qtyGroup = document.getElementById('jm-atc-qty-group');

    if (atcCartForm && atcViewCart) {
      if (inCart) {
        atcCartForm.classList.add('d-none');
        atcViewCart.classList.remove('d-none');
      } else {
        atcCartForm.classList.remove('d-none');
        atcViewCart.classList.add('d-none');
      }
    }
    if (qtyGroup) {
      qtyGroup.style.opacity = isOut ? '0.5' : '1';
      qtyGroup.style.pointerEvents = isOut ? 'none' : 'auto';
    }
    if (atcAddBtn) {
      if (isOut) {
        atcAddBtn.type = 'button';
        atcAddBtn.disabled = true;
        atcAddBtn.classList.add('disabled');
        atcAddBtn.textContent = 'Sold out';
        atcAddBtn.style.cursor = 'not-allowed';
      } else {
        atcAddBtn.type = 'submit';
        atcAddBtn.disabled = false;
        atcAddBtn.classList.remove('disabled');
        atcAddBtn.textContent = 'Add';
        atcAddBtn.style.cursor = 'pointer';
      }
    }
    
  }

  function openAddToCartModal(card) {
    var modalEl = document.getElementById('jmAddToCartModal');
    if (!modalEl || !window.bootstrap) return;

    var variantsData = [];
    try {
      if (card.dataset.productVariants) {
        variantsData = JSON.parse(card.dataset.productVariants);
      }
    } catch (e) { }

    if (variantsData.length <= 1) {
      var selectedVid = variantsData.length === 1 ? String(variantsData[0].id) : (card.dataset.variantId || '');
      var form = document.getElementById('jm-atc-cart');
      if (form && window.htmx) {
        var pidInput = document.getElementById('jm-atc-product-id');
        var vidInput = document.getElementById('jm-atc-variant-id');
        var qtyInput = document.getElementById('jm-atc-qty');
        
        if (pidInput) pidInput.value = card.dataset.productId || '';
        if (vidInput) vidInput.value = selectedVid;
        if (qtyInput) qtyInput.value = '1';
        
        htmx.trigger(form, 'submit');
      }
      return;
    }

    var title = document.getElementById('jmAddToCartTitle');
    var pName = document.getElementById('jm-atc-product-name');
    var price = document.getElementById('jm-atc-price');
    var mrp = document.getElementById('jm-atc-mrp');
    var discount = document.getElementById('jm-atc-discount');
    var stock = document.getElementById('jm-atc-stock');
    var selVariantName = document.getElementById('jm-atc-selected-variant-name');
    
    var productId = document.getElementById('jm-atc-product-id');
    var variantId = document.getElementById('jm-atc-variant-id');
    var isOut = card.dataset.isOutOfStock === 'true';

    var qtyInput = document.getElementById('jm-atc-qty');
    var errorMsg = document.getElementById('jm-atc-stock-error-msg');
    
    if (qtyInput) {
      qtyInput.value = '1';
      qtyInput.setAttribute('data-max-stock', card.dataset.stockQuantity || '0');
    }
    if (errorMsg) {
      errorMsg.textContent = '';
      errorMsg.classList.add('d-none');
    }

    if (pName) pName.textContent = card.dataset.productName || '';
    if (price) price.textContent = card.dataset.productPrice || '';
    if (mrp) mrp.classList.add('d-none');
    if (discount) discount.classList.add('d-none');
    if (selVariantName) selVariantName.hidden = true;
    
    if (stock) {
      stock.innerHTML = card.dataset.productStock || '';
      var cardStockEl = card.querySelector('.jm-product-card__stock');
      if (cardStockEl && cardStockEl.classList.contains('is-low')) {
        stock.className = 'jm-atc__stock is-low text-warning';
      } else if (isOut || (cardStockEl && cardStockEl.classList.contains('is-out'))) {
        stock.className = 'jm-atc__stock is-out text-danger';
      } else {
        stock.className = 'jm-atc__stock is-in text-success';
      }
    }
    if (productId) productId.value = card.dataset.productId || '';

    if (modalEl.dataset.cartItemKeys !== undefined && !window.jmCartItemKeys) {
      window.jmCartItemKeys = new Set(modalEl.dataset.cartItemKeys.split(',').filter(Boolean));
    }
    if (!window.jmCartItemKeys) window.jmCartItemKeys = new Set();

    var variantsWrap = document.getElementById('jm-atc-variants-wrap');
    var variantsGroup = document.getElementById('jm-atc-variants-group');

    var selectedVid = card.dataset.variantId || '';

    if (variantsWrap && variantsGroup) {
      if (!variantsData || !variantsData.length) {
        variantsWrap.classList.add('d-none');
        variantsGroup.innerHTML = '';
        if (title) title.textContent = 'Select quantity';
        if (variantId) variantId.value = selectedVid;
        updateAtcState(productId ? productId.value : '', selectedVid, card);
      } else {
        variantsWrap.classList.remove('d-none');
        variantsGroup.innerHTML = '';
        if (title) title.textContent = 'Select variant';

        if (!selectedVid && variantsData.length > 0) {
          selectedVid = String(variantsData[0].id);
        }

        variantsData.forEach(function (v) {
          var vidStr = String(v.id);
          var isOutVariant = v.stock <= 0;
          var inputId = 'atc_variant_' + vidStr;

          var radio = document.createElement('input');
          radio.type = 'radio';
          radio.className = 'btn-check atc-variant-radio';
          radio.name = 'atc_variant_option';
          radio.id = inputId;
          radio.value = vidStr;
          radio.autocomplete = 'off';
          radio.dataset.price = v.price || '';
          radio.dataset.mrp = v.mrp || '';
          radio.dataset.discount = v.discount || '0';
          radio.dataset.stock = String(v.stock !== undefined ? v.stock : 0);
          radio.dataset.thresh = String(v.thresh !== undefined ? v.thresh : 5);
          if (vidStr === selectedVid) {
            radio.checked = true;
          }

          var label = document.createElement('label');
          label.className = 'd-block position-relative border rounded-3 p-2 cursor-pointer';
          label.style.minWidth = '100px';
          label.setAttribute('for', inputId);
          if (isOutVariant) {
            label.style.opacity = '0.5';
          }
          
          var curSymbol = '';
          if (card.dataset.productPrice) {
            var match = card.dataset.productPrice.match(/^[^\d.,]+/);
            if (match) curSymbol = match[0].trim() + ' ';
          }
          var formattedPrice = curSymbol + parseFloat(v.price || 0).toFixed(2).replace(/\.00$/, '');
          var formattedMrp = v.mrp ? (curSymbol + parseFloat(v.mrp).toFixed(2).replace(/\.00$/, '')) : '';

          label.innerHTML = `
            <div class="fw-bold text-dark fs-6">${v.name}</div>
            ${parseInt(v.discount) > 0 ? `<div class="small fw-bold text-success mb-1">${v.discount}% OFF</div>` : ''}
            <div class="fw-bold mt-1" style="font-size:0.9rem;">
              ${formattedPrice}
              ${formattedMrp ? `<span class="text-muted text-decoration-line-through small fw-normal ms-1">${formattedMrp}</span>` : ''}
            </div>
            ${isOutVariant ? `<div class="small text-danger mt-1">Out of stock</div>` : ''}
          `;

          radio.addEventListener('change', function () {
            if (variantId) variantId.value = this.value;
            if (selVariantName) {
              selVariantName.hidden = false;
              selVariantName.textContent = 'Quantity: ' + v.name;
            }
            if (price) {
              price.textContent = curSymbol + parseFloat(this.dataset.price).toFixed(2).replace(/\.00$/, '');
            }
            if (mrp && this.dataset.mrp) {
              mrp.textContent = curSymbol + parseFloat(this.dataset.mrp).toFixed(2).replace(/\.00$/, '');
              mrp.classList.remove('d-none');
            } else if (mrp) {
              mrp.classList.add('d-none');
            }
            if (discount && parseInt(this.dataset.discount) > 0) {
              discount.textContent = this.dataset.discount + '% OFF';
              discount.classList.remove('d-none');
            } else if (discount) {
              discount.classList.add('d-none');
            }
            
            // update border color of selected label
            variantsGroup.querySelectorAll('label').forEach(l => {
              l.classList.remove('border-primary');
              l.style.borderWidth = '1px';
            });
            label.classList.add('border-primary');
            label.style.borderWidth = '2px';
            
            resetAtcQty();
            updateAtcState(productId ? productId.value : '', this.value, null);
          });

          variantsGroup.appendChild(radio);
          variantsGroup.appendChild(label);
        });

        var checked = variantsGroup.querySelector('.atc-variant-radio:checked');
        var initVid = checked ? checked.value : selectedVid;
        if (variantId) variantId.value = initVid;
        
        // trigger change event to style the initially checked radio
        if (checked) {
          checked.dispatchEvent(new Event('change'));
        }
      }
    } else {
      if (variantId) variantId.value = selectedVid;
      if (title) title.textContent = 'Select quantity';
      updateAtcState(productId ? productId.value : '', selectedVid, card);
    }

    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initRailArrows(document);
  });

  document.body.addEventListener('htmx:afterSwap', function () {
    initRailArrows(document);
  });

  document.body.addEventListener('wishlistUpdated', function (event) {
    var detail = event.detail || {};
    syncWishlistChrome(detail);

    if (detail.added === false && window.location.pathname.indexOf('/wishlist') !== -1) {
      var productId = detail.product_id;
      if (productId) {
        document.querySelectorAll('.jm-product-card__wish').forEach(function (btn) {
          var form = btn.closest('form');
          var input = form ? form.querySelector('input[name="product_id"]') : null;
          if (input && String(input.value) === String(productId)) {
            var gridItem = btn.closest('.product-grid-item');
            if (gridItem) {
              gridItem.style.transition = 'opacity 0.3s ease';
              gridItem.style.opacity = '0';
              setTimeout(function () {
                gridItem.remove();
                var gridInner = document.querySelector('.product-grid-inner');
                if (gridInner && gridInner.children.length === 0) {
                  window.location.reload();
                }
              }, 300);
            }
          }
        });
      }
    }
  });

  function isCardFullyInCart(card, defaultInCart) {
    if (!window.jmCartItemKeys || window.jmCartItemKeys.size === 0) return defaultInCart;
    var pid = card.dataset.productId ? String(card.dataset.productId) : '';
    if (!pid) return defaultInCart;

    var variantsData = [];
    try {
      if (card.dataset.productVariants) {
        variantsData = JSON.parse(card.dataset.productVariants);
      }
    } catch (e) {}

    if (variantsData && variantsData.length > 0) {
      for (var i = 0; i < variantsData.length; i++) {
        var v = variantsData[i];
        if (v && v.stock > 0 && !window.jmCartItemKeys.has(pid + '_' + String(v.id))) {
          return false;
        }
      }
      return true;
    }
    return window.jmCartItemKeys.has(pid) ? true : defaultInCart;
  }

  function setProductCardCartState(productId, inCart) {
    document.querySelectorAll('.jm-product-card[data-product-id="' + productId + '"]').forEach(function (card) {
      var fullyInCart = isCardFullyInCart(card, inCart);
      card.dataset.inCart = fullyInCart ? 'true' : 'false';
      var form = card.querySelector('.jm-product-card__cart');
      var viewCartLink = card.querySelector('.jm-dynamic-view-cart');

      if (fullyInCart) {
        if (form && !form.classList.contains('d-none')) {
          var newLink = document.createElement('a');
          var cartUrl = '/cart/';
          var existingLink = document.querySelector('a[href*="/cart/"]');
          if (existingLink) cartUrl = existingLink.getAttribute('href');

          newLink.href = cartUrl;
          newLink.className = 'btn btn-outline-theme jm-product-card__atc jm-product-card__atc--in-cart mt-auto jm-dynamic-view-cart';
          newLink.innerHTML = '<span>View Cart</span>';

          form.classList.add('d-none');
          if (viewCartLink) viewCartLink.replaceWith(newLink);
          else form.parentNode.insertBefore(newLink, form.nextSibling);
        }
      } else {
        if (viewCartLink) viewCartLink.remove();
        if (form) form.classList.remove('d-none');
      }
    });

    var qvProductId = document.getElementById('jm-qv-product-id');
    var qvVariantId = document.getElementById('jm-qv-variant-id');
    if (qvProductId && qvProductId.value === productId) {
      var qvVid = qvVariantId ? qvVariantId.value : '';
      var qvKey = qvVid ? (productId + '_' + qvVid) : productId;
      var qvInCart = window.jmCartItemKeys ? window.jmCartItemKeys.has(qvKey) : inCart;
      var qvCartForm = document.getElementById('jm-qv-cart');
      var qvViewCart = document.getElementById('jm-qv-view-cart');
      if (qvCartForm && qvViewCart) {
        if (qvInCart) {
          qvCartForm.classList.add('d-none');
          qvViewCart.classList.remove('d-none');
        } else {
          qvCartForm.classList.remove('d-none');
          qvViewCart.classList.add('d-none');
        }
      }
    }
  }

  document.body.addEventListener('cartItemAdded', function (event) {
    var pid = (event.detail && event.detail.product_id) ? String(event.detail.product_id) : '';
    var vid = (event.detail && event.detail.variant_id) ? String(event.detail.variant_id) : '';
    if (pid) {
      if (!window.jmCartItemKeys) {
        var modalEl = document.getElementById('jmQuickViewModal');
        if (modalEl && modalEl.dataset.cartItemKeys !== undefined) {
          window.jmCartItemKeys = new Set(modalEl.dataset.cartItemKeys.split(',').filter(Boolean));
        } else {
          window.jmCartItemKeys = new Set();
        }
      }
      window.jmCartItemKeys.add(vid ? (pid + '_' + vid) : pid);
      setProductCardCartState(pid, true);
    }
    lastSync = 0;
    syncCartStatus();
  });

  document.body.addEventListener('cartItemRemoved', function (event) {
    var pid = (event.detail && event.detail.product_id) ? String(event.detail.product_id) : '';
    var vid = (event.detail && event.detail.variant_id) ? String(event.detail.variant_id) : '';
    if (pid) {
      if (window.jmCartItemKeys) {
        window.jmCartItemKeys.delete(vid ? (pid + '_' + vid) : pid);
      }
      setProductCardCartState(pid, false);
    }
    lastSync = 0;
    syncCartStatus();
  });

  var lastSync = 0;
  function syncCartStatus() {
    if (Date.now() - lastSync < 300) return;
    lastSync = Date.now();

    fetch('/cart/status/', { headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !Array.isArray(data.cart_product_ids)) return;
        var cartSet = new Set(data.cart_product_ids.map(String));
        if (Array.isArray(data.cart_item_keys)) {
          window.jmCartItemKeys = new Set(data.cart_item_keys.map(String));
        }
        document.querySelectorAll('.jm-product-card').forEach(function (card) {
          if (card.dataset.productId) setProductCardCartState(String(card.dataset.productId), cartSet.has(String(card.dataset.productId)));
        });

        var qvPidEl = document.getElementById('jm-qv-product-id');
        var qvVidEl = document.getElementById('jm-qv-variant-id');
        if (qvPidEl && qvPidEl.value) {
          var qvPid = qvPidEl.value;
          var qvVid = qvVidEl ? qvVidEl.value : '';
          var qvKey = qvVid ? (qvPid + '_' + qvVid) : qvPid;
          var qvInCart = window.jmCartItemKeys ? window.jmCartItemKeys.has(qvKey) : cartSet.has(qvPid);
          var qvCartForm = document.getElementById('jm-qv-cart');
          var qvViewCart = document.getElementById('jm-qv-view-cart');
          if (qvCartForm && qvViewCart) {
            qvCartForm.classList.toggle('d-none', qvInCart);
            qvViewCart.classList.toggle('d-none', !qvInCart);
          }
        }

        var badge = document.getElementById('cart-count-badge');
        if (badge && data.cart_count !== undefined) {
          badge.innerHTML = data.cart_count > 0 ? '<span class="badge-count">' + data.cart_count + '</span>' : '';
        }

        var pdpForm = document.getElementById('buy-form');
        if (pdpForm) {
          var pid = (pdpForm.querySelector('input[name="product_id"]') || {}).value;
          var vid = (pdpForm.querySelector('input[name="variant_id"]') || {}).value;
          if (pid) {
            var itemKey = vid ? (pid + '_' + vid) : pid;
            var inPdp = Array.isArray(data.cart_item_keys) ? data.cart_item_keys.indexOf(itemKey) !== -1 : cartSet.has(pid);
            var addGrp = document.getElementById('pdp-add-to-cart-group');
            var viewGrp = document.getElementById('pdp-view-cart-group');
            var stickyAdd = document.getElementById('sticky-buy-form');
            var stickyView = document.getElementById('pdp-sticky-view-cart-btn');
            if (addGrp) addGrp.classList.toggle('d-none', inPdp);
            if (viewGrp) viewGrp.classList.toggle('d-none', !inPdp);
            if (stickyAdd) stickyAdd.classList.toggle('d-none', inPdp);
            if (stickyView) stickyView.classList.toggle('d-none', !inPdp);
          }
        }
      }).catch(function () { });
  }

  window.addEventListener('pageshow', function (e) {
    syncCartStatus();
    if (e.persisted) {
      var loader = document.getElementById('jm-loader');
      if (loader && !loader.classList.contains('is-done')) {
        loader.classList.add('is-done');
        loader.setAttribute('hidden', '');
      }
    }
  });
  window.addEventListener('focus', syncCartStatus);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') syncCartStatus(); });
})();

/* Desert Star: sticky header offset + mobile trust auto-slide */
(function () {
  'use strict';

  function syncHeaderStickyOffset() {
    var header = document.querySelector('.site-header.jm-header');
    if (!header) return;
    var height = Math.ceil(header.getBoundingClientRect().height);
    if (height > 0) {
      document.documentElement.style.setProperty('--jm-header-sticky-offset', height + 'px');
    }
  }

  function initHeaderScrollHide() {
    var header = document.querySelector('.site-header.jm-header');
    if (!header || header.dataset.jmScrollHideReady === '1') return;
    header.dataset.jmScrollHideReady = '1';

    var lastScrollY = window.scrollY;
    var hideThreshold = 80; // don't hide until scrolled past the top-of-page area
    var ticking = false;

    function isBlockingOverlayOpen() {
      return !!(
        document.querySelector('#jmMainNav.show') ||
        document.querySelector('#cartOffcanvas.show') ||
        document.querySelector('.mobile-search.is-open, .mobile-search[aria-hidden="false"]')
      );
    }

    function update() {
      var currentScrollY = window.scrollY;
      if (isBlockingOverlayOpen()) {
        header.classList.remove('jm-header--hidden');
        document.documentElement.classList.remove('jm-header-is-hidden');
      } else if (currentScrollY <= hideThreshold) {
        header.classList.remove('jm-header--hidden');
        document.documentElement.classList.remove('jm-header-is-hidden');
      } else if (currentScrollY > lastScrollY) {
        header.classList.add('jm-header--hidden');
        document.documentElement.classList.add('jm-header-is-hidden');
      } else if (currentScrollY < lastScrollY) {
        header.classList.remove('jm-header--hidden');
        document.documentElement.classList.remove('jm-header-is-hidden');
      }
      lastScrollY = currentScrollY;
      ticking = false;
    }

    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(update);
        ticking = true;
      }
    }, { passive: true });
  }

  function initTrustAutoSlide(root) {
    var track = (root || document).querySelector('[data-jm-trust-track]');
    if (!track || track.dataset.jmTrustReady === '1') return;
    track.dataset.jmTrustReady = '1';

    var timer = null;
    var paused = false;
    var mq = window.matchMedia('(max-width: 991.98px)');

    function step() {
      if (paused || !mq.matches) return;
      var item = track.querySelector('.jm-trust__item');
      if (!item) return;
      var gap = 8;
      var distance = item.getBoundingClientRect().width + gap;
      var maxScroll = track.scrollWidth - track.clientWidth - 2;
      if (maxScroll <= 0) return;
      if (track.scrollLeft >= maxScroll) {
        track.scrollTo({ left: 0, behavior: 'smooth' });
      } else {
        track.scrollBy({ left: distance, behavior: 'smooth' });
      }
    }

    function start() {
      stop();
      if (!mq.matches) return;
      timer = window.setInterval(step, 3200);
    }

    function stop() {
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    }

    ['pointerdown', 'touchstart', 'mouseenter', 'focusin'].forEach(function (evt) {
      track.addEventListener(evt, function () { paused = true; }, { passive: true });
    });
    ['pointerup', 'touchend', 'mouseleave', 'focusout'].forEach(function (evt) {
      track.addEventListener(evt, function () { paused = false; }, { passive: true });
    });

    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', start);
    } else if (typeof mq.addListener === 'function') {
      mq.addListener(start);
    }

    start();
  }

  document.addEventListener('DOMContentLoaded', function () {
    syncHeaderStickyOffset();
    initHeaderScrollHide();
    initTrustAutoSlide(document);
  });

  window.addEventListener('resize', syncHeaderStickyOffset);
  window.addEventListener('load', syncHeaderStickyOffset);

  document.addEventListener('click', function (event) {
    var link = event.target.closest('[data-jm-scroll-target]');
    if (!link) return;
    var id = link.getAttribute('data-jm-scroll-target');
    var target = id ? document.getElementById(id) : null;
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (history.replaceState) {
      history.replaceState(null, '', '#' + id);
    }
  });
})();
