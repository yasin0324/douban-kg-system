"""
管理员用户管理路由 — /api/admin/users
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.dependencies import get_mysql_conn, get_current_admin
from app.models.admin import AdminUserUpdate
from app.services import admin_service

router = APIRouter(prefix="/api/admin/users", tags=["管理员-用户管理"])


class ReasonBody(BaseModel):
    reason: Optional[str] = None


@router.get("", summary="用户列表")
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str = Query(None),
    admin=Depends(get_current_admin),
    conn=Depends(get_mysql_conn),
):
    return admin_service.list_users(conn, page, size, status)


@router.get("/{uid}", summary="用户详情")
def get_user(uid: int, admin=Depends(get_current_admin), conn=Depends(get_mysql_conn)):
    try:
        return admin_service.get_user(conn, uid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{uid}", summary="更新用户")
def update_user(uid: int, body: AdminUserUpdate, admin=Depends(get_current_admin), conn=Depends(get_mysql_conn)):
    try:
        return admin_service.update_user(conn, admin["id"], uid, **body.model_dump(exclude_none=True))
    except ValueError as e:
        if str(e) == "用户不存在":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{uid}/ban", summary="封禁用户")
def ban_user(uid: int, body: ReasonBody = None, admin=Depends(get_current_admin), conn=Depends(get_mysql_conn)):
    reason = body.reason if body else None
    try:
        admin_service.ban_user(conn, admin["id"], uid, reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "已封禁"}


@router.post("/{uid}/unban", summary="解封用户")
def unban_user(uid: int, body: ReasonBody = None, admin=Depends(get_current_admin), conn=Depends(get_mysql_conn)):
    reason = body.reason if body else None
    try:
        admin_service.unban_user(conn, admin["id"], uid, reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "已解封"}


@router.post("/{uid}/logout", summary="强制用户下线")
def force_logout(uid: int, body: ReasonBody = None, admin=Depends(get_current_admin), conn=Depends(get_mysql_conn)):
    reason = body.reason if body else None
    try:
        admin_service.force_logout_user(conn, admin["id"], uid, reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "已强制下线"}
