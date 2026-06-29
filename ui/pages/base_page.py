# ui/pages/base_page.py (обновлённый)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QHeaderView, QAbstractItemView, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem
import psycopg2
from database.error_handler import parse_db_error
from ui.widgets import MultiFilterProxy, FilterBar, export_proxy_to_csv
from ui.utils import format_currency


class SubTable:
    """
    Удобная обёртка для вложенных таблиц (QTableView + модель + прокси + фильтр-бар).
    При пустой таблице фильтр-бар скрыт.
    """
    def __init__(self, parent_widget, column_types: list):
        self.model = QStandardItemModel()
        self.proxy = MultiFilterProxy()
        self.proxy.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)

        self.filter_bar = FilterBar(self.table, self.proxy, parent_widget)
        self.filter_bar.rebuild(column_types)
        self.filter_bar.setVisible(False)   # изначально скрыт, пока нет заголовков

    def set_headers(self, headers):
        self.model.setHorizontalHeaderLabels(headers)
        self.table.resizeColumnsToContents()
        self.filter_bar.setVisible(True)    # показываем фильтр-бар, когда есть заголовки

    def clear(self):
        self.model.clear()
        self.filter_bar.setVisible(False)   # скрываем фильтр-бар при очистке

    def add_row(self, items: list, id_data=None, extra_data=None):
        if not items:
            return
        if id_data is not None:
            items[0].setData(id_data, Qt.UserRole)
        if extra_data is not None:
            items[0].setData(extra_data, Qt.UserRole + 1)

        for item in items:
            if not item.toolTip():
                item.setToolTip("Двойной клик для просмотра")
        self.model.appendRow(items)

    def get_selected_ids(self):
        selection = self.table.selectionModel()
        if not selection.hasSelection():
            return []
        ids = []
        for proxy_idx in selection.selectedRows():
            src_idx = self.proxy.mapToSource(proxy_idx)
            item = self.model.item(src_idx.row(), 0)
            if item:
                id_data = item.data(Qt.UserRole)
                if id_data is not None:
                    ids.append(id_data)
        return ids

    def get_selected_extra_data(self):
        selection = self.table.selectionModel()
        if not selection.hasSelection():
            return []
        data = []
        for proxy_idx in selection.selectedRows():
            src_idx = self.proxy.mapToSource(proxy_idx)
            item = self.model.item(src_idx.row(), 0)
            if item:
                extra = item.data(Qt.UserRole + 1)
                if extra is not None:
                    data.append(extra)
        return data

    def finalize(self):
        """Вызвать после загрузки всех данных для подгонки ширины столбцов."""
        self.table.resizeColumnsToContents()
        BasePage._apply_min_column_widths(self.table, self.model)
        if self.filter_bar.isVisible():
            self.filter_bar.sync_geometry()

    def connect_context_menu(self, callback):
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(callback)

    def connect_double_click(self, callback):
        self.table.doubleClicked.connect(callback)


class BasePage(QWidget):
    """
    Базовый класс для страниц с таблицей, фильтрами и экспортом CSV.
    Автоматически настраивает QTableView + MultiFilterProxy + FilterBar.
    Достаточно переопределить метод load_data() и указать типы колонок.
    """

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.model = QStandardItemModel()
        self.proxy = MultiFilterProxy()
        self.proxy.setSourceModel(self.model)

        # Главный layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Панель с кнопками
        self._btn_layout = QHBoxLayout()
        self._btn_layout.setContentsMargins(5, 2, 5, 2)
        self._main_layout.addLayout(self._btn_layout)

        # Фильтр-бар (будет добавлен позже)
        self.filter_bar = None

        # Таблица
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)

    def setup_table_with_filterbar(self, column_types: list):
        self.filter_bar = FilterBar(self.table, self.proxy, self)
        self._main_layout.addWidget(self.filter_bar)
        self._main_layout.addWidget(self.table)
        self.filter_bar.rebuild(column_types)
        self.filter_bar.sync_geometry()

    def add_button(self, text, callback=None, tooltip=None, alignment='left'):
        btn = QPushButton(text)
        if tooltip:
            btn.setToolTip(tooltip)
        if callback:
            btn.clicked.connect(callback)
        if alignment == 'right':
            self._btn_layout.addStretch()
            self._btn_layout.addWidget(btn)
        else:
            self._btn_layout.addWidget(btn)
        return btn

    def add_export_button(self):
        self.add_button("Экспорт CSV", callback=lambda: export_proxy_to_csv(self.proxy, self),
                        tooltip="Экспортировать видимые данные в CSV", alignment='right')

    def add_clear_filters_button(self):
        self.add_button("Очистить фильтры", callback=self.reset_filters,
                        tooltip="Сбросить все фильтры таблицы")

    def reset_filters(self):
        if self.filter_bar:
            self.filter_bar.reset()

    @staticmethod
    def _apply_min_column_widths(table, model, padding=30):
        """Гарантирует, что ширина столбцов не меньше ширины заголовков + padding."""
        header = table.horizontalHeader()
        font_metrics = table.fontMetrics()
        for i in range(header.count()):
            text = model.headerData(i, Qt.Horizontal)
            if text:
                text_width = font_metrics.horizontalAdvance(text) + padding
                if header.sectionSize(i) < text_width:
                    header.resizeSection(i, text_width)

    def load_query_into_model(self, query: str, params=None, headers: list = None,
                              data_extractor=None, id_extractor=None,
                              extra_data_extractor=None,
                              id_column=0, format_money_columns=None):
        """
        Выполняет SQL-запрос и заполняет модель данными.
        :param query: SQL-запрос.
        :param params: параметры для запроса.
        :param headers: список заголовков колонок. Если None, берутся из результата (начиная с колонки после id).
        :param data_extractor: функция(row) -> list of values для отображения. По умолчанию row[id_column+1:].
        :param id_extractor: функция(row) -> dict/значение, сохраняется в UserRole первого элемента.
        :param extra_data_extractor: функция(row) -> значение, сохраняется в UserRole+1 первого элемента.
        :param id_column: индекс колонки с базовым ID (используется, если id_extractor не задан).
        :param format_money_columns: set индексов колонок, где надо применить format_currency.
        """
        try:
            rows, cols = self.db.fetch_all(query, params)
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки данных", parse_db_error(e))
            return

        self.model.clear()

        if headers is None:
            headers = cols[id_column+1:] if len(cols) > id_column else []

        self.model.setHorizontalHeaderLabels(headers)

        for row_data in rows:
            if data_extractor:
                values = data_extractor(row_data)
            else:
                values = row_data[id_column+1:]

            items = []
            for i, val in enumerate(values):
                if format_money_columns and i in format_money_columns:
                    item = QStandardItem(format_currency(val))
                else:
                    item = QStandardItem(str(val))
                item.setToolTip("Двойной клик для редактирования")
                items.append(item)

            # Сохраняем ID
            if items:
                if id_extractor:
                    items[0].setData(id_extractor(row_data), Qt.UserRole)
                else:
                    items[0].setData(row_data[id_column], Qt.UserRole)

                if extra_data_extractor:
                    items[0].setData(extra_data_extractor(row_data), Qt.UserRole + 1)

            self.model.appendRow(items)

        self.table.resizeColumnsToContents()

    def get_selected_ids(self):
        """Возвращает список ID выделенных строк (из UserRole первого столбца)."""
        selection = self.table.selectionModel()
        if not selection.hasSelection():
            return []
        ids = []
        for proxy_idx in selection.selectedRows():
            src_idx = self.proxy.mapToSource(proxy_idx)
            item = self.model.item(src_idx.row(), 0)
            if item:
                id_data = item.data(Qt.UserRole)
                if id_data is not None:
                    ids.append(id_data)
        return ids