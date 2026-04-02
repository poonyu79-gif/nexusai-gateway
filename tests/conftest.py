"""
测试配置和 Fixtures
"""
import pytest
import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 测试使用内存 SQLite
TEST_DATABASE_URL = "sqlite:///:memory:"

import os
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-32c"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"

from app.models.base import Base, get_db
from app.models.user import User
from app.models.token import Token
from app.models.channel import Channel
from app.main import app
from app.utils.helpers import generate_token_key, encrypt_api_key

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    """每个测试前重建数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db):
    pw = bcrypt.hashpw("testpass".encode(), bcrypt.gensalt()).decode()
    user = User(username="admin", password_hash=pw, role="admin", quota=-1)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def test_user(db):
    pw = bcrypt.hashpw("userpass".encode(), bcrypt.gensalt()).decode()
    user = User(username="testuser", password_hash=pw, role="user", quota=10.0)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin_token(db, admin_user):
    key = generate_token_key()
    token = Token(
        user_id=admin_user.id,
        token_key=key,
        name="Admin Token",
        total_quota=-1,
        used_quota=0,
        rate_limit=600,
        allowed_models="*",
        status=1,
    )
    db.add(token)
    db.commit()
    return token


@pytest.fixture
def user_token(db, test_user):
    key = generate_token_key()
    token = Token(
        user_id=test_user.id,
        token_key=key,
        name="User Token",
        total_quota=5.0,
        used_quota=0,
        rate_limit=60,
        allowed_models="gpt-4o,gpt-4o-mini",
        status=1,
    )
    db.add(token)
    db.commit()
    return token


@pytest.fixture
def test_channel(db):
    ch = Channel(
        name="Test OpenAI",
        channel_type="openai",
        api_key=encrypt_api_key("sk-test-fake-key"),
        base_url="https://api.openai.com/v1",
        supported_models="gpt-4o,gpt-4o-mini,gpt-3.5-turbo",
        priority=0,
        weight=1,
        max_retries=2,
        timeout=30,
        status=1,
        error_count=0,
    )
    db.add(ch)
    db.commit()
    return ch
