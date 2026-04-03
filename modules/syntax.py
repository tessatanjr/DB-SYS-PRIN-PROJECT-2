"""SQL syntax highlighter with dark/light mode support."""

import re
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter

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
    """Applies SQL syntax colouring to a QPlainTextEdit. Supports dark/light."""

    def __init__(self, document):
        super().__init__(document)
        self._is_dark = False
        self._kw_pattern = re.compile(
            r'\b(' + '|'.join(SQL_KEYWORDS) + r')\b', re.IGNORECASE
        )
        self._str_pattern = re.compile(r"'[^']*'")
        self._num_pattern = re.compile(r'\b\d+\.?\d*\b')
        self._cmt_pattern = re.compile(r'--.*$')
        self._build_formats()

    def set_dark(self, dark):
        self._is_dark = dark
        self._build_formats()
        self.rehighlight()

    def _build_formats(self):
        dark = self._is_dark
        self._rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(100, 160, 255) if dark else QColor(0, 0, 180))
        kw_fmt.setFontWeight(QFont.Bold)
        self._rules.append((self._kw_pattern, kw_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor(255, 140, 100) if dark else QColor(163, 21, 21))
        self._rules.append((self._str_pattern, str_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor(80, 220, 200) if dark else QColor(0, 128, 128))
        self._rules.append((self._num_pattern, num_fmt))

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor(120, 120, 120) if dark else QColor(128, 128, 128))
        cmt_fmt.setFontItalic(True)
        self._rules.append((self._cmt_pattern, cmt_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
