"""
管理员相关 Pydantic 模型
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminInfo(BaseModel):
    id: int
    username: str
    role: str
    status: str = "active"
    last_login_at: Optional[datetime] = None


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    admin: AdminInfo


class AdminUserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    status: Optional[Literal["active", "banned"]] = None


class AdminActionLog(BaseModel):
    id: int
    admin_id: int
    target_user_id: int
    action_type: str
    reason: Optional[str] = None
    created_at: Optional[datetime] = None
