"""Syntax highlighting for code editors (Monokai theme)."""

from PyQt6.QtGui import (
    QTextCharFormat,
    QSyntaxHighlighter,
    QColor,
    QFont,
)
from PyQt6.QtCore import QRegularExpression


class PythonHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Python code."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Keyword format
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#F92672"))  # pink
        keyword_format.setFontWeight(QFont.Weight.Bold)

        # Class name format
        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#A6E22E"))  # green
        class_format.setFontWeight(QFont.Weight.Bold)

        # Function format
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#66D9EF"))  # cyan

        # String format
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#E6DB74"))  # yellow

        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#75715E"))  # gray
        comment_format.setFontItalic(True)

        # Number format
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#AE81FF"))  # purple

        # Decorator format
        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor("#F92672"))  # pink

        # Keywords
        keywords = [
            r"\bclass\b", r"\bdef\b", r"\bfor\b", r"\bwhile\b",
            r"\bif\b", r"\belif\b", r"\belse\b", r"\breturn\b",
            r"\bimport\b", r"\bfrom\b", r"\bas\b",
            r"\btry\b", r"\bexcept\b", r"\bfinally\b", r"\bwith\b",
            r"\bpass\b", r"\bbreak\b", r"\bcontinue\b", r"\braise\b",
            r"\bassert\b", r"\blambda\b", r"\byield\b",
            r"\bTrue\b", r"\bFalse\b", r"\bNone\b",
            r"\band\b", r"\bor\b", r"\bnot\b", r"\bin\b", r"\bis\b",
            r"\basync\b", r"\bawait\b", r"\bnonlocal\b", r"\bglobal\b", r"\bdel\b",
            r"\bmatch\b", r"\bcase\b",
            r"\bself\b",
        ]

        # Build regex patterns
        patterns = []

        # Class names
        patterns.append((QRegularExpression(r"\bclass\s+(\w+)"), 1, class_format))

        # Function definitions
        patterns.append((QRegularExpression(r"\bdef\s+(\w+)"), 1, function_format))

        # Function calls
        patterns.append((QRegularExpression(r"(\w+)(?=\()"), 0, function_format))

        # Keywords
        for keyword in keywords:
            patterns.append((QRegularExpression(keyword), 0, keyword_format))

        # Strings
        patterns.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), 0, string_format))
        patterns.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), 0, string_format))

        # Comments
        patterns.append((QRegularExpression(r"#.*"), 0, comment_format))

        # Numbers
        patterns.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), 0, number_format))

        # Decorators
        patterns.append((QRegularExpression(r"@\w+"), 0, decorator_format))

        # Method calls
        patterns.append((QRegularExpression(r"\.(\w+)(?=\()"), 0, function_format))

        self.rules = patterns

    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text."""
        for pattern, capture, fmt in self.rules:
            match = pattern.match(text)
            while match.hasMatch():
                start = match.capturedStart(capture)
                length = match.capturedLength(capture)
                self.setFormat(start, length, fmt)
                match = pattern.match(text, match.capturedEnd(capture))
