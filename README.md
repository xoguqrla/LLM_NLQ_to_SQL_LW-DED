# LLM_NLQ_to_SQL_LW-DED

본 프로젝트는 PyQt5 기반의 GUI 애플리케이션으로, LLM을 사용하여 자연어 질의(NLQ)를 SQL로 변환하고 LW-DED(Laser Wire DED) 공정 데이터를 분석합니다.

이 도구를 사용하면 "1~10 레이어까지의 mpt 통계량 조사해줘"와 같은 복잡한 질문을 한국어로 입력하여, SQL을 직접 작성할 필요 없이 즉각적인 답변과 관련 데이터를 받을 수 있습니다.

<img width="1916" height="1024" alt="image" src="https://github.com/user-attachments/assets/4aacf15c-d24e-45a3-b0ba-5d8256d2f3a4" />
<img width="1695" height="976" alt="image" src="https://github.com/user-attachments/assets/c421af40-79e2-4deb-9129-daa3f005ac72" />



## 주요 기능 (Features)

* **자연어-SQL 변환 (NL2SQL):** 복잡한 한국어 질문을 실행 가능한 PostgreSQL 쿼리로 변환합니다.
* **도메인 특화 컨텍스트:** LLM에게 '공정'='프로젝트', 'MPT'='용융풀 온도' 등 DED 공정 전문 용어 및 DB 스키마 정의가 포함된 상세한 컨텍스트를 제공합니다.
* **다중 의도 분류:** 사용자의 의도를 다음 3가지로 자동 분류하여 정밀하게 처리합니다.
    1.  **SQL:** 데이터 분석 질의
    2.  **SCHEMA_INFO:** "raw_data 컬럼 뭐 있어?"와 같은 DB 구조 질문
    3.  **CHAT:** 일반 대화
* **프로젝트 기반 필터링:** GUI의 체크리스트에서 특정 프로젝트를 선택하면, 이후 모든 질의가 해당 `project_id` 기준으로 자동 필터링됩니다.

---

## 기술 스택 (Tech Stack)

* **Application:** Python 3.10+, PyQt5
* **AI (LLM):** OpenAI API (gpt-4o)
* **Database:** PostgreSQL
* **DB Interface:** SQLAlchemy, Pandas

---

## 설치 및 설정 (Installation and Setup)

1.  **리포지토리 클론:**
    ```bash
    git clone [https://github.com/xoguqrla/LLM_NLQ_to_SQL_LW-DED.git](https://github.com/xoguqrla/LLM_NLQ_to_SQL_LW-DED.git)
    cd LLM_NLQ_to_SQL_LW-DED
    ```

2.  **가상 환경 생성 및 활성화:**
    ```bash
    # Windows
    python -m venv ded_venv
    .\ded_venv\Scripts\activate
    ```

3.  **필요한 라이브러리 설치:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **환경 변수 파일 생성:**
    프로젝트 루트 디렉토리에 `.env` 파일을 생성합니다. 이 파일은 `.gitignore`에 등록되어 GitHub에 업로드되지 않습니다. 파일에는 DB 접속 정보와 API 키가 포함되어야 합니다.

    **`.env` 파일 내용:**
    ```ini
    # PostgreSQL 연결 문자열
    DATABASE_URL="postgresql://사용자명:비밀번호@호스트:포트/데이터베이스명"
    
    # OpenAI API 키
    OPENAI_API_KEY="sk-..."
    OPENAI_MODEL="gpt-4o"
    ```

5.  **애플리케이션 실행:**
    ```bash
    python app.py
    ```

---

## 핵심 아키텍처 및 데이터 흐름 (Core Architecture & Data Flow)

이 시스템은 `app.py`가 모든 로직을 관장하는 중앙 집중형 구조입니다. 사용자가 질의를 제출하면 다음 6단계 흐름이 실행됩니다.

1.  **[입력] 사용자 질의 (User Query)**
    * 사용자가 GUI(`QLineEdit`)에 질문을 입력합니다.

2.  **[흐름 1] 의도 분류 (`llm_classify_intent`)**
    * 첫 번째 LLM이 호출되어 사용자의 목표를 'SQL', 'SCHEMA_INFO', 'CHAT' 중 하나로 분류합니다.

3.  **[흐름 2] SQL 생성 (`llm_generate_sql`)**
    * 의도가 'SQL'인 경우, 시스템은 `CONTEXT_DEFINITIONS`(도메인 용어 및 DB 스키마 정의)를 새로운 LLM 프롬프트에 주입합니다.
    * LLM은 이 컨텍스트와 사용자 질문을 기반으로 PostgreSQL 쿼리를 생성합니다.

4.  **[흐름 3] DB 실행 (`db.connector.run_query`)**
    * 생성된 SQL은 `db/connector.py`로 전달됩니다.
    * `connector` 모듈은 SQLAlchemy를 사용해 DB에 쿼리를 실행하고, 그 결과를 **Pandas DataFrame**으로 반환합니다.

5.  **[흐름 4] 답변 생성 (`llm_answer`)**
    * 마지막 LLM이 호출됩니다.
    * 이 프롬프트는 "사용자의 원본 질문", "생성된 SQL", 그리고 "DB에서 반환된 실제 데이터(DataFrame)"를 모두 전달받습니다.
    * LLM은 이 모든 정보를 종합하여 사용자에게 제공할 최종적인 자연어 답변을 생성합니다.

6.  **[출력] GUI 업데이트**
    * 중앙 채팅 위젯에 LLM의 최종 답변이 표시됩니다.
    * 우측 패널에 실행된 SQL과 결과 데이터 미리보기가 표시됩니다.

---

## 파일 구조 (File Structure)

| 파일 / 폴더 | 설명 |
| :--- | :--- |
| **`app.py`** | **[핵심 애플리케이션]** <br> PyQt5 GUI, 6단계 핵심 흐름(Orchestration), 모든 LLM 프롬프트 로직, 이벤트 핸들러를 포함하는 단일 진입점입니다. |
| **`db/connector.py`** | **[데이터베이스 모듈]** <br> `.env`의 `DATABASE_URL`을 읽어 SQLAlchemy `engine`을 생성하고, SQL 실행을 위한 `run_query` 함수를 제공합니다.<br><br>**`create_engine`이란?**<br><ul><li>이것은 LangChain의 '체인(Chain)'(작업 순서)이 아닙니다.</li><li>SQLAlchemy의 핵심 기능으로, DB와 통신하는 '연결 관리자(Connection Pool)'를 생성합니다.</li><li>`run_query` 함수는 쿼리 실행 시 이 `engine`에게 실제 DB 연결(Connection)을 요청하여 작업을 수행합니다.</li></ul> |
| **`assets/logo.png`** | 메인 윈도우에 사용되는 애플리케이션 아이콘입니다. |
| `requirements.txt` | 프로젝트 실행에 필요한 모든 Python 라이브러리 목록입니다. |
| `.gitignore` | Git이 무시할 파일 및 폴더 목록 (예: `.env`, `ded_venv/`, `source_data/DB_raw/`)입니다. |
