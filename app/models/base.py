"""
数据库引擎、Session工厂、基类 Base
支持 SQLite（开发）和 MySQL（生产）
"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(db_url: str):
    """确保 SQLite 数据库文件所在目录存在"""
    # sqlite:////data/proxy.db  →  /data/proxy.db
    # sqlite:///proxy.db        →  proxy.db (相对路径)
    if "///" not in db_url:
        return
    path = db_url.split("///", 1)[1]
    if not path or path == ":memory:":
        return
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"创建数据库目录: {directory}")
        except OSError as e:
            logger.warning(f"无法创建目录 {directory}: {e}，降级使用 /tmp/proxy.db")
            # 降级到 /tmp，Render 免费层保证可写
            return "sqlite:////tmp/proxy.db"
    return db_url


def _get_engine():
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        fixed = _ensure_sqlite_dir(db_url)
        if fixed and fixed != db_url:
            db_url = fixed
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
