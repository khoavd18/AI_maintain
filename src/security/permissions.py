"""Canonical role and permission definitions shared through the auth API."""

from enum import StrEnum


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    PROPERTY_MANAGER = "property_manager"
    CHIEF_ENGINEER = "chief_engineer"
    TECHNICIAN = "technician"
    HELPDESK = "helpdesk"
    STOREKEEPER = "storekeeper"


class Permission(StrEnum):
    ASSETS_READ = "assets:read"
    ASSETS_CREATE = "assets:create"
    ASSETS_UPDATE = "assets:update"
    ASSETS_CHANGE_STATUS = "assets:change_status"
    ASSETS_ARCHIVE = "assets:archive"
    ASSETS_RESTORE = "assets:restore"
    LOCATIONS_READ = "locations:read"
    LOCATIONS_CREATE = "locations:create"
    LOCATIONS_UPDATE = "locations:update"
    LOCATIONS_ARCHIVE = "locations:archive"
    ATTACHMENTS_READ = "attachments:read"
    ATTACHMENTS_CREATE = "attachments:create"
    ATTACHMENTS_DELETE = "attachments:delete"
    TICKETS_READ = "tickets:read"
    TICKETS_CREATE = "tickets:create"
    TICKETS_ASSIGN = "tickets:assign"
    TICKETS_UPDATE = "tickets:update"
    TICKETS_RESOLVE = "tickets:resolve"
    MAINTENANCE_LOGS_READ = "maintenance_logs:read"
    MAINTENANCE_LOGS_CREATE = "maintenance_logs:create"
    MAINTENANCE_PLANS_READ = "maintenance_plans:read"
    MAINTENANCE_PLANS_CREATE = "maintenance_plans:create"
    MAINTENANCE_PLANS_UPDATE = "maintenance_plans:update"
    MAINTENANCE_PLANS_PAUSE = "maintenance_plans:pause"
    MAINTENANCE_PLANS_ARCHIVE = "maintenance_plans:archive"
    CHECKLIST_TEMPLATES_READ = "checklist_templates:read"
    CHECKLIST_TEMPLATES_CREATE = "checklist_templates:create"
    CHECKLIST_TEMPLATES_UPDATE = "checklist_templates:update"
    WORK_ORDERS_READ = "work_orders:read"
    WORK_ORDERS_CREATE = "work_orders:create"
    WORK_ORDERS_ASSIGN = "work_orders:assign"
    WORK_ORDERS_UPDATE = "work_orders:update"
    WORK_ORDERS_EXECUTE = "work_orders:execute"
    WORK_ORDERS_COMPLETE = "work_orders:complete"
    WORK_ORDERS_VERIFY = "work_orders:verify"
    WORK_ORDERS_CANCEL = "work_orders:cancel"
    WORK_ORDERS_REOPEN = "work_orders:reopen"
    WORK_ORDER_ATTACHMENTS_READ = "work_order_attachments:read"
    WORK_ORDER_ATTACHMENTS_CREATE = "work_order_attachments:create"
    WORK_ORDER_ATTACHMENTS_DELETE = "work_order_attachments:delete"
    MAINTENANCE_GENERATION_RUN = "maintenance_generation:run"
    ANALYTICS_READ = "analytics:read"
    COPILOT_USE = "copilot:use"
    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    AUDIT_LOGS_READ = "audit_logs:read"


ROLE_DISPLAY_NAMES = {
    Role.ADMINISTRATOR: "Quản trị viên",
    Role.PROPERTY_MANAGER: "Quản lý cơ sở",
    Role.CHIEF_ENGINEER: "Kỹ sư trưởng",
    Role.TECHNICIAN: "Kỹ thuật viên",
    Role.HELPDESK: "Bộ phận tiếp nhận",
    Role.STOREKEEPER: "Thủ kho",
}

_MAINTENANCE_TEAM = {
    Permission.ASSETS_READ,
    Permission.LOCATIONS_READ,
    Permission.TICKETS_READ,
    Permission.TICKETS_CREATE,
    Permission.TICKETS_ASSIGN,
    Permission.TICKETS_UPDATE,
    Permission.TICKETS_RESOLVE,
    Permission.MAINTENANCE_LOGS_READ,
    Permission.MAINTENANCE_LOGS_CREATE,
    Permission.ANALYTICS_READ,
    Permission.COPILOT_USE,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMINISTRATOR: frozenset(Permission),
    Role.PROPERTY_MANAGER: frozenset(
        _MAINTENANCE_TEAM
        - {Permission.MAINTENANCE_LOGS_CREATE}
        | {
            Permission.ASSETS_UPDATE,
            Permission.ASSETS_CHANGE_STATUS,
            Permission.ASSETS_ARCHIVE,
            Permission.ASSETS_RESTORE,
            Permission.LOCATIONS_CREATE,
            Permission.LOCATIONS_UPDATE,
            Permission.LOCATIONS_ARCHIVE,
            Permission.ATTACHMENTS_READ,
            Permission.ATTACHMENTS_CREATE,
            Permission.ATTACHMENTS_DELETE,
            Permission.AUDIT_LOGS_READ,
            Permission.MAINTENANCE_PLANS_READ,
            Permission.CHECKLIST_TEMPLATES_READ,
            Permission.WORK_ORDERS_READ,
            Permission.WORK_ORDERS_CREATE,
            Permission.WORK_ORDERS_ASSIGN,
            Permission.WORK_ORDERS_UPDATE,
            Permission.WORK_ORDERS_VERIFY,
            Permission.WORK_ORDERS_CANCEL,
            Permission.WORK_ORDERS_REOPEN,
            Permission.WORK_ORDER_ATTACHMENTS_READ,
            Permission.WORK_ORDER_ATTACHMENTS_CREATE,
            Permission.WORK_ORDER_ATTACHMENTS_DELETE,
        }
    ),
    Role.CHIEF_ENGINEER: frozenset(
        _MAINTENANCE_TEAM
        | {
            Permission.ASSETS_CREATE,
            Permission.ASSETS_UPDATE,
            Permission.ASSETS_CHANGE_STATUS,
            Permission.LOCATIONS_CREATE,
            Permission.LOCATIONS_UPDATE,
            Permission.ATTACHMENTS_READ,
            Permission.ATTACHMENTS_CREATE,
            Permission.ATTACHMENTS_DELETE,
            Permission.MAINTENANCE_PLANS_READ,
            Permission.MAINTENANCE_PLANS_CREATE,
            Permission.MAINTENANCE_PLANS_UPDATE,
            Permission.MAINTENANCE_PLANS_PAUSE,
            Permission.MAINTENANCE_PLANS_ARCHIVE,
            Permission.CHECKLIST_TEMPLATES_READ,
            Permission.CHECKLIST_TEMPLATES_CREATE,
            Permission.CHECKLIST_TEMPLATES_UPDATE,
            Permission.WORK_ORDERS_READ,
            Permission.WORK_ORDERS_CREATE,
            Permission.WORK_ORDERS_ASSIGN,
            Permission.WORK_ORDERS_UPDATE,
            Permission.WORK_ORDERS_EXECUTE,
            Permission.WORK_ORDERS_COMPLETE,
            Permission.WORK_ORDERS_VERIFY,
            Permission.WORK_ORDERS_CANCEL,
            Permission.WORK_ORDERS_REOPEN,
            Permission.WORK_ORDER_ATTACHMENTS_READ,
            Permission.WORK_ORDER_ATTACHMENTS_CREATE,
            Permission.WORK_ORDER_ATTACHMENTS_DELETE,
            Permission.MAINTENANCE_GENERATION_RUN,
        }
    ),
    Role.TECHNICIAN: frozenset(
        {
            Permission.ASSETS_READ,
            Permission.ASSETS_CHANGE_STATUS,
            Permission.LOCATIONS_READ,
            Permission.ATTACHMENTS_READ,
            Permission.TICKETS_READ,
            Permission.TICKETS_UPDATE,
            Permission.TICKETS_RESOLVE,
            Permission.MAINTENANCE_LOGS_READ,
            Permission.MAINTENANCE_LOGS_CREATE,
            Permission.COPILOT_USE,
            Permission.CHECKLIST_TEMPLATES_READ,
            Permission.WORK_ORDERS_READ,
            Permission.WORK_ORDERS_EXECUTE,
            Permission.WORK_ORDERS_COMPLETE,
            Permission.WORK_ORDER_ATTACHMENTS_READ,
            Permission.WORK_ORDER_ATTACHMENTS_CREATE,
            Permission.WORK_ORDER_ATTACHMENTS_DELETE,
        }
    ),
    Role.HELPDESK: frozenset(
        {
            Permission.ASSETS_READ,
            Permission.TICKETS_READ,
            Permission.TICKETS_CREATE,
            Permission.TICKETS_UPDATE,
            Permission.WORK_ORDERS_READ,
        }
    ),
    Role.STOREKEEPER: frozenset(
        {Permission.ASSETS_READ, Permission.WORK_ORDERS_READ}
    ),
}


def permissions_for_role(role: str | Role) -> frozenset[Permission]:
    """Return the canonical permission set or reject an unknown persisted role."""

    return ROLE_PERMISSIONS[Role(role)]


def role_options() -> list[dict[str, object]]:
    """Expose role labels and permissions so clients do not duplicate the matrix."""

    return [
        {
            "code": role.value,
            "display_name": ROLE_DISPLAY_NAMES[role],
            "permissions": sorted(permission.value for permission in permissions),
        }
        for role, permissions in ROLE_PERMISSIONS.items()
    ]
