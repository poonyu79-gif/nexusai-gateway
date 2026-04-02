"""
数据库引擎、Session工厂、基类 Base
支持 SQLite（开发）和 MySQL（生产）
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _get_engine():
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        # SQLite 需要特殊配置以支持多线程
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        # 开启 WAL 模式提高并发写性能
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
    return engine


engine = _get_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    """FastAPI 依赖注入：获取数据库 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库，创建所有表"""
    # 导入所有模型确保表被注册
    from app.models import user, token, channel, log, recharge  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表初始化完成")
