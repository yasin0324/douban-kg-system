"""
管理员服务 — 管理员鉴权 + 用户管理 + 操作审计
"""
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from app.services.auth_service import verify_password, hash_token


def _create_admin_access_token(admin_id: int, session_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {"sub": str(admin_id), "type": "admin_access", "sid": session_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def _create_admin_refresh_token(admin_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {"sub": str(admin_id), "type": "admin_refresh", "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def _ensure_target_user_exists(cursor, user_id: int):
    cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cursor.fetchone():
        raise ValueError("用户不存在")


# ---------- 登录 / 登出 ----------

def admin_login(conn, username: str, password: str, ip_address: str = None, user_agent: str = None) -> dict:
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, username, role, status, password_hash FROM admins WHERE username = %s", (username,))
        admin = cursor.fetchone()
    if not admin:
        raise ValueError("用户名或密码错误")
    if admin["status"] != "active":
        raise ValueError("管理员账号已禁用")
    if not verify_password(password, admin["password_hash"]):
        raise ValueError("用户名或密码错误")

    refresh_token = _create_admin_refresh_token(admin["id"])

    with conn.cursor() as cursor:
        cursor.execute("UPDATE admins SET last_login_at = NOW() WHERE id = %s", (admin["id"],))
        expires_at = datetime.now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
        cursor.execute(
            "INSERT INTO admin_sessions (admin_id, refresh_token_hash, ip_address, user_agent, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (admin["id"], hash_token(refresh_token), ip_address, user_agent, expires_at),
        )
        session_id = cursor.lastrowid
        conn.commit()

    access_token = _create_admin_access_token(admin["id"], session_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "admin": {"id": admin["id"], "username": admin["username"], "role": admin["role"], "status": admin["status"]},
    }


def admin_logout(conn, admin_id: int):
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE admin_sessions SET revoked_at = NOW() WHERE admin_id = %s AND revoked_at IS NULL",
            (admin_id,),
        )
        conn.commit()


# ---------- 用户管理 ----------

def list_users(conn, page: int = 1, size: int = 20, status_filter: str = None) -> dict:
    offset = (page - 1) * size
    with conn.cursor() as cursor:
        where = "WHERE 1=1"
        params: list = []
        if status_filter:
            where += " AND status = %s"
            params.append(status_filter)
        cursor.execute(f"SELECT COUNT(*) as total FROM users {where}", params)
        total = cursor.fetchone()["total"]
        cursor.execute(
            f"SELECT id, username, nickname, email, status, last_login_at, created_at FROM users {where} "
            f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params + [size, offset],
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "page": page, "size": size}


def get_user(conn, user_id: int) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, username, nickname, email, status, last_login_at, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
    if not user:
        raise ValueError("用户不存在")
    return user


def update_user(conn, admin_id: int, user_id: int, **kwargs) -> dict:
    sets = []
    params = []
    for key in ("nickname", "email", "status"):
        if key in kwargs and kwargs[key] is not None:
            sets.append(f"{key} = %s")
            params.append(kwargs[key])
    if not sets:
        raise ValueError("无有效更新字段")
    params.append(user_id)
    with conn.cursor() as cursor:
        _ensure_target_user_exists(cursor, user_id)
        cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", params)
        # 审计
        cursor.execute(
            "INSERT INTO admin_user_actions (admin_id, target_user_id, action_type, reason) "
            "VALUES (%s, %s, 'update_profile', %s)",
            (admin_id, user_id, str(kwargs)),
        )
        conn.commit()
    return get_user(conn, user_id)


def ban_user(conn, admin_id: int, user_id: int, reason: str = None):
    with conn.cursor() as cursor:
        _ensure_target_user_exists(cursor, user_id)
        cursor.execute("UPDATE users SET status = 'banned' WHERE id = %s", (user_id,))
        cursor.execute(
            "INSERT INTO admin_user_actions (admin_id, target_user_id, action_type, reason) VALUES (%s, %s, 'ban_user', %s)",
            (admin_id, user_id, reason),
        )
        conn.commit()


def unban_user(conn, admin_id: int, user_id: int, reason: str = None):
    with conn.cursor() as cursor:
        _ensure_target_user_exists(cursor, user_id)
        cursor.execute("UPDATE users SET status = 'active' WHERE id = %s", (user_id,))
        cursor.execute(
            "INSERT INTO admin_user_actions (admin_id, target_user_id, action_type, reason) VALUES (%s, %s, 'unban_user', %s)",
            (admin_id, user_id, reason),
        )
        conn.commit()


def force_logout_user(conn, admin_id: int, user_id: int, reason: str = None):
    with conn.cursor() as cursor:
        _ensure_target_user_exists(cursor, user_id)
        cursor.execute("UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL", (user_id,))
        cursor.execute(
            "INSERT INTO admin_user_actions (admin_id, target_user_id, action_type, reason) VALUES (%s, %s, 'force_logout', %s)",
            (admin_id, user_id, reason),
        )
        conn.commit()
