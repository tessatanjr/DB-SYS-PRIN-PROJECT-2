import re
from preprocessing import connect_db, get_qep, get_all_aqps, extract_cost, close_db


# ---------------------------------------------------------------------------
# 1. QEP Tree Parsing
# ---------------------------------------------------------------------------

def flatten_plan_tree(plan_node, depth=0):
    """
    Recursively flattens the QEP/AQP plan tree into a list of node dicts.
    Each dict includes the depth for hierarchy tracking.
    """
    node = dict(plan_node)
    node["Depth"] = depth
    children = node.pop("Plans", [])
    result = [node]
    for child in children:
        result.extend(flatten_plan_tree(child, depth + 1))
    return result


def get_root_plan(plan_json):
    """Extracts the root Plan node from EXPLAIN JSON output."""
    return plan_json[0]["Plan"]


# ---------------------------------------------------------------------------
# 2. Operator Classification Helpers
# ---------------------------------------------------------------------------

SCAN_TYPES = {
    "Seq Scan", "Index Scan", "Index Only Scan",
    "Bitmap Heap Scan", "Bitmap Index Scan",
    "Tid Scan", "Tid Range Scan", "Subquery Scan",
    "Function Scan", "Values Scan", "CTE Scan",
    "Named Tuplestore Scan", "WorkTable Scan",
    "Foreign Scan", "Custom Scan",
}

JOIN_TYPES = {
    "Hash Join", "Merge Join", "Nested Loop",
}

AGGREGATE_TYPES = {
    "Aggregate", "HashAggregate", "GroupAggregate",
}

SORT_TYPES = {
    "Sort", "Incremental Sort",
}

# Maps a chosen join/scan type to the planner flags that would disable the
# *alternative* operators, so we can compare costs.
JOIN_DISABLE_MAP = {
    "Hash Join":   {"enable_hashjoin"},
    "Merge Join":  {"enable_mergejoin"},
    "Nested Loop": {"enable_nestloop"},
}

SCAN_DISABLE_MAP = {
    "Seq Scan":         {"enable_seqscan"},
    "Index Scan":       {"enable_indexscan"},
    "Index Only Scan":  {"enable_indexonlyscan"},
    "Bitmap Heap Scan": {"enable_bitmapscan"},
    "Bitmap Index Scan": {"enable_bitmapscan"},
}

# Human-readable names for planner settings
OPERATOR_FRIENDLY_NAME = {
    "enable_hashjoin":      "Hash Join",
    "enable_mergejoin":     "Merge Join",
    "enable_nestloop":      "Nested Loop",
    "enable_seqscan":       "Sequential Scan",
    "enable_indexscan":     "Index Scan",
    "enable_indexonlyscan": "Index Only Scan",
    "enable_bitmapscan":    "Bitmap Scan",
}


def classify_node(node_type):
    """Returns a category string for a given plan node type."""
    if node_type in SCAN_TYPES:
        return "scan"
    if node_type in JOIN_TYPES:
        return "join"
    if node_type in AGGREGATE_TYPES:
        return "aggregate"
    if node_type in SORT_TYPES:
        return "sort"
    if node_type == "Limit":
        return "limit"
    return "other"


# ---------------------------------------------------------------------------
# 3. Extract Interesting Operators from Plan
# ---------------------------------------------------------------------------

def extract_operators(plan_json):
    """
    Walks the QEP tree and returns categorised operator info.

    Returns a dict:
    {
        "scans":      [{ "node_type", "relation", "alias", "filter", "cost", ... }],
        "joins":      [{ "node_type", "join_type", "condition", "cost", "tables", ... }],
        "aggregates": [{ "node_type", "strategy", "group_key", "cost", ... }],
        "sorts":      [{ "node_type", "sort_key", "cost", ... }],
        "other":      [{ "node_type", "cost", ... }],
        "total_cost": float,
    }
    """
    root = get_root_plan(plan_json)
    nodes = flatten_plan_tree(root)

    scans = []
    joins = []
    aggregates = []
    sorts = []
    other = []

    for node in nodes:
        ntype = node.get("Node Type", "")
        category = classify_node(ntype)
        cost = node.get("Total Cost", 0)

        if category == "scan":
            scans.append({
                "node_type":  ntype,
                "relation":   node.get("Relation Name", ""),
                "alias":      node.get("Alias", ""),
                "schema":     node.get("Schema", ""),
                "filter":     node.get("Filter", ""),
                "index_name": node.get("Index Name", ""),
                "index_cond": node.get("Index Cond", ""),
                "rows":       node.get("Plan Rows", 0),
                "cost":       cost,
            })

        elif category == "join":
            # Collect table names from child scan nodes
            child_tables = _collect_child_relations(node)
            joins.append({
                "node_type":  ntype,
                "join_type":  node.get("Join Type", ""),
                "condition":  node.get("Hash Cond", node.get("Merge Cond", node.get("Join Filter", ""))),
                "tables":     child_tables,
                "rows":       node.get("Plan Rows", 0),
                "cost":       cost,
            })

        elif category == "aggregate":
            aggregates.append({
                "node_type":  ntype,
                "strategy":   node.get("Strategy", ""),
                "group_key":  node.get("Group Key", []),
                "filter":     node.get("Filter", ""),
                "rows":       node.get("Plan Rows", 0),
                "cost":       cost,
            })

        elif category == "sort":
            sorts.append({
                "node_type": ntype,
                "sort_key":  node.get("Sort Key", []),
                "rows":      node.get("Plan Rows", 0),
                "cost":      cost,
            })

        elif category == "limit":
            other.append({
                "node_type": ntype,
                "rows":      node.get("Plan Rows", 0),
                "cost":      cost,
            })

    return {
        "scans":      scans,
        "joins":      joins,
        "aggregates": aggregates,
        "sorts":      sorts,
        "other":      other,
        "total_cost": root.get("Total Cost", 0),
    }


def _collect_child_relations(node):
    """Recursively collect relation names from scan nodes beneath a join."""
    relations = []
    for child in node.get("Plans", []):
        if child.get("Relation Name"):
            relations.append(child["Relation Name"])
        relations.extend(_collect_child_relations(child))
    return list(dict.fromkeys(relations))  # unique, order-preserved


# ---------------------------------------------------------------------------
# 4. AQP Cost Comparison  (the "WHY" logic)
# ---------------------------------------------------------------------------

def compare_aqp_costs(qep_cost, aqps):
    """
    Compares the QEP total cost against every AQP.

    Parameters
    ----------
    qep_cost : float
    aqps     : dict  {disabled_ops_str: aqp_json, ...}

    Returns a list of dicts:
    [
        {
            "disabled":     "enable_hashjoin",
            "aqp_cost":     1234.5,
            "cost_ratio":   2.3,       # aqp_cost / qep_cost
            "operator_name": "Hash Join",
        },
        ...
    ]
    sorted by cost_ratio ascending.
    """
    comparisons = []
    for disabled_str, aqp_json in aqps.items():
        aqp_cost = extract_cost(aqp_json)
        if aqp_cost is None or qep_cost is None or qep_cost == 0:
            continue
        ratio = aqp_cost / qep_cost
        # Build a friendly description of what was disabled
        disabled_list = [d.strip() for d in disabled_str.split(",")]
        friendly = ", ".join(
            OPERATOR_FRIENDLY_NAME.get(d, d) for d in disabled_list
        )
        comparisons.append({
            "disabled":      disabled_str,
            "disabled_list": disabled_list,
            "aqp_cost":      aqp_cost,
            "cost_ratio":    round(ratio, 2),
            "operator_name": friendly,
        })
    comparisons.sort(key=lambda c: c["cost_ratio"])
    return comparisons


# ---------------------------------------------------------------------------
# 5. Annotation Generation
# ---------------------------------------------------------------------------

def _format_scan_annotation(scan, aqp_comparisons):
    """Generate annotation text for a single scan operator."""
    relation = scan["relation"]
    alias = scan["alias"]
    node_type = scan["node_type"]
    label = f'"{alias}"' if alias and alias != relation else f'"{relation}"'

    lines = []
    # WHAT: how the table is accessed
    if node_type == "Seq Scan":
        lines.append(
            f"Table {label} is read using sequential scan."
        )
        # WHY: check if index scan AQPs exist but are more expensive
        has_index_aqp = any(
            "enable_seqscan" in c["disabled"] for c in aqp_comparisons
        )
        if has_index_aqp:
            lines.append(
                "Sequential scan was chosen because no suitable index exists "
                "or index scan is more expensive for this query."
            )
        else:
            lines.append("No index is defined on this table for the queried columns.")

    elif node_type in ("Index Scan", "Index Only Scan"):
        idx = scan["index_name"] or "an index"
        lines.append(
            f"Table {label} is accessed via {node_type.lower()} using {idx}."
        )
        cond = scan["index_cond"]
        if cond:
            lines.append(f"Index condition: {cond}")

    elif node_type in ("Bitmap Heap Scan", "Bitmap Index Scan"):
        lines.append(
            f"Table {label} is accessed via bitmap scan."
        )
        if scan["filter"]:
            lines.append(f"Recheck condition: {scan['filter']}")

    else:
        lines.append(f"Table {label} is accessed via {node_type.lower()}.")

    # Add filter info if present
    if scan["filter"] and "Bitmap" not in node_type:
        lines.append(f"Filter applied: {scan['filter']}")

    return " ".join(lines)


def _format_join_annotation(join, qep_cost, aqp_comparisons):
    """Generate annotation text for a single join operator."""
    node_type = join["node_type"]
    join_type = join["join_type"]
    condition = join["condition"]
    tables = join["tables"]

    lines = []
    table_str = " and ".join(f'"{t}"' for t in tables) if tables else "the tables"

    # WHAT
    friendly_join = node_type.lower()
    if join_type:
        lines.append(
            f"The {join_type.lower()} join between {table_str} is implemented "
            f"using the {friendly_join} operator."
        )
    else:
        lines.append(
            f"The join between {table_str} is implemented using "
            f"the {friendly_join} operator."
        )

    if condition:
        lines.append(f"Join condition: {condition}")

    # WHY: compare with alternatives
    # Find AQPs where this join type's flag was disabled (those use alternatives)
    own_flags = JOIN_DISABLE_MAP.get(node_type, set())
    # We want AQPs where one of the *other* join types was NOT disabled
    # i.e., AQPs that disabled the alternatives to force this type are uninteresting.
    # We want AQPs that disabled THIS type, forcing a different operator.
    alternatives = [
        c for c in aqp_comparisons
        if own_flags & set(c["disabled_list"])
    ]

    if alternatives:
        alt_parts = []
        for alt in alternatives:
            # Describe what the alternative was
            other_disabled = [
                d for d in alt["disabled_list"] if d not in own_flags
            ]
            if other_disabled:
                alt_name = ", ".join(
                    OPERATOR_FRIENDLY_NAME.get(d, d) for d in other_disabled
                )
                description = f"forcing neither {alt_name}"
            else:
                alt_name = alt["operator_name"]
                description = f"disabling {alt_name}"

            if alt["cost_ratio"] > 1:
                alt_parts.append(
                    f"{description} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f})"
                )
            else:
                alt_parts.append(
                    f"{description} has similar cost "
                    f"({alt['cost_ratio']}x, cost {alt['aqp_cost']:.1f})"
                )
        if alt_parts:
            lines.append("Alternatives: " + "; ".join(alt_parts) + ".")

    return " ".join(lines)


def _format_aggregate_annotation(agg):
    """Generate annotation text for an aggregate operator."""
    strategy = agg["strategy"]
    group_key = agg["group_key"]
    node_type = agg["node_type"]

    lines = []
    if group_key:
        keys_str = ", ".join(str(k) for k in group_key)
        lines.append(f"Grouping is performed on ({keys_str}).")
    if strategy:
        lines.append(f"Aggregation uses the {strategy.lower()} strategy ({node_type}).")
    else:
        lines.append(f"Aggregation is performed using {node_type}.")
    if agg["filter"]:
        lines.append(f"Having filter: {agg['filter']}")
    return " ".join(lines)


def _format_sort_annotation(sort):
    """Generate annotation text for a sort operator."""
    keys = sort["sort_key"]
    keys_str = ", ".join(str(k) for k in keys) if keys else "unspecified keys"
    return f"Results are sorted by ({keys_str}) using {sort['node_type'].lower()}."


def _format_limit_annotation(node):
    return f"Output is limited to {node['rows']} row(s)."


# ---------------------------------------------------------------------------
# 6. SQL ↔ Annotation Mapping
# ---------------------------------------------------------------------------

def _parse_sql_clauses(sql):
    """
    Roughly splits an SQL query into clause regions.
    Returns a list of (clause_name, start_pos, end_pos) tuples.
    """
    # Normalise whitespace for matching but keep original positions
    upper = sql.upper()

    clause_keywords = [
        "SELECT", "FROM", "WHERE", "GROUP BY", "HAVING",
        "ORDER BY", "LIMIT", "OFFSET",
        "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN",
        "FULL JOIN", "CROSS JOIN", "NATURAL JOIN",
        "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "FULL OUTER JOIN",
        "ON",
    ]
    # Sort longest first so "ORDER BY" matches before "ORDER"
    clause_keywords.sort(key=len, reverse=True)

    found = []
    for kw in clause_keywords:
        # Use word-boundary regex to avoid partial matches
        pattern = r'\b' + re.escape(kw) + r'\b'
        for m in re.finditer(pattern, upper):
            found.append((kw, m.start(), m.end()))

    # Sort by position
    found.sort(key=lambda x: x[1])

    # Assign each clause a range until the next clause starts
    clauses = []
    for i, (kw, start, _kw_end) in enumerate(found):
        end = found[i + 1][1] if i + 1 < len(found) else len(sql)
        clauses.append({
            "clause": kw,
            "start":  start,
            "end":    end,
            "text":   sql[start:end].strip(),
        })

    return clauses


def map_annotations_to_sql(sql, operators, qep_cost, aqp_comparisons):
    """
    Maps annotation strings to positions/clauses in the SQL query.

    Returns a list of dicts:
    [
        {
            "clause":      "FROM",
            "start":       12,
            "end":         45,
            "sql_text":    "from customer C, orders O",
            "annotations": ["Table \"customer\" is read using sequential scan. ..."],
        },
        ...
    ]
    """
    clauses = _parse_sql_clauses(sql)
    sql_lower = sql.lower()

    result = []
    used_clauses = set()

    for clause_info in clauses:
        annotations = []
        clause_name = clause_info["clause"]
        clause_text_lower = clause_info["text"].lower()

        # --- Scans → FROM / JOIN clauses ---
        if clause_name in ("FROM", "JOIN", "LEFT JOIN", "RIGHT JOIN",
                           "INNER JOIN", "FULL JOIN", "CROSS JOIN",
                           "NATURAL JOIN", "LEFT OUTER JOIN",
                           "RIGHT OUTER JOIN", "FULL OUTER JOIN"):
            for scan in operators["scans"]:
                rel = scan["relation"].lower()
                alias = scan["alias"].lower() if scan["alias"] else ""
                if rel in clause_text_lower or alias in clause_text_lower:
                    annotations.append(
                        _format_scan_annotation(scan, aqp_comparisons)
                    )

        # --- Joins → WHERE / ON / JOIN clauses ---
        if clause_name in ("WHERE", "ON", "FROM",
                           "JOIN", "LEFT JOIN", "RIGHT JOIN",
                           "INNER JOIN", "FULL JOIN"):
            for join in operators["joins"]:
                # Check if the join condition columns appear in this clause
                cond = join.get("condition", "") or ""
                tables = join.get("tables", [])
                # Heuristic: if any table in the join appears in the clause
                relevant = any(t.lower() in clause_text_lower for t in tables)
                if relevant or (cond and _condition_in_clause(cond, clause_text_lower)):
                    ann = _format_join_annotation(join, qep_cost, aqp_comparisons)
                    if ann not in annotations:
                        annotations.append(ann)

        # --- Aggregates → GROUP BY / HAVING / SELECT ---
        if clause_name in ("GROUP BY", "HAVING", "SELECT"):
            for agg in operators["aggregates"]:
                if clause_name == "GROUP BY" and agg["group_key"]:
                    annotations.append(_format_aggregate_annotation(agg))
                elif clause_name == "HAVING" and agg["filter"]:
                    annotations.append(_format_aggregate_annotation(agg))
                elif clause_name == "SELECT" and not agg["group_key"]:
                    # Scalar aggregate (e.g., COUNT(*) without GROUP BY)
                    annotations.append(_format_aggregate_annotation(agg))

        # --- Sorts → ORDER BY ---
        if clause_name == "ORDER BY":
            for sort in operators["sorts"]:
                annotations.append(_format_sort_annotation(sort))

        # --- Limit ---
        if clause_name == "LIMIT":
            for o in operators["other"]:
                if o["node_type"] == "Limit":
                    annotations.append(_format_limit_annotation(o))

        if annotations:
            key = (clause_info["start"], clause_info["end"])
            if key not in used_clauses:
                used_clauses.add(key)
                result.append({
                    "clause":      clause_name,
                    "start":       clause_info["start"],
                    "end":         clause_info["end"],
                    "sql_text":    clause_info["text"],
                    "annotations": annotations,
                })

    return result


def _condition_in_clause(condition, clause_lower):
    """Check if column names from a join condition appear in a clause."""
    # Extract column-like tokens from the condition
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_.]*', condition)
    return any(t.lower() in clause_lower for t in tokens)


# ---------------------------------------------------------------------------
# 7. Main Entry Point
# ---------------------------------------------------------------------------

def generate_annotations(conn, sql_query):
    """
    Main function: takes a DB connection and SQL query string,
    returns structured annotations.

    Returns
    -------
    dict with keys:
        "sql":          original SQL query
        "qep":          QEP dict (json + text)
        "operators":    extracted operator info
        "aqp_comparisons": cost comparison list
        "annotations":  list of clause-level annotations
        "total_cost":   QEP total cost
    """
    # 1. Get QEP
    qep = get_qep(conn, sql_query)
    if not qep:
        return {"error": "Failed to retrieve QEP."}

    # 2. Extract operators from QEP
    operators = extract_operators(qep["json"])

    # 3. Get AQPs and compare costs
    aqps = get_all_aqps(conn, sql_query)
    qep_cost = operators["total_cost"]
    aqp_comparisons = compare_aqp_costs(qep_cost, aqps)

    # 4. Map annotations to SQL clauses
    annotations = map_annotations_to_sql(
        sql_query, operators, qep_cost, aqp_comparisons
    )

    return {
        "sql":             sql_query,
        "qep":             qep,
        "operators":       operators,
        "aqp_comparisons": aqp_comparisons,
        "annotations":     annotations,
        "total_cost":      qep_cost,
    }


# ---------------------------------------------------------------------------
# Quick test (remove or guard behind __main__ later)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    conn = connect_db()
    if conn:
        test_query = (
            "SELECT * FROM customer C, orders O "
            "WHERE C.c_custkey = O.o_custkey"
        )
        result = generate_annotations(conn, test_query)

        if "error" in result:
            print(result["error"])
        else:
            print(f"QEP Total Cost: {result['total_cost']}")
            print(f"\n{'='*60}")
            print("ANNOTATIONS:")
            print(f"{'='*60}")
            for ann in result["annotations"]:
                print(f"\n[{ann['clause']}] {ann['sql_text']}")
                for a in ann["annotations"]:
                    print(f"  -> {a}")
            print(f"\n{'='*60}")
            print("AQP Cost Comparisons:")
            for c in result["aqp_comparisons"]:
                print(f"  Disabled {c['operator_name']}: "
                      f"cost={c['aqp_cost']:.1f}, ratio={c['cost_ratio']}x")

        close_db(conn)
