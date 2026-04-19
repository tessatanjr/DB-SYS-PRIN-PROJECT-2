import psycopg2
import json

# Fallback DB config; actual config comes from the GUI
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "TPC-H",
    "user": "postgres",
    "password": "qwerty"
}

# Connect to PostgreSQL and return the connection
def connect_db(config=DB_CONFIG):
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    return conn

# Run EXPLAIN on the query and return both JSON and text plans
def get_qep(conn, sql_query):
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (FORMAT JSON, VERBOSE, SETTINGS) {sql_query}")
        qep_json = cur.fetchone()[0]

        cur.execute(f"EXPLAIN (FORMAT TEXT, VERBOSE, SETTINGS) {sql_query}")
        qep_text = "\n".join(row[0] for row in cur.fetchall())

        return {
            "json": qep_json,
            "text": qep_text
        }


# Get an alternative plan by disabling specific operators (e.g. ['enable_hashjoin'])
def get_aqp(conn, sql_query, operators_to_disable):
    with conn.cursor() as cur:
        for op in operators_to_disable:
            cur.execute(f"SET {op} = off;")

        cur.execute(f"EXPLAIN (FORMAT JSON, VERBOSE, SETTINGS) {sql_query}")
        aqp = cur.fetchone()[0]

        cur.execute("RESET ALL")

        return aqp


# Try disabling different operator combos to get alternative plans for cost comparison
def get_all_aqps(conn, sql_query):
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


# Pull total cost from the root node of a plan
def extract_cost(plan_json):
    return plan_json[0]["Plan"]["Total Cost"]


def close_db(conn):
    if conn:
        conn.close()