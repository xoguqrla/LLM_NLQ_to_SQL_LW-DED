# LLM_NLQ_to_SQL_LW-DED

A PyQt5-based GUI application that uses an LLM to translate natural language queries (NLQ) into SQL for analyzing Laser Wire DED (LW-DED) process data.

This tool allows users to ask complex questions in Korean (e.g., "What is the average MPT for project 3?") and receive a direct answer and the corresponding data, without writing any SQL.

## Features

* **Natural Language-to-SQL (NL2SQL):** Translates complex Korean questions into executable PostgreSQL queries.
* **Domain-Specific Context:** The LLM is provided with a detailed context of the DED process, including schema definitions and domain-specific terminology (e.G., 'Gongjeong' = 'Project', 'MPT' = 'Melt Pool Temperature').
* **Multi-Intent Classification:** Automatically classifies user intent into three categories for precise handling:
    1.  **SQL:** For data analysis queries.
    2.  **SCHEMA_INFO:** For questions about database structure (e.g., "What columns are in raw_data?").
    3.  **CHAT:** For general conversation.
* **Project-Based Filtering:** A simple checklist GUI allows users to select specific projects, and all subsequent queries are automatically filtered for those `project_id`s.

---

## Tech Stack

* **Application:** Python 3.10+, PyQt5
* **AI (LLM):** OpenAI API (gpt-4o)
* **Database:** PostgreSQL
* **DB Interface:** SQLAlchemy, Pandas

---

## Installation and Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/xoguqrla/LLM_NLQ_to_SQL_LW-DED.git](https://github.com/xoguqrla/LLM_NLQ_to_SQL_LW-DED.git)
    cd LLM_NLQ_to_SQL_LW-DED
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv ded_venv
    .\ded_venv\Scripts\activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create the environment file:**
    Create a file named `.env` in the root directory. This file is listed in `.gitignore` and will not be uploaded to GitHub. It must contain your database URL and API key.

    **`.env` file contents:**
    ```ini
    # PostgreSQL connection string
    DATABASE_URL="postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME"
    
    # OpenAI API Key
    OPENAI_API_KEY="sk-..."
    OPENAI_MODEL="gpt-4o"
    ```

5.  **Run the application:**
    ```bash
    python app.py
    ```

---

## Core Architecture & Data Flow

The system is managed entirely by `app.py`, which acts as the central orchestrator. When a user submits a query, the following 6-step flow is executed:

1.  **[Input] User Query:** The user types a question into the `QLineEdit` GUI.

2.  **[Flow 1] Intent Classification (`llm_classify_intent`)**
    * A fast, low-temperature LLM call classifies the user's goal as 'SQL', 'SCHEMA_INFO', or 'CHAT'.

3.  **[Flow 2] SQL Generation (`llm_generate_sql`)**
    * If the intent is 'SQL', the system injects the `CONTEXT_DEFINITIONS` (which define all domain terminology and DB schema) into a new LLM prompt.
    * The LLM generates a PostgreSQL query based on this context and the user's question.

4.  **[Flow 3] DB Execution (`db.connector.run_query`)**
    * The generated SQL is passed to `db/connector.py`.
    * The `connector` module uses SQLAlchemy to execute the query against the database and returns the result as a **Pandas DataFrame**.

5.  **[Flow 4] Answer Generation (`llm_answer`)**
    * A final LLM call is made.
    * This prompt receives the user's original question, the generated SQL, and **the actual data (DataFrame)** from the database.
    * The LLM synthesizes this information into a final, natural-language answer for the user.

6.  **[Output] GUI Update**
    * The central chat widget is updated with the LLM's final answer.
    * The right-hand panel is updated to show the SQL that was executed and a preview of the resulting data.

---

## File Structure

| File / Folder | Description |
| :--- | :--- |
| **`app.py`** | **[Core Application]** Contains the main `App` class (PyQt5 GUI), all LLM prompt logic, and event handlers. This is the single entry point. |
| **`db/connector.py`** | **[Database Module]** Handles the SQLAlchemy `engine` creation (from `.env`) and provides the `run_query` function to execute SQL. |
| **`assets/logo.png`** | The application icon used for the main window. |
| `requirements.txt` | A list of all Python dependencies required to run the project. |
| `.gitignore` | Specifies files and folders for Git to ignore (e.g., `.env`, `ded_venv/`, `source_data/DB_raw/`). |
