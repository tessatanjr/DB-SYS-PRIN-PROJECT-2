"""Chat panel widget — AI Q&A with preset questions."""

import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QApplication,
)
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor

from modules.llm import llm_chat


def _md_to_html(text):
    """Lightweight markdown-to-HTML for common LLM output patterns."""
    import html as _html
    lines = text.split("\n")
    out = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        # Headers
        m = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = len(m.group(1))
            sizes = {1: "16px", 2: "14px", 3: "13px", 4: "12px"}
            out.append(f'<p style="font-size:{sizes[level]}; font-weight:700; '
                       f'margin-top:8px; margin-bottom:4px;">'
                       f'{_inline_fmt(_html.escape(m.group(2)))}</p>')
            continue
        # Bullet / numbered list
        if re.match(r"^[-*]\s+|^\d+\.\s+", stripped):
            item = re.sub(r"^[-*]\s+|^\d+\.\s+", "", stripped)
            if not in_list:
                out.append("<ul style='margin-top:2px; margin-bottom:2px;'>")
                in_list = True
            out.append(f"<li>{_inline_fmt(_html.escape(item))}</li>")
            continue
        # Close list if we leave it
        if in_list and not stripped:
            out.append("</ul>")
            in_list = False
        # Empty line
        if not stripped:
            out.append("<br/>")
            continue
        # Normal paragraph
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f"<p style='margin:2px 0;'>{_inline_fmt(_html.escape(stripped))}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _inline_fmt(text):
    """Apply inline markdown: **bold**, *italic*, `code`."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<code style='background:rgba(128,128,128,0.15); "
                  r"padding:1px 4px; border-radius:3px;'>\1</code>", text)
    return text


CHAT_PRESETS = [
    "Why was this join strategy chosen over alternatives?",
    "How are the tables being accessed and why?",
    "What is the most expensive operation and how can it be optimized?",
    "Summarize the entire query execution plan in simple terms.",
]


class ChatPanel(QWidget):
    """Self-contained chat panel widget for the Ask AI tab."""

    def __init__(self, theme_manager, parent=None):
        super().__init__(parent)
        self.theme = theme_manager
        self._chat_history = []
        self._last_result = None
        self._status_callback = None  # set by MainWindow

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Segoe UI", 10))
        self.chat_display.setPlaceholderText(
            "Ask questions about the query plan here.\n"
            "Run an analysis first, then type your question below."
        )
        layout.addWidget(self.chat_display)

        # Preset question buttons
        self.preset_label = QLabel("Quick questions:")
        self.preset_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self.preset_label)

        preset_grid = QGridLayout()
        self.preset_buttons = []
        for i, preset in enumerate(CHAT_PRESETS):
            btn = QPushButton(preset[:45] + ("..." if len(preset) > 45 else ""))
            btn.setToolTip(preset)
            btn.clicked.connect(lambda checked, q=preset: self._send_preset(q))
            self.preset_buttons.append(btn)
            preset_grid.addWidget(btn, i // 2, i % 2)
        layout.addLayout(preset_grid)

        # Input row
        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setFont(QFont("Segoe UI", 10))
        self.chat_input.setPlaceholderText("Ask about the query plan...")
        self.chat_input.returnPressed.connect(self._send_chat)
        input_row.addWidget(self.chat_input)

        self.btn_send = QPushButton("Send")
        self.btn_send.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        self.btn_send.clicked.connect(self._send_chat)
        input_row.addWidget(self.btn_send)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet("padding: 6px 12px;")
        self.btn_clear.clicked.connect(self.clear_chat)
        input_row.addWidget(self.btn_clear)

        layout.addLayout(input_row)
        self.apply_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_result(self, result):
        """Set the analysis result for chat context. Clears history."""
        self._last_result = result
        self._chat_history = []
        self.chat_display.clear()

    def set_status_callback(self, callback):
        """Set a callback(str) for status bar messages."""
        self._status_callback = callback

    def clear_chat(self):
        self._chat_history = []
        self.chat_display.clear()

    def apply_theme(self):
        """Update all theme-dependent styles."""
        self.preset_label.setStyleSheet(self.theme.preset_label_style())
        style = self.theme.preset_button_style()
        for btn in self.preset_buttons:
            btn.setStyleSheet(style)
        self.rerender_history()

    def rerender_history(self):
        """Re-render all chat messages with current theme colours."""
        if not self._chat_history:
            return
        self.chat_display.clear()
        for msg in self._chat_history:
            if msg["role"] == "user":
                self._append("You", msg["content"], self.theme.chat_you_color())
            else:
                self._append("AI", msg["content"], self.theme.chat_ai_color())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _send_preset(self, question):
        self.chat_input.setText(question)
        self._send_chat()

    def _send_chat(self):
        user_msg = self.chat_input.text().strip()
        if not user_msg:
            return
        if not self._last_result:
            self._append("System",
                "Please run an analysis first so I have context about the query plan.",
                QColor(180, 0, 0))
            return

        self._append("You", user_msg, self.theme.chat_you_color())
        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self.btn_send.setEnabled(False)
        if self._status_callback:
            self._status_callback("Waiting for AI response...")
        QApplication.processEvents()

        r = self._last_result
        response = llm_chat(
            user_message=user_msg,
            sql_query=r["sql"],
            qep_text=r["qep"]["text"],
            operators=r["operators"],
            aqp_comparisons=r["aqp_comparisons"],
            chat_history=self._chat_history,
        )

        self._chat_history.append({"role": "user", "content": user_msg})
        self._chat_history.append({"role": "assistant", "content": response})

        self._append("AI", response, self.theme.chat_ai_color())

        self.chat_input.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.chat_input.setFocus()
        if self._status_callback:
            self._status_callback("Ready")

    def _append(self, sender, message, color):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        sender_fmt = QTextCharFormat()
        sender_fmt.setFont(QFont("Segoe UI", 10, QFont.Bold))
        sender_fmt.setForeground(color)
        cursor.insertText(f"\n{sender}:\n", sender_fmt)

        if sender == "AI":
            body_color = self.theme.chat_body_color().name()
            html = (f'<div style="color:{body_color}; font-family:Segoe UI; '
                    f'font-size:10pt;">{_md_to_html(message)}</div>')
            cursor.insertHtml(html)
            cursor.insertText("\n")
        else:
            body_fmt = QTextCharFormat()
            body_fmt.setFont(QFont("Segoe UI", 10))
            body_fmt.setForeground(self.theme.chat_body_color())
            cursor.insertText(f"{message}\n", body_fmt)

        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
