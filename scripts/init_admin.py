"""
初始化管理员账号脚本（手动运行）
用法: python scripts/init_admin.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import bcrypt
from app.models.base import SessionLocal, init_db
from app.models.user import User
from app.models.token import Token
from app.config import settings
from app.utils.helpers import generate_token_key


def main():
    print("初始化数据库...")
    init_db()

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.admin_username).first()
        if admin:
            print(f"管理员账号 '{settings.admin_username}' 已存在，跳过创建")
            # 检查是否有 token
            token = db.query(Token).filter(Token.user_id == admin.id, Token.status == 1).first()
            if not token:
                token_key = generate_token_key()
                t = Token(
                    user_id=admin.id,
                    token_key=token_key,
                    name="Admin Default Token",
                    total_quota=-1,
                    used_quota=0,
                    rate_limit=600,
                    allowed_models="*",
                    status=1,
                )
                db.add(t)
                db.commit()
                print(f"新管理员 Token: {token_key}")
            else:
                print(f"管理员已有 Token（已隐藏）")
            return

        pw_hash = bcrypt.hashpw(settings.admin_password.encode(), bcrypt.gensalt()).decode()
        admin = User(
            username=settings.admin_username,
            password_hash=pw_hash,
            role="admin",
            quota=-1,
        )
        db.add(admin)
        db.flush()

        token_key = generate_token_key()
        token = Token(
            user_id=admin.id,
            token_key=token_key,
            name="Admin Default Token",
            total_quota=-1,
            used_quota=0,
            rate_limit=600,
            allowed_models="*",
            status=1,
        )
        db.add(token)
        db.commit()

        print(f"✓ 管理员账号创建成功: {settings.admin_username}")
        print(f"✓ 管理员 Token: {token_key}")
        print("请妥善保存 Token，此后不会再次显示！")
    finally:
        db.close()


if __name__ == "__main__":
    main()
