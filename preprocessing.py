import psycopg2
import json

# Database connection configuration - just a fallback; should be defined by user in app.
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "TPC-H",
    "user": "postgres",
    "password": "qwerty"
}

def connect_db(config=DB_CONFIG):
    """
    Establishes a connection to the PostgreSQL database.
    Returns a connection object.
    Raises psycopg2.Error with a specific message on failure.
    """
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    return conn

def get_qep(conn, sql_query):
    """
    Retrieves the Query Execution Plan (QEP).

    Returns:
    {
        "json": parsed JSON plan,
        "text": readable text plan
    }
    """

    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (FORMAT JSON, VERBOSE, SETTINGS) {sql_query}")
        qep_json = cur.fetchone()[0]

        cur.execute(f"EXPLAIN (FORMAT TEXT, VERBOSE, SETTINGS) {sql_query}")
        qep_text = "\n".join(row[0] for row in cur.fetchall())

        return {
            "json": qep_json,
            "text": qep_text
        }


def get_aqp(conn, sql_query, operators_to_disable):
    """
    Retrieves an Alternative Query Plan (AQP) by disabling specific operators.
    
    operators_to_disable: list of PostgreSQL planner settings to turn off
    e.g. ['enable_hashjoin', 'enable_mergejoin']
    
    Returns the AQP as a parsed JSON object.
    """
    with conn.cursor() as cur:
        for op in operators_to_disable:
            cur.execute(f"SET {op} = off;")

        cur.execute(f"EXPLAIN (FORMAT JSON, VERBOSE, SETTINGS) {sql_query}")
        aqp = cur.fetchone()[0]

        cur.execute("RESET ALL")

        return aqp


def get_all_aqps(conn, sql_query):
    """
    Retrieves multiple AQPs by disabling different combinations of operators.
    Returns a dictionary mapping disabled operator(s) to their AQP.
    
    This is used to compare costs and explain WHY the QEP chose certain operators.
    """
    # Define operator combinations to disable
    operator_combinations = [
        ["enable_hashjoin"],
        ["enable_mergejoin"],
        ["enable_nestloop"],
        ["enable_seqscan"],
        ["enable_indexscan"],
        ["enable_hashjoin", "enable_mergejoin"],  # force nestloop
        ["enable_hashjoin", "enable_nestloop"],   # force mergejoin
        ["enable_mergejoin", "enable_nestloop"],  # force hashjoin
    ]
    
    aqps = {}
    for ops in operator_combinations:
        key = ", ".join(ops)
        aqp = get_aqp(conn, sql_query, ops)
        if aqp:
            aqps[key] = aqp
    
    return aqps


def extract_cost(plan_json):
    """
    Extracts the total cost from a QEP/AQP JSON object.
    The cost is found in the root node of the plan.
    """
    return plan_json[0]["Plan"]["Total Cost"]


def close_db(conn):
    if conn:
        conn.close()
        print("Database connection closed.")