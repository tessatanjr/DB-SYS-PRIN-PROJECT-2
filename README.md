# SC3020 Project 2 — Query Plan-Based SQL Comprehension

A desktop tool that takes an SQL query, retrieves PostgreSQL's Query Execution
Plan (QEP), and produces an annotated SQL — explaining *how* each clause is
executed and *why* the planner picked each operator (backed by cost comparisons
against alternative plans).

Built with PySide6 (Qt) + psycopg2. An optional LLM (Azure OpenAI / OpenAI)
rewrites the template annotations into clearer natural language and powers a
Q&A chatbot about the plan.

## Requirements

- Python 3.10+
- PostgreSQL 14+ (we use 17) running on `localhost:5433`
- A database named `TPC-H` loaded with the standard TPC-H schema and data
- (Optional) an OpenAI or Azure OpenAI API key for AI annotations / chat

Default DB credentials assumed by the app (editable in the GUI):

```
host=localhost  port=5433  dbname=TPC-H  user=postgres  password=qwerty
```

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Make sure PostgreSQL is running on port 5433
#    and the TPC-H database is loaded (see "TPC-H Setup" below).

# 4. Launch the app
python project.py
```

## Using the App

1. **Connect** — open the *Database Connection* panel, confirm the credentials,
   click **Connect**. The status pill turns green.
2. *(Optional)* **Connect LLM** — pick a provider (Azure OpenAI / OpenAI),
   paste your API key, click **Connect LLM**.
3. **Pick or paste a query** — use the *Examples* dropdown for sample TPC-H
   queries, or paste your own into the SQL editor.
4. Click **Analyse Query**. Results appear in the right pane:
   - **Annotated Query** — your SQL with inline operator + cost explanations
   - **QEP Diagram** — the plan tree as nodes; hover any node for full details
     and the matching annotation
   - **QEP Tree / Text / JSON** — alternative plan views
   - **AQP Comparison** — costs of plans where specific operators were
     forced off, used to justify *why* the planner chose each operator
5. Use the **chat panel** (bottom-left) to ask follow-up questions about the
   plan. Quick-question chips are provided.

Click any annotation in the *Annotated Query* tab (or any node in the diagram)
to highlight the corresponding part in the other view.

## Project Structure

```
project.py             Entry point — launches the GUI
interface.py           Main window, layout, tab wiring
preprocessing.py       Postgres connection, EXPLAIN, AQP generation
annotation.py          Plan parsing, template annotations, LLM enhancement
modules/
  settings_panel.py    DB + LLM connection panel
  chat_panel.py        AI Q&A chat panel
  qep_diagram.py       QGraphicsView-based plan diagram + node tooltips
  themes.py            Dark / light theme manager (QSS + palette)
  constants.py         Operator categories, node colors, example queries
requirements.txt
```

## TPC-H Setup (one-time)

Install PostgreSQL, create the database, and load the TPC-H schema/data:

```bash
# macOS (Homebrew example)
brew install postgresql@17
brew services start postgresql@17

# Configure port 5433 in postgresql.conf, then restart.

createdb -p 5433 TPC-H
psql -p 5433 -d TPC-H -f path/to/tpch_schema.sql
psql -p 5433 -d TPC-H -f path/to/tpch_data.sql
```

If you already have data owned by another user, transfer ownership:

```sql
ALTER TABLE customer  OWNER TO postgres;
ALTER TABLE orders    OWNER TO postgres;
ALTER TABLE lineitem  OWNER TO postgres;
ALTER TABLE nation    OWNER TO postgres;
ALTER TABLE part      OWNER TO postgres;
ALTER TABLE partsupp  OWNER TO postgres;
ALTER TABLE region    OWNER TO postgres;
ALTER TABLE supplier  OWNER TO postgres;
```

## Notes

- **Tooltips on the QEP diagram** — hover any node to see its operator details
  *and* the matching annotation, without leaving the diagram view.
- **Theme toggle** — top-right button switches between dark and light mode.
- **No LLM?** The app still works; annotations fall back to template-generated
  text and the chatbot tab is disabled.

## Team

NTU SC3020 Database System Principles, AY2025/26 Semester 2.
