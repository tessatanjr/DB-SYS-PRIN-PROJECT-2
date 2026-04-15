from PySide6.QtWidgets import (
    QGraphicsRectItem, QGraphicsView, QGraphicsSimpleTextItem, QGraphicsItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPen, QBrush, QPainter

from annotation import classify_node
from modules.constants import NODE_COLORS

NODE_W = 200
NODE_H = 55
H_GAP = 30
V_GAP = 50


class QepNodeItem(QGraphicsRectItem):
    def __init__(self, plan_node, annotation_index=-1, callback=None, annotation=None):
        super().__init__(0, 0, NODE_W, NODE_H)
        self.plan_node = plan_node
        self.annotation_index = annotation_index
        self.annotation = annotation
        self._callback = callback

        node_type = plan_node.get("Node Type", "")
        category = classify_node(node_type)
        color = NODE_COLORS.get(category, NODE_COLORS["other"])

        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(80, 80, 80), 1.5))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setToolTip(self._build_tooltip())

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

        # Line 3: cost and rows
        cost = plan_node.get("Total Cost", 0)
        rows = plan_node.get("Plan Rows", 0)
        if rows >= 1_000_000:
            rows_str = f"{rows / 1_000_000:.1f}M"
        elif rows >= 1_000:
            rows_str = f"{rows / 1_000:.1f}K"
        else:
            rows_str = str(rows)
        cost_item = QGraphicsSimpleTextItem(f"Cost: {cost:.1f}  Rows: {rows_str}", self)
        cost_item.setFont(QFont("Segoe UI", 6))
        cost_item.setBrush(QBrush(QColor(100, 100, 100)))
        cost_item.setPos(4, 35)

    def _build_tooltip(self):
        """Build a rich-text tooltip showing plan node details + annotation."""
        plan = self.plan_node or {}
        node_type = plan.get("Node Type", "")
        cost = plan.get("Total Cost", 0)
        rows = plan.get("Plan Rows", 0)
        width = plan.get("Plan Width", 0)

        # --- Top section: plan node info ---
        top_lines = [f"<b style='font-size:12px;'>{node_type}</b>"]

        if plan.get("Relation Name"):
            rel = plan["Relation Name"]
            alias = plan.get("Alias")
            top_lines.append(
                f"<b>Relation:</b> {rel}" + (f" ({alias})" if alias and alias != rel else "")
            )
        for key, label in [
            ("Index Name",  "Index"),
            ("Hash Cond",   "Hash Cond"),
            ("Merge Cond",  "Merge Cond"),
            ("Join Filter", "Join Filter"),
            ("Filter",      "Filter"),
            ("Index Cond",  "Index Cond"),
        ]:
            if plan.get(key):
                top_lines.append(f"<b>{label}:</b> {plan[key]}")
        if plan.get("Sort Key"):
            top_lines.append(f"<b>Sort Key:</b> {', '.join(str(k) for k in plan['Sort Key'])}")
        if plan.get("Group Key"):
            top_lines.append(f"<b>Group Key:</b> {', '.join(str(k) for k in plan['Group Key'])}")

        top_lines.append(
            f"<span style='color:#888;'>Cost: {cost:.1f} &nbsp;·&nbsp; "
            f"Rows: {rows} &nbsp;·&nbsp; Width: {width}</span>"
        )
        top_html = "<br>".join(top_lines)

        # --- Bottom section: annotation ---
        ann = self.annotation
        bottom_html = ""
        if ann:
            ann_lines = ann.get("annotations") or []
            sql_text = (ann.get("sql_text") or "").strip()
            clause = ann.get("clause", "")
            if ann_lines:
                bottom_lines = [
                    f"<b style='color:#3ecf8e;'>Annotation ({clause})</b>"
                ]
                if sql_text:
                    snippet = sql_text if len(sql_text) <= 120 else sql_text[:117] + "..."
                    bottom_lines.append(
                        f"<span style='color:#aaa; font-style:italic;'>{snippet}</span>"
                    )
                for line in ann_lines:
                    bottom_lines.append(f"&bull;&nbsp; {line}")
                bottom_html = "<br>".join(bottom_lines)

        if bottom_html:
            divider = "<hr style='border:none; border-top:1px solid #444; margin:0;'>"
            return (
                f"<div style='max-width:420px; margin:0; padding:0;'>"
                f"{top_html}{divider}{bottom_html}"
                f"</div>"
            )
        return f"<div style='max-width:420px; margin:0; padding:0;'>{top_html}</div>"

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._callback and self.annotation_index >= 0:
            self._callback(self.annotation_index)


class QepGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)
