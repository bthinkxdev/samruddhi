
(function () {
  "use strict";


  function initSidebar() {
    var sidebar = document.getElementById("sidebar");
    var content = document.getElementById("content");
    var topbar = document.getElementById("topbar");
    var toggleBtn = document.getElementById("toggleBtn");
    var mobileBtn = document.getElementById("mobileBtn");
    var overlay = document.getElementById("overlay");

    if (toggleBtn) {
      toggleBtn.addEventListener("click", function () {
        if (sidebar) sidebar.classList.toggle("collapsed");
        if (content) content.classList.toggle("full");
        if (topbar) topbar.classList.toggle("full");
      });
    }
    if (mobileBtn) {
      mobileBtn.addEventListener("click", function () {
        if (sidebar) sidebar.classList.add("mobile-show");
        if (overlay) overlay.classList.add("show");
      });
    }
    if (overlay) {
      overlay.addEventListener("click", function () {
        if (sidebar) sidebar.classList.remove("mobile-show");
        if (overlay) overlay.classList.remove("show");
      });
    }

    if (sidebar) {
      var activeLink = sidebar.querySelector(".nav-link.active");
      if (activeLink) {
        activeLink.scrollIntoView({ block: "center" });
      }
    }
  }


  function initFormValidation() {
    var forms = document.querySelectorAll(".needs-validation");
    Array.prototype.forEach.call(forms, function (form) {
      form.addEventListener(
        "submit",
        function (event) {
          if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
          }
          form.classList.add("was-validated");
        },
        false
      );
    });
  }


  function readJSON(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return fallback;
    }
  }

  function currency(val) {
    var n = Number(val || 0);
    return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function initCharts() {
    if (typeof ApexCharts === "undefined") return;


    var salesEl = document.querySelector("#salesChart");
    if (salesEl) {
      var sales = readJSON("sales-chart-data", { categories: [], revenue: [], orders: [] });
      new ApexCharts(salesEl, {
        chart: {
          type: "area",
          height: 360,
          fontFamily: "Poppins, sans-serif",
          toolbar: { show: false },
          zoom: { enabled: false },
        },
        colors: ["#e66239", "#2e90fa"],
        stroke: { width: [3, 2], curve: "smooth" },
        dataLabels: { enabled: false },
        series: [
          { name: "Revenue", data: sales.revenue },
          { name: "Orders", data: sales.orders },
        ],
        fill: {
          type: "gradient",
          gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.02, stops: [0, 100] },
        },
        grid: { borderColor: "#eef0f3", strokeDashArray: 4, padding: { left: 8, right: 8 } },
        xaxis: {
          categories: sales.categories,
          tickPlacement: "on",
          axisBorder: { show: false },
          axisTicks: { show: false },
          labels: { style: { colors: "#667085", fontSize: "11px" } },
        },
        yaxis: [
          { labels: { formatter: currency, style: { colors: "#667085" } } },
          {
            opposite: true,
            labels: {
              formatter: function (v) { return Math.round(v); },
              style: { colors: "#667085" },
            },
          },
        ],
        tooltip: { shared: true },
        legend: { position: "top", horizontalAlign: "right", markers: { radius: 12 } },
      }).render();
    }

    var custEl = document.querySelector("#customerChart");
    if (custEl) {
      var cust = readJSON("customer-chart-data", { series: [0, 0] });
      new ApexCharts(custEl, {
        chart: { type: "donut", height: 260, fontFamily: "Poppins, sans-serif" },
        colors: ["#e66239", "#2e90fa"],
        series: cust.series,
        labels: ["New", "Returning"],
        stroke: { width: 0 },
        legend: { position: "bottom", markers: { radius: 12 } },
        dataLabels: {
          enabled: true,
          formatter: function (val) { return Math.round(val) + "%"; },
          style: { fontSize: "12px", fontWeight: 600 },
          dropShadow: { enabled: false },
        },
        plotOptions: {
          pie: {
            donut: {
              size: "70%",
              labels: {
                show: true,
                total: {
                  show: true,
                  label: "Customers",
                  fontSize: "13px",
                  color: "#667085",
                  formatter: function () { return "100%"; },
                },
              },
            },
          },
        },
      }).render();
    }
  }

  // ---- Dynamic inline formsets (product variants / images) ---------------
  function initFormsets() {
    var wraps = document.querySelectorAll("[data-formset]");
    Array.prototype.forEach.call(wraps, function (wrap) {
      var prefix = wrap.getAttribute("data-formset");
      var total = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
      var body = wrap.querySelector("[data-formset-body]");
      var tmpl = wrap.querySelector("template[data-formset-empty]");
      var addBtn = wrap.querySelector("[data-formset-add]");

      if (addBtn && total && body && tmpl) {
        addBtn.addEventListener("click", function () {
          var idx = parseInt(total.value, 10);
          var html = tmpl.innerHTML.replace(/__prefix__/g, idx);
          var holder = document.createElement("tbody");
          holder.innerHTML = html.trim();
          var row = holder.firstElementChild;
          if (row) {
            body.appendChild(row);
            total.value = idx + 1;
          }
        });
      }

      //hide any rows that are already marked for deletion on load (e.g. on validation re-render)
      var deleteCheckboxes = wrap.querySelectorAll("input[name$='-DELETE']");
      Array.prototype.forEach.call(deleteCheckboxes, function (cb) {
        if (cb.checked) {
          var row = cb.closest("tr");
          if (row) {
            row.style.display = "none";
          }
        }
      });

      wrap.addEventListener("click", function (e) {
        //handle row delete/remove
        var btnRemove = e.target.closest ? e.target.closest("[data-row-remove]") : null;
        if (btnRemove) {
          var row = btnRemove.closest("tr");
          if (row) {
            var idInput = row.querySelector("input[name$='-id']");
            var isExisting = idInput && idInput.value;

            if (isExisting) {
              var deleteCheckbox = row.querySelector("input[name$='-DELETE']");
              if (deleteCheckbox) {
                deleteCheckbox.checked = true;
              }
            } else {
              Array.prototype.forEach.call(row.querySelectorAll("input, select, textarea"), function (inp) {
                if (inp.type === "checkbox" || inp.type === "radio") inp.checked = false;
                else if (inp.type !== "hidden") inp.value = "";
              });
            }
            row.style.display = "none";
          }
          return;
        }

        //handle custom replace file button click
        var btnReplace = e.target.closest ? e.target.closest("[data-replace-file-btn]") : null;
        if (btnReplace) {
          var container = btnReplace.closest("[data-existing-file-container]");
          var fileInput = container ? container.querySelector("input[type='file']") : null;
          if (fileInput) {
            fileInput.click();
          }
        }
      });

      wrap.addEventListener("change", function (e) {
        var inp = e.target;
        if (inp.type === "file" && inp.files && inp.files[0]) {
          var fileUrl = URL.createObjectURL(inp.files[0]);

          //update custom label if inside an existing file container
          var container = inp.closest("[data-existing-file-container]");
          if (container) {
            var label = container.querySelector("[data-file-label]");
            if (label) {
              label.innerHTML = '<i class="ti ti-file-text me-1 text-success"></i>' + inp.files[0].name;
            }
          }

          //image preview logic
          var row = inp.closest("tr");
          var prev = row ? row.querySelector("[data-img-preview]") : null;
          if (prev) {
            if (prev.src && prev.src.startsWith("blob:")) {
              URL.revokeObjectURL(prev.src);
            }
            prev.src = fileUrl;
            prev.classList.remove("d-none");
          }

          //document view button update logic
          var viewContainer = row ? row.querySelector("[data-view-container]") : null;
          if (viewContainer) {
            var viewBtn = viewContainer.querySelector("[data-view-btn]");
            if (viewBtn) {
              if (viewBtn.href && viewBtn.href.startsWith("blob:")) {
                URL.revokeObjectURL(viewBtn.href);
              }
              viewBtn.href = fileUrl;
            } else {
              var placeholder = viewContainer.querySelector("[data-view-placeholder]");
              if (placeholder) {
                placeholder.remove();
              }
              viewContainer.innerHTML = '<a href="' + fileUrl + '" target="_blank" class="btn btn-icon btn-sm btn-light text-info" data-view-btn title="View Document"><i class="ti ti-eye"></i></a>';
            }
          }
        }
      });
    });
  }

  function initTableLabels() {
    var tables = document.querySelectorAll(".table:not(.repeater)");
    Array.prototype.forEach.call(tables, function (table) {
      var headers = table.querySelectorAll("thead th");
      var headerTexts = [];
      Array.prototype.forEach.call(headers, function (th) {
        headerTexts.push(th.textContent.trim());
      });
      var rows = table.querySelectorAll("tbody tr");
      Array.prototype.forEach.call(rows, function (tr) {
        var cells = tr.querySelectorAll("td");
        if (cells.length === 1 && cells[0].hasAttribute("colspan")) {
          tr.classList.add("empty-row-card");
          return;
        }
        Array.prototype.forEach.call(cells, function (td, i) {
          if (headerTexts[i] && !td.getAttribute("data-label")) {
            td.setAttribute("data-label", headerTexts[i]);
          }
          if (!td.querySelector(".td-content")) {
            var wrapper = document.createElement("div");
            wrapper.className = "td-content";
            while (td.firstChild) {
              wrapper.appendChild(td.firstChild);
            }
            td.appendChild(wrapper);
          }
        });
      });
    });
  }

  function initFilterForms() {
    document.querySelectorAll("[data-filter-submit]").forEach(function (button) {
      var form = button.form;
      if (!form) return;

      var filters = Array.prototype.filter.call(form.elements, function (el) {
        if (!el.name) return false;
        return el.tagName === "SELECT" || (el.tagName === "INPUT" && el.type === "date");
      });
      if (!filters.length) return;

      var applied = filters.map(function (select) {
        if (select.tagName === "INPUT") return select.defaultValue;
        var options = Array.prototype.slice.call(select.options);
        var selected = options.filter(function (opt) { return opt.defaultSelected; })[0];
        return selected ? selected.value : (options[0] ? options[0].value : "");
      });

      function hasChanges() {
        return filters.some(function (select, i) {
          return select.value !== applied[i];
        });
      }

      function sync() {
        button.disabled = !hasChanges();
      }

      filters.forEach(function (select) {
        select.addEventListener("change", sync);
        if (select.tagName === "INPUT") select.addEventListener("input", sync);
      });
      window.addEventListener("pageshow", sync);
      sync();

      form.addEventListener("submit", function (event) {
        if (event.submitter === button && !hasChanges()) {
          event.preventDefault();
        }
      });

      var search = form.querySelector('input[name="q"]');
      if (search) {
        var appliedQuery = search.defaultValue.trim();
        search.addEventListener("keydown", function (event) {
          if (event.key !== "Enter") return;
          event.preventDefault();
          if (search.value.trim() !== appliedQuery || hasChanges()) {
            form.submit();
          }
        });
      }
    });
  }

  
  function initDateRanges() {
    document.querySelectorAll("input[data-min-from]").forEach(function (end) {
      var start = document.getElementById(end.getAttribute("data-min-from"));
      if (!start) return;
      var ownMin = end.getAttribute("min") || "";
      function sync() {
        var min = start.value && start.value > ownMin ? start.value : ownMin;
        if (min) end.setAttribute("min", min);
      }
      start.addEventListener("change", sync);
      start.addEventListener("input", sync);
      sync();
    });
  }

  var SUBMIT_LOCK_SELECTOR = 'button[type="submit"], button:not([type]), input[type="submit"]';
  var SPINNER_HTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>';

  function submitButtons(form) {
    return Array.prototype.filter.call(form.elements, function (el) {
      return el.matches(SUBMIT_LOCK_SELECTOR);
    });
  }

  function lockForm(form, submitter) {
    form.dataset.submitting = "1";
    form.setAttribute("aria-busy", "true");

    setTimeout(function () {
      submitButtons(form).forEach(function (btn) {
        if (btn.disabled) return;
        btn.dataset.submitLocked = "1";
        btn.disabled = true;
        if (btn === submitter && btn.tagName === "BUTTON") {
          btn.dataset.submitLabel = btn.innerHTML;
          btn.insertAdjacentHTML("afterbegin", SPINNER_HTML);
        }
      });
    }, 0);
  }

  function unlockForm(form) {
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    submitButtons(form).forEach(function (btn) {
      if (!btn.dataset.submitLocked) return;
      btn.disabled = false;
      if (btn.dataset.submitLabel !== undefined) btn.innerHTML = btn.dataset.submitLabel;
      delete btn.dataset.submitLocked;
      delete btn.dataset.submitLabel;
    });
  }

  function initSubmitLock() {
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      if ((form.getAttribute("method") || "get").toLowerCase() !== "post") return;
      if (form.hasAttribute("data-no-submit-lock")) return;

      if (form.dataset.submitting) {
        event.preventDefault(); 
        return;
      }
      if (event.defaultPrevented) return; 

      lockForm(form, event.submitter || null);

      var target = (event.submitter && event.submitter.getAttribute("formtarget")) || form.getAttribute("target");
      if (target && target !== "_self") {
        setTimeout(function () { unlockForm(form); }, 2000);
      }
    });

    window.addEventListener("pageshow", function (event) {
      if (!event.persisted) return;
      document.querySelectorAll("form[data-submitting]").forEach(unlockForm);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSidebar();
    initSubmitLock();
    initFormValidation();
    initCharts();
    initFormsets();
    initTableLabels();
    initFilterForms();
    initDateRanges();
  });
})();
