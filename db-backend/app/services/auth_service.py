"""
认证服务 — 注册、登录、JWT 管理
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt 上下文（passlib 兼容 bcrypt<5.0）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _sha256_prehash(password: str) -> str:
    """SHA256 预哈希，解决 bcrypt 72 字节限制"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return pwd_context.hash(_sha256_prehash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_sha256_prehash(plain_password), hashed_password)


def create_access_token(subject: int | str, token_type: str = "access", extra: dict = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {"sub": str(subject), "type": token_type, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def create_refresh_token(subject: int | str, token_type: str = "refresh") -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {"sub": str(subject), "type": token_type, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def hash_token(token: str) -> str:
    """对 refresh_token 做 SHA256 哈希后存储"""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- 用户注册 ----------

def register(conn, username: str, password: str, nickname: str = None, email: str = None) -> dict:
    with conn.cursor() as cursor:
        # 检查用户名
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            raise ValueError("用户名已存在")
        if email:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                raise ValueError("邮箱已被注册")

        password_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, nickname, email) VALUES (%s, %s, %s, %s)",
            (username, password_hash, nickname, email),
        )
        conn.commit()
        user_id = cursor.lastrowid
    return {"id": user_id, "username": username, "nickname": nickname, "email": email}


# ---------- 用户登录 ----------

def login(conn, username: str, password: str, user_agent: str = None, ip_address: str = None) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, username, nickname, email, password_hash, status FROM users WHERE username = %s",
            (username,),
        )
        user = cursor.fetchone()
    if not user:
        raise ValueError("用户名或密码错误")
    if user["status"] != "active":
        raise ValueError("账号已被禁用")
    if not verify_password(password, user["password_hash"]):
        raise ValueError("用户名或密码错误")

    refresh_token = create_refresh_token(user["id"])

    # 存储 refresh_token 的哈希
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user["id"],))
        expires_at = datetime.now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
        cursor.execute(
            "INSERT INTO user_sessions (user_id, refresh_token_hash, user_agent, ip_address, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user["id"], hash_token(refresh_token), user_agent, ip_address, expires_at),
        )
        session_id = cursor.lastrowid
        conn.commit()

    access_token = create_access_token(user["id"], extra={"sid": session_id})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "email": user["email"],
        },
    }


# ---------- 刷新 Token ----------

def refresh(conn, refresh_token_str: str) -> dict:
    from jose import JWTError

    try:
        payload = jwt.decode(refresh_token_str, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise ValueError("Refresh Token 无效或已过期")

    user_id = payload.get("sub")
    token_type = payload.get("type")
    if not user_id:
        raise ValueError("Refresh Token 无效")
    if token_type != "refresh":
        raise ValueError("Refresh Token 类型错误")

    token_hash = hash_token(refresh_token_str)
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM user_sessions WHERE refresh_token_hash = %s AND revoked_at IS NULL AND expires_at > NOW()",
            (token_hash,),
        )
        session = cursor.fetchone()
        if not session:
            raise ValueError("Refresh Token 已撤销或过期")

        # 撤销旧 token
        cursor.execute("UPDATE user_sessions SET revoked_at = NOW() WHERE id = %s", (session["id"],))

        # 签发新 token
        new_refresh = create_refresh_token(int(user_id))
        expires_at = datetime.now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
        cursor.execute(
            "INSERT INTO user_sessions (user_id, refresh_token_hash, expires_at) VALUES (%s, %s, %s)",
            (int(user_id), hash_token(new_refresh), expires_at),
        )
        new_session_id = cursor.lastrowid
        new_access = create_access_token(int(user_id), extra={"sid": new_session_id})
        conn.commit()

    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


# ---------- 登出 ----------

def logout(conn, user_id: int):
    """撤销该用户所有活跃会话"""
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )
        conn.commit()
