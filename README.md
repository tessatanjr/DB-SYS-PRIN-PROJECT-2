# SC3020 Project 2 - LEBRON (Logical Execution Breakdown for Relational Operations & Nodes)

A desktop GUI that takes an SQL query, retrieves PostgreSQL's Query Execution
Plan (QEP), and produces annotated SQL explaining *how* each clause is
executed and *why* the planner picked each operator.

---

## Quick Start

> We assume that PostgreSQL is running with TPC-H loaded. If not, see [Setup Guide](#setup-guide) below.

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the app:
   ```
   python project.py
   ```

3. Enter your PostgreSQL password and click **Connect**.
   The default fields are pre-filled (`localhost:5432`, database `TPC-H`, user `postgres`).

4. LLM API keys are hardcoded for this submission and connects to OpenAI GPT-4.1 Nano by default. To use a different model or provider, select it from the dropdown and click **Connect LLM** again.

5. Pick a query from the **Examples** dropdown or paste your own, then click **Analyse Query**.

6. Navigate the tabs on the right panel to view different perspectives: **Annotated Query**, **QEP Diagram**, **AQP Comparison**, **QEP Tree**, **QEP Text**, and **QEP JSON**.

7. Use the **chat panel** on the bottom left to ask follow-up questions about the query plan.

8. Click **Export Results** to save the analysis as a `.txt` or `.json` report.

---

## Project Files

```
project.py             Entry point - launches the GUI
interface.py           Main window, layout, tab wiring
preprocessing.py       Postgres connection, EXPLAIN, AQP generation
annotation.py          Plan parsing, template annotations, orchestration
modules/
  llm.py               LLM client setup (OpenAI, Claude, Ollama) + chat
  settings_panel.py    DB + LLM connection panel
  chat_panel.py        AI Q&A chat panel
  qep_diagram.py       QGraphicsView-based plan diagram + click popups
  themes.py            Dark / light theme manager (QSS + palette)
  constants.py         Operator categories, node colors, example queries
  syntax.py            SQL syntax highlighter
  export.py            Export results to file
requirements.txt
```

---

## Setup Guide

If you don't have PostgreSQL and TPC-H set up yet, follow these steps.

### Install Prerequisites

- **Python 3.10+** - check with `python --version`
- **PostgreSQL 14+** (developed on PostgreSQL 17) - check with `psql --version`
- **TPC-H data** - schema + data `.sql` files from the official TPC-H tools or the course distribution

After installing PostgreSQL, make sure `psql` and `createdb` are on your PATH.

### Create the TPC-H Database

```bash
createdb -p 5432 -U postgres "TPC-H"
psql -p 5432 -U postgres -d "TPC-H" -f path/to/tpch_schema.sql
psql -p 5432 -U postgres -d "TPC-H" -f path/to/tpch_data.sql
```

Verify tables exist:
```bash
psql -p 5432 -U postgres -d "TPC-H" -c "\dt"
```

You should see: `customer`, `lineitem`, `nation`, `orders`, `part`, `partsupp`, `region`, `supplier`.

### Troubleshooting

| Problem | Fix |
|---|---|
| `connection refused` on port 5432 | Postgres is not running or listening on a different port. |
| `password authentication failed` | Enter the correct password in the GUI's Database Connection panel. |
| `permission denied for table` | Run `ALTER TABLE <table> OWNER TO postgres;` for each table. |
| `ModuleNotFoundError: PySide6` | Activate your venv and re-run `pip install -r requirements.txt`. |
| LLM connection fails | Verify the API key. For Ollama, ensure it's running (`ollama list`). |

---

## Team

NTU SC3020 Database System Principles, AY2025/26 Semester 2, Group 6.
- Pang Boslyn
- Chan Kit Ho
- Bombay Saroj Susanna
- Tessa Tan Jie Ru
- Tan Jin Wei Daniel
