"""Pydantic contracts for authentication, user administration, and audit reads."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.security.permissions import Role

Password = Annotated[str, StringConstraints(min_length=12, max_length=256)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str | None
    display_name: str
    role: Role
    role_display_name: str
    permissions: list[str]
    technician_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    version: int


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: Password

    @model_validator(mode="after")
    def passwords_must_differ(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("Mật khẩu mới phải khác mật khẩu hiện tại.")
        return self


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str | None = Field(
        default=None,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: Password
    display_name: str = Field(min_length=2, max_length=200)
    role: Role
    technician_id: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: Role | None = None
    technician_id: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "UserUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        return self


class RoleOptionResponse(BaseModel):
    code: Role
    display_name: str
    permissions: list[str]


class AuditLogResponse(BaseModel):
    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_display_name: str | None
    action: str
    resource_type: str
    resource_id: str | None
    request_id: str
    before_state: dict[str, object] | None
    after_state: dict[str, object] | None
    metadata: dict[str, object] | None
    outcome: str


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
