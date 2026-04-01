import psycopg2
import json

# Database connection configuration
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
    """
    try:
        conn = psycopg2.connect(**config)
        print("Connected to database successfully.")
        return conn
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return None


def get_qep(conn, sql_query):
    """
    Retrieves the Query Execution Plan (QEP) for a given SQL query.
    Returns the QEP as a parsed JSON object.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN (FORMAT JSON, ANALYZE FALSE) {sql_query}")
            qep_json = cur.fetchone()[0]

            cur.execute(f"EXPLAIN (FORMAT TEXT, ANALYZE FALSE) {sql_query}")
            qep_text_rows = cur.fetchall()
            qep_text = "\n".join(row[0] for row in qep_text_rows)

            return {
                "json": qep_json,
                "text": qep_text
            }
    except Exception as e:
        print(f"Failed to retrieve QEP: {e}")
        conn.rollback()
        return None


def get_aqp(conn, sql_query, operators_to_disable):
    """
    Retrieves an Alternative Query Plan (AQP) by disabling specific operators.
    
    operators_to_disable: list of PostgreSQL planner settings to turn off
    e.g. ['enable_hashjoin', 'enable_mergejoin']
    
    Returns the AQP as a parsed JSON object.
    """
    try:
        with conn.cursor() as cur:
            # Disable specified operators
            for op in operators_to_disable:
                cur.execute(f"SET {op} = off;")
            
            # Get the alternative plan
            cur.execute(f"EXPLAIN (FORMAT JSON, ANALYZE FALSE) {sql_query}")
            aqp = cur.fetchone()[0]
            
            # Re-enable all operators (reset to default)
            for op in operators_to_disable:
                cur.execute(f"SET {op} = on;")
            
            return aqp
    except Exception as e:
        print(f"Failed to retrieve AQP: {e}")
        conn.rollback()
        return None


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
    try:
        return plan_json[0]["Plan"]["Total Cost"]
    except Exception as e:
        print(f"Failed to extract cost: {e}")
        return None


def close_db(conn):
    if conn:
        conn.close()
        print("Database connection closed.")