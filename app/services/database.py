"""
MySQL 数据库访问层（任务持久化 + 推荐食谱）
"""
import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv

load_dotenv(override=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "fitness_db"),
    "charset": "utf8mb4",
    "autocommit": False,
}


@contextmanager
def get_conn():
    """获取数据库连接：自动提交 / 回滚 / 关闭"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
