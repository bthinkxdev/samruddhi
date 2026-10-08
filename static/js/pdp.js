(function () {
  var variantGroup = document.getElementById('variant-select-group');
  var variantRadios = document.querySelectorAll('.variant-radio');
  if (variantGroup && variantRadios.length > 0) {
    variantRadios.forEach(function (radio) {
      radio.addEventListener('change', function () {
        var url = variantGroup.getAttribute('data-price-url');
        var vid = this.value;

        document.querySelectorAll('.pdp-variant-id-input').forEach(function (input) {
          input.value = vid;
        });

        var qtyInput = document.getElementById('pdp-qty');
        if (qtyInput) qtyInput.value = '1';
        document.querySelectorAll('.pdp-qty-input').forEach(function (input) {
          input.value = '1';
        });
        var qty = '1';
        var queryString = '?quantity=' + qty + (vid ? '&variant_id=' + vid : '');

        fetch(url + queryString)
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var el = document.getElementById('pdp-price');
            var elSticky = document.getElementById('pdp-sticky-price');
            var retailContainer = document.getElementById('pdp-retail-price-container');
            var symbol = variantGroup.getAttribute('data-currency-symbol') || '';
            var elPriceValue = document.getElementById('pdp-price-value');

            if (elPriceValue) {
              elPriceValue.textContent = symbol + ' ' + parseFloat(data.price).toFixed(2).replace(/\.00$/, '');
            }

            var elMrp = document.getElementById('pdp-price-mrp');
            if (elMrp) {
              if (data.is_flash_sale !== 'true' && data.has_mrp_discount === 'true' && data.mrp) {
                elMrp.textContent = symbol + ' ' + parseFloat(data.mrp).toFixed(2).replace(/\.00$/, '');
                elMrp.style.display = 'inline';
              } else {
                elMrp.style.display = 'none';
              }
            }

            if (retailContainer) {
              if (data.is_tier_active === 'true') {
                retailContainer.classList.remove("d-none");
              } else {
                retailContainer.classList.add("d-none");
              }
            }
            if (elSticky) elSticky.textContent = symbol + ' ' + parseFloat(data.price).toFixed(2).replace(/\.00$/, '');
            
            var stickyVariantName = document.getElementById('pdp-sticky-variant-name');
            if (stickyVariantName) {
              var checkedLabel = document.querySelector('label[for="variant_' + vid + '"]');
              if (checkedLabel) {
                 var nameText = checkedLabel.childNodes[0].textContent.trim();
                 stickyVariantName.textContent = nameText;
              }
            }

            var elRetail = document.getElementById('pdp-retail-price');
            if (elRetail && data.retail_price) {
              elRetail.textContent = symbol + ' ' + parseFloat(data.retail_price).toFixed(2).replace(/\.00$/, '');
            }
            var elRetailVal = document.getElementById('pdp-retail-price-val');
            if (elRetailVal && data.retail_price) {
              elRetailVal.value = data.retail_price;
            }

            if (data.is_in_cart !== undefined) {
              var addGroup = document.getElementById('pdp-add-to-cart-group');
              var viewGroup = document.getElementById('pdp-view-cart-group');
              var stickyAdd = document.getElementById('sticky-buy-form');
              var stickyView = document.getElementById('pdp-sticky-view-cart-btn');

              if (data.is_in_cart) {
                if (addGroup) addGroup.classList.add('d-none');
                if (viewGroup) viewGroup.classList.remove('d-none');
                if (stickyAdd) stickyAdd.classList.add('d-none');
                if (stickyView) stickyView.classList.remove('d-none');
              } else {
                if (addGroup) addGroup.classList.remove('d-none');
                if (viewGroup) viewGroup.classList.add('d-none');
                if (stickyAdd) stickyAdd.classList.remove('d-none');
                if (stickyView) stickyView.classList.add('d-none');
              }
            }

            if (data.is_in_stock !== undefined) {
              var atcBtn = document.querySelector('#buy-form button');
              var bnForm = document.getElementById('buy-now-form');
              var qtyStepper = document.querySelector('.jm-pdp-qty');
              var stickyAtcBtn = document.querySelector('#sticky-buy-form button');
              var stickyBnForm = document.getElementById('sticky-buy-now-form');

              if (data.is_in_stock) {
                if (atcBtn) {
                  atcBtn.type = 'submit';
                  atcBtn.classList.remove('disabled');
                  atcBtn.style.cursor = 'pointer';
                  atcBtn.style.opacity = '1';
                  atcBtn.style.pointerEvents = 'auto';
                  atcBtn.onclick = null;
                  atcBtn.textContent = 'Add to Cart';
                }
                if (stickyAtcBtn) {
                  stickyAtcBtn.type = 'submit';
                  stickyAtcBtn.classList.remove('disabled');
                  stickyAtcBtn.style.cursor = 'pointer';
                  stickyAtcBtn.style.opacity = '1';
                  stickyAtcBtn.style.pointerEvents = 'auto';
                  stickyAtcBtn.onclick = null;
                  var stText = stickyAtcBtn.querySelector('.btn-text');
                  if (stText) stText.textContent = 'Add to cart';
                  else stickyAtcBtn.textContent = 'Add to cart';
                }
                if (bnForm) bnForm.classList.remove('d-none');
                if (stickyBnForm) stickyBnForm.classList.remove('d-none');
                if (qtyStepper) qtyStepper.style.opacity = '1';
              } else {
                if (atcBtn) {
                  atcBtn.type = 'button';
                  atcBtn.classList.add('disabled');
                  atcBtn.style.cursor = 'not-allowed';
                  atcBtn.style.opacity = '0.6';
                  atcBtn.style.pointerEvents = 'auto';
                  atcBtn.onclick = function (e) { e.preventDefault(); return false; };
                  atcBtn.textContent = 'Sold out';
                }
                if (stickyAtcBtn) {
                  stickyAtcBtn.type = 'button';
                  stickyAtcBtn.classList.add('disabled');
                  stickyAtcBtn.style.cursor = 'not-allowed';
                  stickyAtcBtn.style.opacity = '0.6';
                  stickyAtcBtn.style.pointerEvents = 'auto';
                  stickyAtcBtn.onclick = function (e) { e.preventDefault(); return false; };
                  var stText = stickyAtcBtn.querySelector('.btn-text');
                  if (stText) stText.textContent = 'Sold out';
                  else stickyAtcBtn.textContent = 'Sold out';
                }
                if (bnForm) bnForm.classList.add('d-none');
                if (stickyBnForm) stickyBnForm.classList.add('d-none');
                if (qtyStepper) qtyStepper.style.opacity = '0.5';
              }

              var stockText = document.getElementById('pdp-stock-text');
              if (stockText) {
                if (data.is_in_stock) {
                  stockText.classList.remove('is-out');
                  if (data.stock_quantity !== undefined && data.low_stock_threshold !== undefined && data.stock_quantity <= data.low_stock_threshold) {
                    stockText.classList.remove('is-in');
                    stockText.classList.add('is-low');
                    stockText.innerHTML = 'Only ' + data.stock_quantity + ' left';
                  } else {
                    stockText.classList.remove('is-low');
                    stockText.classList.add('is-in');
                    stockText.innerHTML = 'In stock';
                  }
                } else {
                  stockText.classList.remove('is-in');
                  stockText.classList.remove('is-low');
                  stockText.classList.add('is-out');
                  stockText.textContent = 'Out of stock';
                }
              }
            }
            if (data.stock_quantity !== undefined) {
              var qtyInput = document.getElementById('pdp-qty');
              if (qtyInput) qtyInput.setAttribute('data-max-stock', data.stock_quantity);
            }
            if (window.validatePdpStock) window.validatePdpStock();
          });
      });
    });

    var checkedRadio = document.querySelector('.variant-radio:checked');
    if (checkedRadio) {
      checkedRadio.dispatchEvent(new Event('change'));
    }
  }

  var citySelect = document.getElementById('delivery-city');
  if (citySelect) {
    citySelect.addEventListener('change', function () {
      if (!this.value) {
        return;
      }
      var url = this.getAttribute('data-estimate-url') + '?city=' + encodeURIComponent(this.value);
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var el = document.getElementById('delivery-estimate-text');
          if (el) el.textContent = 'Delivery: ' + data.label + ' to ' + data.city;
        });
    });
  }

  window.handlePdpQtyChange = function (delta) {
    var qtyInput = document.getElementById('pdp-qty');
    if (!qtyInput) return;
    var maxStock = parseInt(qtyInput.getAttribute('data-max-stock'));
    var currQty = parseInt(qtyInput.value) || 1;
    var errorMsg = document.getElementById('pdp-stock-error-msg');

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
    document.querySelectorAll('.pdp-qty-input').forEach(function (i) { i.value = newQty; });

    if (errorMsg) {
      errorMsg.classList.add('d-none');
      errorMsg.textContent = '';
    }
    if (window.validatePdpStock) window.validatePdpStock();
  };

  window.validatePdpStock = function () {
    var qtyInput = document.getElementById('pdp-qty');
    if (!qtyInput) return;
    var maxStock = parseInt(qtyInput.getAttribute('data-max-stock'));
    if (isNaN(maxStock)) return;
    var currQty = parseInt(qtyInput.value) || 1;
    var errorMsg = document.getElementById('pdp-stock-error-msg');
    var atcBtn = document.querySelector('#buy-form button');
    var bnBtn = document.querySelector('#buy-now-form button');
    var stickyAtcBtn = document.querySelector('#sticky-buy-form button');
    var stickyBnBtn = document.querySelector('#sticky-buy-now-form button');
    var allBtns = [atcBtn, bnBtn, stickyAtcBtn, stickyBnBtn].filter(Boolean);

    if (currQty > maxStock && maxStock > 0) {
      currQty = maxStock;
      qtyInput.value = maxStock;
      document.querySelectorAll('.pdp-qty-input').forEach(function (i) { i.value = maxStock; });
    }

    if (maxStock <= 0) {
      if (errorMsg) {
        errorMsg.textContent = '';
        errorMsg.classList.add('d-none');
      }
      allBtns.forEach(function (btn) {
        btn.type = 'button';
        btn.classList.add('disabled');
        btn.style.cursor = 'not-allowed';
        btn.style.opacity = '0.6';
        btn.style.pointerEvents = 'auto';
        btn.onclick = function (e) { e.preventDefault(); return false; };
      });
      if (atcBtn) atcBtn.textContent = 'Sold out';
      if (stickyAtcBtn) {
        var stText = stickyAtcBtn.querySelector('.btn-text');
        if (stText) stText.textContent = 'Sold out';
        else stickyAtcBtn.textContent = 'Sold out';
      }
    } else {
      if (errorMsg) {
        errorMsg.textContent = '';
        errorMsg.classList.add('d-none');
      }
      allBtns.forEach(function (btn) {
        btn.type = 'submit';
        btn.classList.remove('disabled');
        btn.style.cursor = 'pointer';
        btn.style.opacity = '1';
        btn.style.pointerEvents = 'auto';
        btn.onclick = null;
      });
      if (atcBtn) atcBtn.textContent = 'Add to Cart';
      if (stickyAtcBtn) {
        var stText = stickyAtcBtn.querySelector('.btn-text');
        if (stText) stText.textContent = 'Add to cart';
        else stickyAtcBtn.textContent = 'Add to cart';
      }
    }
  };

  if (window.validatePdpStock) window.validatePdpStock();
  var galleryModal = document.getElementById('pdpGalleryModal');
  if (galleryModal) {
    galleryModal.addEventListener('show.bs.modal', function () {
      var carouselEl = document.getElementById('pdpGalleryCarousel');
      if (carouselEl) {
        var bsCarousel = bootstrap.Carousel.getInstance(carouselEl);
        if (!bsCarousel && window.bootstrap) {
          bsCarousel = new bootstrap.Carousel(carouselEl);
        }
        if (bsCarousel) {
          var activeThumb = document.querySelector('.jm-pdp-gallery__thumb.is-active');
          if (activeThumb) {
            var thumbs = Array.from(document.querySelectorAll('.jm-pdp-gallery__thumb'));
            var activeIndex = thumbs.indexOf(activeThumb);
            if (activeIndex > -1) {
              bsCarousel.to(activeIndex);
            }
          }
        }
      }
    });
  }

})();
