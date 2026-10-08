(function () {
  const form = document.getElementById("gift-builder-form");
  if (!form) return;

  function collectAddonIds() {
    const checked = form.querySelectorAll('input[name="addon_product_ids"]:checked');
    return Array.from(checked).map((el) => el.value);
  }

  function collectSelections() {
    const data = new FormData(form);
    return {
      personal_message: data.get("personal_message") || "",
      greeting_card_id: data.get("greeting_card_id") || null,
      gift_wrap_id: data.get("gift_wrap_id") || null,
      ribbon_id: data.get("ribbon_id") || null,
      photo_upload_id: data.get("photo_upload_id") || null,
      addon_product_ids: collectAddonIds(),
      delivery_date: data.get("delivery_date") || null,
      delivery_slot_id: data.get("delivery_slot_id") || null,
      delivery_instructions: data.get("delivery_instructions") || "",
      recipient_phone: data.get("recipient_phone") || "",
      is_anonymous: !!form.querySelector('[name="is_anonymous"]')?.checked,
      reveal_sender_after_delivery:
        !!form.querySelector('[name="reveal_sender_after_delivery"]')?.checked,
      is_gift_receipt: !!form.querySelector('[name="is_gift_receipt"]')?.checked,
    };
  }

  form.addEventListener("htmx:configRequest", function (event) {
    const isAddToCart = event.detail.elt && event.detail.elt.id === "add-to-cart-btn";

    if (isAddToCart) {
      event.detail.parameters = {
        product_id: form.dataset.productId,
        quantity: form.querySelector('[name="quantity"]')?.value || 1,
        gift_selections: JSON.stringify(collectSelections()),
      };
      return;
    }

    event.detail.parameters["addon_product_ids"] = collectAddonIds().join(",");
  });

  document.body.addEventListener("cartItemAdded", function () {
    const el = document.getElementById("add-to-cart-feedback");
    if (el) {
      el.textContent = "Added to cart!";
      setTimeout(() => { el.textContent = ""; }, 3000);
    }
  });
})();
