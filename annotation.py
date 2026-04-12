import os
import re
import json
from openai import AzureOpenAI
from preprocessing import connect_db, get_qep, get_all_aqps, extract_cost, close_db


# ---------------------------------------------------------------------------
# 0. Azure OpenAI LLM Client
# ---------------------------------------------------------------------------

# Module-level LLM config — set via set_llm_config() from the GUI
_llm_config = {
    "endpoint": "https://sc3020-db.openai.azure.com/",
    "api_key": "",
    "deployment": "gpt-4.1-nano",
}


def set_llm_config(endpoint, api_key, deployment):
    _llm_config["endpoint"] = endpoint
    _llm_config["api_key"] = api_key
    _llm_config["deployment"] = deployment


def _get_llm_client():
    endpoint = _llm_config["endpoint"]
    api_key = _llm_config["api_key"]
    deployment = _llm_config["deployment"]

    if not all([endpoint, api_key, deployment]):
        return None, None

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-12-01-preview",
    )
    return client, deployment


def llm_enhance_annotations(sql_query, operators, aqp_comparisons, annotations):
    client, deployment = _get_llm_client()
    if not client:
        return annotations 

    # Build context for the LLM
    context = {
        "sql_query": sql_query,
        "operators": operators,
        "aqp_comparisons": aqp_comparisons,
        "template_annotations": [
            {"clause": a["clause"], "sql_text": a["sql_text"],
             "annotations": a["annotations"]}
            for a in annotations
        ],
    }

    prompt = (
        "You are a database query plan expert. Given an SQL query, its execution plan "
        "details, alternative plan cost comparisons, and template annotations, rewrite "
        "each annotation into a clear, concise, and insightful natural language explanation.\n\n"
        "Guidelines:\n"
        "- Explain HOW each part of the query is executed (scan type, join algorithm, etc.)\n"
        "- Explain WHY the optimizer chose that operator over alternatives, using cost ratios\n"
        "- Keep each annotation to 1-3 sentences, be specific with numbers\n"
        "- Do NOT add information not supported by the data\n"
        "- Use plain English understandable by someone learning databases\n\n"
        "Return ONLY a valid JSON array where each element has:\n"
        '  {"clause": "<clause name>", "annotations": ["<rewritten annotation 1>", ...]}\n\n'
        f"Data:\n{json.dumps(context, default=str)}"
    )

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]  # remove opening line
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        enhanced = json.loads(content)

        # Merge enhanced annotations back
        enhanced_map = {e["clause"]: e["annotations"] for e in enhanced}
        for ann in annotations:
            if ann["clause"] in enhanced_map:
                ann["annotations"] = enhanced_map[ann["clause"]]

        return annotations

    except Exception as e:
        print(f"LLM enhancement failed, using template annotations: {e}")
        return annotations  # fallback


def llm_chat(user_message, sql_query, qep_text, operators, aqp_comparisons, chat_history):

    client, deployment = _get_llm_client()
    if not client:
        return ("LLM not configured. Enter your Azure OpenAI API Key\n"
                "in the connection settings panel at the top.")

    system_msg = (
        "You are a helpful database query plan expert assistant. "
        "The user has submitted an SQL query and you have access to its "
        "query execution plan (QEP), operator details, and alternative plan "
        "cost comparisons. Answer the user's questions about the query, its "
        "execution plan, performance, and possible optimizations.\n\n"
        "Be concise, specific, and reference actual costs/operators from the data. "
        "If the user asks something unrelated to the query plan, politely redirect.\n\n"
        f"=== SQL QUERY ===\n{sql_query}\n\n"
        f"=== QEP (TEXT) ===\n{qep_text}\n\n"
        f"=== OPERATORS ===\n{json.dumps(operators, default=str)}\n\n"
        f"=== AQP COST COMPARISONS ===\n{json.dumps(aqp_comparisons, default=str)}"
    )

    messages = [{"role": "system", "content": system_msg}]

    # Add chat history
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=0.4,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"LLM error: {e}"


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
    "Seq Scan":          {"enable_seqscan"},
    "Index Scan":        {"enable_indexscan"},
    "Index Only Scan":   {"enable_indexonlyscan"},
    "Bitmap Heap Scan":  {"enable_bitmapscan"},
}

AGG_DISABLE_MAP = {
    "Aggregate":      set(),  # plain agg, no alternatives
    "HashAggregate":  {"enable_hashagg"},
    "GroupAggregate":  set(),  # no single flag to disable sort-based agg
}

# Human-readable names for planner settings
SCAN_FRIENDLY_NAME = {
    "enable_seqscan":       "sequential scan",
    "enable_indexscan":     "index scan",
    "enable_indexonlyscan": "index-only scan",
    "enable_bitmapscan":    "bitmap scan",
}

OPERATOR_FRIENDLY_NAME = {
    "enable_hashjoin":      "Hash Join",
    "enable_mergejoin":     "Merge Join",
    "enable_nestloop":      "Nested Loop",
    "enable_seqscan":       "Sequential Scan",
    "enable_indexscan":     "Index Scan",
    "enable_indexonlyscan": "Index Only Scan",
    "enable_bitmapscan":    "Bitmap Scan",
}

AGG_FRIENDLY_NAME = {
    "enable_hashagg": "hash aggregation",
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
def _extract_bitmap_info(node):
    """Recursively collect index names and conditions from Bitmap Index Scan children."""
    indexes = []
    conditions = []

    if node.get("Node Type") == "Bitmap Index Scan":
        indexes.append(node.get("Index Name"))
        conditions.append(node.get("Index Cond"))

    for child in node.get("Plans", []):
        child_idx, child_cond = _extract_bitmap_info(child)
        indexes.extend(child_idx)
        conditions.extend(child_cond)

    return indexes, conditions

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
        if ntype == "Bitmap Index Scan":
            continue # skip, handled by parent Bitmap Heap Scan

        category = classify_node(ntype)
        cost = node.get("Total Cost", 0)

        if category == "scan":
            scan_entry = {
            "node_type":    ntype,
            "relation":     node.get("Relation Name", ""),
            "alias":        node.get("Alias", ""),
            "schema":       node.get("Schema", ""),
            "filter":       node.get("Filter", ""),
            "index_name":   node.get("Index Name", ""),
            "index_cond":   node.get("Index Cond", ""),
            "recheck_cond": node.get("Recheck Cond", ""),
            "rows":         node.get("Plan Rows", 0),
            "cost":         cost,
            "startup_cost": node.get("Startup Cost", 0),
        }

            if ntype == "Bitmap Heap Scan":
                indexes, conditions = _extract_bitmap_info(node)
                scan_entry["index_name"] = ", ".join(filter(None, indexes))
                scan_entry["index_cond"] = "; ".join(filter(None, conditions))

            scans.append(scan_entry)

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
                "startup_cost": node.get("Startup Cost", 0),
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

    elif node_type == "Index Scan":
        idx = scan["index_name"] or "an index"
        lines.append(
            f"Table {label} is accessed via index scan using {idx}."
        )
        cond = scan["index_cond"]
        if cond:
            lines.append(f"Index condition: {cond}")

    elif node_type == "Index Only Scan":
        idx = scan["index_name"] or "an index"
        lines.append(
            f"Table {label} is accessed via index-only scan using {idx}. "
            f"All required columns are present in the index, "
            f"so the table heap is not accessed."
        )
        cond = scan["index_cond"]
        if cond:
            lines.append(f"Index condition: {cond}")

    elif node_type == "Bitmap Heap Scan":
        idx = scan["index_name"] or "an unknown index"
        lines.append(
            f"Table {label} is accessed via bitmap scan using the index {idx}."
    )
        recheck = scan["recheck_cond"]
        if recheck:
            lines.append(f"Recheck condition: {recheck}")

    elif node_type == "Bitmap Index Scan":
        return ""  # skip, handled by parent Bitmap Heap Scan

    else:
        lines.append(f"Table {label} is accessed via {node_type.lower()}.")

    # Add filter info if present
    if scan["filter"] and "Bitmap" not in node_type:
        lines.append(f"Filter applied: {scan['filter']}")

    # WHY: compare with alternatives (same pattern as join annotation)
    own_flags = SCAN_DISABLE_MAP.get(node_type, set())
    alternatives = [
        c for c in aqp_comparisons
        if own_flags & set(c["disabled_list"])
    ]

    if alternatives:
        alt_parts = []
        for alt in alternatives:
            alt_name = alt.get("operator_name") or ", ".join(
                SCAN_FRIENDLY_NAME.get(d, d)
                for d in alt["disabled_list"] if d not in own_flags
            )
            if alt["cost_ratio"] > 1.1:
                alt_parts.append(
                    f"disabling {alt_name} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f})"
                )
            elif alt["cost_ratio"] > 1:
                alt_parts.append(
                    f"disabling {alt_name} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f}) — similar cost"
                )
            else:
                alt_parts.append(
                    f"disabling {alt_name} has similar cost "
                    f"({alt['cost_ratio']}x, cost {alt['aqp_cost']:.1f})"
                )
        if alt_parts:
            lines.append("Alternatives: " + "; ".join(alt_parts) + ".")

    startup = scan.get("startup_cost", 0)
    total = scan.get("cost", 0)
    lines.append(f"Cost: startup={startup:.1f}, total={total:.1f}.")

    return "\n".join(lines)

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

    startup = join.get("startup_cost", 0)
    total = join.get("cost", 0)
    lines.append(f"Cost: startup={startup:.1f}, total={total:.1f}.")

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
            all_disabled_names = " and ".join(
                OPERATOR_FRIENDLY_NAME.get(d, d) for d in alt["disabled_list"]
            )
            description = f"disabling {all_disabled_names}"

            if alt["cost_ratio"] > 1.1:
                alt_parts.append(
                    f"{description} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f})"
                )
            elif alt["cost_ratio"] > 1:
                alt_parts.append(
                    f"{description} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f}) — similar cost"
                )
            else:
                alt_parts.append(
                    f"{description} has similar cost "
                    f"({alt['cost_ratio']}x, cost {alt['aqp_cost']:.1f})"
                )
        if alt_parts:
            lines.append("Alternatives: " + "; ".join(alt_parts) + ".")

    return "\n".join(lines)


def _format_aggregate_annotation(agg, aqp_comparisons):
    """Generate annotation text for an aggregate operator."""
    strategy = agg["strategy"]
    group_key = agg["group_key"]
    node_type = agg["node_type"]

    lines = []
    # What: describe the aggregation type and grouping
    if group_key:
        keys_str = ", ".join(str(k) for k in group_key)
        lines.append(f"Grouping is performed on ({keys_str}).")
    if strategy:
        lines.append(f"Aggregation uses the {strategy.lower()} strategy ({node_type}).")
    else:
        lines.append(f"Aggregation is performed using {node_type}.")
    if agg["filter"]:
        lines.append(f"Having filter: {agg['filter']}")

     # Why: compare with alternatives
    own_flags = AGG_DISABLE_MAP.get(node_type, set())
    alternatives = [
        c for c in aqp_comparisons
        if own_flags & set(c["disabled_list"])
    ]

    if alternatives:
        alt_parts = []
        for alt in alternatives:
            alt_name = alt.get("operator_name") or ", ".join(
                AGG_FRIENDLY_NAME.get(d, d)
                for d in alt["disabled_list"] if d not in own_flags
            )
            if alt["cost_ratio"] > 1.1:
                alt_parts.append(
                    f"disabling {alt_name} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f})"
                )
            elif alt["cost_ratio"] > 1:
                alt_parts.append(
                    f"disabling {alt_name} increases cost by "
                    f"~{alt['cost_ratio']}x (cost {alt['aqp_cost']:.1f}) — similar cost"
                )
            else:
                alt_parts.append(
                    f"disabling {alt_name} has similar cost "
                    f"({alt['cost_ratio']}x, cost {alt['aqp_cost']:.1f})"
                )
        if alt_parts:
            lines.append("Alternatives: " + "; ".join(alt_parts) + ".")

    return "\n".join(lines)


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
                    annotations.append(_format_aggregate_annotation(agg, aqp_comparisons))
                elif clause_name == "HAVING" and agg["filter"]:
                    annotations.append(_format_aggregate_annotation(agg, aqp_comparisons))
                elif clause_name == "SELECT" and not agg["group_key"]:
                    # Scalar aggregate (e.g., COUNT(*) without GROUP BY)
                    annotations.append(_format_aggregate_annotation(agg, aqp_comparisons))

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

def generate_annotations(conn, sql_query, use_llm=True):
    """
    Main function: takes a DB connection and SQL query string,
    returns structured annotations.

    Parameters
    ----------
    conn       : psycopg2 connection
    sql_query  : str
    use_llm    : bool — if True, attempt to enhance annotations via Azure OpenAI

    Returns
    -------
    dict with keys:
        "sql":          original SQL query
        "qep":          QEP dict (json + text)
        "operators":    extracted operator info
        "aqp_comparisons": cost comparison list
        "annotations":  list of clause-level annotations
        "total_cost":   QEP total cost
        "llm_used":     bool — whether LLM enhancement was applied
    """
    # 1. Get QEP
    qep = get_qep(conn, sql_query)
    if not qep:
        return {"error": "Failed to retrieve QEP."}

    # 2. Extract operators from QEP
    operators = extract_operators(qep["json"])

    # Check if any operators were found
    if not any([operators["scans"], operators["joins"], 
                operators["aggregates"], operators["sorts"], operators["other"]]):
        return {
            "sql":          sql_query,
            "qep":          qep,
            "operators":    operators,
            "aqp_comparisons": [],
            "annotations":  [],
            "total_cost":   operators["total_cost"],
            "llm_used":     False,
            "note":         "No annotatable operators found (e.g. SELECT 1)."
        }

    # 3. Get AQPs and compare costs
    aqps = get_all_aqps(conn, sql_query)
    qep_cost = operators["total_cost"]
    aqp_comparisons = compare_aqp_costs(qep_cost, aqps)

    # 4. Map annotations to SQL clauses (template-based)
    annotations = map_annotations_to_sql(
        sql_query, operators, qep_cost, aqp_comparisons
    )

    # Store template annotations before LLM enhancement
    for ann in annotations:
        ann["template_annotations"] = ann["annotations"][:]

    # 5. Optionally enhance annotations with LLM
    llm_used = False
    if use_llm:
        import copy
        llm_annotations = copy.deepcopy(annotations)
        llm_annotations = llm_enhance_annotations(
            sql_query, operators, aqp_comparisons, llm_annotations
        )
        # Check if LLM actually changed anything
        for orig, enhanced in zip(annotations, llm_annotations):
            if orig["annotations"] != enhanced["annotations"]:
                orig["llm_annotations"] = enhanced["annotations"]
                llm_used = True
            else:
                orig["llm_annotations"] = []

    return {
        "sql":             sql_query,
        "qep":             qep,
        "operators":       operators,
        "aqp_comparisons": aqp_comparisons,
        "annotations":     annotations,
        "total_cost":      qep_cost,
        "llm_used":        llm_used,
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
