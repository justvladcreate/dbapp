# ui/history_sidebar.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QStyle
)
from PySide6.QtCore import Qt, Signal
from ui.history_manager import HistoryManager


class HistorySidebar(QWidget):
    repeat_requested = Signal(object)
    show_requested = Signal(str, object)
    undo_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(650)
        self.setMaximumWidth(700)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Одна строка: комбобокс фильтра и кнопка очистки
        filter_layout = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Все", "Арендатор", "Собственник", "Объект", "Договор"])
        self.type_combo.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.type_combo)

        self.clear_history_btn = QPushButton("Очистить")
        self.clear_history_btn.setToolTip("Удалить всю историю действий")
        self.clear_history_btn.setFixedWidth(90)
        self.clear_history_btn.setObjectName("ClearHistoryButton")
        self.clear_history_btn.clicked.connect(self._clear_history)
        filter_layout.addWidget(self.clear_history_btn)
        layout.addLayout(filter_layout)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list_widget)

        self.history = HistoryManager()
        self.history.event_added.connect(self._on_event_added)
        self._events = []
        for ev in self.history.all_events():
            self._on_event_added(ev)

    def _clear_history(self):
        self.history.clear()
        self._events.clear()
        self.list_widget.clear()

    def _on_event_added(self, event):
        self._events.append(event)
        if self._passes_filter(event):
            self._add_item(event)

    def _passes_filter(self, event):
        filter_type = self.type_combo.currentText()
        if filter_type == "Все":
            return True
        mapping = {
            "Арендатор": "tenant",
            "Собственник": "landlord",
            "Объект": "estate",
            "Договор": "contract"
        }
        return event.get("type") == mapping.get(filter_type)

    def _add_item(self, event):
        item = QListWidgetItem()
        widget = QWidget()
        widget_layout = QHBoxLayout(widget)
        widget_layout.setContentsMargins(2, 2, 2, 2)

        # Время
        ts = event.get("timestamp")
        time_str = ts.toString("hh:mm:ss") if ts else ""
        time_label = QLabel(time_str)
        time_label.setStyleSheet("color: gray; font-size: 10px;")
        widget_layout.addWidget(time_label)

        # Текст
        text_label = QLabel(event["text"])
        text_label.setWordWrap(True)
        widget_layout.addWidget(text_label, 1)

        # Кнопка «Показать»
        if event.get("show_target"):
            entity_type, identifier = event["show_target"]
            show_btn = QPushButton()
            show_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
            show_btn.setFlat(True)
            show_btn.setToolTip("Показать запись")
            show_btn.clicked.connect(lambda checked=False, t=entity_type, i=identifier: self.show_requested.emit(t, i))
            widget_layout.addWidget(show_btn)
        elif event.get("show_callback"):
            show_btn = QPushButton()
            show_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
            show_btn.setFlat(True)
            show_btn.setToolTip("Показать запись")
            show_btn.clicked.connect(event["show_callback"])
            widget_layout.addWidget(show_btn)

        # Кнопка «Повторить»
        if event.get("repeat_data") is not None:
            repeat_btn = QPushButton()
            repeat_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
            repeat_btn.setFlat(True)
            repeat_btn.setToolTip("Повторить действие")
            data = event["repeat_data"]
            repeat_btn.clicked.connect(lambda checked=False, d=data: self.repeat_requested.emit(d))
            widget_layout.addWidget(repeat_btn)

        # Кнопка «Отменить» (стрелка назад)
        if event.get("undo_data") is not None:
            undo_btn = QPushButton()
            undo_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
            undo_btn.setFlat(True)
            undo_btn.setToolTip("Отменить это действие")
            ud = event["undo_data"]
            undo_btn.clicked.connect(lambda checked=False, d=ud: self.undo_requested.emit(d))
            widget_layout.addWidget(undo_btn)

        item.setSizeHint(widget.sizeHint())
        # Вставляем в начало списка, чтобы новые события были сверху
        self.list_widget.insertItem(0, item)
        self.list_widget.setItemWidget(item, widget)

    def _apply_filter(self):
        self.list_widget.clear()
        # Идём от новых к старым, чтобы сохранить порядок "сверху новые"
        for event in reversed(self._events):
            if self._passes_filter(event):
                self._add_item(event)