import sys
import json
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QSplitter, QGroupBox,
    QMessageBox, QLineEdit, QFormLayout, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QPlainTextEdit, QComboBox, QFileDialog,
    QGraphicsScene, QGraphicsView, QGraphicsRectItem,
    QGraphicsLineItem, QGraphicsSimpleTextItem, QGraphicsItem,
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import (
    QFont, QColor, QTextCharFormat, QTextCursor,
    QSyntaxHighlighter, QPen, QBrush, QPainter,
)

from preprocessing import connect_db, close_db
from annotation import (
    generate_annotations, get_root_plan, flatten_plan_tree, classify_node,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIGHLIGHT_COLORS = [
    QColor(173, 216, 230, 120),  # light blue
    QColor(144, 238, 144, 120),  # light green
    QColor(255, 218, 185, 120),  # peach
    QColor(221, 160, 221, 120),  # plum
    QColor(255, 255, 180, 120),  # light yellow
    QColor(200, 200, 255, 120),  # lavender
]

NODE_COLORS = {
    "scan":      QColor(173, 216, 230),
    "join":      QColor(144, 238, 144),
    "aggregate": QColor(255, 255, 180),
    "sort":      QColor(255, 218, 185),
    "limit":     QColor(221, 160, 221),
    "other":     QColor(220, 220, 220),
}

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


# ---------------------------------------------------------------------------
# Feature 1: SQL Syntax Highlighter
# ---------------------------------------------------------------------------

SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "GROUP\\s+BY", "ORDER\\s+BY", "HAVING",
    "LIMIT", "OFFSET", "JOIN", "INNER\\s+JOIN", "LEFT\\s+JOIN",
    "RIGHT\\s+JOIN", "FULL\\s+JOIN", "CROSS\\s+JOIN", "NATURAL\\s+JOIN",
    "LEFT\\s+OUTER\\s+JOIN", "RIGHT\\s+OUTER\\s+JOIN", "FULL\\s+OUTER\\s+JOIN",
    "ON", "AS", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE",
    "IS", "NULL", "DISTINCT", "UNION", "ALL", "CASE", "WHEN", "THEN",
    "ELSE", "END", "ASC", "DESC", "INSERT", "UPDATE", "DELETE",
    "CREATE", "ALTER", "DROP", "INTO", "VALUES", "SET",
    "COUNT", "SUM", "AVG", "MIN", "MAX", "DATE", "INTERVAL",
    "TRUE", "FALSE",
]


class SqlSyntaxHighlighter(QSyntaxHighlighter):
    """Applies SQL syntax colouring to a QPlainTextEdit."""

    def __init__(self, document):
        super().__init__(document)
        self._rules = []

        # Keywords — blue bold
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(0, 0, 180))
        kw_fmt.setFontWeight(QFont.Bold)
        kw_pattern = r'\b(' + '|'.join(SQL_KEYWORDS) + r')\b'
        self._rules.append((re.compile(kw_pattern, re.IGNORECASE), kw_fmt))

        # Strings — dark red
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor(163, 21, 21))
        self._rules.append((re.compile(r"'[^']*'"), str_fmt))

        # Numbers — dark cyan
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor(0, 128, 128))
        self._rules.append((re.compile(r'\b\d+\.?\d*\b'), num_fmt))

        # Comments — gray italic
        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor(128, 128, 128))
        cmt_fmt.setFontItalic(True)
        self._rules.append((re.compile(r'--.*$'), cmt_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


# ---------------------------------------------------------------------------
# Feature 3: Visual QEP Diagram
# ---------------------------------------------------------------------------

NODE_W = 200
NODE_H = 55
H_GAP = 30
V_GAP = 50


class QepNodeItem(QGraphicsRectItem):
    """A single operator box in the visual QEP tree."""

    def __init__(self, plan_node, annotation_index=-1, callback=None):
        super().__init__(0, 0, NODE_W, NODE_H)
        self.plan_node = plan_node
        self.annotation_index = annotation_index
        self._callback = callback

        node_type = plan_node.get("Node Type", "")
        category = classify_node(node_type)
        color = NODE_COLORS.get(category, NODE_COLORS["other"])

        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(80, 80, 80), 1.5))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        # Line 1: node type (bold)
        title = QGraphicsSimpleTextItem(node_type, self)
        title.setFont(QFont("Segoe UI", 8, QFont.Bold))
        title.setPos(4, 3)

        # Line 2: relation or condition
        detail = ""
        if plan_node.get("Relation Name"):
            detail = plan_node["Relation Name"]
            alias = plan_node.get("Alias", "")
            if alias and alias != plan_node["Relation Name"]:
                detail += f" ({alias})"
        elif plan_node.get("Hash Cond"):
            detail = plan_node["Hash Cond"]
        elif plan_node.get("Merge Cond"):
            detail = plan_node["Merge Cond"]
        elif plan_node.get("Join Filter"):
            detail = plan_node["Join Filter"]
        elif plan_node.get("Sort Key"):
            detail = ", ".join(str(k) for k in plan_node["Sort Key"])
        elif plan_node.get("Group Key"):
            detail = ", ".join(str(k) for k in plan_node["Group Key"])
        if len(detail) > 30:
            detail = detail[:27] + "..."
        detail_item = QGraphicsSimpleTextItem(detail, self)
        detail_item.setFont(QFont("Segoe UI", 7))
        detail_item.setPos(4, 19)

        # Line 3: cost
        cost = plan_node.get("Total Cost", 0)
        rows = plan_node.get("Plan Rows", 0)
        # Format large numbers compactly
        if rows >= 1_000_000:
            rows_str = f"{rows/1_000_000:.1f}M"
        elif rows >= 1_000:
            rows_str = f"{rows/1_000:.1f}K"
        else:
            rows_str = str(rows)
        cost_item = QGraphicsSimpleTextItem(f"Cost: {cost:.1f}  Rows: {rows_str}", self)
        cost_item.setFont(QFont("Segoe UI", 6))
        cost_item.setBrush(QBrush(QColor(100, 100, 100)))
        cost_item.setPos(4, 35)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._callback and self.annotation_index >= 0:
            self._callback(self.annotation_index)


class QepGraphicsView(QGraphicsView):
    """QGraphicsView with Ctrl+Scroll zoom."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SQL Query Plan Annotator \u2014 SC3020 Project 2")
        self.setMinimumSize(1200, 750)
        self.conn = None
        self._last_result = None

        # Linking data (Feature 2)
        self._annotation_char_ranges = []   # [(display_start, display_end, ann_idx)]
        self._tree_items_by_relation = {}   # relation_name -> QTreeWidgetItem
        self._visual_nodes = []             # list of QepNodeItem
        self._annotation_to_tree_items = {} # ann_idx -> [QTreeWidgetItem]

        self._build_ui()
        self._connect_db()

    # ==================================================================
    # UI Construction
    # ==================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- Feature 4: Collapsible DB connection bar ---
        conn_group = QGroupBox("Database Connection")
        conn_main_layout = QVBoxLayout(conn_group)

        # Always-visible row: toggle + status
        toggle_row = QHBoxLayout()
        self.btn_toggle_conn = QPushButton("\u25BC Hide Connection Settings")
        self.btn_toggle_conn.setFlat(True)
        self.btn_toggle_conn.setStyleSheet("text-align: left; padding: 2px 6px;")
        self.btn_toggle_conn.clicked.connect(self._toggle_conn_bar)
        toggle_row.addWidget(self.btn_toggle_conn)

        self.conn_status_label = QLabel("  DISCONNECTED")
        self.conn_status_label.setStyleSheet(
            "color: red; font-weight: bold; padding: 2px 8px;"
        )
        toggle_row.addWidget(self.conn_status_label)
        toggle_row.addStretch()
        conn_main_layout.addLayout(toggle_row)

        # Collapsible fields
        self.conn_fields_widget = QWidget()
        row = QHBoxLayout(self.conn_fields_widget)
        row.setContentsMargins(0, 0, 0, 0)
        self.input_host = QLineEdit("localhost")
        self.input_port = QLineEdit("5433")
        self.input_dbname = QLineEdit("TPC-H")
        self.input_user = QLineEdit("postgres")
        self.input_password = QLineEdit("qwerty")
        self.input_password.setEchoMode(QLineEdit.Password)
        self.btn_connect = QPushButton("Reconnect")
        self.btn_connect.clicked.connect(self._connect_db)

        for label, widget in [
            ("Host:", self.input_host), ("Port:", self.input_port),
            ("DB:", self.input_dbname), ("User:", self.input_user),
            ("Pass:", self.input_password),
        ]:
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        row.addWidget(self.btn_connect)

        conn_main_layout.addWidget(self.conn_fields_widget)
        main_layout.addWidget(conn_group)

        # --- Main splitter ---
        splitter = QSplitter(Qt.Horizontal)

        # ========== LEFT PANEL ==========
        left = QWidget()
        left_layout = QVBoxLayout(left)

        # Feature 5: Example queries dropdown
        example_row = QHBoxLayout()
        example_row.addWidget(QLabel("Examples:"))
        self.query_combo = QComboBox()
        self.query_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for label, _sql in EXAMPLE_QUERIES:
            self.query_combo.addItem(label)
        self.query_combo.currentIndexChanged.connect(self._on_example_selected)
        example_row.addWidget(self.query_combo, 1)
        left_layout.addLayout(example_row)

        # SQL input with syntax highlighting (Feature 1)
        query_label = QLabel("SQL Query:")
        query_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        left_layout.addWidget(query_label)

        self.query_input = QPlainTextEdit()
        self.query_input.setFont(QFont("Consolas", 11))
        self.query_input.setPlaceholderText(
            "Paste your SQL query here, or select an example above..."
        )
        self.query_input.setMinimumHeight(100)
        self._sql_highlighter = SqlSyntaxHighlighter(self.query_input.document())
        left_layout.addWidget(self.query_input)

        # Buttons row
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("Analyze Query")
        self.btn_run.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 8px; }"
            "QPushButton:hover { background-color: #45a049; }"
        )
        self.btn_run.clicked.connect(self._run_analysis)
        btn_row.addWidget(self.btn_run)

        # Feature 7: Export button
        self.btn_export = QPushButton("Export Results")
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet("padding: 8px;")
        self.btn_export.clicked.connect(self._export_results)
        btn_row.addWidget(self.btn_export)
        left_layout.addLayout(btn_row)

        # Annotated query display
        ann_label = QLabel("Annotated Query:")
        ann_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        left_layout.addWidget(ann_label)

        self.annotated_display = QTextEdit()
        self.annotated_display.setReadOnly(True)
        self.annotated_display.setFont(QFont("Consolas", 11))
        self.annotated_display.mousePressEvent = self._on_annotated_click
        left_layout.addWidget(self.annotated_display)

        splitter.addWidget(left)

        # ========== RIGHT PANEL ==========
        self.right_tabs = QTabWidget()

        # Tab 0: QEP Diagram (Feature 3)
        self.qep_scene = QGraphicsScene()
        self.qep_visual_view = QepGraphicsView(self.qep_scene)
        self.right_tabs.addTab(self.qep_visual_view, "QEP Diagram")

        # Tab 1: QEP Tree (list)
        self.qep_tree_widget = QTreeWidget()
        self.qep_tree_widget.setHeaderLabels(["Operator", "Detail", "Cost", "Rows"])
        self.qep_tree_widget.setColumnWidth(0, 200)
        self.qep_tree_widget.setColumnWidth(1, 250)
        self.qep_tree_widget.currentItemChanged.connect(self._on_tree_item_selected)
        self.right_tabs.addTab(self.qep_tree_widget, "QEP Tree")

        # Tab 2: QEP Text
        self.qep_text_display = QPlainTextEdit()
        self.qep_text_display.setReadOnly(True)
        self.qep_text_display.setFont(QFont("Consolas", 10))
        self.right_tabs.addTab(self.qep_text_display, "QEP Text")

        # Tab 3: AQP Comparison — chart + table (Features 6 & existing)
        aqp_tab = QWidget()
        aqp_layout = QVBoxLayout(aqp_tab)

        aqp_chart_label = QLabel("Cost Comparison Chart:")
        aqp_chart_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        aqp_layout.addWidget(aqp_chart_label)

        self.aqp_chart_scene = QGraphicsScene()
        self.aqp_chart_view = QGraphicsView(self.aqp_chart_scene)
        self.aqp_chart_view.setRenderHint(QPainter.Antialiasing)
        self.aqp_chart_view.setMaximumHeight(220)
        aqp_layout.addWidget(self.aqp_chart_view)

        aqp_table_label = QLabel("Detail Table:")
        aqp_table_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        aqp_layout.addWidget(aqp_table_label)

        self.aqp_tree_widget = QTreeWidget()
        self.aqp_tree_widget.setHeaderLabels(
            ["Disabled Operator(s)", "AQP Cost", "QEP Cost", "Cost Ratio"]
        )
        self.aqp_tree_widget.setColumnWidth(0, 250)
        aqp_layout.addWidget(self.aqp_tree_widget)

        self.right_tabs.addTab(aqp_tab, "AQP Comparison")

        # Tab 4: QEP JSON
        self.qep_json_display = QPlainTextEdit()
        self.qep_json_display.setReadOnly(True)
        self.qep_json_display.setFont(QFont("Consolas", 9))
        self.right_tabs.addTab(self.qep_json_display, "QEP JSON")

        splitter.addWidget(self.right_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        self.statusBar().showMessage("Ready")

    # ==================================================================
    # Feature 4: Toggle connection bar
    # ==================================================================
    def _toggle_conn_bar(self):
        visible = not self.conn_fields_widget.isVisible()
        self.conn_fields_widget.setVisible(visible)
        arrow = "\u25BC" if visible else "\u25B6"
        label = "Hide" if visible else "Show"
        self.btn_toggle_conn.setText(f"{arrow} {label} Connection Settings")

    # ==================================================================
    # Feature 5: Example query selection
    # ==================================================================
    def _on_example_selected(self, index):
        if index > 0 and index < len(EXAMPLE_QUERIES):
            self.query_input.setPlainText(EXAMPLE_QUERIES[index][1])

    # ==================================================================
    # DB helpers
    # ==================================================================
    def _get_db_config(self):
        return {
            "host":     self.input_host.text(),
            "port":     int(self.input_port.text()),
            "dbname":   self.input_dbname.text(),
            "user":     self.input_user.text(),
            "password": self.input_password.text(),
        }

    def _connect_db(self):
        if self.conn:
            close_db(self.conn)
        config = self._get_db_config()
        self.conn = connect_db(config)
        if self.conn:
            self.conn_status_label.setText("  CONNECTED")
            self.conn_status_label.setStyleSheet(
                "color: green; font-weight: bold; padding: 2px 8px;"
            )
            self.statusBar().showMessage(
                f"Connected to {config['dbname']}@{config['host']}:{config['port']}"
            )
        else:
            self.conn_status_label.setText("  DISCONNECTED")
            self.conn_status_label.setStyleSheet(
                "color: red; font-weight: bold; padding: 2px 8px;"
            )
            self.statusBar().showMessage("Connection failed")
            QMessageBox.warning(
                self, "Connection Error",
                "Could not connect to the database. Check your settings."
            )

    # ==================================================================
    # Core analysis
    # ==================================================================
    def _run_analysis(self):
        sql = self.query_input.toPlainText().strip()
        if not sql:
            QMessageBox.information(self, "No Query", "Please enter an SQL query.")
            return
        if not self.conn:
            QMessageBox.warning(self, "No Connection", "Not connected to a database.")
            return

        self.statusBar().showMessage("Analyzing query...")
        self.btn_run.setEnabled(False)
        QApplication.processEvents()

        try:
            result = generate_annotations(self.conn, sql)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Analysis failed:\n{e}")
            self.statusBar().showMessage("Analysis failed")
            self.btn_run.setEnabled(True)
            return

        if "error" in result:
            QMessageBox.warning(self, "Error", result["error"])
            self.statusBar().showMessage("Analysis failed")
            self.btn_run.setEnabled(True)
            return

        self._last_result = result
        self.btn_export.setEnabled(True)

        # Add to query history in combo box
        truncated = sql.replace("\n", " ")[:60]
        if sql not in [EXAMPLE_QUERIES[i][1] for i in range(len(EXAMPLE_QUERIES))]:
            self.query_combo.blockSignals(True)
            self.query_combo.insertItem(1, f"History: {truncated}...", sql)
            # Keep combo box manageable
            while self.query_combo.count() > len(EXAMPLE_QUERIES) + 20:
                self.query_combo.removeItem(self.query_combo.count() - 1)
            self.query_combo.blockSignals(False)

        # Populate all views
        self._display_annotated_query(sql, result["annotations"])
        self._display_qep_tree(result["qep"]["json"], result["annotations"])
        self._display_qep_visual(result["qep"]["json"], result["annotations"])
        self._display_qep_text(result["qep"]["text"])
        self._display_qep_json(result["qep"]["json"])
        self._display_aqp_chart(result["aqp_comparisons"], result["total_cost"])
        self._display_aqp_comparison(result["aqp_comparisons"], result["total_cost"])

        self.btn_run.setEnabled(True)
        self.statusBar().showMessage(
            f"Done \u2014 QEP total cost: {result['total_cost']:.2f}"
        )

    # ==================================================================
    # Display: Annotated Query (with char-range tracking for Feature 2)
    # ==================================================================
    def _display_annotated_query(self, sql, annotations):
        self.annotated_display.clear()
        self._annotation_char_ranges = []
        cursor = self.annotated_display.textCursor()

        default_fmt = QTextCharFormat()
        default_fmt.setFont(QFont("Consolas", 11))

        annotations_sorted = sorted(annotations, key=lambda a: a["start"])

        pos = 0
        color_idx = 0
        char_offset = 0  # tracks position in the display widget

        for ann_idx, ann in enumerate(annotations_sorted):
            # Text before this annotation
            if ann["start"] > pos:
                gap = sql[pos:ann["start"]]
                cursor.insertText(gap, default_fmt)
                char_offset += len(gap)

            # Highlighted clause
            hl_fmt = QTextCharFormat()
            hl_fmt.setFont(QFont("Consolas", 11, QFont.Bold))
            color = HIGHLIGHT_COLORS[color_idx % len(HIGHLIGHT_COLORS)]
            hl_fmt.setBackground(color)

            clause_text = sql[ann["start"]:ann["end"]]
            display_start = char_offset
            cursor.insertText(clause_text, hl_fmt)
            char_offset += len(clause_text)

            # Annotation lines
            ann_fmt = QTextCharFormat()
            ann_fmt.setFont(QFont("Segoe UI", 9))
            ann_fmt.setForeground(QColor(50, 50, 150))
            annotation_text = "\n".join(f"  \u00BB {a}" for a in ann["annotations"])
            block = f"\n{annotation_text}\n"
            cursor.insertText(block, ann_fmt)
            char_offset += len(block)

            display_end = char_offset
            self._annotation_char_ranges.append((display_start, display_end, ann_idx))

            pos = ann["end"]
            color_idx += 1

        if pos < len(sql):
            cursor.insertText(sql[pos:], default_fmt)

        self.annotated_display.setTextCursor(cursor)

    # ==================================================================
    # Display: QEP Tree (list view) with annotation mapping (Feature 2)
    # ==================================================================
    def _display_qep_tree(self, qep_json, annotations):
        self.qep_tree_widget.clear()
        self._tree_items_by_relation = {}
        self._annotation_to_tree_items = {}

        root_plan = get_root_plan(qep_json)
        self._add_tree_node(None, root_plan, annotations)
        self.qep_tree_widget.expandAll()

    def _add_tree_node(self, parent_item, plan_node, annotations):
        node_type = plan_node.get("Node Type", "Unknown")
        detail_parts = []
        if plan_node.get("Relation Name"):
            detail_parts.append(f"on {plan_node['Relation Name']}")
        if plan_node.get("Alias") and plan_node["Alias"] != plan_node.get("Relation Name"):
            detail_parts.append(f"(alias: {plan_node['Alias']})")
        if plan_node.get("Index Name"):
            detail_parts.append(f"using {plan_node['Index Name']}")
        for key in ("Hash Cond", "Merge Cond", "Join Filter"):
            if plan_node.get(key):
                detail_parts.append(f"cond: {plan_node[key]}")
                break
        if plan_node.get("Sort Key"):
            detail_parts.append(f"by {plan_node['Sort Key']}")
        if plan_node.get("Group Key"):
            detail_parts.append(f"group: {plan_node['Group Key']}")

        detail = " ".join(detail_parts)
        cost = f"{plan_node.get('Total Cost', 0):.2f}"
        rows = str(plan_node.get("Plan Rows", ""))

        if parent_item is None:
            item = QTreeWidgetItem(self.qep_tree_widget, [node_type, detail, cost, rows])
        else:
            item = QTreeWidgetItem(parent_item, [node_type, detail, cost, rows])

        # Build mapping: relation name -> tree item
        rel = plan_node.get("Relation Name", "")
        if rel:
            self._tree_items_by_relation[rel.lower()] = item

        # Map tree items to annotation indices
        for ann_idx, ann in enumerate(annotations):
            matched = False
            if rel and rel.lower() in ann.get("sql_text", "").lower():
                matched = True
            for key in ("Hash Cond", "Merge Cond", "Join Filter"):
                if plan_node.get(key) and ann.get("clause") in ("WHERE", "ON"):
                    matched = True
            if matched:
                self._annotation_to_tree_items.setdefault(ann_idx, []).append(item)

        # Store reverse mapping on the item itself
        item.setData(0, Qt.UserRole, id(item))

        for child in plan_node.get("Plans", []):
            self._add_tree_node(item, child, annotations)

    # ==================================================================
    # Display: Visual QEP Diagram (Feature 3)
    # ==================================================================
    def _display_qep_visual(self, qep_json, annotations):
        self.qep_scene.clear()
        self._visual_nodes = []

        root_plan = get_root_plan(qep_json)
        self._layout_visual_node(root_plan, 0, 0, annotations)

        # Fit the view to the scene
        self.qep_visual_view.setSceneRect(
            self.qep_scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        )
        self.qep_visual_view.fitInView(
            self.qep_scene.sceneRect(), Qt.KeepAspectRatio
        )

    def _layout_visual_node(self, plan_node, x, y, annotations, parent_item=None):
        """
        Recursively lay out the tree. Returns (node_item, total_width).
        """
        children = plan_node.get("Plans", [])

        # Find annotation index for this node
        ann_idx = self._find_annotation_index(plan_node, annotations)

        if not children:
            # Leaf node
            node_item = QepNodeItem(
                plan_node, ann_idx, self._on_visual_node_clicked
            )
            node_item.setPos(x, y)
            self.qep_scene.addItem(node_item)
            self._visual_nodes.append(node_item)
            return node_item, NODE_W
        else:
            # Lay out children first
            child_items = []
            child_width_total = 0
            cx = x
            for child in children:
                child_item, cw = self._layout_visual_node(
                    child, cx, y + NODE_H + V_GAP, annotations, None
                )
                child_items.append((child_item, cw))
                cx += cw + H_GAP
                child_width_total += cw
            child_width_total += H_GAP * (len(children) - 1)

            # Center parent above children
            parent_x = x + (child_width_total - NODE_W) / 2
            node_item = QepNodeItem(
                plan_node, ann_idx, self._on_visual_node_clicked
            )
            node_item.setPos(parent_x, y)
            self.qep_scene.addItem(node_item)
            self._visual_nodes.append(node_item)

            # Draw edges
            parent_cx = parent_x + NODE_W / 2
            parent_cy = y + NODE_H
            for child_item, _cw in child_items:
                child_cx = child_item.pos().x() + NODE_W / 2
                child_cy = child_item.pos().y()
                line = QGraphicsLineItem(parent_cx, parent_cy, child_cx, child_cy)
                line.setPen(QPen(QColor(100, 100, 100), 1.5))
                self.qep_scene.addItem(line)

            return node_item, max(child_width_total, NODE_W)

    def _find_annotation_index(self, plan_node, annotations):
        """Heuristic match: find which annotation this plan node belongs to."""
        rel = (plan_node.get("Relation Name") or "").lower()
        alias = (plan_node.get("Alias") or "").lower()
        node_type = plan_node.get("Node Type", "")

        for idx, ann in enumerate(annotations):
            text_lower = ann.get("sql_text", "").lower()
            # Scan nodes match on relation/alias in FROM clauses
            if rel and (rel in text_lower or alias in text_lower):
                return idx
            # Join nodes match on WHERE/ON clauses
            if classify_node(node_type) == "join" and ann.get("clause") in ("WHERE", "ON", "FROM"):
                for key in ("Hash Cond", "Merge Cond", "Join Filter"):
                    if plan_node.get(key):
                        return idx
            # Sort -> ORDER BY
            if classify_node(node_type) == "sort" and ann.get("clause") == "ORDER BY":
                return idx
            # Aggregate -> GROUP BY
            if classify_node(node_type) == "aggregate" and ann.get("clause") in ("GROUP BY", "SELECT"):
                return idx
        return -1

    # ==================================================================
    # Feature 2: Bidirectional Clicking
    # ==================================================================
    def _on_annotated_click(self, event):
        """When user clicks in annotated display, find and select matching tree node."""
        # Call original handler
        QTextEdit.mousePressEvent(self.annotated_display, event)

        cursor = self.annotated_display.cursorForPosition(event.pos())
        click_pos = cursor.position()

        for display_start, display_end, ann_idx in self._annotation_char_ranges:
            if display_start <= click_pos <= display_end:
                # Select in QEP tree
                items = self._annotation_to_tree_items.get(ann_idx, [])
                if items:
                    self.qep_tree_widget.setCurrentItem(items[0])
                    self.qep_tree_widget.scrollToItem(items[0])
                # Highlight in visual diagram
                self._highlight_visual_node(ann_idx)
                # Switch to diagram tab if not already visible
                break

    def _on_tree_item_selected(self, current, previous):
        """When a tree item is selected, highlight the corresponding annotation."""
        if not current or not self._last_result:
            return
        annotations = self._last_result.get("annotations", [])
        for ann_idx, items in self._annotation_to_tree_items.items():
            if current in items:
                self._scroll_to_annotation(ann_idx)
                self._highlight_visual_node(ann_idx)
                break

    def _on_visual_node_clicked(self, ann_idx):
        """Callback from QepNodeItem click."""
        self._scroll_to_annotation(ann_idx)
        items = self._annotation_to_tree_items.get(ann_idx, [])
        if items:
            self.qep_tree_widget.setCurrentItem(items[0])

    def _scroll_to_annotation(self, ann_idx):
        """Scroll the annotated display to show the given annotation."""
        for display_start, display_end, idx in self._annotation_char_ranges:
            if idx == ann_idx:
                cursor = self.annotated_display.textCursor()
                cursor.setPosition(display_start)
                cursor.setPosition(display_end, QTextCursor.KeepAnchor)
                self.annotated_display.setTextCursor(cursor)
                self.annotated_display.ensureCursorVisible()
                break

    def _highlight_visual_node(self, ann_idx):
        """Highlight the visual node matching the annotation index."""
        for node in self._visual_nodes:
            if node.annotation_index == ann_idx:
                node.setPen(QPen(QColor(255, 50, 50), 3))
            else:
                node.setPen(QPen(QColor(80, 80, 80), 1.5))

    # ==================================================================
    # Display: QEP Text & JSON
    # ==================================================================
    def _display_qep_text(self, text):
        self.qep_text_display.setPlainText(text)

    def _display_qep_json(self, qep_json):
        self.qep_json_display.setPlainText(json.dumps(qep_json, indent=2))

    # ==================================================================
    # Display: AQP Cost Bar Chart (Feature 6)
    # ==================================================================
    def _display_aqp_chart(self, comparisons, qep_cost):
        self.aqp_chart_scene.clear()

        if not comparisons:
            return

        max_cost = max(qep_cost, max(c["aqp_cost"] for c in comparisons))
        if max_cost == 0:
            return

        bar_h = 22
        gap = 6
        label_w = 220
        max_bar_w = 300
        cost_label_w = 80
        y = 10

        # QEP reference bar
        self._draw_bar(
            y, "QEP (chosen plan)", qep_cost, max_cost,
            QColor(76, 175, 80), label_w, max_bar_w, bar_h
        )
        y += bar_h + gap

        for c in comparisons:
            if c["cost_ratio"] > 1.5:
                color = QColor(229, 115, 115)   # red
            elif c["cost_ratio"] > 1.0:
                color = QColor(255, 213, 79)    # yellow
            else:
                color = QColor(129, 199, 132)   # green

            self._draw_bar(
                y, c["operator_name"], c["aqp_cost"], max_cost,
                color, label_w, max_bar_w, bar_h
            )
            y += bar_h + gap

        self.aqp_chart_scene.setSceneRect(
            self.aqp_chart_scene.itemsBoundingRect().adjusted(-5, -5, 5, 5)
        )

    def _draw_bar(self, y, label, cost, max_cost, color, label_w, max_bar_w, bar_h):
        # Label (right-aligned before bar)
        text = QGraphicsSimpleTextItem(label)
        text.setFont(QFont("Segoe UI", 8))
        text_width = text.boundingRect().width()
        text.setPos(label_w - text_width - 8, y + 2)
        self.aqp_chart_scene.addItem(text)

        # Bar
        bar_w = (cost / max_cost) * max_bar_w if max_cost > 0 else 0
        self.aqp_chart_scene.addRect(
            label_w, y, bar_w, bar_h,
            QPen(color.darker(120), 1),
            QBrush(color),
        )

        # Cost value (always to the right of the bar)
        cost_text = QGraphicsSimpleTextItem(f"{cost:.1f}")
        cost_text.setFont(QFont("Segoe UI", 8))
        cost_text.setPos(label_w + bar_w + 8, y + 2)
        self.aqp_chart_scene.addItem(cost_text)

    # ==================================================================
    # Display: AQP Table (existing)
    # ==================================================================
    def _display_aqp_comparison(self, comparisons, qep_cost):
        self.aqp_tree_widget.clear()
        for c in comparisons:
            item = QTreeWidgetItem([
                c["operator_name"],
                f"{c['aqp_cost']:.2f}",
                f"{qep_cost:.2f}",
                f"{c['cost_ratio']}x",
            ])
            if c["cost_ratio"] > 1.5:
                item.setForeground(3, QColor(200, 0, 0))
            elif c["cost_ratio"] < 1.0:
                item.setForeground(3, QColor(0, 150, 0))
            self.aqp_tree_widget.addTopLevelItem(item)

    # ==================================================================
    # Feature 7: Export Results
    # ==================================================================
    def _export_results(self):
        if not self._last_result:
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Results", "query_analysis",
            "Text Files (*.txt);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return

        try:
            if path.endswith(".json"):
                export = {
                    "sql":             self._last_result["sql"],
                    "total_cost":      self._last_result["total_cost"],
                    "annotations":     self._last_result["annotations"],
                    "aqp_comparisons": self._last_result["aqp_comparisons"],
                    "qep_json":        self._last_result["qep"]["json"],
                    "qep_text":        self._last_result["qep"]["text"],
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(export, f, indent=2, default=str)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    r = self._last_result
                    f.write("=" * 60 + "\n")
                    f.write("SQL QUERY PLAN ANALYSIS REPORT\n")
                    f.write("=" * 60 + "\n\n")

                    f.write("SQL Query:\n")
                    f.write(r["sql"] + "\n\n")

                    f.write("-" * 60 + "\n")
                    f.write("ANNOTATIONS:\n")
                    f.write("-" * 60 + "\n")
                    for ann in r["annotations"]:
                        f.write(f"\n[{ann['clause']}] {ann['sql_text']}\n")
                        for a in ann["annotations"]:
                            f.write(f"  >> {a}\n")

                    f.write("\n" + "-" * 60 + "\n")
                    f.write("QEP (Text Format):\n")
                    f.write("-" * 60 + "\n")
                    f.write(r["qep"]["text"] + "\n")

                    f.write("\n" + "-" * 60 + "\n")
                    f.write("AQP COST COMPARISONS:\n")
                    f.write("-" * 60 + "\n")
                    f.write(f"QEP Total Cost: {r['total_cost']:.2f}\n\n")
                    for c in r["aqp_comparisons"]:
                        f.write(
                            f"  Disabled {c['operator_name']}: "
                            f"cost={c['aqp_cost']:.2f}, "
                            f"ratio={c['cost_ratio']}x\n"
                        )

                    f.write("\n" + "=" * 60 + "\n")

            self.statusBar().showMessage(f"Exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    # ==================================================================
    # Cleanup
    # ==================================================================
    def closeEvent(self, event):
        if self.conn:
            close_db(self.conn)
        event.accept()


# ==================================================================
# Entry Point
# ==================================================================

def launch_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    launch_gui()
