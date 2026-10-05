"""Мелкие общие элементы интерфейса."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from alchimist.core.errors import Message, Severity
from alchimist.core.models import coerce_enum
from alchimist.i18n import _, describe
from alchimist.ui_qt.theme import error_color, muted_color, on_theme_changed, warning_color


class SearchBox(QLineEdit):
    """Поле поиска с задержкой: список не дёргается на каждую букву (NFR-9: Ctrl+F)."""

    search = Signal(str)

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder or _("Поиск…"))
        self.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(lambda: self.search.emit(self.text().strip()))
        self.textChanged.connect(lambda _t: self._timer.start())

    def focus_shortcut(self, parent: QWidget) -> QShortcut:
        shortcut = QShortcut(QKeySequence.StandardKey.Find, parent)
        shortcut.activated.connect(self._focus)
        return shortcut

    def _focus(self) -> None:
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.selectAll()


class MessageStrip(QFrame):
    """Полоска с предупреждениями. Текст берётся из кодов через i18n."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        # Без этого перенесённый на несколько строк текст обрезается до одной строки.
        self._label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        layout.addWidget(self._label)
        self._messages: list[Message] = []
        self._text = ""
        self._extra = ""
        on_theme_changed(self._retheme)
        self.hide()

    def show_messages(self, messages: list[Message], extra: str = "") -> None:
        """`extra` — готовая HTML-строка, которая дописывается под сообщениями."""
        self._messages = list(messages)
        self._text = ""
        self._extra = extra
        if not messages:
            self.show_text(extra) if extra else self.clear()
            return
        lines = []
        for message in messages:
            color = {
                Severity.ERROR: error_color(),
                Severity.WARNING: warning_color(),
                Severity.INFO: muted_color(),
            }[message.severity].name()
            mark = {Severity.ERROR: "✕", Severity.WARNING: "▲", Severity.INFO: "•"}[
                message.severity
            ]
            lines.append(f'<span style="color:{color}">{mark} {describe(message)}</span>')
        if extra:
            # Приписка идёт приглушённой, как обычный текст полоски: свои цвета
            # внутри `extra` от этого не теряются — вложенный span перекрывает.
            lines.append(f'<span style="color:{muted_color().name()}">{extra}</span>')
        self._label.setText("<br>".join(lines))
        self.show()
        self._sync_height()

    def show_text(self, text: str, color: str | None = None) -> None:
        self._messages = []
        self._extra = ""
        self._text = text
        self._label.setText(f'<span style="color:{color or muted_color().name()}">{text}</span>')
        self.setVisible(bool(text))
        self._sync_height()

    def _retheme(self) -> None:
        """Цвета зашиты в готовый HTML, поэтому после смены темы его надо пересобрать."""
        if self._messages:
            self.show_messages(self._messages, self._extra)
        elif self._text:
            self.show_text(self._text)

    def clear(self) -> None:
        self._messages = []
        self._extra = ""
        self._text = ""
        self._label.clear()
        self.hide()

    def _sync_height(self) -> None:
        """Перенесённый на несколько строк текст иначе обрезается до одной строки.

        `QLabel` с переносом сообщает высоту для одной строки, пока не знает своей
        ширины, поэтому минимальная высота пересчитывается по фактической ширине.
        """
        width = self._label.width()
        if width <= 0:
            return
        wanted = self._label.heightForWidth(width)
        if wanted > 0 and wanted != self._label.minimumHeight():
            self._label.setMinimumHeight(wanted)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_height()


class FilterBar(QWidget):
    """Строка фильтров: набор выпадающих списков и флажков."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._widgets: dict[str, QWidget] = {}
        self._enums: dict[str, type] = {}

    def add_combo(
        self,
        key: str,
        label: str,
        options: list[tuple[str, object]],
        *,
        enum_type: type | None = None,
    ) -> QComboBox:
        """`enum_type` возвращает значение обратно самим enum'ом.

        Qt хранит данные пункта как QVariant и разворачивает `StrEnum` в обычную
        строку, а `IntEnum` — нет. Без приведения сравнения фильтров ведут себя
        по-разному в зависимости от вида перечисления.
        """
        combo = QComboBox()
        for text, value in options:
            combo.addItem(text, value)
        combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
        self._layout.addWidget(QLabel(label))
        self._layout.addWidget(combo)
        self._widgets[key] = combo
        if enum_type is not None:
            self._enums[key] = enum_type
        return combo

    def add_check(self, key: str, label: str) -> QCheckBox:
        check = QCheckBox(label)
        check.stateChanged.connect(lambda _s: self.changed.emit())
        self._layout.addWidget(check)
        self._widgets[key] = check
        return check

    def add_stretch(self) -> None:
        self._layout.addStretch(1)

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def value(self, key: str):
        widget = self._widgets[key]
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            enum_type = self._enums.get(key)
            if enum_type is not None:
                return coerce_enum(enum_type, data, data)
            return data
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return None


def format_difficulty(difficulty, *, full: bool = True) -> str:
    """«Сл 14 = 10 + 2 + 2 + 0» — разбор по слагаемым правила П-8."""
    if not full:
        return _("Сл {total}").format(total=difficulty.total)
    return _("Сл {total}  =  {parts}").format(
        total=difficulty.total, parts=" + ".join(str(v) for _n, v in difficulty.parts())
    )


def difficulty_tooltip(difficulty) -> str:
    """Подробное объяснение каждого слагаемого."""
    from alchimist.core.models import RARITY_NAMES_RU

    lines = [
        _("Основа расчёта: {value}").format(value=difficulty.base),
        _("Редкость ({name}): +{value}").format(
            name=RARITY_NAMES_RU[difficulty.rarity].lower(), value=difficulty.rarity_penalty
        ),
        _("Порций {count}: +{value}").format(
            count=difficulty.portions, value=difficulty.portion_penalty
        ),
        _("Лишних эссенций {count}: +{value}").format(
            count=difficulty.excess_units, value=difficulty.excess_penalty
        ),
        _("Итого: {total}").format(total=difficulty.total),
    ]
    return "\n".join(lines)


def title_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    return label


def title_rule(width: int = 44) -> QFrame:
    """Короткая латунная черта под заголовком — единственное украшение страницы."""
    rule = QFrame()
    rule.setObjectName("titleRule")
    rule.setFixedSize(QSize(width, 2))
    return rule


def page_heading(text: str) -> QWidget:
    """Заголовок страницы вместе с латунной чертой под ним."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(title_label(text))
    layout.addWidget(title_rule())
    layout.addStretch(1)
    return holder


def hint_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label
