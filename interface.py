"""
Main GUI window — orchestrates all modules.
"""

import sys
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QPlainTextEdit, QComboBox, QCheckBox, QMessageBox,
    QGraphicsScene, QGraphicsLineItem, QGraphicsSimpleTextItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QPen, QBrush

from annotation import generate_annotations, get_root_plan, classify_node
from modules.constants import HIGHLIGHT_COLORS, EXAMPLE_QUERIES
from modules.themes import ThemeManager
from modules.syntax import SqlSyntaxHighlighter
from modules.qep_diagram import QepNodeItem, QepGraphicsView, NODE_W, NODE_H, H_GAP, V_GAP
from modules.chat_panel import ChatPanel
from modules.settings_panel import SettingsPanel
from modules.export import export_results


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SQL Query Plan Annotator \u2014 SC3020 Project 2")
        self.setMinimumSize(1200, 750)
        self._last_result = None
        self.theme = ThemeManager()

        # Linking data for bidirectional clicking
        self._annotation_char_ranges = []
        self._tree_items_by_relation = {}
        self._visual_nodes = []
        self._annotation_to_tree_items = {}

        self._build_ui()
        self.settings_panel.connect_db()

    # ==================================================================
    # UI Construction
    # ==================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- Top bar ---
        top_bar = QHBoxLayout()

        self.btn_toggle_settings = QPushButton("\u25BC Hide Settings")
        self.btn_toggle_settings.setFlat(True)
        self.btn_toggle_settings.clicked.connect(self._toggle_settings)
        top_bar.addWidget(self.btn_toggle_settings)

        self.db_status_label = QLabel("  DB: Disconnected")
        self.db_status_label.setStyleSheet("color: red; font-weight: bold; padding: 2px 8px;")
        top_bar.addWidget(self.db_status_label)

        self.llm_status_label = QLabel("  LLM: Not Configured")
        self.llm_status_label.setStyleSheet("color: orange; font-weight: bold; padding: 2px 8px;")
        top_bar.addWidget(self.llm_status_label)

        top_bar.addStretch()

        self.btn_theme = QPushButton("\u263E Dark Mode")
        self.btn_theme.setFlat(True)
        self.btn_theme.clicked.connect(self._toggle_theme)
        top_bar.addWidget(self.btn_theme)

        main_layout.addLayout(top_bar)

        # --- Settings panel ---
        self.settings_panel = SettingsPanel(self.theme)
        self.settings_panel._on_db_status = self._on_db_status
        self.settings_panel._on_llm_status = self._on_llm_status
        self.settings_panel._status_callback = self.statusBar().showMessage
        main_layout.addWidget(self.settings_panel)

        # --- Main splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ========== LEFT PANEL ==========
        left = QWidget()
        left_layout = QVBoxLayout(left)

        # Example queries dropdown
        example_row = QHBoxLayout()
        example_row.addWidget(QLabel("Examples:"))
        self.query_combo = QComboBox()
        self.query_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for label, _ in EXAMPLE_QUERIES:
            self.query_combo.addItem(label)
        self.query_combo.currentIndexChanged.connect(self._on_example_selected)
        example_row.addWidget(self.query_combo, 1)
        left_layout.addLayout(example_row)

        # SQL input with syntax highlighting
        left_layout.addWidget(QLabel("SQL Query:", font=QFont("Segoe UI", 10, QFont.Bold)))
        self.query_input = QPlainTextEdit()
        self.query_input.setFont(QFont("Consolas", 11))
        self.query_input.setPlaceholderText("Paste your SQL query here, or select an example above...")
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

        self.btn_export = QPushButton("Export Results")
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet("padding: 8px;")
        self.btn_export.clicked.connect(self._export_results)
        btn_row.addWidget(self.btn_export)

        self.chk_llm = QCheckBox("Show AI Insights")
        self.chk_llm.setChecked(True)
        self.chk_llm.setToolTip("Show LLM-generated insights alongside algorithm annotations.")
        self.chk_llm.toggled.connect(self._on_llm_toggle)
        btn_row.addWidget(self.chk_llm)
        left_layout.addLayout(btn_row)

        # Annotated query display
        left_layout.addWidget(QLabel("Annotated Query:", font=QFont("Segoe UI", 10, QFont.Bold)))
        self.annotated_display = QTextEdit()
        self.annotated_display.setReadOnly(True)
        self.annotated_display.setFont(QFont("Consolas", 11))
        self.annotated_display.mousePressEvent = self._on_annotated_click
        left_layout.addWidget(self.annotated_display)
        splitter.addWidget(left)

        # ========== RIGHT PANEL (tabs) ==========
        self.right_tabs = QTabWidget()

        # Tab: QEP Diagram
        self.qep_scene = QGraphicsScene()
        self.qep_visual_view = QepGraphicsView(self.qep_scene)
        self.right_tabs.addTab(self.qep_visual_view, "QEP Diagram")

        # Tab: QEP Tree
        self.qep_tree_widget = QTreeWidget()
        self.qep_tree_widget.setHeaderLabels(["Operator", "Detail", "Cost", "Rows"])
        self.qep_tree_widget.setColumnWidth(0, 200)
        self.qep_tree_widget.setColumnWidth(1, 250)
        self.qep_tree_widget.currentItemChanged.connect(self._on_tree_item_selected)
        self.right_tabs.addTab(self.qep_tree_widget, "QEP Tree")

        # Tab: QEP Text
        self.qep_text_display = QPlainTextEdit()
        self.qep_text_display.setReadOnly(True)
        self.qep_text_display.setFont(QFont("Consolas", 10))
        self.right_tabs.addTab(self.qep_text_display, "QEP Text")

        # Tab: AQP Comparison (chart + table)
        aqp_tab = QWidget()
        aqp_layout = QVBoxLayout(aqp_tab)
        aqp_layout.addWidget(QLabel("Cost Comparison Chart:", font=QFont("Segoe UI", 9, QFont.Bold)))
        self.aqp_chart_scene = QGraphicsScene()
        from PySide6.QtWidgets import QGraphicsView
        from PySide6.QtGui import QPainter
        self.aqp_chart_view = QGraphicsView(self.aqp_chart_scene)
        self.aqp_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.aqp_chart_view.setMaximumHeight(220)
        aqp_layout.addWidget(self.aqp_chart_view)
        aqp_layout.addWidget(QLabel("Detail Table:", font=QFont("Segoe UI", 9, QFont.Bold)))
        self.aqp_tree_widget = QTreeWidget()
        self.aqp_tree_widget.setHeaderLabels(["Disabled Operator(s)", "AQP Cost", "QEP Cost", "Cost Ratio"])
        self.aqp_tree_widget.setColumnWidth(0, 250)
        aqp_layout.addWidget(self.aqp_tree_widget)
        self.right_tabs.addTab(aqp_tab, "AQP Comparison")

        # Tab: QEP JSON
        self.qep_json_display = QPlainTextEdit()
        self.qep_json_display.setReadOnly(True)
        self.qep_json_display.setFont(QFont("Consolas", 9))
        self.right_tabs.addTab(self.qep_json_display, "QEP JSON")

        # Tab: Ask AI (chat)
        self.chat_panel = ChatPanel(self.theme)
        self.chat_panel.set_status_callback(self.statusBar().showMessage)
        self.right_tabs.addTab(self.chat_panel, "Ask AI")

        splitter.addWidget(self.right_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)
        self.statusBar().showMessage("Ready")

    # ==================================================================
    # Settings toggle
    # ==================================================================
    def _toggle_settings(self):
        visible = not self.settings_panel.isVisible()
        self.settings_panel.setVisible(visible)
        arrow = "\u25BC" if visible else "\u25B6"
        self.btn_toggle_settings.setText(f"{arrow} {'Hide' if visible else 'Show'} Settings")

    # ==================================================================
    # Status callbacks from SettingsPanel
    # ==================================================================
    def _on_db_status(self, connected, msg):
        if connected:
            self.db_status_label.setText("  DB: Connected")
            self.db_status_label.setStyleSheet("color: #4CAF50; font-weight: bold; padding: 2px 8px;")
        else:
            self.db_status_label.setText("  DB: Disconnected")
            self.db_status_label.setStyleSheet("color: #F44336; font-weight: bold; padding: 2px 8px;")
        self.statusBar().showMessage(msg)

    def _on_llm_status(self, status, color):
        self.llm_status_label.setText(f"  LLM: {status}")
        self.llm_status_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px 8px;")

    # ==================================================================
    # Theme toggle
    # ==================================================================
    def _toggle_theme(self):
        is_dark = self.theme.toggle()
        self.btn_theme.setText("\u2600 Light Mode" if is_dark else "\u263E Dark Mode")

        # Restyle all theme-aware widgets
        btn_color = self.theme.button_text_color()
        self.btn_theme.setStyleSheet(f"padding: 2px 10px; color: {btn_color};")
        self.btn_toggle_settings.setStyleSheet(f"text-align: left; padding: 2px 6px; color: {btn_color};")
        self._sql_highlighter.set_dark(is_dark)
        self.settings_panel.apply_theme()
        self.chat_panel.apply_theme()

        # Re-render views
        if self._last_result:
            r = self._last_result
            self._display_annotated_query(r["sql"], r["annotations"], self.chk_llm.isChecked())
            self._display_qep_visual(r["qep"]["json"], r["annotations"])
            self._display_aqp_chart(r["aqp_comparisons"], r["total_cost"])
            self._display_aqp_comparison(r["aqp_comparisons"], r["total_cost"])

    # ==================================================================
    # Example queries
    # ==================================================================
    def _on_example_selected(self, index):
        if 0 < index < len(EXAMPLE_QUERIES):
            self.query_input.setPlainText(EXAMPLE_QUERIES[index][1])

    # ==================================================================
    # Core analysis
    # ==================================================================
    def _run_analysis(self):
        sql = self.query_input.toPlainText().strip()
        if not sql:
            QMessageBox.information(self, "No Query", "Please enter an SQL query.")
            return
        conn = self.settings_panel.conn
        if not conn:
            QMessageBox.warning(self, "No Connection", "Not connected to a database.")
            return

        self.statusBar().showMessage("Analyzing query...")
        self.btn_run.setEnabled(False)
        QApplication.processEvents()

        try:
            result = generate_annotations(conn, sql, use_llm=self.chk_llm.isChecked())
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

        # Add to query history
        truncated = sql.replace("\n", " ")[:60]
        if sql not in [EXAMPLE_QUERIES[i][1] for i in range(len(EXAMPLE_QUERIES))]:
            self.query_combo.blockSignals(True)
            self.query_combo.insertItem(1, f"History: {truncated}...", sql)
            while self.query_combo.count() > len(EXAMPLE_QUERIES) + 20:
                self.query_combo.removeItem(self.query_combo.count() - 1)
            self.query_combo.blockSignals(False)

        # Populate all views
        self._display_annotated_query(sql, result["annotations"], self.chk_llm.isChecked())
        self._display_qep_tree(result["qep"]["json"], result["annotations"])
        self._display_qep_visual(result["qep"]["json"], result["annotations"])
        self.qep_text_display.setPlainText(result["qep"]["text"])
        self.qep_json_display.setPlainText(json.dumps(result["qep"]["json"], indent=2))
        self._display_aqp_chart(result["aqp_comparisons"], result["total_cost"])
        self._display_aqp_comparison(result["aqp_comparisons"], result["total_cost"])
        self.chat_panel.set_result(result)

        self.btn_run.setEnabled(True)
        llm_tag = " [LLM enhanced]" if result.get("llm_used") else ""
        self.statusBar().showMessage(f"Done \u2014 QEP total cost: {result['total_cost']:.2f}{llm_tag}")

    def _on_llm_toggle(self, checked):
        if self._last_result:
            self._display_annotated_query(
                self._last_result["sql"], self._last_result["annotations"], checked
            )

    def _export_results(self):
        path = export_results(self, self._last_result)
        if path:
            self.statusBar().showMessage(f"Exported to {path}")

    # ==================================================================
    # Annotated query display
    # ==================================================================
    def _display_annotated_query(self, sql, annotations, show_llm=True):
        self.annotated_display.clear()
        self._annotation_char_ranges = []
        cursor = self.annotated_display.textCursor()
        t = self.theme

        sql_fmt = QTextCharFormat()
        sql_fmt.setFont(QFont("Consolas", 11))
        sql_fmt.setForeground(t.sql_color())

        annotations_sorted = sorted(annotations, key=lambda a: a["start"])

        pos = 0
        color_idx = 0
        char_offset = 0

        for ann_idx, ann in enumerate(annotations_sorted):
            if ann["start"] > pos:
                gap = sql[pos:ann["start"]]
                cursor.insertText(gap, sql_fmt)
                char_offset += len(gap)

            hl_fmt = QTextCharFormat()
            hl_fmt.setFont(QFont("Consolas", 11, QFont.Bold))
            hl_fmt.setForeground(t.sql_color())
            hl_fmt.setBackground(HIGHLIGHT_COLORS[color_idx % len(HIGHLIGHT_COLORS)])

            display_start = char_offset
            cursor.insertText(sql[ann["start"]:ann["end"]], hl_fmt)
            char_offset += ann["end"] - ann["start"]

            # Clause header
            cursor.insertText("\n", sql_fmt)
            char_offset += 1
            header_fmt = QTextCharFormat()
            header_fmt.setFont(QFont("Segoe UI", 8, QFont.Bold))
            header_fmt.setForeground(t.header_fg())
            header_fmt.setBackground(t.header_bg())
            clause_header = f"  [{ann['clause']}] "
            cursor.insertText(clause_header, header_fmt)
            char_offset += len(clause_header)
            cursor.insertText("\n", sql_fmt)
            char_offset += 1

            # Algorithm annotations
            template = ann.get("template_annotations", ann["annotations"])
            algo_label = QTextCharFormat()
            algo_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
            algo_label.setForeground(t.algo_label_color())
            algo_text = QTextCharFormat()
            algo_text.setFont(QFont("Segoe UI", 9))
            algo_text.setForeground(t.algo_text_color())

            cursor.insertText("  Analysis: ", algo_label)
            char_offset += len("  Analysis: ")
            for i, a in enumerate(template):
                line = a + (" " if i < len(template) - 1 else "")
                cursor.insertText(line, algo_text)
                char_offset += len(line)
            cursor.insertText("\n", sql_fmt)
            char_offset += 1

            # LLM annotations
            llm_anns = ann.get("llm_annotations", [])
            if show_llm and llm_anns:
                llm_label = QTextCharFormat()
                llm_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
                llm_label.setForeground(t.llm_label_color())
                llm_text = QTextCharFormat()
                llm_text.setFont(QFont("Segoe UI", 9))
                llm_text.setForeground(t.llm_text_color())

                cursor.insertText("  AI Insight: ", llm_label)
                char_offset += len("  AI Insight: ")
                for i, a in enumerate(llm_anns):
                    line = a + (" " if i < len(llm_anns) - 1 else "")
                    cursor.insertText(line, llm_text)
                    char_offset += len(line)
                cursor.insertText("\n", sql_fmt)
                char_offset += 1

            cursor.insertText("\n", sql_fmt)
            char_offset += 1
            self._annotation_char_ranges.append((display_start, char_offset, ann_idx))
            pos = ann["end"]
            color_idx += 1

        if pos < len(sql):
            cursor.insertText(sql[pos:], sql_fmt)
        self.annotated_display.setTextCursor(cursor)

    # ==================================================================
    # QEP Tree (list view)
    # ==================================================================
    def _display_qep_tree(self, qep_json, annotations):
        self.qep_tree_widget.clear()
        self._tree_items_by_relation = {}
        self._annotation_to_tree_items = {}
        self._add_tree_node(None, get_root_plan(qep_json), annotations)
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

        cost = f"{plan_node.get('Total Cost', 0):.2f}"
        rows = str(plan_node.get("Plan Rows", ""))
        cols = [node_type, " ".join(detail_parts), cost, rows]
        item = QTreeWidgetItem(self.qep_tree_widget if parent_item is None else parent_item, cols)

        rel = plan_node.get("Relation Name", "")
        if rel:
            self._tree_items_by_relation[rel.lower()] = item
        for ann_idx, ann in enumerate(annotations):
            matched = rel and rel.lower() in ann.get("sql_text", "").lower()
            for key in ("Hash Cond", "Merge Cond", "Join Filter"):
                if plan_node.get(key) and ann.get("clause") in ("WHERE", "ON"):
                    matched = True
            if matched:
                self._annotation_to_tree_items.setdefault(ann_idx, []).append(item)
        item.setData(0, Qt.ItemDataRole.UserRole, id(item))

        for child in plan_node.get("Plans", []):
            self._add_tree_node(item, child, annotations)

    # ==================================================================
    # Visual QEP Diagram
    # ==================================================================
    def _display_qep_visual(self, qep_json, annotations):
        self.qep_scene.clear()
        self.qep_scene.setBackgroundBrush(QBrush(self.theme.scene_bg()))
        self._visual_nodes = []
        self._layout_visual_node(get_root_plan(qep_json), 0, 0, annotations)
        self.qep_visual_view.setSceneRect(self.qep_scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.qep_visual_view.fitInView(self.qep_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _layout_visual_node(self, plan_node, x, y, annotations):
        children = plan_node.get("Plans", [])
        ann_idx = self._find_annotation_index(plan_node, annotations)

        if not children:
            node_item = QepNodeItem(plan_node, ann_idx, self._on_visual_node_clicked)
            node_item.setPos(x, y)
            self.qep_scene.addItem(node_item)
            self._visual_nodes.append(node_item)
            return node_item, NODE_W

        child_items = []
        cx = x
        child_width_total = 0
        for child in children:
            ci, cw = self._layout_visual_node(child, cx, y + NODE_H + V_GAP, annotations)
            child_items.append((ci, cw))
            cx += cw + H_GAP
            child_width_total += cw
        child_width_total += H_GAP * (len(children) - 1)

        parent_x = x + (child_width_total - NODE_W) / 2
        node_item = QepNodeItem(plan_node, ann_idx, self._on_visual_node_clicked)
        node_item.setPos(parent_x, y)
        self.qep_scene.addItem(node_item)
        self._visual_nodes.append(node_item)

        for ci, _ in child_items:
            line = QGraphicsLineItem(parent_x + NODE_W / 2, y + NODE_H, ci.pos().x() + NODE_W / 2, ci.pos().y())
            line.setPen(QPen(QColor(100, 100, 100), 1.5))
            self.qep_scene.addItem(line)

        return node_item, max(child_width_total, NODE_W)

    def _find_annotation_index(self, plan_node, annotations):
        rel = (plan_node.get("Relation Name") or "").lower()
        alias = (plan_node.get("Alias") or "").lower()
        node_type = plan_node.get("Node Type", "")
        for idx, ann in enumerate(annotations):
            text_lower = ann.get("sql_text", "").lower()
            if rel and (rel in text_lower or alias in text_lower):
                return idx
            if classify_node(node_type) == "join" and ann.get("clause") in ("WHERE", "ON", "FROM"):
                for key in ("Hash Cond", "Merge Cond", "Join Filter"):
                    if plan_node.get(key):
                        return idx
            if classify_node(node_type) == "sort" and ann.get("clause") == "ORDER BY":
                return idx
            if classify_node(node_type) == "aggregate" and ann.get("clause") in ("GROUP BY", "SELECT"):
                return idx
        return -1

    # ==================================================================
    # Bidirectional clicking
    # ==================================================================
    def _on_annotated_click(self, event):
        QTextEdit.mousePressEvent(self.annotated_display, event)
        click_pos = self.annotated_display.cursorForPosition(event.pos()).position()
        for display_start, display_end, ann_idx in self._annotation_char_ranges:
            if display_start <= click_pos <= display_end:
                items = self._annotation_to_tree_items.get(ann_idx, [])
                if items:
                    self.qep_tree_widget.setCurrentItem(items[0])
                    self.qep_tree_widget.scrollToItem(items[0])
                self._highlight_visual_node(ann_idx)
                break

    def _on_tree_item_selected(self, current, previous):
        if not current or not self._last_result:
            return
        for ann_idx, items in self._annotation_to_tree_items.items():
            if current in items:
                self._scroll_to_annotation(ann_idx)
                self._highlight_visual_node(ann_idx)
                break

    def _on_visual_node_clicked(self, ann_idx):
        self._scroll_to_annotation(ann_idx)
        items = self._annotation_to_tree_items.get(ann_idx, [])
        if items:
            self.qep_tree_widget.setCurrentItem(items[0])

    def _scroll_to_annotation(self, ann_idx):
        for ds, de, idx in self._annotation_char_ranges:
            if idx == ann_idx:
                cursor = self.annotated_display.textCursor()
                cursor.setPosition(ds)
                cursor.setPosition(de, QTextCursor.MoveMode.KeepAnchor)
                self.annotated_display.setTextCursor(cursor)
                self.annotated_display.ensureCursorVisible()
                break

    def _highlight_visual_node(self, ann_idx):
        for node in self._visual_nodes:
            if node.annotation_index == ann_idx:
                node.setPen(QPen(QColor(255, 50, 50), 3))
            else:
                node.setPen(QPen(QColor(80, 80, 80), 1.5))

    # ==================================================================
    # AQP chart + table
    # ==================================================================
    def _display_aqp_chart(self, comparisons, qep_cost):
        self.aqp_chart_scene.clear()
        self.aqp_chart_scene.setBackgroundBrush(QBrush(self.theme.scene_bg()))
        if not comparisons:
            return
        max_cost = max(qep_cost, max(c["aqp_cost"] for c in comparisons))
        if max_cost == 0:
            return

        bar_h, gap, label_w, max_bar_w, y = 22, 6, 220, 300, 10
        self._draw_bar(y, "QEP (chosen plan)", qep_cost, max_cost, QColor(76, 175, 80), label_w, max_bar_w, bar_h)
        y += bar_h + gap
        for c in comparisons:
            color = QColor(229, 115, 115) if c["cost_ratio"] > 1.5 else QColor(255, 213, 79) if c["cost_ratio"] > 1.0 else QColor(129, 199, 132)
            self._draw_bar(y, c["operator_name"], c["aqp_cost"], max_cost, color, label_w, max_bar_w, bar_h)
            y += bar_h + gap
        self.aqp_chart_scene.setSceneRect(self.aqp_chart_scene.itemsBoundingRect().adjusted(-5, -5, 5, 5))

    def _draw_bar(self, y, label, cost, max_cost, color, label_w, max_bar_w, bar_h):
        tc = self.theme.chart_text_color()
        text = QGraphicsSimpleTextItem(label)
        text.setFont(QFont("Segoe UI", 8))
        text.setBrush(QBrush(tc))
        text.setPos(label_w - text.boundingRect().width() - 8, y + 2)
        self.aqp_chart_scene.addItem(text)

        bar_w = (cost / max_cost) * max_bar_w if max_cost > 0 else 0
        self.aqp_chart_scene.addRect(label_w, y, bar_w, bar_h, QPen(color.darker(120), 1), QBrush(color))

        ct = QGraphicsSimpleTextItem(f"{cost:.1f}")
        ct.setFont(QFont("Segoe UI", 8))
        ct.setBrush(QBrush(tc))
        ct.setPos(label_w + bar_w + 8, y + 2)
        self.aqp_chart_scene.addItem(ct)

    def _display_aqp_comparison(self, comparisons, qep_cost):
        self.aqp_tree_widget.clear()
        red, green = self.theme.aqp_red(), self.theme.aqp_green()
        for c in comparisons:
            item = QTreeWidgetItem([c["operator_name"], f"{c['aqp_cost']:.2f}", f"{qep_cost:.2f}", f"{c['cost_ratio']}x"])
            if c["cost_ratio"] > 1.5:
                item.setForeground(3, red)
            elif c["cost_ratio"] < 1.0:
                item.setForeground(3, green)
            self.aqp_tree_widget.addTopLevelItem(item)

    # ==================================================================
    # Cleanup
    # ==================================================================
    def closeEvent(self, event):
        self.settings_panel.close_connection()
        event.accept()


# ==================================================================
# Entry Point
# ==================================================================
def launch_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.theme.apply_initial()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
