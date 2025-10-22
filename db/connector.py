# db/connector.py
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("환경변수 DATABASE_URL이 비어 있습니다. .env를 확인하세요.")

# echo=False, pool_pre_ping=True 권장
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)

def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """
    SQL을 실행하고 항상 pandas.DataFrame으로 반환한다.
    - search_path는 매 호출마다 public, data로 설정
    - sql은 text()로 감싼다
    """
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL search_path TO public, data;"))
        df = pd.read_sql_query(text(sql), conn, params=params)
        return df
