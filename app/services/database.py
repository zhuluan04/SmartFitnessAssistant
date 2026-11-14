"""
MySQL 数据库访问层（任务持久化 + 推荐食谱）
"""
import os
from contextlib import contextmanager

import pymysql
import pymysql.cursors
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
    # 调用方普遍按 row["字段"] / row.get() 取值，必须用字典游标；
    # 默认 Cursor 返回 tuple，会导致 _get_task 直接抛 AttributeError。
    "cursorclass": pymysql.cursors.DictCursor,
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
