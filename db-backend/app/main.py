"""
FastAPI 应用入口 — 注册路由、中间件、生命周期管理
"""
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.mysql import init_pool, close_pool
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger("uvicorn.error")


# ---------- 生命周期管理 ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库连接，关闭时释放"""
    logger.info("正在初始化 MySQL 连接池...")
    init_pool()
    logger.info("正在初始化 Neo4j 驱动...")
    Neo4jConnection.get_driver()
    logger.info("数据库连接初始化完成")
    yield
    logger.info("正在关闭数据库连接...")
    close_pool()
    Neo4jConnection.close()
    logger.info("数据库连接已关闭")


# ---------- 创建应用 ----------

app = FastAPI(
    title="豆瓣知识图谱 API",
    description="基于 Neo4j 知识图谱的豆瓣电影查询、推荐与管理系统",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------- CORS 中间件 ----------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 请求日志中间件 ----------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration_ms:.0f}ms)")
    return response


# ---------- 健康检查 ----------

@app.get("/health", tags=["系统"])
async def health():
    return {"status": "ok"}


# ---------- 注册路由 ----------

from app.routers import auth, users, admin_auth, admin_users, movies, persons, graph, stats, proxy, recommend  # noqa: E402

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin_auth.router)
app.include_router(admin_users.router)
app.include_router(movies.router)
app.include_router(persons.router)
app.include_router(graph.router)
app.include_router(stats.router)
app.include_router(proxy.router)
app.include_router(recommend.router)

