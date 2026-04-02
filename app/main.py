"""
FastAPI 应用入口
"""
import logging
import bcrypt
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os

from app.config import settings
from app.models.base import init_db, SessionLocal
from app.models.user import User
from app.models.token import Token
from app.core.rate_limiter import get_rate_limiter
from app.utils.helpers import generate_token_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _init_admin():
    """首次启动时自动创建管理员账号和初始 Token"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.admin_username).first()
        if not admin:
            pw_hash = bcrypt.hashpw(
                settings.admin_password.encode(), bcrypt.gensalt()
            ).decode()
            admin = User(
                username=settings.admin_username,
                password_hash=pw_hash,
                role="admin",
                quota=-1,  # 管理员无限额度
            )
            db.add(admin)
            db.flush()

            # 为管理员创建初始 Token
            init_token_key = generate_token_key()
            token = Token(
                user_id=admin.id,
                token_key=init_token_key,
                name="Admin Default Token",
                total_quota=-1,
                used_quota=0,
                rate_limit=600,
                allowed_models="*",
                allowed_ips="*",
                status=1,
            )
            db.add(token)
            db.commit()
            logger.info(f"管理员账号已创建: {settings.admin_username}")
            logger.info(f"初始管理员 Token: {init_token_key}")
            logger.info("请妥善保存 Token，此后不会再次显示")
        else:
            logger.info(f"管理员账号已存在: {settings.admin_username}")
    except Exception as e:
        db.rollback()
        logger.error(f"初始化管理员失败: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库和管理员"""
    logger.info(f"启动 {settings.app_name}...")
    init_db()          # 创建数据库表
    _init_admin()      # 初始化管理员
    get_rate_limiter() # 初始化限流器
    logger.info("初始化完成，服务就绪")
    yield
    logger.info("服务关闭")


app = FastAPI(
    title="AI API Proxy",
    description="生产可用的 AI API 中转站，兼容 OpenAI API 格式",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 全局错误处理 ─────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "server_error",
                "code": "internal_error",
            }
        },
    )


# ─── 挂载路由 ────────────────────────────────────────────────────────────────
from app.api import proxy, admin, models_list, auth, recharge, user_tokens

app.include_router(proxy.router)
app.include_router(models_list.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(recharge.router)
app.include_router(user_tokens.router)

# ─── 挂载静态文件 ────────────────────────────────────────────────────────────
_base = os.path.dirname(os.path.dirname(__file__))

web_dir = os.path.join(_base, "web")
if os.path.exists(web_dir):
    app.mount("/admin-panel", StaticFiles(directory=web_dir, html=True), name="admin-panel")


# ─── 健康检查 ────────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.app_name}


# 公开前端必须最后挂载，避免覆盖 API 路由
public_dir = os.path.join(_base, "public")
if os.path.exists(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
