"""
Product context module for ProductSignal.

Handles product configuration storage and retrieval.
"""

from .repository import (
    ProductContext,
    ProductContextCreate,
    ProductContextUpdate,
    ProductContextRepository,
    get_repository,
)

__all__ = [
    "ProductContext",
    "ProductContextCreate",
    "ProductContextUpdate",
    "ProductContextRepository",
    "get_repository",
]