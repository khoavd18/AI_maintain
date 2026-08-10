"""Compatibility facade for operational-governance record validation."""

from .operational_governance.limitations_record import _validate_limitations
from .operational_governance.ownership_record import _validate_ownership

__all__ = ["_validate_limitations", "_validate_ownership"]
