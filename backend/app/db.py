"""SQLAlchemy 引擎与会话。

SQLite 需要打开外键约束（默认关闭），这里在连接建立时执行 PRAGMA。
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite + 多线程（uvicorn）需要
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    """FastAPI 依赖：每个请求一个会话，结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
