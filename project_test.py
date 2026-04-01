from preprocessing import connect_db, get_qep, get_all_aqps, close_db
# from annotation import generate_annotations
import json

conn = connect_db()

sql_query = "SELECT * FROM customer C, orders O WHERE C.c_custkey = O.o_custkey"

qep = get_qep(conn, sql_query)

aqps = get_all_aqps(conn, sql_query)

# # 5. Generate annotations
# annotated_sql = generate_annotations(sql_query, qep, aqps)

# # 6. Print outputs
# print("=== Annotated SQL ===")
# print(annotated_sql)

print(json.dumps(qep['json'], indent=2))

close_db(conn)