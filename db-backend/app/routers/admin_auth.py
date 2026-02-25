"""
管理员认证路由 — /api/admin/auth
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_mysql_conn, get_current_admin
from app.models.admin import AdminLogin, AdminTokenResponse
from app.services import admin_service

router = APIRouter(prefix="/api/admin/auth", tags=["管理员认证"])


@router.post("/login", response_model=AdminTokenResponse, summary="管理员登录")
def admin_login(body: AdminLogin, request: Request, conn=Depends(get_mysql_conn)):
    try:
        result = admin_service.admin_login(
            conn,
            body.username,
            body.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", summary="管理员登出")
def admin_logout(admin=Depends(get_current_admin), conn=Depends(get_mysql_conn)):
    admin_service.admin_logout(conn, admin["id"])
    return {"message": "已登出"}
