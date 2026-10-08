/*
 * Product picker on the collection form: search products, add them to the
 * collection, remove them. The chosen ids are submitted as repeated hidden
 * "products" inputs, which the form saves as the collection's membership.
 * All text is inserted with textContent, never as HTML.
 */
(function () {
  "use strict";

  var root = document.getElementById("collection-products");
  if (!root) return;

  var searchInput = document.getElementById("collection-product-search");
  var resultsBox = document.getElementById("collection-product-results");
  var listEl = document.getElementById("collection-product-list");
  var emptyEl = document.getElementById("collection-product-empty");
  var inputsEl = document.getElementById("collection-product-inputs");
  var countEl = document.getElementById("collection-product-count");
  var selected = new Map();
  var debounceTimer = null;
  var inFlight = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function thumb(product) {
    if (product.image) {
      var img = el("img", "thumb");
      img.src = product.image;
      img.alt = "";
      return img;
    }
    return el("span", "thumb thumb-fallback", (product.name || "?").charAt(0).toUpperCase());
  }

  function describe(product) {
    var wrap = el("div", "list-main");
    wrap.appendChild(el("p", "list-title mb-0", product.name));
    wrap.appendChild(el("span", "text-secondary small", product.sku));
    return wrap;
  }

  function render() {
    listEl.replaceChildren();
    inputsEl.replaceChildren();
    selected.forEach(function (product) {
      var item = el("li", "list-group-item d-flex align-items-center gap-3");
      item.appendChild(thumb(product));
      var info = describe(product);
      info.classList.add("flex-grow-1");
      item.appendChild(info);
      var remove = el("button", "btn btn-sm btn-light text-danger");
      remove.type = "button";
      remove.title = "Remove from collection";
      remove.setAttribute("aria-label", "Remove " + product.name);
      remove.appendChild(el("i", "ti ti-x"));
      remove.addEventListener("click", function () {
        selected.delete(product.id);
        render();
      });
      item.appendChild(remove);
      listEl.appendChild(item);

      var hidden = el("input");
      hidden.type = "hidden";
      hidden.name = "products";
      hidden.value = product.id;
      inputsEl.appendChild(hidden);
    });
    countEl.textContent = selected.size;
    emptyEl.hidden = selected.size > 0;
  }

  function hideResults() {
    resultsBox.hidden = true;
    resultsBox.replaceChildren();
  }

  function showResults(products) {
    resultsBox.replaceChildren();
    var fresh = products.filter(function (product) {
      return !selected.has(product.id);
    });
    if (!fresh.length) {
      resultsBox.appendChild(el("div", "list-group-item text-secondary small", "No matching products to add."));
    }
    fresh.forEach(function (product) {
      var option = el("button", "list-group-item list-group-item-action d-flex align-items-center gap-3");
      option.type = "button";
      option.appendChild(thumb(product));
      option.appendChild(describe(product));
      option.addEventListener("click", function () {
        selected.set(product.id, product);
        render();
        hideResults();
        searchInput.value = "";
        searchInput.focus();
      });
      resultsBox.appendChild(option);
    });
    resultsBox.hidden = false;
  }

  function search(query) {
    if (inFlight) inFlight.abort();
    inFlight = new AbortController();
    fetch(root.dataset.searchUrl + "?q=" + encodeURIComponent(query), {
      credentials: "same-origin",
      signal: inFlight.signal,
    })
      .then(function (response) {
        if (!response.ok) throw new Error("Search failed");
        return response.json();
      })
      .then(function (data) {
        showResults(data.results);
      })
      .catch(function (error) {
        if (error.name !== "AbortError") hideResults();
      });
  }

  searchInput.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    var query = searchInput.value.trim();
    if (query.length < 2) {
      hideResults();
      return;
    }
    debounceTimer = setTimeout(function () {
      search(query);
    }, 250);
  });
  searchInput.addEventListener("keydown", function (event) {
    //Enter must not submit the collection form while searching
    if (event.key === "Enter") event.preventDefault();
    if (event.key === "Escape") hideResults();
  });
  document.addEventListener("click", function (event) {
    if (!root.contains(event.target)) hideResults();
  });

  JSON.parse(document.getElementById("collection-selected-products").textContent).forEach(
    function (product) {
      selected.set(product.id, product);
    }
  );
  render();

  //the home page product count only matters while the collection is listed there
  var homepageToggle = document.getElementById("id_show_on_homepage");
  var limitWrap = document.getElementById("homepage-limit-wrap");
  if (homepageToggle && limitWrap) {
    var syncLimit = function () {
      limitWrap.hidden = !homepageToggle.checked;
    };
    homepageToggle.addEventListener("change", syncLimit);
    syncLimit();
  }
})();
