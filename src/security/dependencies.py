"""FastAPI authentication and explicit permission dependencies."""

from typing import Annotated, Callable
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.composition.security import get_auth_service
from src.repositories.contracts import StorageUnavailableError
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.security.service import AuthenticationError, AuthService

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()
    try:
        return auth_service.authenticate_access(credentials.credentials)
    except AuthenticationError as exc:
        raise _unauthorized() from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def require_permission(permission: Permission) -> Callable[..., CurrentUser]:
    def dependency(
        request: Request,
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        auth_service: Annotated[AuthService, Depends(get_auth_service)],
    ) -> CurrentUser:
        if current_user.has(permission):
            return current_user
        auth_service.record_authorization_denied(
            actor=current_user,
            permission=permission,
            request_id=request_id(request),
            resource_type=request.url.path[:80],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện thao tác này.",
        )

    return dependency


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid4()))


def audit_context(current_user: CurrentUser, request: Request) -> AuditContext:
    return AuditContext(
        actor_user_id=current_user.id,
        actor_display_name=current_user.display_name,
        request_id=request_id(request),
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        headers={"WWW-Authenticate": "Bearer"},
    )
