import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from django.conf import settings

logger = logging.getLogger(__name__)

def trigger_shipment_on_confirmed(order):
    """
    Trigger a Delhivery B2C shipment when an order status changes to CONFIRMED.
    Sends an actual HTTP POST request directly to Delhivery Express servers.

    Idempotent: a no-op if this order already has a waybill.
    """
    from delhivery.models import DelhiveryShipment

    if DelhiveryShipment.objects.filter(order=order, waybill_number__gt="").exists():
        logger.info(f"Delhivery shipment already exists for order {order.order_number}; skipping.")
        return True

    logger.info(f"Triggering Delhivery shipment for order {order.order_number}")

    api_key = getattr(settings, "DELHIVERY_API_KEY", "")
    base_url = getattr(settings, "DELHIVERY_BASE_URL", "https://staging-express.delhivery.com").rstrip("/")
    
    if not api_key:
        logger.error("DELHIVERY_API_KEY is missing in settings/env. Cannot trigger shipment.")
        return False

    #extract B2C customer details from delivery_address_snapshot
    addr = order.delivery_address_snapshot or {}
    if not isinstance(addr, dict):
        logger.error(f"Invalid delivery_address_snapshot for order {order.order_number}: {addr!r}")
        return False

    customer_name = addr.get("name") or addr.get("recipient_name") or "Customer"
    phone = addr.get("phone") or ""
    if not phone and order.customer_profile and order.customer_profile.phone:
        phone = order.customer_profile.phone

    #check payment method
    is_cod = hasattr(order, 'payment_transactions') and order.payment_transactions.filter(gateway_key="cod").exists()
    
    #extract product descriptions and calculate dimensions/weight for the payload
    items = order.items.select_related("product", "variant").all()
    item_descriptions = []

    total_weight_kg = 0.0
    max_length = 0.0
    max_width = 0.0
    max_height = 0.0
    total_quantity = 0

    for item in items:
        total_quantity += item.quantity
        product = item.product
        #Display name matches Delhivery's printed slip convention: sentence-case
        #product name (color is already part of product.name in this catalog),
        #with the ordered size appended — e.g. "Henley half sleeve muscle fit -
        #dusty black - m".
        display_name = product.name.strip().capitalize()
        if item.variant and item.variant.name:
            display_name = f"{display_name} - {item.variant.name.strip().lower()}"
        if item.quantity > 1:
            display_name = f"{display_name} (Qty: {item.quantity})"

        #variant.sku_suffix already holds the complete abbreviated code (e.g.
        #"M DST BLK HNLY") as entered against the ordered size — it is NOT a
        #suffix to append to product.sku. "0" is used in the catalog as an
        #explicit "not set" placeholder for some variants, so treat it as blank.
        variant_sku = item.variant.sku_suffix.strip() if item.variant and item.variant.sku_suffix else ""
        sku_code = variant_sku if variant_sku and variant_sku != "0" else product.sku

        item_descriptions.append(f"{display_name}\nSKU:{sku_code}")

        # accumulate weight
        if hasattr(product, 'weight') and product.weight:
            total_weight_kg += float(product.weight) * item.quantity

        # find max dimensions for the package (approximate)
        if hasattr(product, 'length') and product.length and float(product.length) > max_length:
            max_length = float(product.length)
        if hasattr(product, 'width') and product.width and float(product.width) > max_width:
            max_width = float(product.width)
        if hasattr(product, 'height') and product.height and float(product.height) > max_height:
            max_height = float(product.height)

    # Delhivery generally expects weight in grams for B2C
    total_weight_grams = total_weight_kg * 1000 if total_weight_kg > 0 else 500.0

    products_description = "\n".join(item_descriptions) if item_descriptions else f"Order {order.order_number} items"
    #construct B2C package payload
    shipment_payload = {
        "name": customer_name,
        "add": f"{addr.get('line1', '')} {addr.get('line2', '')}".strip() or "Shipping Address",
        "pin": addr.get("pin") or addr.get("pincode") or addr.get("postal_code") or "110001",
        "city": addr.get("city", "") or "New Delhi",
        "state": addr.get("state", "") or "Delhi",
        "country": addr.get("country", "") or "India",
        "phone": phone or "9999999999",
        "order": order.order_number,
        "payment_mode": "COD" if is_cod else "Prepaid",
        "return_pin": "",
        "products_desc": products_description,
        #Total piece count for the package. Without this, Delhivery defaults the
        #printed label's Qty column to 1 regardless of what was actually ordered —
        #confirmed against a real label showing "Qty: 1" for an order of 3.
        "quantity": total_quantity or 1,
        "total_amount": float(order.total_amount),
        "cod_amount": float(order.total_amount) if is_cod else 0.0,
        "weight": total_weight_grams,
        # "length": max_length or 10.0,
        # "breadth": max_width or 10.0,
        # "height": max_height or 5.0,
        "length": float(max_length or 10),
        "breadth": float(max_width or 10),
        "height": float(max_height or 5),
    }
    url = f"{base_url}/api/cmu/create.json"
    
    #format according to Delhivery B2C specs - pickup_location must be an object, not a bare string
    pickup_location_name = getattr(settings, "DELHIVERY_PICKUP_LOCATION", "Primary")
    request_payload = {
        "shipments": [shipment_payload],
        "pickup_location": {
            "name": pickup_location_name,
        },
    }
    form_data = {
        "format": "json",
        "data": json.dumps(request_payload),
    }

    logger.info(f"Delhivery request payload for {order.order_number}: {request_payload}")

    encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    
    logger.info(f"Sending real shipment POST request to Delhivery ({url}) for Order {order.order_number}")
    
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            response_data = response.read().decode("utf-8")
            logger.info(f"Delhivery API response for {order.order_number}: {response_data}")
            from delhivery.models import DelhiveryShipment
            try:
                result = json.loads(response_data)
                waybill = ""
                status_label = "Error" if result.get("error") else "Initiated"
                err_msg = result.get("rmk") or str(result) if result.get("error") else ""
                packages = result.get("packages", [])
                if packages and isinstance(packages, list) and len(packages) > 0:
                    waybill = str(packages[0].get("waybill", ""))
                
                DelhiveryShipment.objects.update_or_create(
                    order=order,
                    defaults={
                        "waybill_number": waybill,
                        "tracking_status": status_label,
                        "pickup_location": pickup_location_name,
                        "raw_create_response": result if isinstance(result, dict) else {"raw": str(result)},
                        "error_message": err_msg or str(result),
                    }
                )
                return result.get("success", True)
            except json.JSONDecodeError:
                DelhiveryShipment.objects.update_or_create(
                    order=order,
                    defaults={"tracking_status": "Unknown Response", "error_message": response_data}
                )
                return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        logger.error(f"Delhivery API HTTPError {e.code} for order {order.order_number}: {error_body}")
        from delhivery.models import DelhiveryShipment
        DelhiveryShipment.objects.update_or_create(
            order=order,
            defaults={"tracking_status": f"HTTP Error {e.code}", "error_message": error_body}
        )
        return False
    except urllib.error.URLError as e:
        logger.error(f"Delhivery connection failed for order {order.order_number}: {e.reason}")
        from delhivery.models import DelhiveryShipment
        DelhiveryShipment.objects.update_or_create(
            order=order,
            defaults={"tracking_status": "Connection Error", "error_message": str(e.reason)}
        )
        return False
    except Exception as e:
        logger.error(f"Unexpected error when calling Delhivery API for order {order.order_number}: {str(e)}")
        from delhivery.models import DelhiveryShipment
        DelhiveryShipment.objects.update_or_create(
            order=order,
            defaults={"tracking_status": "Error", "error_message": str(e)}
        )
        return False
