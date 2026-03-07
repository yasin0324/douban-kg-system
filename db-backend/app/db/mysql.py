"""
MySQL 连接池管理
"""
import pymysql
from dbutils.pooled_db import PooledDB
from app.config import settings

_pool: PooledDB | None = None


def init_pool():
    """初始化 MySQL 连接池"""
    global _pool
    _pool = PooledDB(
        creator=pymysql,
        maxconnections=settings.DB_POOL_SIZE,
        mincached=2,
        maxcached=5,
        blocking=True,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        database=settings.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_connection():
    """从连接池获取一个连接"""
    if _pool is None:
        raise RuntimeError("MySQL 连接池未初始化，请先调用 init_pool()")
    return _pool.connection()


def close_pool():
    """关闭连接池"""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
