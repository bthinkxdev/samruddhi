/*
 * Product picker on the collection form: search products, add them to the
 * collection (one at a time or several at once via checkboxes), remove them.
 * The chosen ids are submitted as repeated hidden "products" inputs, which the
 * form saves as the collection's membership.
 * All text is inserted with textContent, never as HTML.
 */
(function () {
  "use strict";

  var root = document.getElementById("collection-products");
  if (!root) return;

  var searchInput = document.getElementById("collection-product-search");
  var resultsBox = document.getElementById("collection-product-results");
  var resultsList = document.getElementById("collection-product-results-list");
  var resultsHead = document.getElementById("collection-product-results-head");
  var resultsFoot = document.getElementById("collection-product-results-foot");
  var resultsMeta = document.getElementById("collection-product-results-meta");
  var selectAll = document.getElementById("collection-product-select-all");
  var addSelectedBtn = document.getElementById("collection-product-add-selected");
  var cancelBtn = document.getElementById("collection-product-cancel");
  var listEl = document.getElementById("collection-product-list");
  var emptyEl = document.getElementById("collection-product-empty");
  var inputsEl = document.getElementById("collection-product-inputs");
  var countEl = document.getElementById("collection-product-count");
  var selected = new Map(); //products in the collection
  var pending = new Map(); //products ticked in the search results, not yet added
  var shown = []; //products currently listed in the search results
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

  function syncBulkControls() {
    addSelectedBtn.textContent = "Add selected (" + pending.size + ")";
    addSelectedBtn.disabled = pending.size === 0;
    var tickedShown = shown.filter(function (product) {
      return pending.has(product.id);
    }).length;
    selectAll.checked = shown.length > 0 && tickedShown === shown.length;
    selectAll.indeterminate = tickedShown > 0 && tickedShown < shown.length;
  }

  function hideResults() {
    resultsBox.hidden = true;
    resultsList.replaceChildren();
    shown = [];
    pending.clear();
    syncBulkControls();
  }

  //add products to the collection (skipping any already in it), then reset the search
  function addProducts(products) {
    products.forEach(function (product) {
      if (!selected.has(product.id)) selected.set(product.id, product);
    });
    render();
    hideResults();
    searchInput.value = "";
    searchInput.focus();
  }

  function setTicked(product, row, checkbox, ticked) {
    checkbox.checked = ticked;
    row.classList.toggle("is-checked", ticked);
    if (ticked) pending.set(product.id, product);
    else pending.delete(product.id);
  }

  function showResults(products, hasMore) {
    resultsList.replaceChildren();
    //products already in the collection are never offered again
    shown = products.filter(function (product) {
      return !selected.has(product.id);
    });
    //ticks survive a refined search only for products still listed
    pending.forEach(function (product, id) {
      if (!shown.some(function (p) { return p.id === id; })) pending.delete(id);
    });

    resultsHead.hidden = resultsFoot.hidden = !shown.length;
    if (!shown.length) {
      resultsList.appendChild(el("div", "list-group-item text-secondary small", "No matching products to add."));
    } else {
      resultsMeta.textContent =
        shown.length + (shown.length === 1 ? " product" : " products") +
        (hasMore ? " · showing first matches, type more to narrow" : "");
    }

    shown.forEach(function (product) {
      //clicking anywhere on the row ticks it; the row's "Add" button adds just this product
      var row = el("label", "list-group-item list-group-item-action d-flex align-items-center gap-3 mb-0");
      var checkbox = el("input", "form-check-input");
      checkbox.type = "checkbox";
      checkbox.value = product.id;
      checkbox.setAttribute("aria-label", "Select " + product.name);
      checkbox.checked = pending.has(product.id);
      row.classList.toggle("is-checked", checkbox.checked);
      checkbox.addEventListener("change", function () {
        setTicked(product, row, checkbox, checkbox.checked);
        syncBulkControls();
      });
      row.appendChild(checkbox);
      row.appendChild(thumb(product));
      var info = describe(product);
      info.classList.add("flex-grow-1");
      row.appendChild(info);

      var addOne = el("button", "btn btn-sm btn-outline-primary");
      addOne.type = "button";
      addOne.title = "Add only this product";
      addOne.setAttribute("aria-label", "Add " + product.name);
      addOne.appendChild(el("i", "ti ti-plus"));
      addOne.addEventListener("click", function (event) {
        event.preventDefault(); //don't let the label toggle the checkbox
        event.stopPropagation();
        addProducts([product]);
      });
      row.appendChild(addOne);
      resultsList.appendChild(row);
    });
    resultsBox.hidden = false;
    syncBulkControls();
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
        //ignore a late response once the box has been cleared
        if (searchInput.value.trim().length < 2) return;
        showResults(data.results, data.has_more);
      })
      .catch(function (error) {
        if (error.name !== "AbortError") hideResults();
      });
  }

  selectAll.addEventListener("change", function () {
    var ticked = selectAll.checked;
    Array.prototype.forEach.call(resultsList.querySelectorAll("label.list-group-item"), function (row, i) {
      setTicked(shown[i], row, row.querySelector("input[type=checkbox]"), ticked);
    });
    syncBulkControls();
  });
  addSelectedBtn.addEventListener("click", function () {
    if (pending.size) addProducts(Array.from(pending.values()));
  });
  cancelBtn.addEventListener("click", function () {
    hideResults();
    searchInput.value = "";
    searchInput.focus();
  });

  searchInput.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    var query = searchInput.value.trim();
    if (query.length < 2) {
      //also covers the search box's own "x" clear button
      if (inFlight) inFlight.abort();
      hideResults();
      return;
    }
    debounceTimer = setTimeout(function () {
      search(query);
    }, 250);
  });
  searchInput.addEventListener("keydown", function (event) {
    //Enter must not submit the collection form while searching; with ticks it adds them
    if (event.key === "Enter") {
      event.preventDefault();
      if (pending.size) addProducts(Array.from(pending.values()));
    }
    if (event.key === "Escape") hideResults();
  });
  document.addEventListener("click", function (event) {
    //close on an outside click, unless products are ticked (don't silently drop a selection)
    if (!resultsBox.hidden && !root.contains(event.target) && !pending.size) hideResults();
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
