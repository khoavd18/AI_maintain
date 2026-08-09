"""FastAPI routes for preventive plans, checklists, and work orders."""

from __future__ import annotations

from fastapi import APIRouter

from src.maintenance_management.attachment_routes import router as attachment_router
from src.maintenance_management.plan_routes import router as plan_router
from src.maintenance_management.checklist_routes import router as checklist_router
from src.maintenance_management.route_support import (
    get_maintenance_planning_service,  # noqa: F401 - compatibility import
)
from src.maintenance_management.work_order_routes import router as work_order_router

router = APIRouter()
router.include_router(plan_router)
router.include_router(checklist_router)
router.include_router(work_order_router)
router.include_router(attachment_router)


# This facade preserves the historical ``src.maintenance_management.routes``
# import while each route family lives in a focused module.
