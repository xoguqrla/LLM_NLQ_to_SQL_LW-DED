# app_gui5_llm.py
import os, re, sys, json, traceback
from typing import List, Union # [수정] Union 임포트

# Qt 플랫폼 플러그인 경로를 PyQt5 import 이전에 설정해야 합니다.
_candidates = [
    os.path.join(sys.prefix, "Lib", "site-packages", "PyQt5", "Qt", "plugins", "platforms"),
    os.path.join(sys.prefix, "Lib", "site-packages", "PyQt5", "Qt5", "plugins", "platforms"),
    os.path.join(sys.prefix, "Lib", "site-packages", "PyQt5", "plugins", "platforms"),
]
for _p in _candidates:
    if os.path.isdir(_p):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _p
        break

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")  # 일부 환경 안정화

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QTextEdit, QPushButton, QLineEdit, QLabel, QSplitter
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor, QTextCursor, QIcon # QTextCursor 임포트

# ── WebEngine 임포트 시도 + 가용 플래그 ───────────────────────────
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView  # type: ignore
    WEB_ENGINE_OK = True
except Exception:
    QWebEngineView = None  # type: ignore
    WEB_ENGINE_OK = False
# ────────────────────────────────────────────────────────────

import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from openai import OpenAI

from db.connector import run_query  # 반드시 pandas.DataFrame 반환

# ─────────────────────────────────────────────────────────────────
# 환경 & LLM
# ─────────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("openai_api_key")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────────────────────────
# 스키마 및 용어 정의 (LLM에게 제공)
# ─────────────────────────────────────────────────────────────────
CONTEXT_DEFINITIONS = """
--- [주요 용어 정의] ---
* **공정 (Gongjeong)**: 사용자가 '공정'이라고 말하면 **프로젝트 (Project)**를 의미한다. (예: "이 공정의 이름은?" -> "이 프로젝트의 이름은?")
* **공정 시작 시각**: 특정 프로젝트의 **1 레이어**(`layer=1` 또는 `layer_number=1`) 데이터 중 **최초로 `laser_on`이 1이 되는 시점**의 `time` 값. (SQL 예: `SELECT MIN(time) FROM data.raw_data WHERE project_id = :id AND layer = 1 AND laser_on = 1`)
* **공정 준비 시작 시각**: 특정 프로젝트의 `raw_data` 전체에서 **가장 빠른 `time` 값**. 데이터 로깅 시작 시각과 같다. (SQL 예: `SELECT MIN(time) FROM data.raw_data WHERE project_id = :id`)
* `mpt_...`: **용융풀 온도 (Melt Pool Temperature)** (처리 시간 아님!)
* `dwell_...`: 레이저 OFF 시간/비율 (단, **공정 시작 시각 이후**만 해당)
* `duration_seconds`: (공정 시작 시각 이후의) 레이어 총 시간 (`active_time` + `dwell_time`)

--- [DB 스키마] ---
* `public.project6`: `project_id` (PK), `project_name` (TEXT UNIQUE)
* `data.meta_data`: `summary_id`(PK), `project_id`(FK), `layer_number`, `process_date`, `duration_seconds`, `dwell_time_seconds`, `active_time_seconds`, `dwell_time_ratio`, `dwell_ratio_by_time`, `dwell_ratio_by_count`, `dwell_count`, `active_count`, `total_sample_count`, `mpt_min`, `mpt_max`, `mpt_avg`, `mpt_median`
* `data.raw_data`: `id`(PK), `project_id`(FK), `layer`, `time`(TEXT, 'MM_DD_HH24_MI_SS_MS'), `laser_on`(0/1), `mpt`, `x`, `y`, `z`, `e1`, `e2`, `s_lp`, `s_rs`, `s_ws`, `r_lp`, `r_rs`, `r_ws`, `mpa`, `mpw`, `load`, `contact`, `bead_number`

--- [테이블 관계 및 규칙] ---
* `meta_data.project_id` ↔ `project6.project_id`
* `raw_data.project_id` ↔ `project6.project_id`
* `raw_data.layer`는 `meta_data.layer_number`와 같다.
* 프로젝트 이름 컬럼은 항상 `project_name`이다.
"""

# SQL 생성용 예시 쿼리
EXAMPLE_QUERIES = """
[EXAMPLES]
1) 선택한 프로젝트들의 레이어 수:
    SELECT project_id, COUNT(DISTINCT layer_number) AS layer_count FROM data.meta_data WHERE project_id IN ({{ids}}) GROUP BY project_id ORDER BY project_id;
2) 레이어별 dwell 비율(시간 기준) 상위 10개:
    SELECT project_id, layer_number, dwell_ratio_by_time FROM data.meta_data WHERE project_id IN ({{ids}}) ORDER BY dwell_ratio_by_time DESC LIMIT 10;
3) 레이어별 MPT 평균:
    SELECT project_id, layer_number, mpt_avg FROM data.meta_data WHERE project_id IN ({{ids}}) ORDER BY layer_number;
4) 선택한 프로젝트 이름:
    SELECT project_name FROM public.project6 WHERE project_id IN ({{ids}});
5) 공정 준비 시작 시각 (가장 빠른 시간):
    SELECT MIN(time) FROM data.raw_data WHERE project_id IN ({{ids}});
6) 공정 시작 시각 (첫 레이저 ON):
    SELECT MIN(time) FROM data.raw_data WHERE project_id IN ({{ids}}) AND layer = 1 AND laser_on = 1;
"""

# ─────────────────────────────────────────────────────────────────
# 유틸: 다크 테마(70%)
# ─────────────────────────────────────────────────────────────────
def apply_dark70_theme(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(36, 39, 46))
    pal.setColor(QPalette.Base, QColor(28, 31, 36))
    pal.setColor(QPalette.AlternateBase, QColor(34, 37, 44))
    pal.setColor(QPalette.Text, QColor(234, 234, 234))
    pal.setColor(QPalette.WindowText, QColor(234, 234, 234))
    pal.setColor(QPalette.Button, QColor(45, 49, 56))
    pal.setColor(QPalette.ButtonText, QColor(235, 235, 235))
    pal.setColor(QPalette.Highlight, QColor(66, 133, 244)) # 파란색 계열
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)
    # QTextEdit의 line-height 및 hr/table 스타일 추가
    app.setStyleSheet("""
        QWidget { background-color:#24272E; color:#EAEAEA; }
        QTextEdit, QPlainTextEdit, QLineEdit, QListWidget {
            background-color:#1C1F24; color:#EAEAEA;
            border:1px solid #3C4048; border-radius:6px;
        }
        QTextEdit { line-height: 140%; }
        QSplitter::handle { background:#3C4048; }
        QPushButton {
            background:#2E3138; border:1px solid #4B4F57; border-radius:6px; padding:6px 12px;
        }
        QPushButton:hover { background:#3A3E46; }
        hr { border: none; border-top: 1px solid #3C4048; height: 1px; margin: 8px 0; }
        table { border-collapse: collapse; width: 95%; margin: 10px 0; border: 1px solid #4B4F57; }
        th, td { border: 1px solid #4B4F57; padding: 5px 8px; text-align: left; }
        th { background-color: #3A3E46; }
    """)

# ─────────────────────────────────────────────────────────────────
# SQL 정제 & 보정 (변경 없음)
# ─────────────────────────────────────────────────────────────────
SQL_START = re.compile(r'(?is)\b(SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|EXPLAIN)\b')

def sanitize_sql(raw: str) -> str:   # LLM의 출력물 정리 (청소부) -> 이 함수는 LLM이 생성한 SQL 쿼리에서 불필요한 주석, 설명, 백틱 등을 제거하고, SQL 문장만 남기는 역할을 합니다.
    if not raw: return ""
    blocks = re.findall(r"```(?:sql)?\s*(.*?)```", raw, flags=re.S)
    if blocks: raw = blocks[0]
    m = SQL_START.search(raw)
    if m: raw = raw[m.start():]
    raw = re.sub(r'\bname\b', 'project_name', raw, flags=re.I)
    raw = raw.strip()
    if not raw.endswith(";"): raw += ";"
    return raw

def enforce_project_filter(sql: str, ids: List[int]) -> str:  # 프로젝트 필터 강제 적용 (안전장치) -> 이 함수는 GUI에서 사용자가 체크박스로 선택한 프로젝트 ID를 SQL 쿼리에 강제로 주입하는 매우 중요한 "안전장치"입니다.
    if not ids: return sql
    ids_csv = ",".join(str(int(i)) for i in sorted(set(ids)))
    if re.search(r'\bproject_id\b\s+IN\s*\(\s*\d+(?:\s*,\s*\d+)*\s*\)', sql, flags=re.I): return sql
    if re.search(r'\bWHERE\b', sql, flags=re.I):
        sql = re.sub(r'\bWHERE\b', f"WHERE project_id IN ({ids_csv}) AND ", sql, count=1, flags=re.I)
    else:
        m = re.search(r'\b(ORDER\s+BY|GROUP\s+BY|LIMIT)\b', sql, flags=re.I)
        if m: sql = sql[:m.start()] + f" WHERE project_id IN ({ids_csv}) " + sql[m.start():]
        else: sql = sql.rstrip(';') + f" WHERE project_id IN ({ids_csv});"
    return sql

# 이 두 함수는 LLM이 실수를 하거나(예: name 사용, ``` 붙임) 중요한 요구사항을 빠뜨려도(예: project_id 필터 누락), 시스템이 이를 자동으로 수정하여 정확하고 안전한 쿼리만 데이터베이스에 전달되도록 보장합니다.

# ─────────────────────────────────────────────────────────────────
# LLM 단계 1: SQL 생성
# ─────────────────────────────────────────────────────────────────
# system 프롬프트에 CONTEXT_DEFINITIONS 포함
def llm_generate_sql(user_text: str, selected_ids: List[int]) -> str:
    ids_csv = ",".join(str(int(i)) for i in sorted(set(selected_ids))) or "/*none*/"
    system = (
        "너는 PostgreSQL 데이터 분석 SQL 생성기다. 다음 정보를 바탕으로 사용자의 질문에 가장 적합한 SQL 쿼리 **하나만** 생성한다.\n"
        f"{CONTEXT_DEFINITIONS}\n" # 스키마 및 용어 정의 포함
        "--- [쿼리 생성 규칙] ---\n"
        "* 주석/설명/자연어/백틱 없이 오직 SQL 문장 하나만 출력한다.\n"
        "* 쿼리 끝에는 항상 세미콜론(;)을 붙인다.\n"
        "* 가능하면 `data.meta_data`(요약 정보), `public.project6`(프로젝트 정보) 테이블을 우선 사용한다.\n"
        "* `data.raw_data`(원본 데이터)는 필요한 경우에만 사용한다 (예: 특정 시간 조회).\n"
        "* **선택된 프로젝트 ID(`ids`)가 있다면, `WHERE project_id IN (...)` 조건을 반드시 포함해야 한다.**\n"
        "* 사용자가 '공정'이라고 하면 '프로젝트'로 해석하여 쿼리를 생성한다.\n"
        "* '공정 시작 시각', '공정 준비 시작 시각' 등의 용어를 이해하고 정의에 맞는 쿼리를 생성한다."
    )
    ids_rule = f"[선택된 프로젝트] ids = ({ids_csv})"
    prompt = f"""{EXAMPLE_QUERIES}

{ids_rule}

[사용자 질문]
{user_text}

[생성할 SQL]
"""
    try:                ## 1. try: SQL 생성 및 API 호출
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.1, # 정확성 위해 온도 낮춤 -> LLM(AI)에서 temperature 매개변수는 답변의 창의성(무작위성)을 조절하는 스위치이다. 낮을수록 더 결정적이고 일관된 답변을 생성한다.
            messages=[ {"role": "system", "content": system}, {"role": "user", "content": prompt} ],   # messages는 역할극 대본 같은 것이라고 생각하면 됨. -> AI가 어떤 역할을 맡고 어떤 맥락에서 답변해야 하는지 알려줌.
        ) # resp는 LLM의 응답 전체를 담고 있는 객체. 이때, 이때 두 가지 핵심 설정을 전달합니다. 첫째, temperature=0.1로 설정하여 답변의 정확성을 높이고, 둘째, messages 배열을 통해 시스템과 사용자 역할을 명확히 구분하여 LLM이 SQL 생성에 집중하도록 유도합니다.
        raw = resp.choices[0].message.content or ""  ## 2. 후처리 (SQL 정제 및 보정)
        sql = sanitize_sql(raw)  # 1단계 정제, AI가 텍스트 앞뒤에 붙인 불필요한 마크다운이나 설명을 제거함.
        sql = enforce_project_filter(sql, selected_ids) # 2단계 보정, 사용자가 선택한 프로젝트 ID 필터를 SQL에 강제로 주입함.
        return sql # 모든 정제와 보정이 끝난, 실행 가능한 최종 SQL 문장을 반환합니다.
    except Exception as e: ## 3. 오류 처리 ---# try 블록의 1~2단계(API 호출, 후처리)에서 어떤 종류의 오류라도 발생하면 (예: 인터넷 끊김, API 키 오류 등) 프로그램이 죽지 않고 이 except 블록이 실행됩니다.
        print(f"🔥 LLM SQL 생성 오류: {e}") # 오류 내용을 터미널에 기록합니다.
        return "-- LLM 오류 --" # 앱(GUI)에는 실제 오류 대신 "--LLM 오류 --"라는 간단한 메시지를 반환하여 사용자에게 알립니다. 그래서 사용자가 오류 상황을 인지할 수 있게 합니다.

# ─────────────────────────────────────────────────────────────────
# LLM 단계 2: 자연어 답변 생성 (데이터 분석용)
# ─────────────────────────────────────────────────────────────────
# 100행 이하면 df.to_html()을 반환 (변경 없음)
def df_preview_text(df: pd.DataFrame, max_rows: int = 100) -> str:
    if df is None or df.empty: return "(결과 없음)"
    if len(df) > max_rows:
        return (f"--- (총 {len(df)}개 행 중 상위 25개) ---\n"
                f"{df.head(25).to_string(index=False)}\n...\n"
                f"--- (총 {len(df)}개 행 중 하위 25개) ---\n"
                f"{df.tail(25).to_string(index=False)}")
    return df.to_html(index=False, border=1)

# system 프롬프트에 CONTEXT_DEFINITIONS 포함 및 dwell time 주의사항 수정
def llm_answer(user_text: str, sql: str, df: pd.DataFrame) -> str:
    df_snip = df_preview_text(df)
    system = (
        "너는 친절하고 전문적인 DED 공정 데이터 분석가다. 다음 정보를 바탕으로 답변한다.\n"
        f"{CONTEXT_DEFINITIONS}\n" # 스키마 및 용어 정의 포함
        "--- [답변 생성 규칙] ---\n"
        "* 아래 [결과 미리보기]를 **[주요 용어 정의]에 따라 정확하게 해석**하여, 사용자의 [사용자 질문]에 대해 자연스러운 한국어 문장으로 답변한다.\n"
        "* 사용자가 '공정'이라고 하면 '프로젝트'로 해석한다.\n"
        "* '공정 시작 시각', '공정 준비 시작 시각' 같은 용어를 이해하고 답변에 활용한다.\n"
        "* 딱딱한 보고서 형식([요약])은 사용하지 않는다.\n"
        "* **[중요] `dwell_time_seconds` 값은 '공정 시작 시각' 이후의 레이저 OFF 시간만을 의미하도록 DB에서 재계산되었음을 인지하고 해석한다.** (즉, 첫 레이어 값이 비정상적으로 높지 않아야 정상이다).\n"
        "* (데이터가 100행 이하일 때 - HTML 수신): '결과 미리보기'가 `<table>` 태그로 시작하면, '요청하신 **모든** 결과를 HTML 표로 제공합니다.'라고 말한 뒤, 해당 HTML 블록을 **그대로 포함**시킨다. 절대 요약하지 않는다.\n"
        "* (데이터가 100행 초과일 때 - 텍스트 수신): '결과 미리보기'가 '--- (총...' 텍스트로 시작하면, '데이터가 너무 많아 모두 표시하기 어렵습니다.'라고 말하고, 텍스트 요약본의 핵심 추세나 주요 값을 설명한다.\n"
        "* 데이터 제시 후, `<strong>[데이터 해석]</strong>` 또는 `<strong>[의미]</strong>` 섹션을 만들어 수치의 의미를 분석한다.\n"
        "* 문단 구분 시에는 `<br><br>` 태그를 사용한다.\n"
        "* SQL 쿼리 내용은 답변에 포함하지 않는다."
    )
    prompt = f"""[사용자 질문]
{user_text}

[결과 미리보기(일부)]
{df_snip}

[답변]
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.4,
            messages=[ {"role": "system", "content": system}, {"role": "user", "content": prompt} ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"🔥 LLM 답변 생성 오류: {e}")
        return "답변 생성 중 오류가 발생했습니다."

# ─────────────────────────────────────────────────────────────────
# LLM 단계 0: 의도 분류 (SCHEMA_INFO 포함)
# ─────────────────────────────────────────────────────────────────
def llm_classify_intent(user_text: str) -> str:
    """사용자 의도를 'SQL', 'CHAT', 또는 'SCHEMA_INFO'로 분류합니다."""
    system = (
        "너는 사용자 의도 분류기다. 다음 규칙에 따라 사용자 질문의 의도를 분류한다:\n"
        "1. DED 공정 데이터(레이어, MPT, dwell time, 프로젝트 정보, 공정 시작 시각 등) 값에 대한 **분석/요청/질문**이면 'SQL'을 반환한다.\n" # 용어 추가
        "2. 데이터베이스 테이블의 **컬럼(column) 이름, 스키마(schema) 구조, 필드 정보**에 대한 질문이면 'SCHEMA_INFO'를 반환한다.\n"
        "3. 단순 인사, 안부, 잡담, 봇의 기능에 대한 질문 등 위 1, 2에 해당하지 않으면 'CHAT'을 반환한다.\n"
        "오직 'SQL', 'CHAT', 'SCHEMA_INFO' 중 하나만 응답한다."
    )
    prompt = f"사용자 질문: {user_text}"
    try:
        resp = client.chat.completions.create( model=OPENAI_MODEL, temperature=0.0, messages=[ {"role": "system", "content": system}, {"role": "user", "content": prompt} ], )
        # temperature=0.0: AI의 창의성을 0으로 설정하여, 제시된 보기 중에서 가장 확률이 높은 정답 하나만을 무조건 선택하도록 강제하는, 분류 작업에 필수적인 설정임.
        intent = (resp.choices[0].message.content or "").strip().upper()
        if intent in ["SQL", "SCHEMA_INFO"]: return intent
        return "CHAT"
    except Exception: return "CHAT"

# ─────────────────────────────────────────────────────────────────
# LLM 단계 2.6: 스키마 정보 답변 생성 (변경 없음)
"""
이 블록은 사용자가 "데이터"가 아닌 "데이터의 구조(스키마)"에 대해 물어볼 때 작동하는 데이터베이스 설명 전문가 입니다.
"""
# ─────────────────────────────────────────────────────────────────
COLUMN_DEFINITIONS = {
    "meta_data": { "summary_id": "PK", "project_id": "FK->project6", "layer_number": "레이어 번호", "process_date": "공정 날짜", "duration_seconds": "레이어 총 시간(첫 ON 이후)", "dwell_time_seconds": "레이저 OFF 시간(첫 ON 이후)", "active_time_seconds": "레이저 ON 시간(첫 ON 이후)", "dwell_time_ratio": "Dwell 비율(시간)", "dwell_ratio_by_time": "Dwell 비율(시간)", "dwell_ratio_by_count": "Dwell 비율(카운트)", "dwell_count": "Dwell 샘플 수(첫 ON 이후)", "active_count": "Active 샘플 수(첫 ON 이후)", "total_sample_count": "총 샘플 수(첫 ON 이후)", "mpt_min": "최소 용융풀 온도", "mpt_max": "최대 용융풀 온도", "mpt_avg": "평균 용융풀 온도", "mpt_median": "중앙값 용융풀 온도" },
    "raw_data": { "id": "PK", "project_id": "FK->project6", "layer": "레이어 번호", "time": "타임스탬프(MM_DD_HH_MI_SS_MS)", "laser_on": "레이저 상태(0/1)", "mpt": "용융풀 온도", "x": "X 좌표", "y": "Y 좌표", "z": "Z 좌표", "e1": "E1", "e2": "E2", "s_lp": "Set LP", "s_rs": "Set RS", "s_ws": "Set WS", "r_lp": "Real LP", "r_rs": "Real RS", "r_ws": "Real WS", "mpa": "MP Area", "mpw": "MP Width", "load": "Load", "contact": "Contact", "bead_number": "Bead Number" }
}
def llm_schema_response(user_text: str) -> str:
    requested_table = None
    if re.search(r'raw[_ ]?data', user_text, re.I): requested_table = "raw_data"
    elif re.search(r'meta[_ ]?data', user_text, re.I): requested_table = "meta_data"
    system = ("너는 DB 스키마 설명 AI다. 요청 테이블(`raw_data` 또는 `meta_data`)의 컬럼 목록/의미를 [컬럼 정의] 참고하여 설명한다. 테이블 명시 없으면 되묻는다.")
    definitions_prompt = "\n[컬럼 정의]\n"; definitions_prompt += "--- meta_data ---\n"; definitions_prompt += '\n'.join([f"- `{k}`: {v}" for k, v in COLUMN_DEFINITIONS["meta_data"].items()]); definitions_prompt += "\n--- raw_data ---\n"; definitions_prompt += '\n'.join([f"- `{k}`: {v}" for k, v in COLUMN_DEFINITIONS["raw_data"].items()])
    prompt = f"{system}\n{definitions_prompt}\n\n[사용자 질문]\n{user_text}\n\n[답변]"
    if requested_table:
        try:
            resp = client.chat.completions.create( model=OPENAI_MODEL, temperature=0.2, messages=[ {"role": "system", "content": system}, {"role": "user", "content": prompt} ], )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e: return f"스키마 정보 조회 중 오류 발생: {str(e)}"
    else: return "어떤 테이블의 컬럼 정보가 필요하신가요? `raw_data` 또는 `meta_data` 중에서 선택해주세요."

# ─────────────────────────────────────────────────────────────────
# LLM 단계 2.5: 일상 대화 답변 생성
# ─────────────────────────────────────────────────────────────────
# system 프롬프트에 '공정'='프로젝트' 정의 추가
def llm_chat_response(user_text: str, context: str) -> str:
    """일상 대화 및 안내용 LLM 응답을 생성합니다."""
    system = (
        "너는 LW-DED 공정 데이터 분석을 돕는 친절한 AI 어시턴트다. 사용자와 한국어로 대화한다.\n"
        "사용자의 간단한 인사, 질문, 잡담에 친절하게 응답한다.\n"
        "대화가 자연스럽게 데이터(MPT, dwell time, 레이어 등) 질문으로 이어지도록 유도한다.\n"
        "**기억할 점:** 사용자가 '공정'이라고 하면 '프로젝트'를 의미한다.\n" # 용어 정의 추가
        "예시: '안녕하세요! LW-DED 공정 데이터에 대해 궁금한 점이 있으신가요? 편하게 물어보세요.'"
    )
    prompt = f"--- 최근 대화 ---\n{context}\n\n--- 사용자 질문 ---\n{user_text}\n\n[답변]"
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.7,
            messages=[ {"role": "system", "content": system}, {"role": "user", "content": prompt} ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"채팅 응답 중 오류가 발생했습니다: {str(e)}"

# ─────────────────────────────────────────────────────────────────
# 메모리(간단 JSON) (변경 없음)
"""
    이 블록은 llm_chat_response가 최근 대화를 기억할 수 있도록 대화 기록을 로컬 파일(memory.json)에 저장하고 불러오는 기능입니다.
"""
# ─────────────────────────────────────────────────────────────────
MEM_FILE = "memory.json"; MAX_MEMORY = 12
def load_memory() -> List[dict]:
    if not os.path.exists(MEM_FILE): return []
    try: return json.loads(open(MEM_FILE, "r", encoding="utf-8").read()).get("memory", [])
    except Exception: return []
def save_memory(history: List[dict]):
    history = history[-MAX_MEMORY:]
    with open(MEM_FILE, "w", encoding="utf-8") as f: json.dump({"memory": history}, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────────────────────────
# 메인 윈도우 (이하 코드 변경 없음 - 원본 구조 유지)
"""

APP 클래스는 이 애플리케이션의 본체이자 두뇌이다,.
QMainWindow를 상속받아 메인 윈도우 그 자체를 구성하며, 모든 사용자 인터렉션(이벤트)을 처리하고 다른 모듈(LLM 함수, DB 커넥터)을 지휘하는 오케스트라 지휘자(Orchestrator)역할을 한다.
    1. __init__ 메서드 - 역할: 앱이 처음 실행될 때 모든 것을 준비하고 설정하는 생성자이다.
    : 윈도우 타이틀 설정, 크기 조정, 메모리 로드, UI 빌드, 프로젝트 로드, 초기 메시지 표시 등 앱 초기화 작업을 수행한다.
    
    2. _build_ui 메서드 - 역할: 앱의 시각적인 레이아웃(뼈대)을 만든다.
    : 좌측 프로젝트 리스트, 중앙 채팅 영역, 우측 그래프 및 SQL 미리보기 영역 등 주요 UI 컴포넌트를 생성하고 배치한다.
 
    3. _on_send 메서드 - 역할: 이 앱의 '두뇌'입니다. 사용자가 "전송"을 눌렀을 때의 모든 워크플로우를 지휘합니다.
        1. 1차 LLM 호출: 사용자의 질문을 분석하여 'SQL', 'CHAT', 'SCHEMA_INFO' 중 하나로 분류합니다.
        2. _checked_ids(): 현재 선택된 프로젝트 ID를 가져오고/ llm_generate_sql(...): (2차 LLM 호출) 자연어를 SQL로 변환합니다.
           run_query(sql): db.connector를 통해 DB에서 df (데이터)를 가져옵니다.
           llm_answer(...): (3차 LLM 호출) df 데이터를 AI에게 보여주고 "데이터 해석" 답변을 생성하게 합니다.
        3. llm_schema_response(...): (LLM 호출) 스키마 정보를 묻는 질문에 답변합니다.
        4. llm_chat_response(...): (LLM 호출) 일상 대화에 답변합니다.
        5. self.last_df에 데이터가 있다면 _maybe_plot(self.last_df)를 호출하여 그래프를 그립니다.
        6. _replace_last_bot_message(answer): "생각 중..." 메시지를 최종 답변으로 교체합니다.
        
    4. _on_project_check_changed (프로젝트 선택 처리) - 역할: 사용자가 프로젝트 체크박스를 변경할 때마다 SQL 미리보기를 업데이트합니다.
    : 선택된 프로젝트 ID를 가져와 SQL 미리보기에 반영합니다.
    
"""
    
    
    
    
# ─────────────────────────────────────────────────────────────────
class App(QMainWindow):
    def __init__(self): #1. 앱이 처음 실행될 때 모든 것을 준비하고 설정하는 생성자.
        super().__init__()
        self.setWindowTitle("Laser Wire DED Monitoring – LLM SQL Assistant v1.0")

        # --- 윈도우 아이콘 설정 로직 추가 ---
        try:
            # 현재 스크립트 파일(.py)이 있는 디렉토리의 절대 경로를 찾습니다.
            base_dir = os.path.dirname(os.path.abspath(__file__))
            # assets/logo.png 파일의 전체 경로를 조합합니다.
            icon_path = os.path.join(base_dir, 'assets', 'logo.png')
            
            # 파일이 실제로 존재하는지 확인합니다.
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                # 아이콘 파일이 없으면 터미널에 경고를 출력합니다.
                print(f"Warning: Icon file not found at {icon_path}")
        except Exception as e:
            # 아이콘 로드 중 다른 예외 발생 시 터미널에 경고를 출력합니다.
            print(f"Warning: Failed to load window icon - {e}")
        # ---  로직 추가 완료  ---

        self.resize(1700, 950)
        self.history = load_memory()
        self.last_df = None

        self._build_ui()
        self._load_projects()
        self._append_bot("초기화 완료! 좌측에서 프로젝트를 선택하고 중앙에 질문을 입력하세요.<br>"
                         "예) '선택한 프로젝트의 레이어별 dwell 비율 보여줘'")

    def _build_ui(self): #2. 앱의 시각적인 레이아웃(뼈대)을 만든다.
        left_title = QLabel("Projects")
        left_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.project_list = QListWidget()
        self.project_list.itemChanged.connect(self._on_project_check_changed)
        left_box = QVBoxLayout()
        left_box.addWidget(left_title)
        left_box.addWidget(self.project_list)
        left = QWidget()
        left.setLayout(left_box)

        center_title = QLabel("LLM SQL Assistant")
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setFont(QFont("Consolas", 11))
        self.input = QLineEdit()
        self.input.setPlaceholderText("질문을 입력하세요... (Enter 전송)")
        self.input.returnPressed.connect(self._on_send)
        self.btn = QPushButton("전송")
        self.btn.clicked.connect(self._on_send)
        center_box = QVBoxLayout()
        center_box.addWidget(center_title)
        center_box.addWidget(self.chat, 1)
        send_row = QHBoxLayout()
        send_row.addWidget(self.input, 1)
        send_row.addWidget(self.btn)
        center_box.addLayout(send_row)
        center = QWidget()
        center.setLayout(center_box)

        if WEB_ENGINE_OK:
            self.webview = QWebEngineView()
            self.webview.setHtml("<html><body style='margin:0;background:#24272E;color:#EAEAEA;font-family:Segoe UI,Malgun Gothic,Arial'>그래프 요청 시 이 영역에 표시됩니다.</body></html>")
        else:
            self.webview = QTextEdit("그래프 요청 시 이 영역에 표시됩니다.")
            self.webview.setReadOnly(True)

        self.sql_preview = QTextEdit()
        self.sql_preview.setReadOnly(True)
        self.sql_preview.setFont(QFont("Consolas", 10))
        right = QSplitter(Qt.Vertical)
        right.addWidget(self.webview)
        right.addWidget(self.sql_preview)
        right.setSizes([520, 380])

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(center)
        main.addWidget(right)
        main.setSizes([320, 930, 450])

        root = QWidget()
        root_box = QHBoxLayout(root)
        root_box.addWidget(main)
        self.setCentralWidget(root)

    def _load_projects(self):
        self.project_list.blockSignals(True)
        self.project_list.clear()
        try:
            df = run_query('SELECT project_id, project_name FROM public.project6 ORDER BY project_id;')
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    txt = f"{int(r['project_id'])}: {r['project_name']}"
                    it = QListWidgetItem(txt)
                    it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                    it.setCheckState(Qt.Unchecked)
                    self.project_list.addItem(it)
            else:
                self.project_list.addItem("(데이터 없음)")
        except Exception as e:
            self.project_list.addItem(f"(로드 오류) {e}")
        finally:
            self.project_list.blockSignals(False)

    def _checked_ids(self) -> List[int]:
        ids = []
        for i in range(self.project_list.count()):
            it = self.project_list.item(i)
            if it.checkState() == Qt.Checked:
                try:
                    ids.append(int(str(it.text()).split(":", 1)[0]))
                except Exception:
                    pass
        return ids

    def _on_project_check_changed(self, _): #4. 좌측 QListWidget의 체크박스 상태가 변경될 때마다 호출됩니다. 사용자가 프로젝트를 선택하거나 선택 해제할 때마다 이 메서드가 실행되어 SQL 미리보기 영역을 업데이트합니다.
        ids = self._checked_ids()
        ids_csv = ",".join(map(str, ids))
        if not ids:
            self.sql_preview.setText("-- 미리보기(선택 프로젝트 없음) --")
            self.history.clear()
            self.last_df = None
            save_memory(self.history)
            self.chat.clear()
            self._append_bot("프로젝트 선택 해제됨.")
            return

        sql = f"""-- 선택 프로젝트 요약 --
SELECT m.project_id, p.project_name, COUNT(m.*) AS "rows(meta)", COUNT(DISTINCT m.layer_number) AS layers, SUM(m.dwell_time_seconds) AS total_dwell, AVG(m.mpt_avg) AS avg_mpt, SUM(m.dwell_time_seconds) / NULLIF(SUM(m.duration_seconds), 0) AS dwell_ratio FROM data.meta_data AS m LEFT JOIN public.project6 AS p ON m.project_id = p.project_id WHERE m.project_id IN ({ids_csv}) GROUP BY m.project_id, p.project_name ORDER BY m.project_id;""".strip()
        try:
            df = run_query(sql)
            self.sql_preview.setText(df_preview_text(df)) # SQL 숨김
        except Exception as e:
            self.sql_preview.setText(f"[요약 로드 오류]\n{e}")

        self.history.clear()
        self.last_df = None
        save_memory(self.history)
        self.chat.clear()
        self._append_bot(f"프로젝트 선택 변경됨 (ID: {ids_csv}).<br>새 질문 시작.")

    def _append_user(self, text: str):
        self.chat.append(f'<b style="color:#FFFF00;">User:</b> {text}')

    def _append_bot(self, text: str):
        self.chat.append(f'<b style="color:#00FF00;">LLM:</b> {text}<br><hr>')

    def _append_bot_placeholder(self):
        self.chat.append(f'<b style="color:#00FF00;">LLM:</b> <i style="color:#AAAAAA;">생각 중...</i>')
        self.chat.moveCursor(QTextCursor.End)

    def _replace_last_bot_message(self, final_answer: str):
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        html = cursor.selection().toHtml()
        if "생각 중..." in html:
            cursor.removeSelectedText()
        cursor.movePosition(QTextCursor.End)
        self.chat.insertHtml(f'<b style="color:#00FF00;">LLM:</b> {final_answer}<br><hr>')
        self.chat.moveCursor(QTextCursor.End)

    def _on_send(self): #3. 이 앱의 '두뇌'입니다. 사용자가 "전송"을 눌렀을 때의 모든 워크플로우를 지휘합니다.
        user_text = self.input.text().strip()
        if not user_text: return

        self.input.clear()
        self._append_user(user_text)
        self._append_bot_placeholder()
        QApplication.processEvents()

        try:
            intent_type = llm_classify_intent(user_text)
            answer = ""

            if intent_type == "SQL":
                ids = self._checked_ids()
                sql = llm_generate_sql(user_text, ids)
                if not SQL_START.match(sql):
                    answer = "SQL 생성 실패."
                    self.sql_preview.setText("(생성 실패)")
                    self._replace_last_bot_message(answer)
                    return

                df = None
                try:
                    df = run_query(sql)
                    self.last_df = df
                except Exception as e:
                    answer = "쿼리 실행 오류."
                    self.sql_preview.setText(f"-- SQL --\n{sql}\n\n[오류]\n{e}")
                    self.last_df = None
                    self._replace_last_bot_message(answer)
                    return

                self.sql_preview.setText(f"-- SQL --\n{sql}\n\n{df_preview_text(df)}")
                answer = llm_answer(user_text, sql, df)
                self.history.append({"user": user_text, "llM": answer}); save_memory(self.history)

            elif intent_type == "SCHEMA_INFO":
                answer = llm_schema_response(user_text)
                self.sql_preview.setText("-- 스키마 정보 조회 --")
                self.history.append({"user": user_text, "llm": answer}); save_memory(self.history)

            else: # CHAT
                wants_graph_chat = bool(re.search(r"(그래프|시각화|plot|chart|그려줘|보여줘)", user_text, re.I))
                if wants_graph_chat and self.last_df is not None:
                    answer = "네, 방금 조회 데이터로 그래프 렌더링."
                else:
                    context = "\n".join([f"User: {m['user']}\nLLM: {m['llm']}" for m in self.history[-5:]])
                    answer = llm_chat_response(user_text, context)
                self.history.append({"user": user_text, "llm": answer}); save_memory(self.history)

            wants_graph_global = bool(re.search(r"(그래프|시각화|plot|chart|그려줘|보여줘)", user_text, re.I))
            if wants_graph_global:
                if self.last_df is not None and not self.last_df.empty:
                    self._maybe_plot(self.last_df)
                else:
                    if not (wants_graph_chat and self.last_df is not None):
                        answer += "<br><br><i>(그래프 그릴 데이터 없음.)</i>"

            self._replace_last_bot_message(answer)

        except Exception as e:
            answer = f"오류 발생."
            self._replace_last_bot_message(answer)
            self.sql_preview.setText(traceback.format_exc())

    # [수정] 타입 힌트 변경 -> Union[str, None]
    def _find_col(self, cols: List[str], candidates: List[str]) -> Union[str, None]:
        cols_lower_map = {c.lower(): c for c in cols}
        for cand in candidates:
            cand_lower = cand.lower()
            if cand_lower in cols_lower_map:
                return cols_lower_map[cand_lower]
        return None

    def _maybe_plot(self, df: pd.DataFrame): #
        try:
            fig = None
            cols = list(df.columns)
            x_col = self._find_col(cols, ["layer_number"])
            if not x_col:
                self._webview_text("'layer_number' 컬럼 없음.")
                return

            y_col = None
            y_title = ""
            mpt_candidates = ["mpt_avg", "average_mpt", "avg_mpt", "mpt 평균"]
            y_col = self._find_col(cols, mpt_candidates)
            if y_col: y_title = "Layer vs MPT 평균"

            if not y_col:
                dwell_candidates = ["dwell_ratio_by_time", "dwell_time_ratio", "avg_dwell_ratio", "dwell 비율"]
                y_col = self._find_col(cols, dwell_candidates)
                if y_col: y_title = "Layer vs Dwell Ratio"

            if not y_col:
                self._webview_text("시각화 가능 컬럼(mpt_avg 등) 없음.")
                return

            fig = px.line(df.sort_values(x_col), x=x_col, y=y_col, title=y_title, markers=True, color_discrete_sequence=["#669df6"])
            fig.update_layout(template="plotly_dark", plot_bgcolor="#24272E", paper_bgcolor="#24272E", font_color="#EAEAEA", title_font_size=16, xaxis_title="Layer Number", yaxis_title=y_title.split(" vs ")[-1].strip())
            html = fig.to_html(include_plotlyjs="cdn", full_html=False)

            if WEB_ENGINE_OK:
                self.webview.setHtml(html)
            else:
                self._webview_text("WebEngine 모듈 필요.")
        except Exception as e:
            self._webview_text(f"그래프 오류: {e}")

    def _webview_text(self, txt: str):
        if WEB_ENGINE_OK:
            html = f"<html><body style='margin:0;background:#24272E;color:#EAEAEA;white-space:pre-wrap;font-family:Segoe UI,Malgun Gothic,Arial'>{txt}</body></html>"
            self.webview.setHtml(html)
        else:
            self.sql_preview.append(f"\n[그래프 영역]\n{txt}")

# ─────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    apply_dark70_theme(app)
    w = App()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()