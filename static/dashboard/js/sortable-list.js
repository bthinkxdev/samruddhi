/*
 * Drag-and-drop row ordering for dashboard lists.
 *
 * Markup contract: <tbody data-sortable data-reorder-url="..." data-csrf="...">
 * with <tr data-id="..."> rows, each holding a .drag-handle button. Works with
 * mouse, touch and pen (pointer events) and with the arrow keys on a focused
 * handle. The full id order is POSTed as JSON; on failure the rows snap back.
 */
(function () {
  "use strict";

  var body = document.querySelector("[data-sortable]");
  if (!body) return;

  var statusEl = document.getElementById("sortable-status");
  var dragging = null;
  var orderBefore = null;

  function currentOrder() {
    return Array.prototype.map.call(body.querySelectorAll("tr[data-id]"), function (row) {
      return Number(row.dataset.id);
    });
  }

  function setStatus(message, ok) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "small mt-2 " + (ok ? "text-success" : "text-danger");
  }

  function restore(order) {
    order.forEach(function (id) {
      var row = body.querySelector('tr[data-id="' + id + '"]');
      if (row) body.appendChild(row);
    });
  }

  function save(order, previous) {
    fetch(body.dataset.reorderUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": body.dataset.csrf },
      body: JSON.stringify({ order: order }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "Could not save the new order.");
        });
      })
      .then(function () {
        setStatus("Order saved.", true);
      })
      .catch(function (error) {
        restore(previous);
        setStatus(error.message, false);
      });
  }

  function commitIfChanged(previous) {
    var order = currentOrder();
    if (order.join() !== previous.join()) save(order, previous);
  }

  body.addEventListener("pointerdown", function (event) {
    var handle = event.target.closest(".drag-handle");
    if (!handle) return;
    dragging = handle.closest("tr[data-id]");
    orderBefore = currentOrder();
    dragging.classList.add("is-dragging");
    handle.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  body.addEventListener("pointermove", function (event) {
    if (!dragging) return;
    var under = document.elementFromPoint(event.clientX, event.clientY);
    var row = under && under.closest("tr[data-id]");
    if (!row || row === dragging || row.parentNode !== body) return;
    var rect = row.getBoundingClientRect();
    var after = event.clientY > rect.top + rect.height / 2;
    body.insertBefore(dragging, after ? row.nextSibling : row);
  });

  function finishDrag() {
    if (!dragging) return;
    dragging.classList.remove("is-dragging");
    dragging = null;
    commitIfChanged(orderBefore);
  }
  body.addEventListener("pointerup", finishDrag);
  body.addEventListener("pointercancel", finishDrag);

  body.addEventListener("keydown", function (event) {
    var handle = event.target.closest(".drag-handle");
    if (!handle || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    var row = handle.closest("tr[data-id]");
    var previous = currentOrder();
    if (event.key === "ArrowUp" && row.previousElementSibling) {
      body.insertBefore(row, row.previousElementSibling);
    } else if (event.key === "ArrowDown" && row.nextElementSibling) {
      body.insertBefore(row.nextElementSibling, row);
    } else {
      return;
    }
    event.preventDefault();
    handle.focus();
    commitIfChanged(previous);
  });
})();
