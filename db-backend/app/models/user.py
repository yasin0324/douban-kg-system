"""
用户相关 Pydantic 模型
"""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ---------- 注册 / 登录 ----------

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    nickname: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    status: str = "active"
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------- 偏好 ----------

class UserPreferenceCreate(BaseModel):
    mid: str = Field(..., max_length=20)
    pref_type: Literal["like", "want_to_watch"]


class UserPreferenceResponse(BaseModel):
    id: int
    mid: str
    pref_type: str
    created_at: Optional[datetime] = None


class PreferenceCheck(BaseModel):
    mid: str
    is_liked: bool = False
    is_want_to_watch: bool = False


# ---------- 评分 ----------

class UserRatingCreate(BaseModel):
    mid: str = Field(..., max_length=20)
    rating: float = Field(..., ge=0.5, le=5.0)
    comment_short: Optional[str] = Field(None, max_length=500)


class UserRatingResponse(BaseModel):
    id: int
    mid: str
    rating: float
    comment_short: Optional[str] = None
    rated_at: Optional[datetime] = None


# ---------- 通用分页 ----------

class PaginatedResponse(BaseModel):
    items: List = []
    total: int = 0
    page: int = 1
    size: int = 20
