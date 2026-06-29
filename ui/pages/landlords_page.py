# ui/pages/landlords_page.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QHeaderView, QMenu,
    QAbstractItemView, QMessageBox, QSplitter,
    QGroupBox, QFormLayout, QLabel, QDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
import psycopg2

from database.connection import Database
from database.queries import (
    GET_LANDLORD_OBJECTS, GET_LANDLORD_CONTRACTS,
    INSERT_LANDLORD, UPDATE_LANDLORD, INSERT_REAL_ESTATE,
    INSERT_CONTRACT, INSERT_REPORT_ITEM
)
from database.error_handler import parse_db_error
from ui.dialogs import LandlordDialog, RealEstateDialog, ContractDialog
from ui.widgets import export_proxy_to_csv
from ui.utils import format_currency
from ui.history_manager import HistoryManager
from ui.pages.base_page import BasePage, SubTable


class LandlordsPage(BasePage):
    view_estate_requested = Signal(int)
    edit_estate_requested = Signal(int)
    view_contract_requested = Signal(int)
    edit_contract_requested = Signal(int)

    MAIN_COLUMN_TYPES = ['text', 'text', 'numeric', 'numeric']
    OBJECTS_SINGLE_COLUMN_TYPES = ['text', 'numeric', 'numeric']
    OBJECTS_MULTI_COLUMN_TYPES = ['text', 'text', 'numeric', 'numeric']
    CONTRACTS_SINGLE_COLUMN_TYPES = ['date', 'text', 'numeric']
    CONTRACTS_MULTI_COLUMN_TYPES = ['text', 'date', 'text', 'numeric']

    def __init__(self, db: Database, refresh_callback=None, parent=None):
        super().__init__(db, parent)
        self.refresh_callback = refresh_callback
        self.current_landlord_ids = []
        self.history = HistoryManager()

        # Настройка главной таблицы через BasePage
        self.add_button("Добавить", self.add_landlord, "Добавить нового собственника (Insert)")
        self.copy_btn = self.add_button("Копировать", self.copy_landlord, "Создать копию выбранного собственника (Ctrl+C)")
        self.copy_btn.setEnabled(False)
        self.del_btn = self.add_button("Удалить", self.delete_landlords, "Удалить выбранных собственников (Del)")
        self.add_clear_filters_button()
        self.add_export_button()

        self.setup_table_with_filterbar(self.MAIN_COLUMN_TYPES)
        self.table.doubleClicked.connect(self._on_main_double_clicked)
        self.table.selectionModel().selectionChanged.connect(self._on_landlord_selection_changed)

        # Нижняя панель: сплиттер
        self.vert_splitter = QSplitter(Qt.Vertical)
        self.vert_splitter.addWidget(self.table)

        # Виджет для вложенных таблиц
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.horiz_splitter = QSplitter(Qt.Horizontal)

        # Статистика
        self.stats_group = QGroupBox("Статистика")
        stats_layout = QFormLayout()
        self.lbl_objects_count = QLabel("—")
        self.lbl_contracts_count = QLabel("—")
        self.lbl_income = QLabel("—")
        self.lbl_avg_price = QLabel("—")
        self.lbl_total_area = QLabel("—")
        stats_layout.addRow("Объектов в собственности:", self.lbl_objects_count)
        stats_layout.addRow("Договоров:", self.lbl_contracts_count)
        stats_layout.addRow("Общий доход:", self.lbl_income)
        stats_layout.addRow("Средняя цена аренды:", self.lbl_avg_price)
        stats_layout.addRow("Общая площадь объектов:", self.lbl_total_area)
        self.stats_group.setLayout(stats_layout)
        self.stats_group.setMinimumWidth(250)
        self.horiz_splitter.addWidget(self.stats_group)

        # Правая часть: объекты и договоры
        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)

        # Подтаблица объектов
        self._objects_subtable = SubTable(self, self.OBJECTS_SINGLE_COLUMN_TYPES)
        self._objects_subtable.table.doubleClicked.connect(self._on_objects_double_clicked)
        self._objects_subtable.connect_context_menu(self._on_objects_context_menu)

        # Кнопки управления объектами
        self._add_object_btn = QPushButton("Добавить")
        self._add_object_btn.setToolTip("Добавить новый объект недвижимости выбранному собственнику")
        self._add_object_btn.clicked.connect(lambda: self.add_object())
        self._add_object_btn.setEnabled(False)

        self._delete_objects_btn = QPushButton("Удалить")
        self._delete_objects_btn.setToolTip("Удалить выделенные объекты недвижимости")
        self._delete_objects_btn.clicked.connect(self.delete_objects)
        self._delete_objects_btn.setEnabled(False)

        objects_group = self._build_subgroup("Объекты в собственности",
                                             self._objects_subtable,
                                             self._add_object_btn,
                                             self._delete_objects_btn,
                                             self._objects_subtable.filter_bar.reset)
        right_layout.addWidget(objects_group)

        # Подтаблица договоров
        self._contracts_subtable = SubTable(self, self.CONTRACTS_SINGLE_COLUMN_TYPES)
        self._contracts_subtable.table.doubleClicked.connect(self._on_contracts_double_clicked)
        self._contracts_subtable.connect_context_menu(self._on_contracts_context_menu)

        # Кнопки управления договорами
        self._add_contract_btn = QPushButton("Создать договор")
        self._add_contract_btn.setToolTip("Создать новый договор аренды для выбранного собственника")
        self._add_contract_btn.clicked.connect(lambda: self.add_contract())
        self._add_contract_btn.setEnabled(False)

        self._delete_contracts_btn = QPushButton("Удалить")
        self._delete_contracts_btn.setToolTip("Удалить выделенные договоры")
        self._delete_contracts_btn.clicked.connect(self.delete_contracts_from_landlord)
        self._delete_contracts_btn.setEnabled(False)

        contracts_group = self._build_subgroup("Участие в договорах",
                                               self._contracts_subtable,
                                               self._add_contract_btn,
                                               self._delete_contracts_btn,
                                               self._contracts_subtable.filter_bar.reset)
        right_layout.addWidget(contracts_group)

        self.horiz_splitter.addWidget(right_widget)
        bottom_layout.addWidget(self.horiz_splitter)
        bottom_widget.setLayout(bottom_layout)

        self.vert_splitter.addWidget(bottom_widget)
        self._main_layout.addWidget(self.vert_splitter)

        # Размеры сплиттеров
        self.vert_splitter.setCollapsible(0, False)
        self.vert_splitter.setCollapsible(1, False)
        self.vert_splitter.setSizes([350, 300])
        self.horiz_splitter.setCollapsible(0, False)
        self.horiz_splitter.setCollapsible(1, False)
        self.horiz_splitter.setSizes([200, 650])
        self.table.setMinimumHeight(150)
        bottom_widget.setMinimumHeight(150)

        self.load_data()

    @staticmethod
    def _build_subgroup(title, subtable, add_btn, del_btn, clear_filters_callback):
        """Создаёт QGroupBox с кнопками и SubTable внутри."""
        group = QGroupBox(title)
        layout = QVBoxLayout()
        header = QHBoxLayout()
        header.addWidget(add_btn)
        header.addWidget(del_btn)
        header.addStretch()
        clear_filters_btn = QPushButton("Очистить фильтры")
        clear_filters_btn.setToolTip("Сбросить фильтры таблицы")
        clear_filters_btn.clicked.connect(clear_filters_callback)
        header.addWidget(clear_filters_btn)
        layout.addLayout(header)
        layout.addWidget(subtable.filter_bar)
        layout.addWidget(subtable.table)
        group.setLayout(layout)
        return group

    # ----------------------------------------------------------------
    #  ДАННЫЕ ГЛАВНОЙ ТАБЛИЦЫ
    # ----------------------------------------------------------------
    def load_data(self):
        query = """
            SELECT l.id, l.name, l.contact_info,
                   COUNT(DISTINCT re.id) AS objects_cnt,
                   COUNT(DISTINCT c.id) AS contracts_cnt
            FROM landlord_info l
            LEFT JOIN real_estate_info re ON re.landlord_id = l.id
            LEFT JOIN report r ON r.real_estate_id = re.id
            LEFT JOIN contract c ON r.contract_id = c.id
            GROUP BY l.id, l.name, l.contact_info
            ORDER BY l.name
        """
        self.load_query_into_model(query, headers=["Имя", "Контакты", "Кол-во объектов", "Кол-во договоров"])

    def get_selected_landlord_ids(self):
        return self.get_selected_ids()

    def _on_landlord_selection_changed(self):
        ids = self.get_selected_landlord_ids()
        self.current_landlord_ids = ids
        single = len(ids) == 1
        self.copy_btn.setEnabled(single)

        # Управляем кнопками в субтаблицах
        self._add_object_btn.setEnabled(single)
        self._delete_objects_btn.setEnabled(single)
        self._add_contract_btn.setEnabled(single)
        self._delete_contracts_btn.setEnabled(single)

        if not ids:
            self.clear_landlord_info()
            return

        if single:
            self._load_landlord_details(ids[0])
        else:
            self._load_landlords_summary(ids)

    def _require_single_landlord(self, action_desc):
        if len(self.current_landlord_ids) != 1:
            QMessageBox.information(self, "Информация", f"Сначала выберите одного собственника ({action_desc}).")
            return None
        return self.current_landlord_ids[0]

    # ----------------------------------------------------------------
    #  ЗАГРУЗКА ИНФОРМАЦИИ О СОБСТВЕННИКЕ(АХ)
    # ----------------------------------------------------------------
    def _load_landlord_details(self, landlord_id):
        self._load_stats([landlord_id])
        self._load_objects_for_ids([landlord_id])
        self._load_contracts_for_ids([landlord_id])

    def _load_landlords_summary(self, landlord_ids):
        self._load_stats(landlord_ids)
        self._load_objects_for_ids(landlord_ids, multi=True)
        self._load_contracts_for_ids(landlord_ids, multi=True)

    def _load_stats(self, landlord_ids):
        placeholders = ','.join(['%s'] * len(landlord_ids))
        query = f"""
            SELECT
                COUNT(DISTINCT re.id) AS objects_count,
                COUNT(DISTINCT c.id) AS contracts_count,
                COALESCE(SUM(r.price_per_month * r.months), 0) AS total_income,
                COALESCE(AVG(r.price_per_month), 0) AS avg_price,
                COALESCE(SUM(re.overall_space), 0) AS total_area
            FROM landlord_info l
            LEFT JOIN real_estate_info re ON re.landlord_id = l.id
            LEFT JOIN report r ON r.real_estate_id = re.id
            LEFT JOIN contract c ON r.contract_id = c.id
            WHERE l.id IN ({placeholders})
        """
        try:
            stats = self.db.fetch_one(query, landlord_ids)
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки статистики", parse_db_error(e))
            return

        if stats:
            self.lbl_objects_count.setText(str(stats["objects_count"]))
            self.lbl_contracts_count.setText(str(stats["contracts_count"]))
            self.lbl_income.setText(format_currency(stats["total_income"]))
            self.lbl_avg_price.setText(format_currency(stats["avg_price"]))
            self.lbl_total_area.setText(f"{stats['total_area']} м²")
        else:
            for lbl in (self.lbl_objects_count, self.lbl_contracts_count,
                        self.lbl_income, self.lbl_avg_price, self.lbl_total_area):
                lbl.setText("—")

    def _load_objects_for_ids(self, landlord_ids, multi=False):
        placeholders = ','.join(['%s'] * len(landlord_ids))
        if not multi:
            query = GET_LANDLORD_OBJECTS
            headers = ["Адрес", "Общая площадь", "Комнат"]
            column_types = self.OBJECTS_SINGLE_COLUMN_TYPES
            params = (landlord_ids[0],)
            extra_lid = landlord_ids[0]
        else:
            query = f"""
                SELECT re.id, re.address, re.overall_space, re.rooms_amount, 
                       l.name AS landlord_name, l.id AS landlord_id
                FROM real_estate_info re
                JOIN landlord_info l ON re.landlord_id = l.id
                WHERE l.id IN ({placeholders})
                ORDER BY l.name, re.address
            """
            headers = ["Собственник", "Адрес", "Общая площадь", "Комнат"]
            column_types = self.OBJECTS_MULTI_COLUMN_TYPES
            params = landlord_ids
            extra_lid = None

        try:
            rows, _ = self.db.fetch_all(query, params)
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки объектов", parse_db_error(e))
            return

        self._objects_subtable.clear()
        self._objects_subtable.set_headers(headers)
        for row_data in rows:
            if not multi:
                items = [QStandardItem(str(val)) for val in row_data[1:]]
                estate_id = row_data[0]
                self._objects_subtable.add_row(items, id_data=estate_id, extra_data=extra_lid)
            else:
                items = [
                    QStandardItem(str(row_data[4])),
                    QStandardItem(str(row_data[1])),
                    QStandardItem(str(row_data[2])),
                    QStandardItem(str(row_data[3]))
                ]
                estate_id = row_data[0]
                landlord_id_val = row_data[5]
                self._objects_subtable.add_row(items, id_data=estate_id, extra_data=landlord_id_val)

        self._objects_subtable.filter_bar.rebuild(column_types)
        self._objects_subtable.finalize()

    def _load_contracts_for_ids(self, landlord_ids, multi=False):
        placeholders = ','.join(['%s'] * len(landlord_ids))
        if not multi:
            query = GET_LANDLORD_CONTRACTS
            headers = ["Дата", "Арендатор", "Сумма"]
            column_types = self.CONTRACTS_SINGLE_COLUMN_TYPES
            params = (landlord_ids[0],)
            extra_lid = landlord_ids[0]
        else:
            query = f"""
                SELECT c.id, c.date, t.name AS tenant_name,
                       SUM(r.price_per_month * r.months) AS total_sum,
                       l.name AS landlord_name, l.id AS landlord_id
                FROM contract c
                JOIN tenant t ON c.tenant_passport = t.passport
                JOIN report r ON c.id = r.contract_id
                JOIN real_estate_info re ON r.real_estate_id = re.id
                JOIN landlord_info l ON re.landlord_id = l.id
                WHERE l.id IN ({placeholders})
                GROUP BY c.id, c.date, t.name, l.name, l.id
                ORDER BY c.date DESC
            """
            headers = ["Собственник", "Дата", "Арендатор", "Сумма"]
            column_types = self.CONTRACTS_MULTI_COLUMN_TYPES
            params = landlord_ids
            extra_lid = None

        try:
            rows, _ = self.db.fetch_all(query, params)
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки договоров", parse_db_error(e))
            return

        self._contracts_subtable.clear()
        self._contracts_subtable.set_headers(headers)
        for row_data in rows:
            if not multi:
                items = [
                    QStandardItem(str(row_data[1])),
                    QStandardItem(str(row_data[2])),
                    QStandardItem(format_currency(row_data[3]))
                ]
                contract_id = row_data[0]
                self._contracts_subtable.add_row(items, id_data=contract_id, extra_data=extra_lid)
            else:
                items = [
                    QStandardItem(str(row_data[4])),
                    QStandardItem(str(row_data[1])),
                    QStandardItem(str(row_data[2])),
                    QStandardItem(format_currency(row_data[3]))
                ]
                contract_id = row_data[0]
                landlord_id_val = row_data[5]
                self._contracts_subtable.add_row(items, id_data=contract_id, extra_data=landlord_id_val)

        self._contracts_subtable.filter_bar.rebuild(column_types)
        self._contracts_subtable.finalize()

    def clear_landlord_info(self):
        for lbl in (self.lbl_objects_count, self.lbl_contracts_count, self.lbl_income,
                    self.lbl_avg_price, self.lbl_total_area):
            lbl.setText("—")
        self._objects_subtable.clear()
        self._contracts_subtable.clear()

    # ----------------------------------------------------------------
    #  НАВИГАЦИЯ И КОНТЕКСТНЫЕ МЕНЮ
    # ----------------------------------------------------------------
    def _on_main_double_clicked(self, index):
        ids = self.current_landlord_ids
        if len(ids) == 1:
            self.edit_landlord_by_id(ids[0])
        else:
            QMessageBox.information(self, "Информация", "Редактирование возможно только при выборе одного собственника.")

    def _on_objects_double_clicked(self, index):
        item = self._objects_subtable.model.item(self._objects_subtable.proxy.mapToSource(index).row(), 0)
        if not item:
            return
        if len(self.current_landlord_ids) == 1:
            estate_id = item.data(Qt.UserRole)
            if estate_id:
                self.view_estate_requested.emit(estate_id)
        else:
            landlord_id = item.data(Qt.UserRole + 1)
            if landlord_id:
                self.select_landlord_by_id(landlord_id)

    def _on_objects_context_menu(self, pos):
        if len(self.current_landlord_ids) != 1:
            return
        index = self._objects_subtable.table.indexAt(pos)
        if not index.isValid():
            return
        proxy_idx = self._objects_subtable.proxy.mapToSource(index)
        item = self._objects_subtable.model.item(proxy_idx.row(), 0)
        if not item:
            return
        estate_id = item.data(Qt.UserRole)
        if not estate_id:
            return
        menu = QMenu(self)
        menu.addAction("Просмотреть", lambda: self.view_estate_requested.emit(estate_id))
        menu.addAction("Редактировать", lambda: self.edit_estate_requested.emit(estate_id))
        menu.exec(self._objects_subtable.table.viewport().mapToGlobal(pos))

    def _on_contracts_double_clicked(self, index):
        item = self._contracts_subtable.model.item(self._contracts_subtable.proxy.mapToSource(index).row(), 0)
        if not item:
            return
        if len(self.current_landlord_ids) == 1:
            contract_id = item.data(Qt.UserRole)
            if contract_id:
                self.view_contract_requested.emit(contract_id)
        else:
            landlord_id = item.data(Qt.UserRole + 1)
            if landlord_id:
                self.select_landlord_by_id(landlord_id)

    def _on_contracts_context_menu(self, pos):
        if len(self.current_landlord_ids) != 1:
            return
        index = self._contracts_subtable.table.indexAt(pos)
        if not index.isValid():
            return
        proxy_idx = self._contracts_subtable.proxy.mapToSource(index)
        item = self._contracts_subtable.model.item(proxy_idx.row(), 0)
        if not item:
            return
        contract_id = item.data(Qt.UserRole)
        if not contract_id:
            return
        menu = QMenu(self)
        menu.addAction("Просмотреть", lambda: self.view_contract_requested.emit(contract_id))
        menu.addAction("Редактировать", lambda: self.edit_contract_requested.emit(contract_id))
        menu.exec(self._contracts_subtable.table.viewport().mapToGlobal(pos))

    # ----------------------------------------------------------------
    #  CRUD СОБСТВЕННИКОВ
    # ----------------------------------------------------------------
    def add_landlord(self, initial_data=None):
        dlg = LandlordDialog(self.db, initial_data=initial_data, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="landlord",
            text=f"Собственник добавлен: {data['name']}",
            show_target=('landlord', data['id']),
            repeat_data=('landlord', data),
            undo_data={"action": "add_landlord", "landlord_id": data['id']}
        )
        self.refresh()
        self.reset_filters()
        self.select_landlord_by_id(data['id'])
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_landlord_by_id(data['id'])

    def edit_landlord(self):
        lid = self._require_single_landlord("для редактирования")
        if lid is None:
            return
        row = self.db.fetch_one("SELECT * FROM landlord_info WHERE id = %s", (lid,))
        if not row:
            return
        old_data = {"id": row["id"], "name": row["name"], "contact_info": row["contact_info"]}
        dlg = LandlordDialog(self.db, landlord=row, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="landlord",
            text=f"Собственник изменён: {data['name']}",
            show_target=('landlord', lid),
            undo_data={"action": "edit_landlord", "old": old_data}
        )

        self.refresh()
        self.reset_filters()
        self.select_landlord_by_id(lid)
        if self.refresh_callback:
            self.refresh_callback()
            self.select_landlord_by_id(lid)
            self.reset_filters()



    def edit_landlord_by_id(self, landlord_id):
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item.data(Qt.UserRole) == landlord_id:
                src_idx = self.model.index(row, 0)
                proxy_idx = self.proxy.mapFromSource(src_idx)
                self.table.selectRow(proxy_idx.row())
                self.current_landlord_ids = [landlord_id]
                self.edit_landlord()
                return

    def select_landlord_by_id(self, landlord_id):
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item.data(Qt.UserRole) == landlord_id:
                src_idx = self.model.index(row, 0)
                proxy_idx = self.proxy.mapFromSource(src_idx)
                self.table.clearSelection()
                self.table.selectRow(proxy_idx.row())
                self.table.scrollTo(proxy_idx)
                self.current_landlord_ids = [landlord_id]
                return
        QMessageBox.information(self, "Информация", "Собственник не найден в текущей таблице.")

    def copy_landlord(self):
        lid = self._require_single_landlord("для копирования")
        if lid is None:
            return
        try:
            landlord = self.db.fetch_one("SELECT name, contact_info FROM landlord_info WHERE id = %s", (lid,))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        if landlord:
            self.add_landlord(initial_data={"name": landlord["name"], "contact_info": landlord["contact_info"]})

    # ----------------------------------------------------------------
    #  УДАЛЕНИЕ
    # ----------------------------------------------------------------
    def delete_landlords(self):
        ids = self.get_selected_landlord_ids()
        if not ids:
            QMessageBox.information(self, "Внимание", "Выделите хотя бы одного собственника для удаления.")
            return
        self._delete_entities("landlord", ids)

    def delete_objects(self):
        lid = self._require_single_landlord("для удаления объектов")
        if lid is None:
            return
        ids = self._objects_subtable.get_selected_ids()
        if not ids:
            QMessageBox.information(self, "Внимание", "Выделите объекты для удаления.")
            return
        self._delete_entities("estate", ids)

    def delete_contracts_from_landlord(self):
        lid = self._require_single_landlord("для удаления договоров")
        if lid is None:
            return
        ids = self._contracts_subtable.get_selected_ids()
        if not ids:
            QMessageBox.information(self, "Внимание", "Выделите договоры для удаления.")
            return
        self._delete_entities("contract", ids)

    def _delete_entities(self, entity_type, entity_ids):
        """
        Универсальный метод удаления с прогресс-баром, undo-данными и историей.
        entity_type: 'landlord', 'estate', 'contract'
        """
        main_win = self.window()
        cnt = len(entity_ids)
        single = cnt == 1

        # Собираем информацию для подтверждения и undo (если один элемент)
        undo_info = None
        stats = None
        try:
            if entity_type == 'landlord':
                if single:
                    landlord = self.db.fetch_one("SELECT * FROM landlord_info WHERE id = %s", (entity_ids[0],))
                    if not landlord:
                        return
                    # Получаем связанные объекты и договоры без null-элементов
                    data = self.db.fetch_one("""
                        SELECT 
                            COALESCE(json_agg(DISTINCT re.*) FILTER (WHERE re.id IS NOT NULL), '[]') AS estates,
                            COALESCE(json_agg(DISTINCT c.*) FILTER (WHERE c.id IS NOT NULL), '[]') AS contracts
                        FROM landlord_info l
                        LEFT JOIN real_estate_info re ON re.landlord_id = l.id
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE l.id = %s
                    """, (entity_ids[0],))
                    estates = data["estates"] if data else []
                    contracts = data["contracts"] if data else []
                    # estates и contracts теперь гарантированно списки без null
                    undo_info = {
                        "landlord": {"id": landlord["id"], "name": landlord["name"], "contact_info": landlord["contact_info"]},
                        "estates": estates,
                        "contracts": contracts
                    }
                    stats = self.db.fetch_one("""
                        SELECT COUNT(DISTINCT re.id) AS objects_cnt,
                               COUNT(DISTINCT c.id) AS contracts_cnt,
                               COUNT(r.real_estate_id) AS report_cnt
                        FROM landlord_info l
                        LEFT JOIN real_estate_info re ON re.landlord_id = l.id
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE l.id = %s
                    """, (entity_ids[0],))
                else:
                    stats = self.db.fetch_one("""
                        SELECT COUNT(DISTINCT l.id) AS landlords_cnt,
                               COUNT(DISTINCT re.id) AS objects_cnt,
                               COUNT(DISTINCT c.id) AS contracts_cnt,
                               COUNT(r.real_estate_id) AS report_cnt
                        FROM landlord_info l
                        LEFT JOIN real_estate_info re ON re.landlord_id = l.id
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE l.id IN %s
                    """, (tuple(entity_ids),))
            elif entity_type == 'estate':
                if single:
                    estate = self.db.fetch_one("SELECT * FROM real_estate_info WHERE id = %s", (entity_ids[0],))
                    if not estate:
                        return
                    data = self.db.fetch_one("""
                        SELECT 
                            COALESCE(json_agg(r.*) FILTER (WHERE r.real_estate_id IS NOT NULL), '[]') AS reports,
                            COALESCE(json_agg(DISTINCT c.*) FILTER (WHERE c.id IS NOT NULL), '[]') AS contracts
                        FROM real_estate_info re
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE re.id = %s
                    """, (entity_ids[0],))
                    reports = data["reports"] if data else []
                    contracts = data["contracts"] if data else []
                    undo_info = {
                        "estate": {
                            "id": estate["id"],
                            "address": estate["address"],
                            "overall_space": estate["overall_space"],
                            "living_space": estate["living_space"],
                            "floor": estate["floor"],
                            "date_of_construction": str(estate["date_of_construction"]),
                            "elevator": estate["elevator"],
                            "rooms_amount": estate["rooms_amount"],
                            "landlord_id": estate["landlord_id"]
                        },
                        "reports": reports,
                        "contracts": contracts
                    }
                    stats = self.db.fetch_one("""
                        SELECT COUNT(DISTINCT c.id) AS contracts_cnt,
                               COUNT(r.real_estate_id) AS report_cnt
                        FROM real_estate_info re
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE re.id = %s
                    """, (entity_ids[0],))
                else:
                    stats = self.db.fetch_one("""
                        SELECT COUNT(DISTINCT c.id) AS contracts_cnt,
                               COUNT(r.real_estate_id) AS report_cnt
                        FROM real_estate_info re
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE re.id IN %s
                    """, (tuple(entity_ids),))
            elif entity_type == 'contract':
                if single:
                    contract = self.db.fetch_one("SELECT * FROM contract WHERE id = %s", (entity_ids[0],))
                    if not contract:
                        return
                    objects = self.db.fetch_all("SELECT real_estate_id, start_date, months, price_per_month FROM report WHERE contract_id = %s", (entity_ids[0],))[0] or []
                    undo_info = {
                        "contract": {"id": contract["id"], "date": str(contract["date"]), "tenant_passport": contract["tenant_passport"]},
                        "objects": [{"real_estate_id": r[0], "start_date": str(r[1]), "months": r[2], "price_per_month": r[3]} for r in objects]
                    }
                    stats = None
                else:
                    stats = self.db.fetch_one("""
                        SELECT COUNT(DISTINCT c.id) AS contracts_cnt,
                               COUNT(r.real_estate_id) AS report_cnt,
                               COUNT(DISTINCT r.real_estate_id) AS objects_cnt
                        FROM contract c
                        LEFT JOIN report r ON r.contract_id = c.id
                        WHERE c.id IN %s
                    """, (tuple(entity_ids),))
            else:
                return
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка при подготовке удаления", parse_db_error(e))
            return

        # Подтверждение
        if not self._confirm_deletion(entity_type, single, entity_ids, stats):
            return

        # Выполнение удаления
        try:
            main_win.start_progress(maximum=2 if not single else 1, text="Удаление...")
            with self.db.conn.cursor() as cur:
                if entity_type == 'landlord':
                    cur.execute("DELETE FROM report WHERE real_estate_id IN (SELECT id FROM real_estate_info WHERE landlord_id = ANY(%s))", (entity_ids,))
                    cur.execute("DELETE FROM contract WHERE id NOT IN (SELECT DISTINCT contract_id FROM report)")
                    cur.execute("DELETE FROM real_estate_info WHERE landlord_id = ANY(%s)", (entity_ids,))
                    cur.execute("DELETE FROM landlord_info WHERE id = ANY(%s)", (entity_ids,))
                elif entity_type == 'estate':
                    cur.execute("DELETE FROM report WHERE real_estate_id = ANY(%s)", (entity_ids,))
                    cur.execute("DELETE FROM contract WHERE id NOT IN (SELECT DISTINCT contract_id FROM report)")
                    cur.execute("DELETE FROM real_estate_info WHERE id = ANY(%s)", (entity_ids,))
                elif entity_type == 'contract':
                    cur.execute("DELETE FROM report WHERE contract_id = ANY(%s)", (entity_ids,))
                    cur.execute("DELETE FROM contract WHERE id = ANY(%s)", (entity_ids,))
                self.db.conn.commit()
            main_win.update_progress(2 if not single else 1)

            if single and undo_info:
                if entity_type == 'landlord':
                    self.history.add_event(
                        event_type="landlord",
                        text=f"Собственник удалён: {undo_info['landlord']['name']}",
                        undo_data={"action": "delete_landlord", "landlord": undo_info["landlord"], "estates": undo_info["estates"], "contracts": undo_info["contracts"]}
                    )
                elif entity_type == 'estate':
                    self.history.add_event(
                        event_type="estate",
                        text=f"Объект удалён: {undo_info['estate']['address']}",
                        undo_data={"action": "delete_estate", "estate": undo_info["estate"], "reports": undo_info["reports"], "contracts": undo_info["contracts"]}
                    )
                elif entity_type == 'contract':
                    self.history.add_event(
                        event_type="contract",
                        text=f"Договор удалён от {undo_info['contract']['date']}",
                        undo_data={"action": "delete_contract", "contract": undo_info["contract"], "objects": undo_info["objects"]}
                    )

            self.refresh()
            if self.refresh_callback:
                self.refresh_callback()
        except Exception as e:
            self.db.conn.rollback()
            if isinstance(e, psycopg2.Error):
                QMessageBox.critical(self, "Ошибка БД", parse_db_error(e))
            else:
                QMessageBox.critical(self, "Ошибка", str(e))
        finally:
            main_win.stop_progress()

    def _confirm_deletion(self, entity_type, single, entity_ids, stats):
        if entity_type == 'landlord':
            if single:
                msg = f"Удалить собственника?\n\nОбъектов: {stats['objects_cnt']}\nДоговоров: {stats['contracts_cnt']}\nЗаписей аренды: {stats['report_cnt']}\n\nВсё перечисленное будет удалено. Продолжить?"
            else:
                msg = f"Удалить {stats['landlords_cnt']} собственников?\n\nОбъектов: {stats['objects_cnt']}\nДоговоров: {stats['contracts_cnt']}\nЗаписей аренды: {stats['report_cnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"
        elif entity_type == 'estate':
            if single:
                msg = f"Удалить объект?\n\nЗатронуто договоров: {stats['contracts_cnt']}\nЗаписей аренды: {stats['report_cnt']}\n\nВсё связанное будет удалено. Продолжить?"
            else:
                msg = f"Удалить {len(entity_ids)} объектов?\n\nЗатронуто договоров: {stats['contracts_cnt']}\nЗаписей аренды: {stats['report_cnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"
        elif entity_type == 'contract':
            if single:
                msg = "Удалить договор?\n\nВсе связанные записи аренды будут удалены."
            else:
                msg = f"Удалить {stats['contracts_cnt']} договоров?\n\nЗаписей аренды: {stats['report_cnt']}\nУникальных объектов: {stats['objects_cnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"
        else:
            return False

        reply = QMessageBox.question(self, "Подтверждение удаления", msg, QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

    def add_object(self, initial_data=None):
        if initial_data is not None:
            dlg = RealEstateDialog(self.db, initial_data=initial_data, parent=self)
        else:
            lid = self._require_single_landlord("для добавления объекта")
            if lid is None:
                return
            dlg = RealEstateDialog(self.db, landlord_id=lid, parent=self)

        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        new_id = data["id"]
        self.history.add_event(
            event_type="estate",
            text=f"Объект добавлен: {data['address']}",
            show_target=('estate', new_id),
            repeat_data=('estate', data),
            undo_data={"action": "add_estate", "estate_id": new_id}
        )
        self.refresh()
        if self.refresh_callback:
            self.refresh_callback()

    def add_contract(self, initial_data=None):
        lid = None
        if initial_data is None:
            lid = self._require_single_landlord("для создания договора")
            if lid is None:
                return
        if initial_data:
            dlg = ContractDialog(self.db, initial_data=initial_data, parent=self)
        else:
            dlg = ContractDialog(self.db, initial_landlord_id=lid, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        contract_id = data["contract_id"]
        self.history.add_event(
            event_type="contract",
            text=f"Договор создан от {data['date']}",
            show_target=('contract', contract_id),
            repeat_data=('contract', data),
            undo_data={"action": "add_contract", "contract_id": contract_id}
        )
        self.refresh()
        if self.refresh_callback:
            self.refresh_callback()

    def refresh(self):
        self.load_data()
        self.current_landlord_ids = []
        self.clear_landlord_info()
        self._add_object_btn.setEnabled(False)
        self._delete_objects_btn.setEnabled(False)
        self._add_contract_btn.setEnabled(False)
        self._delete_contracts_btn.setEnabled(False)

    def open_edit_dialog(self, landlord_id):
        self.edit_landlord_by_id(landlord_id)