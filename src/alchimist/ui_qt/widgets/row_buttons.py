"""Кнопки в строке списка, которые рисуются, а не создаются.

Раньше у каждой строки «Могу сварить» был свой маленький виджет с раскладкой и двумя
`QPushButton` — на справочник кампании это сотни объектов Qt, и перерисовка списка
уходила в создание и раскладку кнопок. Делегат рисует те же кнопки прямо в ячейке и
сам ловит щелчки: виджетов ноль, а выглядят кнопки так же.

Чтобы глобальная таблица стилей оформила кнопку как кнопку, рисование идёт от имени
одной скрытой `QPushButton`-образца: правила `QPushButton` в стилях применяются по
классу виджета, а состояния (наведение, нажатие) берутся из флагов опции. При смене
темы образец пересоздаётся: при таблице стилей новый шрифт приложения достаётся только
свежим виджетам, как раньше доставался свежим кнопкам строк.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QRect, QSize, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QToolTip,
)

#: Расстояние между кнопками и запас справа — как было у прежней раскладки.
SPACING = 4
MARGIN = 10


class RowButtonsDelegate(QStyledItemDelegate):
    """Ряд кнопок в одной колонке. Кнопки есть только у строк, где `role` не пуст."""

    #: (индекс строки, номер кнопки) — по щелчку.
    clicked = Signal(QModelIndex, int)

    def __init__(
        self,
        view: QAbstractItemView,
        labels: list[str],
        tooltips: list[str] | None = None,
        *,
        role: int,
    ) -> None:
        super().__init__(view)
        self._view = view
        self._labels = list(labels)
        self._tooltips = list(tooltips or [""] * len(labels))
        self._role = role
        self._probe_widget: QPushButton | None = None
        self._sizes: list[QSize] | None = None
        self._hover: tuple[QPersistentModelIndex, int] | None = None
        self._pressed: tuple[QPersistentModelIndex, int] | None = None
        view.setMouseTracking(True)
        view.viewport().installEventFilter(self)

    # ── размеры ───────────────────────────────────────────────────────────
    def forget_sizes(self) -> None:
        """Шрифт или тема поменялись — кнопки надо мерить заново."""
        self._sizes = None
        if self._probe_widget is not None:
            self._probe_widget.deleteLater()
            self._probe_widget = None

    @property
    def _probe(self) -> QPushButton:
        """Скрытая кнопка-образец: по ней меряются и рисуются кнопки строк."""
        if self._probe_widget is None:
            self._probe_widget = QPushButton(self._view)
            self._probe_widget.hide()
        return self._probe_widget

    def _button_sizes(self) -> list[QSize]:
        if self._sizes is None:
            self._probe.ensurePolished()
            sizes = []
            for label in self._labels:
                self._probe.setText(label)
                sizes.append(self._probe.sizeHint())
            self._sizes = sizes
        return self._sizes

    def preferred_width(self) -> int:
        """Ширина колонки, при которой ни одна надпись не обрезается."""
        sizes = self._button_sizes()
        return sum(s.width() for s in sizes) + SPACING * (len(sizes) - 1) + MARGIN

    def _inner(self, cell: QRect) -> QRect:
        """Часть ячейки без отступов `::item` из темы.

        Ровно туда Qt ставил виджет с кнопками (`updateEditorGeometry`), так что
        кнопки ложатся на прежнее место и с прежними зазорами между строками.
        """
        option = QStyleOptionViewItem()
        option.initFrom(self._view)
        option.rect = cell
        option.showDecorationSelected = True
        return self._view.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, option, self._view
        )

    def button_rects(self, cell: QRect) -> list[QRect]:
        """Где в ячейке лежит каждая кнопка.

        Как в прежней раскладке: слева направо, по высоте — не больше своей и по
        центру, а лишнюю ширину, как `QBoxLayout`, сначала получает самая узкая.
        """
        inner = self._inner(cell)
        sizes = self._button_sizes()
        widths = [s.width() for s in sizes]
        spare = inner.width() - sum(widths) - SPACING * (len(widths) - 1)
        for _pixel in range(max(spare, 0)):
            widths[widths.index(min(widths))] += 1
        rects = []
        x = inner.left()
        for size, width in zip(sizes, widths, strict=True):
            height = min(size.height(), inner.height())
            top = inner.top() + (inner.height() - height) // 2
            rects.append(QRect(x, top, width, height))
            x += width + SPACING
        return rects

    def _has_buttons(self, index: QModelIndex) -> bool:
        return index.isValid() and index.siblingAtColumn(0).data(self._role) is not None

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        hint = super().sizeHint(option, index)
        if self._has_buttons(index):
            tallest = max(s.height() for s in self._button_sizes())
            hint = QSize(max(hint.width(), self.preferred_width()), max(hint.height(), tallest))
        return hint

    # ── рисование ─────────────────────────────────────────────────────────
    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().paint(painter, option, index)  # фон строки: чередование, выделение
        if not self._has_buttons(index):
            return
        style = self._probe.style()
        painter.save()
        painter.setFont(self._probe.font())  # надпись — тем шрифтом, по которому мерили
        for number, rect in enumerate(self.button_rects(option.rect)):
            button = QStyleOptionButton()
            button.initFrom(self._probe)
            button.rect = rect
            button.text = self._labels[number]
            button.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Raised
            key = (QPersistentModelIndex(index.siblingAtColumn(0)), number)
            if self._hover == key:
                button.state |= QStyle.StateFlag.State_MouseOver
            if self._pressed == key:
                button.state |= QStyle.StateFlag.State_Sunken
                button.state &= ~QStyle.StateFlag.State_Raised
            style.drawControl(QStyle.ControlElement.CE_PushButton, button, painter, self._probe)
        painter.restore()

    # ── мышь ──────────────────────────────────────────────────────────────
    def _hit(self, index: QModelIndex, pos) -> int | None:
        if not self._has_buttons(index):
            return None
        cell = self._view.visualRect(index)
        for number, rect in enumerate(self.button_rects(cell)):
            if rect.contains(pos):
                return number
        return None

    def _set_hover(self, key: tuple[QPersistentModelIndex, int] | None) -> None:
        if key != self._hover:
            self._hover = key
            self._view.viewport().update()

    def editorEvent(self, event, model, option, index: QModelIndex) -> bool:
        kind = event.type()
        if kind not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonDblClick,
        ):
            return super().editorEvent(event, model, option, index)
        number = self._hit(index, event.position().toPoint())
        key = (
            (QPersistentModelIndex(index.siblingAtColumn(0)), number)
            if number is not None
            else None
        )
        if kind == QEvent.Type.MouseMove:
            self._set_hover(key)
            return False
        if key is None:
            return super().editorEvent(event, model, option, index)
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            # Двойной щелчок по кнопке — это два нажатия кнопки, а не «сварить строку».
            self._pressed = key
            self._view.viewport().update()
            return True
        # Отпустили: срабатывает, только если отпустили над той же кнопкой.
        fired = self._pressed == key
        self._pressed = None
        self._view.viewport().update()
        if fired:
            self.clicked.emit(QModelIndex(index.siblingAtColumn(0)), number)
        return True

    def helpEvent(self, event, view, option, index: QModelIndex) -> bool:
        number = self._hit(index, event.pos())
        if number is not None and self._tooltips[number]:
            QToolTip.showText(event.globalPos(), self._tooltips[number], view)
            return True
        return super().helpEvent(event, view, option, index)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Мышь ушла из списка — подсветку и нажатие снять."""
        if event.type() == QEvent.Type.Leave:
            self._pressed = None
            self._set_hover(None)
        return False
