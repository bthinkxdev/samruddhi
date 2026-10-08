"""Read-only query functions for the delivery app; views must not call the ORM directly."""

from __future__ import annotations

from decimal import Decimal


def get_delivery_charge(*, item_count: int, is_cod: bool = False) -> Decimal:
    """
    Return delivery charge.
    
    Delivery is free by default. If COD is selected, charge is applied.
    """
    if item_count <= 0:
        return Decimal("0.00")
        
    if is_cod:
        return Decimal("25.00")
        
    return Decimal("0.00")
