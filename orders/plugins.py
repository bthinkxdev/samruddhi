import logging

logger = logging.getLogger(__name__)

class OrderConfirmedPluginRegistry:
    def __init__(self):
        self._plugins = []

    def register(self, plugin_func):
        """Register a new plugin function to be called on order confirmation."""
        if plugin_func not in self._plugins:
            self._plugins.append(plugin_func)

    def execute_plugins(self, order):
        """Execute all registered plugins, passing the order instance."""
        for plugin in self._plugins:
            try:
                plugin(order)
            except Exception as e:
                # Log the exception so one failing plugin doesn't stop others
                logger.error(f"Error executing plugin {plugin.__name__}: {e}")

#global registry instance
order_confirmed_registry = OrderConfirmedPluginRegistry()
