"""
Theme management for dark and light modes.

Centralises palette definitions, QSS stylesheet generation, and
theme-aware colour getters used by other GUI modules.

Aesthetic direction: refined technical (JetBrains Fleet / Linear
inspired). Layered graphite darks, warm paper lights, a single
electric-mint accent, and crisp 1px borders instead of shadows.
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette, QFontDatabase


# ---------------------------------------------------------------------------
# Palette tokens
# ---------------------------------------------------------------------------

DARK = {
    "bg":             "#0f1115",
    "bg_elev":        "#161a21",
    "bg_input":       "#1b2029",
    "bg_hover":       "#232a35",
    "bg_active":      "#2a3340",
    "border":         "#262c36",
    "border_strong":  "#333b48",
    "text":           "#d7dbe3",
    "text_dim":       "#8b93a3",
    "text_mute":      "#5c6474",
    "accent":         "#3ecf8e",
    "accent_hover":   "#4de29d",
    "accent_dim":     "#2a8c63",
    "accent_bg":      "#122922",
    "amber":          "#f5a524",
    "rose":           "#f87171",
    "cyan":           "#7dd3fc",
    "violet":         "#a78bfa",
}

LIGHT = {
    "bg":             "#fbfaf7",
    "bg_elev":        "#ffffff",
    "bg_input":       "#ffffff",
    "bg_hover":       "#f0eee8",
    "bg_active":      "#e8e5dd",
    "border":         "#e5e2d8",
    "border_strong":  "#cfcbbf",
    "text":           "#181a1f",
    "text_dim":       "#5a5e68",
    "text_mute":      "#8a8f99",
    "accent":         "#16a06a",
    "accent_hover":   "#128757",
    "accent_dim":     "#0f6b45",
    "accent_bg":      "#e4f3ea",
    "amber":          "#b26a00",
    "rose":           "#c03030",
    "cyan":           "#2970b2",
    "violet":         "#6b4ad1",
}


# ---------------------------------------------------------------------------
# Typography stacks
# ---------------------------------------------------------------------------

def _first_available(candidates):
    families = set(QFontDatabase.families())
    for c in candidates:
        if c in families:
            return c
    return candidates[-1]


def mono_family():
    return _first_available([
        "JetBrains Mono",
        "Cascadia Code", "Cascadia Mono",
        "SF Mono", "Menlo",
        "Consolas",
        "Monaco",
        "Courier New",
    ])


def ui_family():
    return _first_available([
        "Inter", "Inter Tight", "Inter Display",
        "SF Pro Text", "SF Pro Display",
        "Segoe UI Variable", "Segoe UI",
        "Helvetica Neue",
        "Arial",
    ])


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------

class ThemeManager:
    """Manages dark/light theme state and emits theme-aware values."""

    def __init__(self):
        self.is_dark = True

    @property
    def p(self):
        return DARK if self.is_dark else LIGHT

    def qcolor(self, token):
        return QColor(self.p[token])

    # -- public -------------------------------------------------------
    def toggle(self):
        self.is_dark = not self.is_dark
        self._apply()
        return self.is_dark

    def apply_initial(self):
        self._apply()

    # -- core ---------------------------------------------------------
    def _apply(self):
        app = QApplication.instance()
        p = self.p

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window,          QColor(p["bg"]))
        pal.setColor(QPalette.ColorRole.WindowText,      QColor(p["text"]))
        pal.setColor(QPalette.ColorRole.Base,            QColor(p["bg_input"]))
        pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(p["bg_elev"]))
        pal.setColor(QPalette.ColorRole.ToolTipBase,     QColor(p["bg_elev"]))
        pal.setColor(QPalette.ColorRole.ToolTipText,     QColor(p["text"]))
        pal.setColor(QPalette.ColorRole.Text,            QColor(p["text"]))
        pal.setColor(QPalette.ColorRole.Button,          QColor(p["bg_elev"]))
        pal.setColor(QPalette.ColorRole.ButtonText,      QColor(p["text"]))
        pal.setColor(QPalette.ColorRole.BrightText,      QColor(p["rose"]))
        pal.setColor(QPalette.ColorRole.Link,            QColor(p["accent"]))
        pal.setColor(QPalette.ColorRole.Highlight,       QColor(p["accent"]))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#0a0c10" if self.is_dark else "#ffffff"))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["text_mute"]))
        app.setPalette(pal)
        app.setStyleSheet(self._qss())

    # -- stylesheet ---------------------------------------------------
    def _qss(self):
        p = self.p
        mono = mono_family()
        ui = ui_family()
        sel_fg = "#0a0c10" if self.is_dark else "#ffffff"

        return f"""
        * {{ font-family: "{ui}", sans-serif; font-size: 13px; }}
        QWidget {{ color: {p["text"]}; background-color: {p["bg"]}; }}
        QMainWindow, QDialog {{ background-color: {p["bg"]}; }}
        QStatusBar {{
            background-color: {p["bg_elev"]};
            color: {p["text_dim"]};
            border-top: 1px solid {p["border"]};
            padding: 3px 10px; font-size: 12px;
        }}

        QGroupBox {{
            background-color: {p["bg_elev"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            margin-top: 10px;
            padding: 4px 6px 4px 6px;
            font-weight: 600;
            color: {p["text_dim"]};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px; padding: 0 5px;
            color: {p["text_dim"]};
            font-size: 10px; font-weight: 700;
            letter-spacing: 1.2px;
        }}

        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
            background-color: {p["bg_input"]};
            color: {p["text"]};
            border: 1px solid {p["border"]};
            border-radius: 5px;
            padding: 4px 8px;
            selection-background-color: {p["accent"]};
            selection-color: {sel_fg};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
            border: 1px solid {p["accent"]};
        }}
        QLineEdit:read-only {{
            background-color: {p["bg_elev"]};
            color: {p["text_dim"]};
        }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background-color: {p["bg_input"]};
            border: 1px solid {p["border_strong"]};
            selection-background-color: {p["accent_bg"]};
            selection-color: {p["accent"]};
            outline: none; padding: 4px;
        }}

        QPushButton {{
            background-color: {p["bg_elev"]};
            color: {p["text"]};
            border: 1px solid {p["border_strong"]};
            border-radius: 5px;
            padding: 4px 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {p["bg_hover"]};
            border-color: {p["accent_dim"]};
        }}
        QPushButton:pressed {{ background-color: {p["bg_active"]}; }}
        QPushButton:disabled {{
            color: {p["text_mute"]};
            background-color: {p["bg_elev"]};
            border-color: {p["border"]};
        }}
        QPushButton:flat {{
            background: transparent;
            border: none;
            color: {p["text_dim"]};
            padding: 4px 8px;
        }}
        QPushButton:flat:hover {{ color: {p["text"]}; background: transparent; }}
        QPushButton#primary {{
            background-color: {p["accent"]};
            color: {sel_fg};
            border: 1px solid {p["accent"]};
            font-weight: 600;
        }}
        QPushButton#primary:hover {{
            background-color: {p["accent_hover"]};
            border-color: {p["accent_hover"]};
        }}
        QPushButton#primary:pressed {{ background-color: {p["accent_dim"]}; }}

        QCheckBox {{ spacing: 8px; color: {p["text_dim"]}; }}
        QCheckBox::indicator {{
            width: 15px; height: 15px;
            border: 1px solid {p["border_strong"]};
            border-radius: 4px;
            background-color: {p["bg_input"]};
        }}
        QCheckBox::indicator:hover {{ border-color: {p["accent_dim"]}; }}
        QCheckBox::indicator:checked {{
            background-color: {p["accent"]};
            border-color: {p["accent"]};
        }}

        QTabWidget::pane {{
            border: 1px solid {p["border"]};
            border-radius: 8px;
            background-color: {p["bg_elev"]};
            top: -1px;
        }}
        QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
        QTabBar::tab {{
            background: transparent;
            color: {p["text_mute"]};
            padding: 8px 16px;
            border: none;
            border-bottom: 2px solid transparent;
            margin-right: 2px;
            font-size: 12px; font-weight: 500;
        }}
        QTabBar::tab:hover {{ color: {p["text"]}; }}
        QTabBar::tab:selected {{
            color: {p["accent"]};
            border-bottom: 2px solid {p["accent"]};
        }}

        QSplitter::handle {{ background-color: {p["border"]}; }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical {{ height: 1px; }}
        QSplitter::handle:hover {{ background-color: {p["accent_dim"]}; }}

        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
        QScrollBar::handle:vertical {{
            background: {p["border_strong"]};
            border-radius: 4px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {p["text_mute"]}; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
        QScrollBar::handle:horizontal {{
            background: {p["border_strong"]};
            border-radius: 4px; min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {p["text_mute"]}; }}
        QScrollBar::add-line, QScrollBar::sub-line,
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none; border: none; width: 0; height: 0;
        }}

        QTreeWidget, QTreeView {{
            background-color: {p["bg_elev"]};
            alternate-background-color: {p["bg_input"]};
            border: none; outline: none;
        }}
        QTreeWidget::item, QTreeView::item {{ padding: 4px 2px; border: none; }}
        QTreeWidget::item:selected, QTreeView::item:selected {{
            background-color: {p["accent_bg"]};
            color: {p["accent"]};
        }}
        QHeaderView::section {{
            background-color: {p["bg_elev"]};
            color: {p["text_dim"]};
            border: none;
            border-bottom: 1px solid {p["border"]};
            padding: 6px 8px;
            font-weight: 600; font-size: 11px;
            letter-spacing: 0.5px;
        }}

        QWidget#fieldContainer {{ background: transparent; }}
        QLabel {{ background: transparent; }}
        QLabel[fieldLabel="true"] {{
            color: {p["text_mute"]};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.6px;
            text-transform: uppercase;
            padding: 0; margin: 0;
        }}

        QLabel#statusPill {{
            background-color: {p["bg_elev"]};
            border: 1px solid {p["border"]};
            border-radius: 11px;
            padding: 3px 10px 3px 8px;
            font-size: 12px; font-weight: 600;
            color: {p["text_dim"]};
        }}
        QLabel#statusPill[state="ok"] {{
            border-color: {p["accent_dim"]};
            color: {p["accent"]};
            background-color: {p["accent_bg"]};
        }}
        QLabel#statusPill[state="warn"] {{
            border-color: {p["amber"]};
            color: {p["amber"]};
        }}
        QLabel#statusPill[state="err"] {{
            border-color: {p["rose"]};
            color: {p["rose"]};
        }}

        QPlainTextEdit#codeEditor, QTextEdit#codeEditor {{
            font-family: "{mono}", monospace;
            font-size: 13px;
            background-color: {p["bg_input"]};
            border: 1px solid {p["border"]};
            border-radius: 8px;
            padding: 10px 12px;
            selection-background-color: {p["accent"]};
            selection-color: {sel_fg};
        }}
        """

    # -- colour getters (preserved API) --------------------------------
    def sql_color(self):          return self.qcolor("text")
    def header_fg(self):          return self.qcolor("text_dim")
    def header_bg(self):          return self.qcolor("bg_elev")
    def algo_label_color(self):   return self.qcolor("text_dim")
    def algo_text_color(self):    return self.qcolor("cyan")
    def llm_label_color(self):    return self.qcolor("accent")
    def llm_text_color(self):     return self.qcolor("accent_hover") if self.is_dark else self.qcolor("accent")
    def scene_bg(self):           return self.qcolor("bg_elev")
    def chart_text_color(self):   return self.qcolor("text")
    def chat_you_color(self):     return self.qcolor("cyan")
    def chat_ai_color(self):      return self.qcolor("accent")
    def chat_body_color(self):    return self.qcolor("text")
    def aqp_red(self):            return self.qcolor("rose")
    def aqp_green(self):          return self.qcolor("accent")
    def button_text_color(self):  return self.p["text"]

    def readonly_field_bg(self):
        return f"background-color: {self.p['bg_elev']}; color: {self.p['text_dim']};"

    def preset_label_style(self):
        return (
            f"color: {self.p['text_dim']}; margin-top: 4px; "
            f"font-size: 11px; letter-spacing: 0.5px;"
        )

    def preset_button_style(self):
        sel_fg = "#0a0c10" if self.is_dark else "#ffffff"
        return (
            "QPushButton {"
            f"  background-color: {self.p['accent_bg']};"
            f"  border: 1px solid {self.p['accent_dim']};"
            "   border-radius: 12px;"
            "   padding: 4px 11px;"
            "   font-size: 11px;"
            f"  color: {self.p['accent']};"
            "   font-weight: 500;"
            "}"
            "QPushButton:hover {"
            f"  background-color: {self.p['accent']};"
            f"  color: {sel_fg};"
            "}"
        )
