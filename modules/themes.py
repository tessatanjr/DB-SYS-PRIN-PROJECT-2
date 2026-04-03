"""
Theme management for light and dark modes.
Centralises all palette definitions and theme-aware colour lookups.
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette


class ThemeManager:
    """Manages dark/light theme state and provides theme-aware colours."""

    def __init__(self):
        self.is_dark = False

    def toggle(self):
        """Toggle between dark and light mode. Returns new is_dark state."""
        self.is_dark = not self.is_dark
        if self.is_dark:
            self._apply_dark()
        else:
            self._apply_light()
        return self.is_dark

    def apply_initial(self):
        """Apply the light theme on startup."""
        self._apply_light()

    # ------------------------------------------------------------------
    # Palette definitions
    # ------------------------------------------------------------------
    def _apply_dark(self):
        palette = QPalette()
        dark = QColor(30, 30, 30)
        mid = QColor(45, 45, 45)
        light_text = QColor(220, 220, 220)
        accent = QColor(70, 130, 180)

        palette.setColor(QPalette.ColorRole.Window, dark)
        palette.setColor(QPalette.ColorRole.WindowText, light_text)
        palette.setColor(QPalette.ColorRole.Base, QColor(40, 40, 40))
        palette.setColor(QPalette.ColorRole.AlternateBase, mid)
        palette.setColor(QPalette.ColorRole.ToolTipBase, mid)
        palette.setColor(QPalette.ColorRole.ToolTipText, light_text)
        palette.setColor(QPalette.ColorRole.Text, light_text)
        palette.setColor(QPalette.ColorRole.Button, mid)
        palette.setColor(QPalette.ColorRole.ButtonText, light_text)
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Link, accent)
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
        QApplication.instance().setPalette(palette)

    def _apply_light(self):
        palette = QPalette()
        white = QColor(255, 255, 255)
        off_white = QColor(247, 247, 247)
        black = QColor(0, 0, 0)
        accent = QColor(42, 130, 218)

        palette.setColor(QPalette.ColorRole.Window, off_white)
        palette.setColor(QPalette.ColorRole.WindowText, black)
        palette.setColor(QPalette.ColorRole.Base, white)
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.ToolTipBase, white)
        palette.setColor(QPalette.ColorRole.ToolTipText, black)
        palette.setColor(QPalette.ColorRole.Text, black)
        palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.ButtonText, black)
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, accent)
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, white)
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
        QApplication.instance().setPalette(palette)

    # ------------------------------------------------------------------
    # Theme-aware colour getters
    # ------------------------------------------------------------------
    def sql_color(self):
        return QColor(220, 220, 220) if self.is_dark else QColor(0, 0, 0)

    def header_fg(self):
        return QColor(170, 170, 170) if self.is_dark else QColor(100, 100, 100)

    def header_bg(self):
        return QColor(55, 55, 55) if self.is_dark else QColor(240, 240, 240)

    def algo_label_color(self):
        return QColor(180, 180, 180) if self.is_dark else QColor(60, 60, 60)

    def algo_text_color(self):
        return QColor(130, 170, 255) if self.is_dark else QColor(50, 50, 130)

    def llm_label_color(self):
        return QColor(100, 220, 160) if self.is_dark else QColor(0, 100, 60)

    def llm_text_color(self):
        return QColor(80, 200, 140) if self.is_dark else QColor(0, 100, 80)

    def scene_bg(self):
        return QColor(40, 40, 40) if self.is_dark else QColor(255, 255, 255)

    def chart_text_color(self):
        return QColor(200, 200, 200) if self.is_dark else QColor(0, 0, 0)

    def chat_you_color(self):
        return QColor(100, 180, 255) if self.is_dark else QColor(0, 80, 180)

    def chat_ai_color(self):
        return QColor(100, 220, 160) if self.is_dark else QColor(0, 70, 150)

    def chat_body_color(self):
        return QColor(210, 210, 210) if self.is_dark else QColor(30, 30, 30)

    def aqp_red(self):
        return QColor(255, 100, 100) if self.is_dark else QColor(200, 0, 0)

    def aqp_green(self):
        return QColor(100, 255, 100) if self.is_dark else QColor(0, 150, 0)

    def button_text_color(self):
        return "#ddd" if self.is_dark else "#333"

    def readonly_field_bg(self):
        return "background-color: #333;" if self.is_dark else "background-color: #f0f0f0;"

    def preset_label_style(self):
        color = "#aaa" if self.is_dark else "#666"
        return f"color: {color}; margin-top: 4px;"

    def preset_button_style(self):
        if self.is_dark:
            return (
                "QPushButton { background-color: #2a3a4a; border: 1px solid #4a6a8a; "
                "border-radius: 10px; padding: 4px 10px; font-size: 9px; color: #90CAF9; }"
                "QPushButton:hover { background-color: #3a4a5a; }"
            )
        return (
            "QPushButton { background-color: #E3F2FD; border: 1px solid #90CAF9; "
            "border-radius: 10px; padding: 4px 10px; font-size: 9px; color: #1565C0; }"
            "QPushButton:hover { background-color: #BBDEFB; }"
        )
