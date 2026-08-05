"""Compatibility facade for inventory HTTP routes.

The route implementation is kept under the inventory route package so future
catalogue, stock, movement, reservation, work-order-parts, and evidence routers
can be extracted without changing the historical import path.
"""

from src.inventory_management.routes._legacy import *  # noqa: F401,F403

