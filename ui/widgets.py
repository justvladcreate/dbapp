# ui/widgets.py (полностью, с исправлением в DateFilterWidget)

import csv
from datetime import date, timedelta
from PySide6.QtCore import QSortFilterProxyModel, Qt, QDate, Signal, QTimer, QPoint
from PySide6.QtWidgets import (
    QFileDialog, QWidget, QHBoxLayout, QLineEdit,
    QPushButton, QDateEdit, QLabel, QMenu, QTableView,
    QVBoxLayout, QFrame, QSizePolicy, QStyle,
    QWidgetAction, QGridLayout
)
from PySide6.QtGui import QIcon


class MultiFilterProxy(QSortFilterProxyModel):
    # (без изменений)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filters = {}
        self._date_filters = {}
        self._global_text = ""
        self._numeric_filters = {}

    def set_filter(self, column: int, text: str):
        if text:
            self._filters[column] = text.lower()
        else:
            self._filters.pop(column, None)
        self.invalidateFilter()

    def set_date_filter(self, column: int, from_date: QDate, to_date: QDate):
        if from_date.isValid() and to_date.isValid():
            self._date_filters[column] = (from_date, to_date)
        else:
            self._date_filters.pop(column, None)
        self.invalidateFilter()

    def set_global_filter(self, text: str):
        self._global_text = text.lower()
        self.invalidateFilter()

    def set_numeric_filter(self, column: int, operator: str, value: float):
        if operator and value is not None:
            self._numeric_filters[column] = (operator, value)
        else:
            self._numeric_filters.pop(column, None)
        self.invalidateFilter()

    def reset_filters(self):
        self._filters.clear()
        self._date_filters.clear()
        self._global_text = ""
        self._numeric_filters.clear()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        for col, text in self._filters.items():
            if col < 0 or col >= model.columnCount():
                continue
            idx = model.index(source_row, col)
            data = idx.data()
            if data is None:
                data = ""
            if text not in str(data).lower():
                return False

        for col, (op, val) in self._numeric_filters.items():
            if col < 0 or col >= model.columnCount():
                continue
            idx = model.index(source_row, col)
            data = idx.data()
            if data is None:
                return False
            try:
                clean = str(data).replace(" ", "").replace("₽", "").replace(",", ".")
                num = float(clean)
            except (ValueError, TypeError):
                return False
            if op == "=" and num != val:
                return False
            elif op == ">" and num <= val:
                return False
            elif op == "<" and num >= val:
                return False
            elif op == ">=" and num < val:
                return False
            elif op == "<=" and num > val:
                return False

        for col, (from_d, to_d) in self._date_filters.items():
            if col < 0 or col >= model.columnCount():
                continue
            idx = model.index(source_row, col)
            data = idx.data()
            if data is None:
                return False
            date_val = QDate.fromString(str(data), "yyyy-MM-dd")
            if not date_val.isValid():
                return False
            if not (from_d <= date_val <= to_d):
                return False

        if self._global_text:
            found = False
            for col in range(model.columnCount()):
                idx = model.index(source_row, col)
                data = idx.data()
                if data is None:
                    data = ""
                if self._global_text in str(data).lower():
                    found = True
                    break
            if not found:
                return False

        return True

    def lessThan(self, left, right):
        left_str = left.data(Qt.DisplayRole)
        right_str = right.data(Qt.DisplayRole)

        def clean(s):
            if s is None:
                return ""
            return str(s).replace(" ", "").replace("₽", "").replace(",", ".")

        try:
            left_num = float(clean(left_str))
            right_num = float(clean(right_str))
            return left_num < right_num
        except (ValueError, TypeError):
            pass

        return str(left_str) < str(right_str)


class FilterLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Фильтр...")
        self.setObjectName("FilterLineEdit")


class NumericFilterWidget(QWidget):
    filter_changed = Signal(int, str, float)
    OPERATORS = ["=", ">", "<", ">=", "<="]

    def __init__(self, column, parent=None):
        super().__init__(parent)
        self.column = column
        self._op_index = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet("NumericFilterWidget { border: none; background: transparent; }")
        self.op_btn = QPushButton(self.OPERATORS[self._op_index])
        self.op_btn.setFixedSize(28, 28)
        self.op_btn.setToolTip("Нажмите для смены оператора\n(=, >, <, >=, <=)")
        self.op_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #777;
                border-radius: 2px;
                background: #ffffff;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #f0f0f0;
            }
            """)
        self.op_btn.clicked.connect(self._toggle_operator)
        layout.addWidget(self.op_btn)
        self.edit = FilterLineEdit()
        self.edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.edit)

    def _toggle_operator(self):
        self._op_index = (self._op_index + 1) % len(self.OPERATORS)
        self.op_btn.setText(self.OPERATORS[self._op_index])
        self._on_text_changed()

    def _on_text_changed(self):
        text = self.edit.text().strip()
        if text:
            try:
                value = float(text)
            except ValueError:
                return
        else:
            self.filter_changed.emit(self.column, "", 0.0)
            return
        op = self.OPERATORS[self._op_index]
        self.filter_changed.emit(self.column, op, value)


class DateFilterMenu(QWidget):
    """Современное меню фильтра дат: поля ввода слева, пресеты справа."""

    date_range_selected = Signal(QDate, QDate)
    reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._from_date = QDate(2000, 1, 1)
        self._to_date = QDate.currentDate()
        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ===== Левая часть: выбор дат =====
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)

        # Строка "С"
        from_row = QHBoxLayout()
        from_label = QLabel("С:")
        from_label.setFixedWidth(20)
        self.from_edit = QDateEdit()
        self.from_edit.setCalendarPopup(True)
        self.from_edit.setDisplayFormat("yyyy-MM-dd")
        self.from_edit.setDate(self._from_date)
        self.from_edit.setStyleSheet("QDateEdit { padding: 4px; border: 1px solid #c0c0c0; border-radius: 4px; }")
        from_row.addWidget(from_label)
        from_row.addWidget(self.from_edit)
        left_layout.addLayout(from_row)

        # Строка "По"
        to_row = QHBoxLayout()
        to_label = QLabel("По:")
        to_label.setFixedWidth(20)
        self.to_edit = QDateEdit()
        self.to_edit.setCalendarPopup(True)
        self.to_edit.setDisplayFormat("yyyy-MM-dd")
        self.to_edit.setDate(self._to_date)
        self.to_edit.setStyleSheet("QDateEdit { padding: 4px; border: 1px solid #c0c0c0; border-radius: 4px; }")
        to_row.addWidget(to_label)
        to_row.addWidget(self.to_edit)
        left_layout.addLayout(to_row)


        # Кнопка очистки
        clear_btn = QPushButton("Очистить фильтр")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: #f0f0f0;
            }
        """)
        clear_btn.clicked.connect(self.reset_requested.emit)
        left_layout.addWidget(clear_btn)

        left_layout.addStretch()
        main_layout.addLayout(left_layout)

        # Вертикальный разделитель
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # ===== Правая часть: пресеты =====
        presets_layout = QVBoxLayout()
        presets_layout.setSpacing(6)

        today = QDate.currentDate()
        yesterday = today.addDays(-1)
        this_week_start = today.addDays(-(today.dayOfWeek() - 1))
        this_month_start = QDate(today.year(), today.month(), 1)
        last_month_end = this_month_start.addDays(-1)
        last_month_start = QDate(last_month_end.year(), last_month_end.month(), 1)
        last_30 = today.addDays(-30)
        this_quarter_start = QDate(today.year(), ((today.month() - 1) // 3) * 3 + 1, 1)
        last_quarter_end = this_quarter_start.addDays(-1)
        last_quarter_start = QDate(last_quarter_end.year(), ((last_quarter_end.month() - 1) // 3) * 3 + 1, 1)

        periods = [
            ("Сегодня", today, today),
            ("Вчера", yesterday, yesterday),
            ("Эта неделя", this_week_start, this_week_start.addDays(6)),
            ("Прошлая неделя", this_week_start.addDays(-7), this_week_start.addDays(-1)),
            ("Этот месяц", this_month_start, QDate(today.year(), today.month(), today.daysInMonth())),
            ("Прошлый месяц", last_month_start, last_month_end),
            ("Последние 30 дней", last_30, today),
            ("Этот квартал", this_quarter_start, QDate(today.year(), this_quarter_start.month() + 2, 1).addMonths(1).addDays(-1)),
            ("Прошлый квартал", last_quarter_start, last_quarter_end),
            ("Этот год", QDate(today.year(), 1, 1), QDate(today.year(), 12, 31)),
        ]

        for name, start, end in periods:
            btn = QPushButton(name)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 6px 12px;
                    border: none;
                    background: transparent;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #e8f0fe;
                }
            """)
            btn.clicked.connect(lambda checked, s=start, e=end: self.set_dates(s, e))
            presets_layout.addWidget(btn)

        presets_layout.addStretch()
        main_layout.addLayout(presets_layout)

    def set_dates(self, from_d, to_d):
        self.from_edit.setDate(from_d)
        self.to_edit.setDate(to_d)
        self.date_range_selected.emit(from_d, to_d)


class DateFilterWidget(QWidget):
    """Фильтр даты в стиле Excel: кнопка + всплывающее меню."""

    date_range_changed = Signal(QDate, QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_from = QDate()
        self._current_to = QDate()
        self._menu = None
        self._menu_widget = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.filter_btn = QPushButton("Фильтр по дате...")
        self.filter_btn.setToolTip("Нажмите для выбора даты или периода")
        self.filter_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 4px 6px;
                text-align: left;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        self.filter_btn.clicked.connect(self._show_menu)
        layout.addWidget(self.filter_btn)

    def _show_menu(self):
        if self._menu is None:
            self._menu = QMenu(self)
            self._menu.setStyleSheet("""
                QMenu {
                    background-color: #ffffff;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    padding: 0px;
                }
            """)
            self._menu_widget = DateFilterMenu()
            action = QWidgetAction(self._menu)
            action.setDefaultWidget(self._menu_widget)
            self._menu.addAction(action)
            self._menu_widget.date_range_selected.connect(self._on_dates_selected)
            self._menu_widget.reset_requested.connect(self._on_reset)

        # Позиционируем меню под кнопкой, чтобы не перекрывать другие фильтры
        self._menu.popup(self.filter_btn.mapToGlobal(QPoint(0, self.filter_btn.height())))

    def _on_dates_selected(self, from_d, to_d):
        self._current_from = from_d
        self._current_to = to_d
        if from_d == to_d:
            self.filter_btn.setText(from_d.toString("yyyy-MM-dd"))
        else:
            self.filter_btn.setText(f"{from_d.toString('yyyy-MM-dd')} – {to_d.toString('yyyy-MM-dd')}")
        # Меню уже закрыто? обычно popup закрывается после выбора, но на всякий случай
        if self._menu is not None:
            self._menu.close()
        self.date_range_changed.emit(from_d, to_d)

    def _on_reset(self):
        self._current_from = QDate()
        self._current_to = QDate()
        self.filter_btn.setText("Фильтр по дате...")
        # Исправление: закрываем меню только если оно существует
        if self._menu is not None:
            self._menu.close()
        self.date_range_changed.emit(QDate(), QDate())

    # Метод для внешнего сброса (например, кнопка «Очистить фильтры» на панели)
    def reset(self):
        self._on_reset()


def export_proxy_to_csv(proxy_model, parent=None):
    if proxy_model.rowCount() == 0:
        return
    path, _ = QFileDialog.getSaveFileName(parent, "Сохранить CSV", "", "CSV Files (*.csv)")
    if not path:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=';')
        headers = [proxy_model.headerData(i, Qt.Horizontal) for i in range(proxy_model.columnCount())]
        writer.writerow(headers)
        for row in range(proxy_model.rowCount()):
            row_data = []
            for col in range(proxy_model.columnCount()):
                idx = proxy_model.index(row, col)
                row_data.append(idx.data() if idx.data() else "")
            writer.writerow(row_data)


class FilterBar(QWidget):
    """Панель фильтров, синхронизированная с колонками QTableView."""
    def __init__(self, table_view: QTableView, proxy_model: MultiFilterProxy, parent=None):
        super().__init__(parent)
        self.table = table_view
        self.proxy = proxy_model
        self._filter_widgets = []
        self.setFixedHeight(30)
        self.setObjectName("FilterBar")
        header = self.table.horizontalHeader()
        header.sectionResized.connect(self._sync_geometry)
        header.sectionMoved.connect(self._sync_geometry)
        header.geometriesChanged.connect(self._sync_geometry)
        self.table.horizontalScrollBar().valueChanged.connect(self._sync_geometry)
        self.table.verticalScrollBar().valueChanged.connect(self._sync_geometry)

    def rebuild(self, column_types: list):
        for w in self._filter_widgets:
            w.setParent(None)
            w.deleteLater()
        self._filter_widgets.clear()
        for col, col_type in enumerate(column_types):
            if col_type == 'date':
                w = DateFilterWidget(self)
                w.date_range_changed.connect(lambda from_d, to_d, c=col: self.proxy.set_date_filter(c, from_d, to_d))
            elif col_type == 'numeric':
                w = NumericFilterWidget(col, self)
                w.filter_changed.connect(lambda col, op, val: self.proxy.set_numeric_filter(col, op, val))
            else:
                w = FilterLineEdit(self)
                w.textChanged.connect(lambda text, c=col: self.proxy.set_filter(c, text))
            w.show()
            self._filter_widgets.append(w)
        self._sync_geometry()

    def reset(self):
        self.proxy.reset_filters()
        for w in self._filter_widgets:
            if isinstance(w, DateFilterWidget):
                w.reset()
            elif isinstance(w, NumericFilterWidget):
                w.edit.clear()
            elif isinstance(w, QLineEdit):
                w.clear()
        self._sync_geometry()

    def sync_geometry(self):
        """Публичный метод для принудительной синхронизации положения фильтров."""
        self._sync_geometry()

    def _sync_geometry(self):
        if not self._filter_widgets:
            return
        header = self.table.horizontalHeader()
        scroll = self.table.horizontalScrollBar().value()
        vw = self.table.verticalHeader().width() if self.table.verticalHeader().isVisible() else 0
        for col in range(min(len(self._filter_widgets), header.count())):
            x = header.sectionViewportPosition(col) - scroll + vw
            w = header.sectionSize(col)
            self._filter_widgets[col].setGeometry(x, 0, w, self.height())


class NotificationPanel(QFrame):
    """Панель уведомлений (до 5 записей) с иконками «Показать» и «Повторить»."""
    def __init__(self, max_items=5, parent=None):
        super().__init__(parent)
        self.max_items = max_items
        self.show_callback = None
        self.repeat_callback = None
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setVisible(False)
        self.setStyleSheet("""
            QFrame {
                background-color: #e8f0fe;
                border: none;
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(2)

        header_layout = QHBoxLayout()
        self.title_label = QLabel("Недавние действия:")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.close_btn = QPushButton()
        self.close_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        self.close_btn.setFlat(True)
        self.close_btn.setToolTip("Скрыть уведомления")
        self.close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.close_btn)
        layout.addLayout(header_layout)

        self.entries_layout = QVBoxLayout()
        layout.addLayout(self.entries_layout)

    def add_notification(self, text, show_callback=None, repeat_data=None):
        entry_widget = QWidget()
        entry_layout = QHBoxLayout(entry_widget)
        entry_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(text)
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        entry_layout.addWidget(lbl)

        if show_callback:
            show_btn = QPushButton()
            show_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
            show_btn.setFlat(True)
            show_btn.setToolTip("Показать запись")
            show_btn.clicked.connect(show_callback)
            entry_layout.addWidget(show_btn)
        elif self.show_callback:
            show_btn = QPushButton()
            show_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
            show_btn.setFlat(True)
            show_btn.setToolTip("Показать запись")
            show_btn.clicked.connect(lambda: self.show_callback())
            entry_layout.addWidget(show_btn)

        if repeat_data is not None and self.repeat_callback:
            repeat_btn = QPushButton()
            repeat_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
            repeat_btn.setFlat(True)
            repeat_btn.setToolTip("Повторить действие с теми же данными")
            repeat_btn.clicked.connect(lambda: self.repeat_callback(repeat_data))
            entry_layout.addWidget(repeat_btn)

        while self.entries_layout.count() >= self.max_items:
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.entries_layout.addWidget(entry_widget)
        self.setVisible(True)



def format_currency(value) -> str:
    """Форматирует число как денежную сумму: 1234567 -> '1 234 567 ₽'."""
    try:
        num = int(float(value))
        return f"{num:,} ₽".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)