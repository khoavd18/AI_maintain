"""Focused authentication, user administration, and audit API routes."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status

from src.config.settings import Settings, get_settings
from src.repositories.contracts import StorageUnavailableError
from src.security.dependencies import get_auth_service, get_current_user, request_id, require_permission
from src.security.permissions import Permission, role_options
from src.security.schemas import (
    AccessTokenResponse,
    AuditLogPage,
    ChangePasswordRequest,
    LoginRequest,
    RoleOptionResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from src.security.principal import CurrentUser
from src.security.service import (
    AuthenticationError,
    AuthResult,
    AuthService,
    CsrfValidationError,
    DuplicateUserError,
    UserConflictError,
    UserNotFoundError,
    user_response_values,
)

router = APIRouter()

AuthDependency = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]
UsersReadDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.USERS_READ))
]
UsersCreateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.USERS_CREATE))
]
UsersUpdateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.USERS_UPDATE))
]
AuditReadDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.AUDIT_LOGS_READ))
]


@router.post("/auth/login", response_model=AccessTokenResponse, tags=["authentication"])
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthDependency,
) -> dict[str, object]:
    try:
        result = auth_service.login(
            identifier=payload.identifier,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            request_id=request_id(request),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thông tin đăng nhập không hợp lệ.",
        ) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _set_session_cookies(response, result, get_settings())
    return _auth_response(result)


@router.post("/auth/refresh", response_model=AccessTokenResponse, tags=["authentication"])
def refresh(
    request: Request,
    response: Response,
    auth_service: AuthDependency,
    refresh_token: Annotated[str | None, Cookie(alias="maintenance_refresh")] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> dict[str, object]:
    settings = get_settings()
    # Custom cookie names are read explicitly because FastAPI aliases are static.
    refresh_value = request.cookies.get(settings.refresh_cookie_name) or refresh_token
    try:
        result = auth_service.refresh(
            refresh_token=refresh_value or "",
            csrf_token=csrf_token or "",
            user_agent=request.headers.get("user-agent"),
            request_id=request_id(request),
        )
    except CsrfValidationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthenticationError as exc:
        _clear_session_cookies(response, settings)
        raise HTTPException(
            status_code=401,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        ) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _set_session_cookies(response, result, settings)
    return _auth_response(result)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["authentication"])
def logout(
    request: Request,
    response: Response,
    auth_service: AuthDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Response:
    settings = get_settings()
    try:
        auth_service.logout(
            refresh_token=request.cookies.get(settings.refresh_cookie_name),
            csrf_token=csrf_token,
            request_id=request_id(request),
        )
    except CsrfValidationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/me", response_model=UserResponse, tags=["authentication"])
def me(current_user: CurrentUserDependency) -> dict[str, object]:
    return user_response_values(current_user)


@router.post("/auth/change-password", status_code=204, tags=["authentication"])
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: CurrentUserDependency,
    auth_service: AuthDependency,
) -> Response:
    try:
        auth_service.change_password(
            actor=current_user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            request_id=request_id(request),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _clear_session_cookies(response, get_settings())
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/users", response_model=list[UserResponse], tags=["users"])
def list_users(
    _actor: UsersReadDependency,
    auth_service: AuthDependency,
) -> list[dict[str, object]]:
    return _handle_storage(auth_service.list_users)


@router.get("/users/roles", response_model=list[RoleOptionResponse], tags=["users"])
def list_role_options(_actor: UsersReadDependency) -> list[dict[str, object]]:
    return role_options()


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    actor: UsersCreateDependency,
    auth_service: AuthDependency,
) -> dict[str, object]:
    try:
        return auth_service.create_user(
            actor=actor,
            request_id=request_id(request),
            **payload.model_dump(),
        )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UserConflictError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/users/{user_id}", response_model=UserResponse, tags=["users"])
def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    request: Request,
    actor: UsersUpdateDependency,
    auth_service: AuthDependency,
) -> dict[str, object]:
    try:
        return auth_service.update_user(
            actor=actor,
            user_id=user_id,
            updates=payload.model_dump(exclude_unset=True),
            request_id=request_id(request),
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/audit-logs", response_model=AuditLogPage, tags=["audit"])
def list_audit_logs(
    _actor: AuditReadDependency,
    auth_service: AuthDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    action: str | None = None,
    resource_type: str | None = None,
    outcome: str | None = None,
    actor_user_id: UUID | None = None,
) -> dict[str, object]:
    return _handle_storage(
        auth_service.list_audit_logs,
        page=page,
        page_size=page_size,
        action=action,
        resource_type=resource_type,
        outcome=outcome,
        actor_user_id=actor_user_id,
    )


def _auth_response(result: AuthResult) -> dict[str, object]:
    return {
        "access_token": result.access_token,
        "token_type": "bearer",
        "expires_at": result.access_expires_at,
        "user": user_response_values(result.user),
    }


def _set_session_cookies(response: Response, result: AuthResult, settings: Settings) -> None:
    max_age = max(
        0,
        int((result.refresh_expires_at - datetime.now(timezone.utc)).total_seconds()),
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=result.refresh_token,
        max_age=max_age,
        expires=result.refresh_expires_at,
        path="/auth",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=result.csrf_token,
        max_age=max_age,
        expires=result.refresh_expires_at,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite=settings.auth_cookie_samesite,
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    for key, path in (
        (settings.refresh_cookie_name, "/auth"),
        (settings.csrf_cookie_name, "/"),
    ):
        response.delete_cookie(
            key=key,
            path=path,
            secure=settings.auth_cookie_secure,
            httponly=key == settings.refresh_cookie_name,
            samesite=settings.auth_cookie_samesite,
        )


def _handle_storage(function, **kwargs):
    try:
        return function(**kwargs)
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
