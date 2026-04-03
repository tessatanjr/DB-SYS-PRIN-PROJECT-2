"""Visual QEP diagram widgets — node boxes and zoomable view."""

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
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

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

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._callback and self.annotation_index >= 0:
            self._callback(self.annotation_index)


class QepGraphicsView(QGraphicsView):
    """QGraphicsView with Ctrl+Scroll zoom and drag panning."""

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
