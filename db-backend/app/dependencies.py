"""
依赖注入 — 提供数据库连接、JWT 鉴权等公共依赖
"""
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import settings
from app.db.mysql import get_connection
from app.db.neo4j import Neo4jConnection

# ---------- 数据库依赖 ----------

security = HTTPBearer(auto_error=False)


def get_mysql_conn() -> Generator:
    """获取 MySQL 连接（自动归还连接池）"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_neo4j_session():
    """获取 Neo4j session（自动关闭）"""
    driver = Neo4jConnection.get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        session.close()


# ---------- JWT 鉴权依赖 ----------

def _decode_token(token: str) -> dict:
    """解码并验证 JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    conn=Depends(get_mysql_conn),
) -> dict:
    """获取当前登录用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
        )
    payload = _decode_token(credentials.credentials)
    user_id = payload.get("sub")
    session_id = payload.get("sid")
    token_type = payload.get("type", "access")
    if user_id is None or token_type != "access" or session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
        )
    try:
        user_id = int(user_id)
        session_id = int(session_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
        )
    # 查询用户
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT u.id, u.username, u.nickname, u.email, u.status "
            "FROM users u "
            "JOIN user_sessions s ON s.user_id = u.id "
            "WHERE u.id = %s AND s.id = %s AND s.revoked_at IS NULL AND s.expires_at > NOW()",
            (user_id, session_id),
        )
        user = cursor.fetchone()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录态已失效，请重新登录")
    if user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    conn=Depends(get_mysql_conn),
) -> dict:
    """获取当前登录管理员"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
        )
    payload = _decode_token(credentials.credentials)
    admin_id = payload.get("sub")
    session_id = payload.get("sid")
    token_type = payload.get("type", "access")
    if admin_id is None or token_type != "admin_access" or session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
        )
    try:
        admin_id = int(admin_id)
        session_id = int(session_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
        )
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT a.id, a.username, a.role, a.status "
            "FROM admins a "
            "JOIN admin_sessions s ON s.admin_id = a.id "
            "WHERE a.id = %s AND s.id = %s AND s.revoked_at IS NULL AND s.expires_at > NOW()",
            (admin_id, session_id),
        )
        admin = cursor.fetchone()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录态已失效，请重新登录")
    if admin["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员账号已禁用")
    return admin
