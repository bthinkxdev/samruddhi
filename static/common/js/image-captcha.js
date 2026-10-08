/**
 * Shared image CAPTCHA refresh helper.
 * Markup: [data-image-captcha] with img[data-image-captcha-img],
 * button[data-image-captcha-refresh], input[data-image-captcha-input].
 */
(function () {
  'use strict';

  function bindWidget(root) {
    if (!root || root.getAttribute('data-image-captcha-bound') === '1') return;
    if (root.getAttribute('data-image-captcha-deferred') === '1' || root.hidden) return;

    var img = root.querySelector('[data-image-captcha-img]');
    var btn = root.querySelector('[data-image-captcha-refresh]');
    var input = root.querySelector('[data-image-captcha-input]');
    if (!img || !btn) return;

    var base = (img.getAttribute('data-src-base') || img.getAttribute('src') || '').split('?')[0];
    if (!base) return;
    img.setAttribute('data-src-base', base);
    root.setAttribute('data-image-captcha-bound', '1');

    function refresh() {
      img.src = base + '?t=' + Date.now();
      if (input) {
        input.value = '';
        input.focus();
      }
      
      //clear local captcha errors
      var localErrors = root.querySelectorAll('.text-danger, .img-captcha__error');
      for (var j = 0; j < localErrors.length; j++) localErrors[j].remove();

      //clear global non-field form errors from the container
      var container = root.closest('.card, .container, body');
      if (container) {
        var globalErrors = container.querySelectorAll('.alert-danger');
        for (var k = 0; k < globalErrors.length; k++) globalErrors[k].remove();
      }

      root.dispatchEvent(new CustomEvent('image-captcha:refreshed', { bubbles: true }));
    }

    if (!img.getAttribute('src')) {
      refresh();
    }

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      refresh();
    });
  }

  function init(scope) {
    var roots = (scope || document).querySelectorAll('[data-image-captcha]');
    for (var i = 0; i < roots.length; i++) bindWidget(roots[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { init(document); });
  } else {
    init(document);
  }

  window.ImageCaptcha = { init: init };
})();
