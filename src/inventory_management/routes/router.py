"""Composed inventory route tree."""

from fastapi import APIRouter

from .attachments import router as attachments_router
from .catalogue import router as catalogue_router
from .reservations import router as reservations_router
from .stock import router as stock_router
from .work_order_parts import router as work_order_parts_router

router = APIRouter()
router.include_router(catalogue_router)
router.include_router(stock_router)
router.include_router(reservations_router)
router.include_router(work_order_parts_router)
router.include_router(attachments_router)
