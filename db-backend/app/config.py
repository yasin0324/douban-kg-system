"""
配置管理 - 使用 pydantic-settings 读取 .env 文件
"""
import json
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # MySQL
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASS: str = ""
    DB_NAME: str = "douban"
    DB_POOL_SIZE: int = 20

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASS: str = ""
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50

    # FastAPI
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    APP_ENV: str = "dev"
    KIMI_API_KEY: str = ""

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Cache
    CACHE_TTL_SECONDS: int = 300
    RECOMMEND_USER_PROFILE_CACHE_TTL_SECONDS: int = 120
    RECOMMEND_USER_PROFILE_CACHE_MAXSIZE: int = 256
    RECOMMEND_MOVIE_CACHE_TTL_SECONDS: int = 600
    RECOMMEND_MOVIE_CACHE_MAXSIZE: int = 4096

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
