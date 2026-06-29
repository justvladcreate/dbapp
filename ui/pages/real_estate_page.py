# ui/pages/real_estate_page.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QHeaderView, QMenu, QMessageBox, QSplitter,
    QGroupBox, QFormLayout, QLabel, QDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QAction
import psycopg2

from database.connection import Database
from database.queries import (
    GET_REAL_ESTATES, GET_ESTATE_CONTRACTS,
    INSERT_REAL_ESTATE, UPDATE_REAL_ESTATE,
    INSERT_CONTRACT, INSERT_REPORT_ITEM
)
from database.error_handler import parse_db_error
from ui.dialogs import RealEstateDialog, ContractDialog
from ui.widgets import export_proxy_to_csv
from ui.utils import format_currency
from ui.history_manager import HistoryManager
from ui.pages.base_page import BasePage, SubTable


class RealEstatePage(BasePage):
    view_contract_requested = Signal(int)
    edit_contract_requested = Signal(int)
    view_landlord_requested = Signal(int)  # пока не используется, но оставлен

    MAIN_COLUMN_TYPES = ['text', 'numeric', 'numeric', 'numeric', 'text', 'text', 'numeric', 'text']
    CONTRACTS_SINGLE_COLUMN_TYPES = ['date', 'text', 'numeric', 'date', 'numeric', 'numeric']
    CONTRACTS_MULTI_COLUMN_TYPES = ['text', 'date', 'text', 'numeric', 'date', 'numeric', 'numeric']

    def __init__(self, db: Database, refresh_callback=None, parent=None):
        super().__init__(db, parent)
        self.refresh_callback = refresh_callback
        self.current_estate_ids = []
        self.history = HistoryManager()

        # Верхняя панель кнопок
        self.add_btn = self.add_button("Добавить", self.add_estate, "Добавить объект недвижимости (Insert)")
        self.copy_btn = self.add_button("Копировать", self.copy_estate, "Копировать выбранный объект (Ctrl+C)")
        self.copy_btn.setEnabled(False)
        self.del_btn = self.add_button("Удалить", self.delete_estates, "Удалить выбранные объекты (Del)")
        self.add_clear_filters_button()
        self.add_export_button()

        self.setup_table_with_filterbar(self.MAIN_COLUMN_TYPES)
        self.table.doubleClicked.connect(self._on_main_double_clicked)
        self.table.selectionModel().selectionChanged.connect(self._on_estate_selected)

        # Нижняя панель
        self.vert_splitter = QSplitter(Qt.Vertical)
        self._main_layout.addWidget(self.vert_splitter)

        # Информация об объекте
        self.info_group = QGroupBox("Информация об объекте")
        self.info_group.setMinimumWidth(200)
        info_layout = QFormLayout()
        self.lbl_address = QLabel("—")
        self.lbl_overall = QLabel("—")
        self.lbl_living = QLabel("—")
        self.lbl_floor = QLabel("—")
        self.lbl_rooms = QLabel("—")
        self.lbl_landlord = QLabel("—")
        info_layout.addRow("Адрес:", self.lbl_address)
        info_layout.addRow("Общая площадь:", self.lbl_overall)
        info_layout.addRow("Жилая площадь:", self.lbl_living)
        info_layout.addRow("Этаж:", self.lbl_floor)
        info_layout.addRow("Комнат:", self.lbl_rooms)
        info_layout.addRow("Собственник:", self.lbl_landlord)
        self.info_group.setLayout(info_layout)

        # Договоры через SubTable
        contracts_group = QGroupBox("Договоры с объектом")
        con_layout = QVBoxLayout()
        con_header = QHBoxLayout()
        self.add_contract_btn = QPushButton("Создать договор")
        self.add_contract_btn.clicked.connect(lambda: self.add_contract())
        self.delete_contracts_btn = QPushButton("Удалить")
        self.delete_contracts_btn.clicked.connect(self.delete_contracts)
        self.clear_contracts_filters_btn = QPushButton("Очистить фильтры")
        self.clear_contracts_filters_btn.setToolTip("Сбросить фильтры таблицы")
        con_header.addWidget(self.add_contract_btn)
        con_header.addWidget(self.delete_contracts_btn)
        con_header.addStretch()
        con_header.addWidget(self.clear_contracts_filters_btn)
        con_layout.addLayout(con_header)

        self._contracts_subtable = SubTable(self, self.CONTRACTS_SINGLE_COLUMN_TYPES)
        self._contracts_subtable.table.doubleClicked.connect(self._on_contracts_double_clicked)
        self._contracts_subtable.connect_context_menu(self._on_contracts_context_menu)
        self.clear_contracts_filters_btn.clicked.connect(self._contracts_subtable.filter_bar.reset)

        con_layout.addWidget(self._contracts_subtable.filter_bar)
        con_layout.addWidget(self._contracts_subtable.table)
        contracts_group.setLayout(con_layout)

        # Размещение в сплиттере
        bottom_splitter = QSplitter(Qt.Horizontal)
        bottom_splitter.addWidget(self.info_group)
        bottom_splitter.addWidget(contracts_group)
        bottom_splitter.setCollapsible(0, False)
        bottom_splitter.setCollapsible(1, False)
        bottom_splitter.setSizes([200, 650])

        bottom_widget = QWidget()
        bottom_widget.setMinimumHeight(150)
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(bottom_splitter)

        self.vert_splitter.addWidget(self.table)
        self.vert_splitter.addWidget(bottom_widget)
        self.vert_splitter.setCollapsible(0, False)
        self.vert_splitter.setCollapsible(1, False)
        self.vert_splitter.setSizes([350, 300])

        self.add_contract_btn.setEnabled(False)
        self.delete_contracts_btn.setEnabled(False)

        self.load_data()

    # ----------------------------------------------------------------
    #  ЗАГРУЗКА ДАННЫХ
    # ----------------------------------------------------------------
    def load_data(self):
        def extractor(row):
            # row: [id, address, overall_space, living_space, floor, date, elevator, rooms, landlord_id, landlord_name]
            # Отображаем: address, overall, living, floor, date, elevator, rooms, landlord_name
            return [
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                str(row[5]),
                "Да" if row[6] else "Нет",
                str(row[7]),
                str(row[9])
            ]
        def extra_extractor(row):
            return row[8]  # landlord_id

        self.load_query_into_model(
            query=GET_REAL_ESTATES,
            headers=["Адрес", "Общ.пл", "Жил.пл", "Этаж", "Год постр.", "Лифт", "Комнат", "Собственник"],
            data_extractor=extractor,
            id_extractor=lambda row: row[0],
            extra_data_extractor=extra_extractor
        )
        self.table.resizeColumnsToContents()

    # ----------------------------------------------------------------
    #  ВЫДЕЛЕНИЕ И ОБРАБОТКА
    # ----------------------------------------------------------------
    def get_selected_estate_ids(self):
        return self.get_selected_ids()

    def _on_estate_selected(self):
        ids = self.get_selected_estate_ids()
        self.current_estate_ids = ids
        single = len(ids) == 1
        self.copy_btn.setEnabled(single)
        self.add_contract_btn.setEnabled(single)
        self.delete_contracts_btn.setEnabled(single)

        if not ids:
            self._clear_info()
            return

        if single:
            self._load_estate_info(ids[0])
        else:
            self._load_estates_summary(ids)

    def _require_single_estate(self, action_desc):
        if len(self.current_estate_ids) != 1:
            QMessageBox.information(self, "Информация", f"Сначала выберите один объект ({action_desc}).")
            return None
        return self.current_estate_ids[0]

    def copy_estate(self):
        eid = self._require_single_estate("для копирования")
        if eid is None:
            return
        estate = self.db.fetch_one("""
            SELECT address, overall_space, living_space, floor, date_of_construction,
                   elevator, rooms_amount, landlord_id
            FROM real_estate_info WHERE id = %s
        """, (eid,))
        if not estate:
            return
        self.add_estate(initial_data=estate)

    def _load_estate_info(self, estate_id):
        try:
            estate = self.db.fetch_one("""
                SELECT re.address, re.overall_space, re.living_space, re.floor, re.rooms_amount,
                       l.name AS landlord_name
                FROM real_estate_info re JOIN landlord_info l ON re.landlord_id = l.id
                WHERE re.id = %s
            """, (estate_id,))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки информации", parse_db_error(e))
            return
        if estate:
            self.lbl_address.setText(estate["address"])
            self.lbl_overall.setText(f"{estate['overall_space']} м²")
            self.lbl_living.setText(f"{estate['living_space']} м²")
            self.lbl_floor.setText(str(estate["floor"]))
            self.lbl_rooms.setText(str(estate["rooms_amount"]))
            self.lbl_landlord.setText(estate["landlord_name"])
        else:
            self._clear_info()

        # Договоры
        self._load_contracts_for_estates([estate_id])

    def _load_estates_summary(self, estate_ids):
        placeholders = ','.join(['%s'] * len(estate_ids))
        try:
            summary = self.db.fetch_one(f"""
                SELECT COUNT(*) AS cnt, SUM(overall_space) AS tot_over, SUM(living_space) AS tot_liv,
                       MIN(floor) AS min_f, MAX(floor) AS max_f,
                       STRING_AGG(DISTINCT l.name, ', ') AS landlords
                FROM real_estate_info re JOIN landlord_info l ON re.landlord_id = l.id
                WHERE re.id IN ({placeholders})
            """, tuple(estate_ids))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки сводки", parse_db_error(e))
            return
        if summary:
            self.lbl_address.setText(f"Выбрано объектов: {summary['cnt']}")
            self.lbl_overall.setText(f"{summary['tot_over']} м²")
            self.lbl_living.setText(f"{summary['tot_liv']} м²")
            self.lbl_floor.setText(f"{summary['min_f']} – {summary['max_f']}")
            self.lbl_rooms.setText("—")
            self.lbl_landlord.setText(summary['landlords'] or "—")

        self._load_contracts_for_estates(estate_ids, multi=True)

    def _load_contracts_for_estates(self, estate_ids, multi=False):
        placeholders = ','.join(['%s'] * len(estate_ids))
        if not multi:
            query = GET_ESTATE_CONTRACTS
            params = (estate_ids[0],)
            headers = ["Дата", "Арендатор", "Цена/мес", "Начало", "Срок (мес)", "Сумма"]
            col_types = self.CONTRACTS_SINGLE_COLUMN_TYPES
        else:
            query = f"""
                SELECT c.id, c.date, t.name, r.price_per_month, r.start_date, r.months,
                       (r.price_per_month * r.months) AS total, re.address, re.id AS estate_id
                FROM report r JOIN contract c ON r.contract_id = c.id
                JOIN tenant t ON c.tenant_passport = t.passport
                JOIN real_estate_info re ON r.real_estate_id = re.id
                WHERE re.id IN ({placeholders})
                ORDER BY c.date DESC, re.address
            """
            params = tuple(estate_ids)
            headers = ["Объект", "Дата", "Арендатор", "Цена/мес", "Начало", "Срок (мес)", "Сумма"]
            col_types = self.CONTRACTS_MULTI_COLUMN_TYPES

        try:
            rows, _ = self.db.fetch_all(query, params)
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки договоров", parse_db_error(e))
            return

        self._contracts_subtable.clear()
        self._contracts_subtable.set_headers(headers)
        for row in rows:
            if not multi:
                values = [
                    str(row[1]), str(row[2]),
                    format_currency(row[3]), str(row[4]),
                    str(row[5]), format_currency(row[6])
                ]
                cid = row[0]
                estate_id = None
            else:
                values = [
                    str(row[7]), str(row[1]), str(row[2]),
                    format_currency(row[3]), str(row[4]),
                    str(row[5]), format_currency(row[6])
                ]
                cid = row[0]
                estate_id = row[8]
            items = [QStandardItem(v) for v in values]
            self._contracts_subtable.add_row(items, id_data=cid, extra_data=estate_id)
        self._contracts_subtable.filter_bar.rebuild(col_types)
        self._contracts_subtable.finalize()

    def _clear_info(self):
        for lbl in (self.lbl_address, self.lbl_overall, self.lbl_living, self.lbl_floor, self.lbl_rooms, self.lbl_landlord):
            lbl.setText("—")
        self._contracts_subtable.clear()

    # ----------------------------------------------------------------
    #  НАВИГАЦИЯ И КОНТЕКСТНЫЕ МЕНЮ
    # ----------------------------------------------------------------
    def _on_main_double_clicked(self):
        eid = self._require_single_estate("для редактирования")
        if eid:
            self.edit_estate_by_id(eid)

    def _on_contracts_double_clicked(self, index):
        item = self._contracts_subtable.model.item(self._contracts_subtable.proxy.mapToSource(index).row(), 0)
        if not item:
            return
        if len(self.current_estate_ids) == 1:
            cid = item.data(Qt.UserRole)
            if cid:
                self.view_contract_requested.emit(cid)
        else:
            eid = item.data(Qt.UserRole + 1)
            if eid:
                self.select_estate_by_id(eid)

    def _on_contracts_context_menu(self, pos):
        if len(self.current_estate_ids) != 1:
            return
        index = self._contracts_subtable.table.indexAt(pos)
        if not index.isValid():
            return
        item = self._contracts_subtable.model.item(self._contracts_subtable.proxy.mapToSource(index).row(), 0)
        if not item:
            return
        cid = item.data(Qt.UserRole)
        if not cid:
            return
        menu = QMenu(self)
        menu.addAction("Просмотреть", lambda: self.view_contract_requested.emit(cid))
        menu.addAction("Редактировать", lambda: self.edit_contract_requested.emit(cid))
        menu.exec(self._contracts_subtable.table.viewport().mapToGlobal(pos))

    # ----------------------------------------------------------------
    #  CRUD ОБЪЕКТОВ
    # ----------------------------------------------------------------
    def add_estate(self, initial_data=None):
        dlg = RealEstateDialog(self.db, initial_data=initial_data, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="estate",
            text=f"Объект добавлен: {data['address']}",
            show_target=('estate', data['id']),
            repeat_data=('estate', data),
            undo_data={"action": "add_estate", "estate_id": data['id']}
        )
        self.refresh()
        self.reset_filters()
        self.select_estate_by_id(data['id'])
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_estate_by_id(data['id'])

    def edit_estate(self):
        eid = self._require_single_estate("для редактирования")
        if eid is None:
            return
        row = self.db.fetch_one("SELECT * FROM real_estate_info WHERE id = %s", (eid,))
        if not row:
            return
        old_data = {k: row[k] for k in row.keys()}
        dlg = RealEstateDialog(self.db, estate=row, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="estate",
            text=f"Объект изменён: {data['address']}",
            show_target=('estate', eid),
            undo_data={"action": "edit_estate", "old": old_data}
        )
        self.refresh()
        self.reset_filters()
        self.select_estate_by_id(eid)
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_estate_by_id(eid)

    def delete_estates(self):
        ids = self.get_selected_estate_ids()
        if not ids:
            QMessageBox.information(self, "Внимание", "Выделите хотя бы один объект.")
            return
        self._delete_entities("estate", ids)

    def _delete_entities(self, entity_type, entity_ids):
        """Универсальное удаление объектов или договоров."""
        main_win = self.window()
        single = len(entity_ids) == 1
        undo_info = None

        try:
            if entity_type == "estate":
                if single:
                    eid = entity_ids[0]
                    estate = self.db.fetch_one("SELECT * FROM real_estate_info WHERE id = %s", (eid,))
                    if not estate:
                        return
                    # Собираем связанные записи одним запросом без null
                    data = self.db.fetch_one("""
                        SELECT 
                            COALESCE(json_agg(r.*) FILTER (WHERE r.real_estate_id IS NOT NULL), '[]') AS reports,
                            COALESCE(json_agg(DISTINCT c.*) FILTER (WHERE c.id IS NOT NULL), '[]') AS contracts
                        FROM real_estate_info re
                        LEFT JOIN report r ON r.real_estate_id = re.id
                        LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE re.id = %s
                    """, (eid,))
                    reports = data["reports"] if data else []
                    contracts = data["contracts"] if data else []
                    undo_info = {
                        "estate": {k: estate[k] for k in estate.keys()},
                        "reports": reports,
                        "contracts": contracts
                    }
                    stats = self.db.fetch_one("""
                        SELECT COUNT(DISTINCT c.id) AS ccnt, COUNT(r.real_estate_id) AS rcnt
                        FROM real_estate_info re LEFT JOIN report r ON r.real_estate_id = re.id LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE re.id = %s
                    """, (eid,))
                    msg = f"Удалить объект '{estate['address']}'?\n\nЗатронуто договоров: {stats['ccnt']}\nЗаписей аренды: {stats['rcnt']}\n\nВсё связанное будет удалено. Продолжить?"
                else:
                    stats = self.db.fetch_one(f"""
                        SELECT COUNT(DISTINCT re.id) AS ecnt, COUNT(DISTINCT c.id) AS ccnt, COUNT(r.real_estate_id) AS rcnt
                        FROM real_estate_info re LEFT JOIN report r ON r.real_estate_id = re.id LEFT JOIN contract c ON r.contract_id = c.id
                        WHERE re.id IN ({','.join(['%s']*len(entity_ids))})
                    """, tuple(entity_ids))
                    msg = f"Удалить {stats['ecnt']} объектов?\nДоговоров: {stats['ccnt']}\nЗаписей аренды: {stats['rcnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"

            elif entity_type == "contract":
                if single:
                    cid = entity_ids[0]
                    contract = self.db.fetch_one("SELECT * FROM contract WHERE id = %s", (cid,))
                    if not contract:
                        return
                    objects = self.db.fetch_all("SELECT real_estate_id, start_date, months, price_per_month FROM report WHERE contract_id = %s", (cid,))[0] or []
                    undo_info = {
                        "contract": {"id": cid, "date": str(contract["date"]), "tenant_passport": contract["tenant_passport"]},
                        "objects": [{"real_estate_id": r[0], "start_date": str(r[1]), "months": r[2], "price_per_month": r[3]} for r in objects]
                    }
                    msg = f"Удалить договор от {contract['date']}?\n\nВсе связанные записи аренды будут удалены."
                else:
                    stats = self.db.fetch_one(f"""
                        SELECT COUNT(c.id) AS cnt, COUNT(r.real_estate_id) AS rcnt
                        FROM contract c LEFT JOIN report r ON r.contract_id = c.id
                        WHERE c.id IN ({','.join(['%s']*len(entity_ids))})
                    """, tuple(entity_ids))
                    msg = f"Удалить {stats['cnt']} договоров?\nЗаписей аренды: {stats['rcnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"
            else:
                return

            if QMessageBox.question(self, "Подтверждение удаления", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

            main_win.start_progress(maximum=2, text="Удаление...")
            with self.db.conn.cursor() as cur:
                if entity_type == "estate":
                    if single:
                        cur.execute("DELETE FROM report WHERE real_estate_id = %s", (entity_ids[0],))
                    else:
                        cur.execute("DELETE FROM report WHERE real_estate_id = ANY(%s)", (entity_ids,))
                    main_win.update_progress(1)
                    cur.execute("DELETE FROM contract WHERE id NOT IN (SELECT DISTINCT contract_id FROM report)")
                    if single:
                        cur.execute("DELETE FROM real_estate_info WHERE id = %s", (entity_ids[0],))
                    else:
                        cur.execute("DELETE FROM real_estate_info WHERE id = ANY(%s)", (entity_ids,))
                elif entity_type == "contract":
                    if single:
                        cur.execute("DELETE FROM report WHERE contract_id = %s", (entity_ids[0],))
                    else:
                        cur.execute("DELETE FROM report WHERE contract_id = ANY(%s)", (entity_ids,))
                    main_win.update_progress(1)
                    if single:
                        cur.execute("DELETE FROM contract WHERE id = %s", (entity_ids[0],))
                    else:
                        cur.execute("DELETE FROM contract WHERE id = ANY(%s)", (entity_ids,))
                self.db.conn.commit()
            main_win.update_progress(2)

            if single and undo_info:
                if entity_type == "estate":
                    self.history.add_event(
                        event_type="estate",
                        text=f"Объект удалён: {undo_info['estate']['address']}",
                        undo_data={"action": "delete_estate", "estate": undo_info["estate"], "reports": undo_info["reports"], "contracts": undo_info["contracts"]}
                    )
                else:
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
            self._show_error(e)
        finally:
            main_win.stop_progress()

    def add_contract(self, initial_data=None):
        eid = None
        if initial_data is None:
            eid = self._require_single_estate("для создания договора")
            if eid is None:
                return
        if initial_data:
            dlg = ContractDialog(self.db, initial_data=initial_data, parent=self)
        else:
            dlg = ContractDialog(self.db, initial_estate_id=eid, parent=self)
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

    def delete_contracts(self):
        ids = self._contracts_subtable.get_selected_ids()
        if not ids:
            QMessageBox.information(self, "Внимание", "Выделите договоры для удаления.")
            return
        self._delete_entities("contract", ids)

    def edit_estate_by_id(self, estate_id):
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item.data(Qt.UserRole) == estate_id:
                proxy_idx = self.proxy.mapFromSource(self.model.index(row, 0))
                self.table.selectRow(proxy_idx.row())
                self.table.scrollTo(proxy_idx)
                self.current_estate_ids = [estate_id]
                self.edit_estate()
                return

    def select_estate_by_id(self, estate_id):
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item.data(Qt.UserRole) == estate_id:
                proxy_idx = self.proxy.mapFromSource(self.model.index(row, 0))
                self.table.clearSelection()
                self.table.selectRow(proxy_idx.row())
                self.table.scrollTo(proxy_idx)
                self.current_estate_ids = [estate_id]
                return
        QMessageBox.information(self, "Информация", "Объект не найден в текущей таблице.")

    def refresh(self):
        self.load_data()
        self.current_estate_ids = []
        self._clear_info()
        self.add_contract_btn.setEnabled(False)
        self.delete_contracts_btn.setEnabled(False)

    def open_edit_dialog(self, estate_id):
        self.edit_estate_by_id(estate_id)

    @staticmethod
    def _show_error(e):
        if isinstance(e, psycopg2.Error):
            QMessageBox.critical(None, "Ошибка БД", parse_db_error(e))
        else:
            QMessageBox.critical(None, "Ошибка", str(e))