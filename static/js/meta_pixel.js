/*
 * Meta Pixel event dispatcher.
 *
 * The pixel base code + PageView live in includes/meta_pixel.html. Event payloads are
 * built server-side (core/meta_pixel.py) and reach the browser three ways:
 *   1. <script id="mpx-events"> JSON rendered by base.html on full page loads
 *   2. an `mpxEvent` HX-Trigger on HTMX responses (cart / wishlist actions)
 *   3. window.mpx.track() calls from inline page scripts (Razorpay result)
 * Event shape: { name, params, custom, event_id }.
 */
(function () {
  'use strict';

  if (typeof window.fbq !== 'function') {
    return;
  }

  var checkoutParams = null;
  var paymentInfoSent = {};

  function newEventId() {
    return 'ev_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  function purchaseAlreadySent(eventId) {
    try {
      return !!localStorage.getItem('mpx_purchase_' + eventId);
    } catch (e) {
      return false;
    }
  }

  function markPurchaseSent(eventId) {
    try {
      localStorage.setItem('mpx_purchase_' + eventId, '1');
    } catch (e) { }
  }

  function send(evt) {
    if (!evt || !evt.name) {
      return;
    }
    var eventId = evt.event_id || newEventId();
    var isPurchase = evt.name === 'Purchase';
    if (isPurchase && purchaseAlreadySent(eventId)) {
      return;
    }
    if (evt.name === 'InitiateCheckout') {
      checkoutParams = evt.params || null;
    }
    try {
      window.fbq(evt.custom ? 'trackCustom' : 'track', evt.name, evt.params || {}, { eventID: eventId });
      if (isPurchase) {
        markPurchaseSent(eventId);
      }
    } catch (e) {
      if (window.console) console.warn('[mpx] failed to send', evt.name, e);
    }
  }

  function firePageEvents() {
    var el = document.getElementById('mpx-events');
    if (!el) {
      return;
    }
    var events = [];
    try {
      events = JSON.parse(el.textContent || '[]');
    } catch (e) {
      return;
    }
    events.forEach(send);
  }

  // Server-triggered events on HTMX responses (add/remove cart, wishlist).
  document.body.addEventListener('mpxEvent', function (event) {
    send(event.detail);
  });

  // AddPaymentInfo: the customer submitted a valid checkout form with a chosen method.
  // checkout.html's own beforeRequest handler cancels invalid submits first, so a
  // defaultPrevented event here means validation failed and nothing was placed.
  document.body.addEventListener('htmx:beforeRequest', function (event) {
    var elt = event.detail && event.detail.elt;
    if (!elt || elt.id !== 'checkout-form' || event.defaultPrevented || !checkoutParams) {
      return;
    }
    var selected = document.querySelector('input[name="gateway_key"]:checked');
    var gateway = selected ? selected.value : '';
    if (!gateway || paymentInfoSent[gateway]) {
      return;
    }
    paymentInfoSent[gateway] = true;
    var params = {};
    Object.keys(checkoutParams).forEach(function (key) { params[key] = checkoutParams[key]; });
    params.payment_method = gateway === 'cod' ? 'cod' : 'online';
    params.payment_gateway = gateway;
    send({ name: 'AddPaymentInfo', params: params });
  });

  window.mpx = {
    track: function (name, params, custom) {
      send({ name: name, params: params || {}, custom: !!custom });
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', firePageEvents);
  } else {
    firePageEvents();
  }
})();
