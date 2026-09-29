from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role_code: str
    full_name: str
    mine_id: int | None = None


class UserInfo(BaseModel):
    id: int
    username: str
    full_name: str
    role_code: str
    role_label: str
    mine_id: int | None = None
    mine_name: str | None = None
    department: str | None = None
    can_enter: bool
    can_approve: bool
