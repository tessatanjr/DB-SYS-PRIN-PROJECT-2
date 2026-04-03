"""Shared constants used across the GUI modules."""

from PySide6.QtGui import QColor

# Highlight colours for annotated SQL clauses
HIGHLIGHT_COLORS = [
    QColor(173, 216, 230, 120),  # light blue
    QColor(144, 238, 144, 120),  # light green
    QColor(255, 218, 185, 120),  # peach
    QColor(221, 160, 221, 120),  # plum
    QColor(255, 255, 180, 120),  # light yellow
    QColor(200, 200, 255, 120),  # lavender
]

# Colours for QEP diagram nodes by operator category
NODE_COLORS = {
    "scan":      QColor(173, 216, 230),
    "join":      QColor(144, 238, 144),
    "aggregate": QColor(255, 255, 180),
    "sort":      QColor(255, 218, 185),
    "limit":     QColor(221, 160, 221),
    "other":     QColor(220, 220, 220),
}

# Preset TPC-H example queries for the dropdown
EXAMPLE_QUERIES = [
    ("-- Select an example query --", ""),
    (
        "Simple Join (Customer-Orders)",
        "SELECT *\nFROM customer C, orders O\nWHERE C.c_custkey = O.o_custkey",
    ),
    (
        "TPC-H Q1: Pricing Summary",
        "SELECT\n    l_returnflag,\n    l_linestatus,\n"
        "    sum(l_quantity) as sum_qty,\n"
        "    sum(l_extendedprice) as sum_base_price,\n"
        "    sum(l_extendedprice * (1 - l_discount)) as sum_disc_price,\n"
        "    sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) as sum_charge,\n"
        "    avg(l_quantity) as avg_qty,\n"
        "    avg(l_extendedprice) as avg_price,\n"
        "    avg(l_discount) as avg_disc,\n"
        "    count(*) as count_order\n"
        "FROM lineitem\n"
        "WHERE l_shipdate <= date '1998-12-01' - interval '90 days'\n"
        "GROUP BY l_returnflag, l_linestatus\n"
        "ORDER BY l_returnflag, l_linestatus",
    ),
    (
        "TPC-H Q3: Shipping Priority",
        "SELECT\n    l_orderkey,\n"
        "    sum(l_extendedprice * (1 - l_discount)) as revenue,\n"
        "    o_orderdate,\n    o_shippriority\n"
        "FROM customer, orders, lineitem\n"
        "WHERE c_mktsegment = 'BUILDING'\n"
        "    AND c_custkey = o_custkey\n"
        "    AND l_orderkey = o_orderkey\n"
        "    AND o_orderdate < date '1995-03-15'\n"
        "    AND l_shipdate > date '1995-03-15'\n"
        "GROUP BY l_orderkey, o_orderdate, o_shippriority\n"
        "ORDER BY revenue desc, o_orderdate\n"
        "LIMIT 10",
    ),
    (
        "TPC-H Q5: Local Supplier Volume",
        "SELECT\n    n_name,\n"
        "    sum(l_extendedprice * (1 - l_discount)) as revenue\n"
        "FROM customer, orders, lineitem, supplier, nation, region\n"
        "WHERE c_custkey = o_custkey\n"
        "    AND l_orderkey = o_orderkey\n"
        "    AND l_suppkey = s_suppkey\n"
        "    AND c_nationkey = s_nationkey\n"
        "    AND s_nationkey = n_nationkey\n"
        "    AND n_regionkey = r_regionkey\n"
        "    AND r_name = 'ASIA'\n"
        "    AND o_orderdate >= date '1994-01-01'\n"
        "    AND o_orderdate < date '1995-01-01'\n"
        "GROUP BY n_name\n"
        "ORDER BY revenue desc",
    ),
    (
        "TPC-H Q6: Forecasting Revenue Change",
        "SELECT\n    sum(l_extendedprice * l_discount) as revenue\n"
        "FROM lineitem\n"
        "WHERE l_shipdate >= date '1994-01-01'\n"
        "    AND l_shipdate < date '1995-01-01'\n"
        "    AND l_discount between 0.06 - 0.01 and 0.06 + 0.01\n"
        "    AND l_quantity < 24",
    ),
    (
        "TPC-H Q10: Returned Item Reporting",
        "SELECT\n    c_custkey, c_name,\n"
        "    sum(l_extendedprice * (1 - l_discount)) as revenue,\n"
        "    c_acctbal, n_name, c_address, c_phone, c_comment\n"
        "FROM customer, orders, lineitem, nation\n"
        "WHERE c_custkey = o_custkey\n"
        "    AND l_orderkey = o_orderkey\n"
        "    AND o_orderdate >= date '1993-10-01'\n"
        "    AND o_orderdate < date '1994-01-01'\n"
        "    AND l_returnflag = 'R'\n"
        "    AND c_nationkey = n_nationkey\n"
        "GROUP BY c_custkey, c_name, c_acctbal, c_phone,\n"
        "    n_name, c_address, c_comment\n"
        "ORDER BY revenue desc\n"
        "LIMIT 20",
    ),
]
