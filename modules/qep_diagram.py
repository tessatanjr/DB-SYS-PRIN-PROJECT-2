from PySide6.QtWidgets import (
    QGraphicsRectItem, QGraphicsView, QGraphicsSimpleTextItem, QGraphicsItem,
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QTextEdit,
    QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPen, QBrush, QPainter, QCursor

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
        # Close previous popup (stored on the scene to avoid per-node issues)
        scene = self.scene()
        if scene and hasattr(scene, '_active_popup') and scene._active_popup:
            try:
                scene._active_popup.hide()
                scene._active_popup.deleteLater()
            except RuntimeError:
                pass
            scene._active_popup = None
        popup = _NodePopup(self._build_tooltip())
        popup.adjustSize()
        cursor_pos = QCursor.pos()
        # Smart positioning: keep popup within screen bounds
        screen = QApplication.screenAt(cursor_pos)
        if screen:
            screen_rect = screen.availableGeometry()
            x = cursor_pos.x() + 10
            y = cursor_pos.y() + 10
            if x + popup.width() > screen_rect.right():
                x = cursor_pos.x() - popup.width() - 10
            if y + popup.height() > screen_rect.bottom():
                y = cursor_pos.y() - popup.height() - 10
            x = max(x, screen_rect.left())
            y = max(y, screen_rect.top())
            popup.move(x, y)
        else:
            popup.move(cursor_pos.x() + 10, cursor_pos.y() + 10)
        popup.show()
        if scene:
            scene._active_popup = popup


class _NodePopup(QWidget):
    """Persistent tooltip popup with a close button."""

    def __init__(self, html_content):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._drag_pos = None

        # Theme-aware colors from the app palette
        pal = QApplication.instance().palette()
        bg = pal.window().color().name()
        fg = pal.windowText().color().name()
        border = pal.mid().color().name()
        dim = pal.placeholderText().color().name()

        # Slightly lighter/darker bar color for the drag handle
        base = pal.window().color()
        handle_rgb = base.lighter(115).name() if base.lightness() < 128 else base.darker(110).name()

        self.setStyleSheet(
            f"QWidget#nodePopup {{ background-color: {bg}; border: 1px solid {border}; "
            f"border-radius: 6px; }}"
        )
        self.setObjectName("nodePopup")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Drag handle bar with close button
        handle = QWidget()
        handle.setFixedHeight(24)
        handle.setStyleSheet(
            f"background-color: {handle_rgb}; border: none; "
            f"border-top-left-radius: 6px; border-top-right-radius: 6px;"
        )
        handle.setCursor(Qt.CursorShape.SizeAllCursor)
        handle_layout = QHBoxLayout(handle)
        handle_layout.setContentsMargins(8, 0, 4, 0)
        handle_layout.setSpacing(0)

        grip_label = QLabel("\u2261")
        grip_label.setStyleSheet(f"color: {dim}; font-size: 14px; background: transparent; border: none;")
        handle_layout.addWidget(grip_label)
        handle_layout.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(22, 22)
        close_btn.setFlat(True)
        close_btn.setStyleSheet(
            f"QPushButton {{ color: {dim}; font-size: 16px; border: none; background: transparent; }}"
            f"QPushButton:hover {{ color: {fg}; }}"
        )
        close_btn.clicked.connect(self.close)
        handle_layout.addWidget(close_btn)
        layout.addWidget(handle)

        # Content
        content = QTextEdit()
        content.setReadOnly(True)
        content.setHtml(html_content)
        content.setStyleSheet(
            f"QTextEdit {{ background: transparent; border: none; color: {fg}; "
            f"font-size: 12px; }}"
        )
        content.setMinimumWidth(350)
        content.setMaximumWidth(450)
        content.setMaximumHeight(350)
        doc = content.document()
        doc.setTextWidth(420)
        content.setFixedHeight(min(int(doc.size().height()) + 10, 350))
        layout.addWidget(content)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class QepGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def mousePressEvent(self, event):
        # Middle-click or Ctrl+click to pan
        if (event.button() == Qt.MouseButton.MiddleButton or
                event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)
