"""
认证路由 — /api/auth
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_mysql_conn, get_current_user
from app.models.user import UserRegister, UserLogin, TokenResponse, RefreshRequest
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", summary="用户注册")
def register(body: UserRegister, conn=Depends(get_mysql_conn)):
    try:
        user = auth_service.register(conn, body.username, body.password, body.nickname, body.email)
        return {"message": "注册成功", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(body: UserLogin, request: Request, conn=Depends(get_mysql_conn)):
    try:
        result = auth_service.login(
            conn,
            body.username,
            body.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", summary="用户登出")
def logout(user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    auth_service.logout(conn, user["id"])
    return {"message": "已登出"}


@router.post("/refresh", summary="刷新 Token")
def refresh(body: RefreshRequest, conn=Depends(get_mysql_conn)):
    try:
        result = auth_service.refresh(conn, body.refresh_token)
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", summary="获取当前用户信息")
def me(user=Depends(get_current_user)):
    return user
