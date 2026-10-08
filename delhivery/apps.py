from django.apps import AppConfig


class DelhiveryConfig(AppConfig):
    name = 'delhivery'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from orders.plugins import order_confirmed_registry
        from delhivery.tasks import create_shipment_for_order

        #register a hook that enqueues the async Celery task when an order is CONFIRMED
        order_confirmed_registry.register(
            lambda order: create_shipment_for_order.delay(order_id=order.pk)
        )
