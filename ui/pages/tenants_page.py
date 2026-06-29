# ui/pages/tenants_page.py
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
    GET_TENANTS, GET_TENANT_CONTRACTS, TENANT_STATS,
    INSERT_TENANT, UPDATE_TENANT,
    INSERT_CONTRACT, INSERT_REPORT_ITEM
)
from database.error_handler import parse_db_error
from ui.dialogs import TenantDialog, ContractDialog
from ui.widgets import export_proxy_to_csv
from ui.utils import format_currency
from ui.history_manager import HistoryManager
from ui.pages.base_page import BasePage, SubTable


class TenantsPage(BasePage):
    view_contract_requested = Signal(int)
    edit_contract_requested = Signal(int)

    MAIN_COLUMN_TYPES = ['text', 'text', 'numeric']
    CONTRACTS_SINGLE_COLUMN_TYPES = ['date', 'numeric', 'numeric']
    CONTRACTS_MULTI_COLUMN_TYPES = ['text', 'date', 'numeric', 'numeric']

    def __init__(self, db: Database, refresh_callback=None, parent=None):
        super().__init__(db, parent)
        self.refresh_callback = refresh_callback
        self.current_passports = []
        self.history = HistoryManager()

        self.add_btn = self.add_button("Добавить", self.add_tenant, "Добавить арендатора (Insert)")
        self.copy_btn = self.add_button("Копировать", self.copy_tenant, "Копировать выбранного арендатора (Ctrl+C)")
        self.copy_btn.setEnabled(False)
        self.del_btn = self.add_button("Удалить", self.delete_tenants, "Удалить выбранных арендаторов (Del)")
        self.add_clear_filters_button()
        self.add_export_button()

        self.setup_table_with_filterbar(self.MAIN_COLUMN_TYPES)
        self.table.doubleClicked.connect(self._on_main_double_clicked)
        self.table.selectionModel().selectionChanged.connect(self._on_tenant_selected)

        self.vert_splitter = QSplitter(Qt.Vertical)
        self._main_layout.addWidget(self.vert_splitter)

        bottom_widget = QWidget()
        bottom_widget.setMinimumHeight(150)   # предотвращает схлопывание пустой панели
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.bottom_splitter = QSplitter(Qt.Horizontal)

        self.stats_group = QGroupBox("Статистика")
        self.stats_group.setMinimumWidth(150)
        stats_layout = QFormLayout()
        self.lbl_contracts_count = QLabel("0")
        self.lbl_total_spent = QLabel("0 ₽")
        stats_layout.addRow("Договоров:", self.lbl_contracts_count)
        stats_layout.addRow("Общие расходы:", self.lbl_total_spent)
        self.stats_group.setLayout(stats_layout)
        self.bottom_splitter.addWidget(self.stats_group)

        contracts_group = QGroupBox("Договоры")
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
        self.bottom_splitter.addWidget(contracts_group)

        self.bottom_splitter.setSizes([150, 600])
        self.bottom_splitter.setCollapsible(0, False)
        self.bottom_splitter.setCollapsible(1, False)

        bottom_layout.addWidget(self.bottom_splitter)
        bottom_widget.setLayout(bottom_layout)

        self.vert_splitter.addWidget(self.table)
        self.vert_splitter.addWidget(bottom_widget)
        self.vert_splitter.setCollapsible(0, False)
        self.vert_splitter.setCollapsible(1, False)
        self.vert_splitter.setSizes([300, 300])

        self.add_contract_btn.setEnabled(False)
        self.delete_contracts_btn.setEnabled(False)

        self.load_data()

    # ----------------------------------------------------------------
    def load_data(self):
        # Включаем паспорт как первый столбец, ID – он же
        self.load_query_into_model(
            query=GET_TENANTS,
            headers=["Паспорт", "ФИО", "Кол-во договоров"],
            data_extractor=lambda row: [row[0], row[1], str(row[2])],
            id_column=0   # passport используется и как ID
        )


    def get_selected_passports(self):
        """Возвращает список паспортов (ID) выделенных арендаторов."""
        return self.get_selected_ids()

    def _on_tenant_selected(self):
        passports = self.get_selected_passports()
        self.current_passports = passports
        single = len(passports) == 1
        self.copy_btn.setEnabled(single)
        self.add_contract_btn.setEnabled(single)
        self.delete_contracts_btn.setEnabled(single)

        if not passports:
            self._clear_tenant_info()
            return
        if single:
            self._load_tenant_info(passports[0])
        else:
            self._load_tenants_summary(passports)

    def _require_single_passport(self, action_desc):
        if len(self.current_passports) != 1:
            QMessageBox.information(self, "Информация", f"Сначала выберите одного арендатора ({action_desc}).")
            return None
        return self.current_passports[0]

    def copy_tenant(self):
        passport = self._require_single_passport("для копирования")
        if passport is None:
            return
        tenant = self.db.fetch_one("SELECT name FROM tenant WHERE passport = %s", (passport,))
        if tenant:
            self.add_tenant(initial_data={"passport": "", "name": tenant["name"]})

    def _load_tenant_info(self, passport):
        try:
            stats = self.db.fetch_one(TENANT_STATS, (passport,))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки статистики", parse_db_error(e))
            return
        if stats:
            self.lbl_contracts_count.setText(str(stats["contracts_count"]))
            self.lbl_total_spent.setText(format_currency(stats["total_spent"]))
        else:
            self.lbl_contracts_count.setText("0")
            self.lbl_total_spent.setText("0 ₽")

        self._load_contracts_for_passports([passport])

    def _load_tenants_summary(self, passports):
        placeholders = ','.join(['%s'] * len(passports))
        try:
            stats = self.db.fetch_one(f"""
                SELECT COUNT(DISTINCT c.id) AS contracts_count,
                       COALESCE(SUM(r.price_per_month * r.months), 0) AS total_spent
                FROM tenant t
                LEFT JOIN contract c ON c.tenant_passport = t.passport
                LEFT JOIN report r ON r.contract_id = c.id
                WHERE t.passport IN ({placeholders})
            """, tuple(passports))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки статистики", parse_db_error(e))
            return
        if stats:
            self.lbl_contracts_count.setText(str(stats["contracts_count"]))
            self.lbl_total_spent.setText(format_currency(stats["total_spent"]))
        else:
            self.lbl_contracts_count.setText("0")
            self.lbl_total_spent.setText("0 ₽")

        self._load_contracts_for_passports(passports, multi=True)

    def _load_contracts_for_passports(self, passports, multi=False):
        if not multi:
            query = GET_TENANT_CONTRACTS
            params = (passports[0],)
            headers = ["Дата", "Объектов", "Сумма"]
            col_types = self.CONTRACTS_SINGLE_COLUMN_TYPES
        else:
            placeholders = ','.join(['%s'] * len(passports))
            query = f"""
                SELECT c.id, c.date, t.name AS tenant_name,
                       COUNT(r.real_estate_id) AS objects_count,
                       SUM(r.price_per_month * r.months) AS total_sum,
                       t.passport
                FROM contract c
                JOIN tenant t ON c.tenant_passport = t.passport
                LEFT JOIN report r ON c.id = r.contract_id
                WHERE t.passport IN ({placeholders})
                GROUP BY c.id, c.date, t.name, t.passport
                ORDER BY c.date DESC
            """
            params = tuple(passports)
            headers = ["Арендатор", "Дата", "Объектов", "Сумма"]
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
                    str(row[1]),
                    str(row[2]),
                    format_currency(row[3])
                ]
                cid = row[0]
                extra = None
            else:
                values = [
                    str(row[2]),
                    str(row[1]),
                    str(row[3]),
                    format_currency(row[4])
                ]
                cid = row[0]
                extra = row[5]   # passport
            items = [QStandardItem(v) for v in values]
            self._contracts_subtable.add_row(items, id_data=cid, extra_data=extra)
        self._contracts_subtable.filter_bar.rebuild(col_types)
        self._contracts_subtable.finalize()

    def _clear_tenant_info(self):
        self.lbl_contracts_count.setText("0")
        self.lbl_total_spent.setText("0 ₽")
        self._contracts_subtable.clear()

    # ----------------------------------------------------------------
    #  НАВИГАЦИЯ И КОНТЕКСТНЫЕ МЕНЮ
    # ----------------------------------------------------------------
    def _on_main_double_clicked(self):
        passport = self._require_single_passport("для редактирования")
        if passport:
            self.edit_tenant_by_passport(passport)

    def _on_contracts_double_clicked(self, index):
        item = self._contracts_subtable.model.item(self._contracts_subtable.proxy.mapToSource(index).row(), 0)
        if not item:
            return
        if len(self.current_passports) == 1:
            cid = item.data(Qt.UserRole)
            if cid:
                self.view_contract_requested.emit(cid)
        else:
            passport = item.data(Qt.UserRole + 1)
            if passport:
                self.select_tenant_by_passport(passport)

    def _on_contracts_context_menu(self, pos):
        if len(self.current_passports) != 1:
            return
        index = self._contracts_subtable.table.indexAt(pos)
        if not index.isValid():
            return
        item = self._contracts_subtable.model.item(self._contracts_subtable.proxy.mapToSource(index).row(), 0)
        cid = item.data(Qt.UserRole) if item else None
        if not cid:
            return
        menu = QMenu(self)
        menu.addAction("Просмотреть", lambda: self.view_contract_requested.emit(cid))
        menu.addAction("Редактировать", lambda: self.edit_contract_requested.emit(cid))
        menu.exec(self._contracts_subtable.table.viewport().mapToGlobal(pos))

    # ----------------------------------------------------------------
    #  CRUD АРЕНДАТОРОВ
    # ----------------------------------------------------------------
    def add_tenant(self, initial_data=None):
        dlg = TenantDialog(self.db, initial_data=initial_data, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="tenant",
            text=f"Арендатор добавлен: {data['name']}",
            show_target=('tenant', data['passport']),
            repeat_data=('tenant', data),
            undo_data={"action": "add_tenant", "passport": data['passport']}
        )

        self.refresh()
        self.reset_filters()
        self.select_tenant_by_passport(data['passport'])
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_tenant_by_passport(data['passport'])

    def edit_tenant(self):
        passport = self._require_single_passport("для редактирования")
        if passport is None:
            return
        row = self.db.fetch_one("SELECT * FROM tenant WHERE passport = %s", (passport,))
        if not row:
            return
        old_data = {"passport": row["passport"], "name": row["name"]}
        dlg = TenantDialog(self.db, tenant=row, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="tenant",
            text=f"Арендатор изменён: {data['name']}",
            show_target=('tenant', passport),
            undo_data={"action": "edit_tenant", "old": old_data}
        )
        self.refresh()
        self.reset_filters()
        self.select_tenant_by_passport(passport)
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_tenant_by_passport(passport)

    def delete_tenants(self):
        passports = self.get_selected_passports()
        if not passports:
            QMessageBox.information(self, "Внимание", "Выделите хотя бы одного арендатора.")
            return
        self._delete_entities("tenant", passports)

    def _delete_entities(self, entity_type, entity_ids):
        main_win = self.window()
        single = len(entity_ids) == 1
        undo_info = None

        if entity_type == "tenant":
            if single:
                pp = entity_ids[0]
                tenant = self.db.fetch_one("SELECT * FROM tenant WHERE passport = %s", (pp,))
                if not tenant:
                    return
                contracts = self.db.fetch_all("SELECT c.id, c.date, c.tenant_passport FROM contract c WHERE c.tenant_passport = %s", (pp,))[0] or []
                contracts_data = []
                for c in contracts:
                    objects = self.db.fetch_all("SELECT real_estate_id, start_date, months, price_per_month FROM report WHERE contract_id = %s", (c[0],))[0] or []
                    contracts_data.append({
                        "id": c[0], "date": str(c[1]), "tenant_passport": c[2],
                        "objects": [{"real_estate_id": r[0], "start_date": str(r[1]), "months": r[2], "price_per_month": r[3]} for r in objects]
                    })
                undo_info = {"tenant": {"passport": pp, "name": tenant["name"]}, "contracts": contracts_data}
                stats = self.db.fetch_one("""
                    SELECT COUNT(DISTINCT c.id) AS contracts_cnt, COUNT(r.real_estate_id) AS report_cnt
                    FROM tenant t LEFT JOIN contract c ON c.tenant_passport = t.passport LEFT JOIN report r ON r.contract_id = c.id
                    WHERE t.passport = %s
                """, (pp,))
                msg = f"Удалить арендатора '{tenant['name']}'?\n\nДоговоров: {stats['contracts_cnt']}\nЗаписей аренды: {stats['report_cnt']}\n\nВсё связанное будет удалено. Продолжить?"
            else:
                placeholders = ','.join(['%s'] * len(entity_ids))
                stats = self.db.fetch_one(f"""
                    SELECT COUNT(DISTINCT t.passport) AS tenants_cnt, COUNT(DISTINCT c.id) AS contracts_cnt, COUNT(r.real_estate_id) AS report_cnt
                    FROM tenant t LEFT JOIN contract c ON c.tenant_passport = t.passport LEFT JOIN report r ON r.contract_id = c.id
                    WHERE t.passport IN ({placeholders})
                """, tuple(entity_ids))
                msg = f"Удалить {stats['tenants_cnt']} арендаторов?\n\nДоговоров: {stats['contracts_cnt']}\nЗаписей аренды: {stats['report_cnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"

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
                placeholders = ','.join(['%s'] * len(entity_ids))
                stats = self.db.fetch_one(f"""
                    SELECT COUNT(c.id) AS cnt, COUNT(r.real_estate_id) AS rcnt
                    FROM contract c LEFT JOIN report r ON r.contract_id = c.id
                    WHERE c.id IN ({placeholders})
                """, tuple(entity_ids))
                msg = f"Удалить {stats['cnt']} договоров?\nЗаписей аренды: {stats['rcnt']}\n\nВНИМАНИЕ: отменить массовое удаление будет невозможно!"
        else:
            return

        if QMessageBox.question(self, "Подтверждение удаления", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        try:
            main_win.start_progress(maximum=2, text="Удаление...")
            with self.db.conn.cursor() as cur:
                if entity_type == "tenant":
                    if single:
                        cur.execute("DELETE FROM report WHERE contract_id IN (SELECT id FROM contract WHERE tenant_passport = %s)", (entity_ids[0],))
                    else:
                        cur.execute("DELETE FROM report WHERE contract_id IN (SELECT id FROM contract WHERE tenant_passport = ANY(%s))", (entity_ids,))
                    main_win.update_progress(1)
                    if single:
                        cur.execute("DELETE FROM contract WHERE tenant_passport = %s", (entity_ids[0],))
                        cur.execute("DELETE FROM tenant WHERE passport = %s", (entity_ids[0],))
                    else:
                        cur.execute("DELETE FROM contract WHERE tenant_passport = ANY(%s)", (entity_ids,))
                        cur.execute("DELETE FROM tenant WHERE passport = ANY(%s)", (entity_ids,))
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
                if entity_type == "tenant":
                    self.history.add_event(
                        event_type="tenant",
                        text=f"Арендатор удалён: {undo_info['tenant']['name']}",
                        undo_data={"action": "delete_tenant", "tenant": undo_info["tenant"], "contracts": undo_info["contracts"]}
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
        passport = None
        if initial_data is None:
            passport = self._require_single_passport("для создания договора")
            if passport is None:
                return
        if initial_data:
            dlg = ContractDialog(self.db, initial_data=initial_data, parent=self)
        else:
            dlg = ContractDialog(self.db, initial_tenant_passport=passport, parent=self)
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

    def edit_tenant_by_passport(self, passport):
        for row in range(self.model.rowCount()):
            if self.model.item(row, 0).text() == passport:
                proxy_idx = self.proxy.mapFromSource(self.model.index(row, 0))
                self.table.selectRow(proxy_idx.row())
                self.table.scrollTo(proxy_idx)
                self.current_passports = [passport]
                self.edit_tenant()
                return

    def select_tenant_by_passport(self, passport):
        for row in range(self.model.rowCount()):
            if self.model.item(row, 0).text() == passport:
                proxy_idx = self.proxy.mapFromSource(self.model.index(row, 0))
                self.table.clearSelection()
                self.table.selectRow(proxy_idx.row())
                self.table.scrollTo(proxy_idx)
                self.current_passports = [passport]
                return
        QMessageBox.information(self, "Информация", "Арендатор не найден в текущей таблице.")

    def refresh(self):
        self.load_data()
        self.current_passports = []
        self._clear_tenant_info()
        self.add_contract_btn.setEnabled(False)
        self.delete_contracts_btn.setEnabled(False)

    def open_edit_dialog(self, passport):
        self.edit_tenant_by_passport(passport)

    @staticmethod
    def _show_error(e):
        if isinstance(e, psycopg2.Error):
            QMessageBox.critical(None, "Ошибка БД", parse_db_error(e))
        else:
            QMessageBox.critical(None, "Ошибка", str(e))