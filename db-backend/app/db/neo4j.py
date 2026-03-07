"""
Neo4j 驱动管理
"""
from neo4j import GraphDatabase
from app.config import settings


class Neo4jConnection:
    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            cls._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASS),
                max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
            )
        return cls._driver

    @classmethod
    def close(cls):
        if cls._driver is not None:
            cls._driver.close()
            cls._driver = None
