# ui/pages/contracts_page.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableView, QHeaderView, QAbstractItemView,
    QMessageBox, QSplitter, QMenu, QDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QAction
import psycopg2

from database.connection import Database
from database.queries import (
    GET_CONTRACTS,
    INSERT_CONTRACT, INSERT_REPORT_ITEM,
    UPDATE_CONTRACT, UPDATE_REPORT_ITEM,
    DELETE_REPORT_ITEM
)
from database.error_handler import parse_db_error
from ui.dialogs import ContractDialog
from ui.widgets import export_proxy_to_csv
from ui.utils import format_currency
from ui.history_manager import HistoryManager
from ui.pages.base_page import BasePage, SubTable


class ContractsPage(BasePage):
    """Страница «Договоры» с верхней таблицей всех договоров и нижней панелью деталей."""

    edit_contract_signal = Signal(int)
    view_estate_requested = Signal(int)
    edit_estate_requested = Signal(int)

    TOP_COLUMN_TYPES = ['date', 'text', 'text', 'text', 'numeric', 'numeric']
    DETAIL_SINGLE_COLUMN_TYPES = ['text', 'text', 'numeric', 'date', 'numeric', 'numeric']
    DETAIL_MULTI_COLUMN_TYPES = ['date', 'text', 'text', 'numeric', 'date', 'numeric', 'numeric']

    def __init__(self, db: Database, refresh_callback=None, parent=None):
        super().__init__(db, parent)
        self.refresh_callback = refresh_callback
        self.current_contract_ids = []
        self.history = HistoryManager()

        self.add_btn = self.add_button("Добавить", self.add_contract, "Добавить новый договор (Insert)")

        self.copy_btn = self.add_button("Копировать", self.copy_contract, "Создать копию выбранного договора (Ctrl+C)")
        self.copy_btn.setEnabled(False)
        self.del_btn = self.add_button("Удалить", self.delete_contracts, "Удалить выбранные договоры (Del)")
        self.add_clear_filters_button()
        self.add_export_button()

        self.setup_table_with_filterbar(self.TOP_COLUMN_TYPES)
        self.table.doubleClicked.connect(self._edit_current_contract)
        self.table.selectionModel().selectionChanged.connect(self._on_contract_selected)

        self.splitter = QSplitter(Qt.Vertical)
        self._main_layout.addWidget(self.splitter)

        lower_widget = QWidget()
        lower_layout = QVBoxLayout(lower_widget)
        lower_layout.setContentsMargins(0, 0, 0, 0)

        detail_header = QHBoxLayout()
        self.detail_label = QLabel("Объекты, участвующие в договоре:")
        detail_header.addWidget(self.detail_label)
        detail_header.addStretch()
        self.clear_detail_btn = QPushButton("Очистить фильтры")
        self.clear_detail_btn.setToolTip("Сбросить фильтры таблицы")
        self.clear_detail_btn.clicked.connect(lambda: self._detail_subtable.filter_bar.reset())
        detail_header.addWidget(self.clear_detail_btn)
        lower_layout.addLayout(detail_header)

        self._detail_subtable = SubTable(self, self.DETAIL_SINGLE_COLUMN_TYPES)
        self._detail_subtable.table.doubleClicked.connect(self._on_detail_double_clicked)
        self._detail_subtable.connect_context_menu(self._on_detail_context_menu)
        lower_layout.addWidget(self._detail_subtable.filter_bar)
        lower_layout.addWidget(self._detail_subtable.table)

        self.splitter.addWidget(self.table)
        self.splitter.addWidget(lower_widget)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        lower_widget.setMinimumHeight(150)

        self.load_data()

    # ----------------------------------------------------------------------
    def load_data(self):
        # row[0]=id, row[1]=date, row[2]=tenant_name, row[3]=passport, row[4]=objects_count, row[5]=total_sum, row[6]=landlord_name
        data_extractor = lambda row: [
            str(row[1]),      # Дата
            str(row[2]),      # Арендатор
            str(row[3]),      # Паспорт
            str(row[6] if row[6] else ""),  # Собственник (теперь перед Объектов)
            str(row[4]),      # Объектов
            row[5],           # Сумма
        ]
        self.load_query_into_model(
            query=GET_CONTRACTS,
            headers=["Дата", "Арендатор", "Паспорт", "Собственник", "Объектов", "Сумма"],
            data_extractor=data_extractor,
            id_extractor=lambda row: row[0],
            format_money_columns={5}   # Сумма – шестая колонка (индекс 5)
        )
        hdr = self.table.horizontalHeader()
        if hdr.count() > 0 and hdr.sectionSize(0) < 180:
            hdr.resizeSection(0, 180)

    # ----------------------------------------------------------------------
    # Выделение и навигация
    # ----------------------------------------------------------------------
    def get_selected_contract_ids(self):
        return self.get_selected_ids()

    def _on_contract_selected(self):
        self.current_contract_ids = self.get_selected_contract_ids()
        single = len(self.current_contract_ids) == 1
        self.copy_btn.setEnabled(single)
        self.del_btn.setEnabled(bool(self.current_contract_ids))

        if not self.current_contract_ids:
            self._detail_subtable.clear()
            return

        self._load_contract_details(self.current_contract_ids)

    def _load_contract_details(self, contract_ids):
        single = len(contract_ids) == 1
        placeholders = ', '.join(['%s'] * len(contract_ids))
        query = f"""
            SELECT c.id AS contract_id, c.date AS contract_date,
                   re.id AS real_estate_id,
                   re.address, l.name AS landlord_name,
                   r.price_per_month, r.start_date, r.months,
                   (r.price_per_month * r.months) AS total
            FROM report r
            JOIN real_estate_info re ON r.real_estate_id = re.id
            JOIN landlord_info l ON re.landlord_id = l.id
            JOIN contract c ON r.contract_id = c.id
            WHERE r.contract_id IN ({placeholders})
            ORDER BY c.date DESC, re.address
        """
        try:
            rows, _ = self.db.fetch_all(query, tuple(contract_ids))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка загрузки", parse_db_error(e))
            return

        self._detail_subtable.clear()
        if single:
            headers = ["Адрес", "Собственник", "Цена/мес", "Начало", "Срок (мес)", "Сумма"]
            col_types = self.DETAIL_SINGLE_COLUMN_TYPES
        else:
            headers = ["Договор", "Адрес", "Собственник", "Цена/мес", "Начало", "Срок (мес)", "Сумма"]
            col_types = self.DETAIL_MULTI_COLUMN_TYPES

        self._detail_subtable.set_headers(headers)
        for row in rows:
            if single:
                values = [
                    str(row[3]),
                    str(row[4]),
                    format_currency(row[5]),
                    str(row[6]),
                    str(row[7]),
                    format_currency(row[8])
                ]
            else:
                values = [
                    str(row[1]),  # дата договора
                    str(row[3]),
                    str(row[4]),
                    format_currency(row[5]),
                    str(row[6]),
                    str(row[7]),
                    format_currency(row[8])
                ]
            items = [QStandardItem(v) for v in values]
            self._detail_subtable.add_row(items, id_data=row[0], extra_data=row[2])
        self._detail_subtable.filter_bar.rebuild(col_types)
        self._detail_subtable.finalize()

    def _scroll_to_contract_in_upper_table(self, contract_id):
        for row in range(self.model.rowCount()):
            top_item = self.model.item(row, 0)
            if top_item and top_item.data(Qt.UserRole) == contract_id:
                src_idx = self.model.index(row, 0)
                proxy_idx = self.proxy.mapFromSource(src_idx)
                self.table.clearSelection()
                self.table.selectRow(proxy_idx.row())
                self.table.scrollTo(proxy_idx)
                break

    def _on_detail_double_clicked(self, index):
        if len(self.current_contract_ids) > 1:
            item = self._detail_subtable.model.item(self._detail_subtable.proxy.mapToSource(index).row(), 0)
            if item:
                contract_id = item.data(Qt.UserRole)
                if contract_id:
                    self._scroll_to_contract_in_upper_table(contract_id)
        elif len(self.current_contract_ids) == 1:
            item = self._detail_subtable.model.item(self._detail_subtable.proxy.mapToSource(index).row(), 0)
            if item:
                estate_id = item.data(Qt.UserRole + 1)
                if estate_id:
                    self.view_estate_requested.emit(estate_id)

    def _on_detail_context_menu(self, pos):
        if len(self.current_contract_ids) != 1:
            return
        index = self._detail_subtable.table.indexAt(pos)
        if not index.isValid():
            return
        item = self._detail_subtable.model.item(self._detail_subtable.proxy.mapToSource(index).row(), 0)
        if not item:
            return
        estate_id = item.data(Qt.UserRole + 1)
        if estate_id is None:
            return
        menu = QMenu(self)
        menu.addAction("Просмотреть", lambda: self.view_estate_requested.emit(estate_id))
        menu.addAction("Редактировать", lambda: self.edit_estate_requested.emit(estate_id))
        menu.exec(self._detail_subtable.table.viewport().mapToGlobal(pos))

    # ----------------------------------------------------------------------
    # CRUD договоров
    # ----------------------------------------------------------------------
    def add_contract(self, initial_data=None):
        dlg = ContractDialog(self.db, initial_data=initial_data, parent=self) if initial_data else ContractDialog(self.db, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        contract_id = data["contract_id"]
        self._record_contract_history(contract_id, data, added=True)
        self.refresh()
        self.reset_filters()
        self.select_contract_by_id(contract_id)
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_contract_by_id(contract_id)

    def _record_contract_history(self, contract_id, data, added=True):
        tenant_row = self.db.fetch_one("SELECT name FROM tenant WHERE passport = %s", (data["tenant_passport"],))
        tenant_name = tenant_row["name"] if tenant_row else "Неизвестный"
        text = f"Договор от {data['date']} | Арендатор: {tenant_name} | Объектов: {len(data['objects'])}"
        if added:
            self.history.add_event(
                event_type="contract",
                text=text,
                show_target=('contract', contract_id),
                repeat_data=('contract', data),
                undo_data={"action": "add_contract", "contract_id": contract_id}
            )

    def copy_contract(self):
        if len(self.current_contract_ids) != 1:
            QMessageBox.information(self, "Информация", "Выберите один договор для копирования.")
            return
        contract_id = self.current_contract_ids[0]
        contract = self.db.fetch_one("SELECT id, date, tenant_passport FROM contract WHERE id = %s", (contract_id,))
        if not contract:
            QMessageBox.warning(self, "Ошибка", "Договор не найден.")
            return
        objects = self.db.fetch_all(
            "SELECT real_estate_id, price_per_month, start_date, months FROM report WHERE contract_id = %s",
            (contract_id,)
        )[0] or []
        landlord_id = None
        if objects:
            estate = self.db.fetch_one("SELECT landlord_id FROM real_estate_info WHERE id = %s", (objects[0][0],))
            if estate:
                landlord_id = estate["landlord_id"]
        data = {
            "date": contract["date"],
            "tenant_passport": contract["tenant_passport"],
            "landlord_id": landlord_id,
            "objects": [{"real_estate_id": o[0], "price_per_month": o[1], "start_date": o[2], "months": o[3]} for o in objects]
        }
        self.add_contract(initial_data=data)

    def _edit_current_contract(self):
        if len(self.current_contract_ids) != 1:
            QMessageBox.information(self, "Инфо", "Выберите один договор.")
            return
        self.edit_contract_by_id(self.current_contract_ids[0])

    def edit_contract_by_id(self, contract_id):
        contract_row = self.db.fetch_one(
            "SELECT id, date, tenant_passport FROM contract WHERE id = %s", (contract_id,)
        )
        if not contract_row:
            return
        old_objects = self.db.fetch_all(
            "SELECT real_estate_id, start_date, months, price_per_month FROM report WHERE contract_id = %s",
            (contract_id,)
        )[0] or []
        old_data = {
            "id": contract_row["id"],
            "date": str(contract_row["date"]),
            "tenant_passport": contract_row["tenant_passport"],
            "objects": [{"real_estate_id": r[0], "start_date": str(r[1]), "months": r[2], "price_per_month": r[3]} for r in old_objects]
        }

        dlg = ContractDialog(self.db, contract=contract_row, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        self.history.add_event(
            event_type="contract",
            text=f"Договор изменён от {data['date']}",
            show_target=('contract', data['contract_id']),
            undo_data={"action": "edit_contract", "old": old_data}
        )
        self.refresh()
        self.reset_filters()
        self.select_contract_by_id(data['contract_id'])
        if self.refresh_callback:
            self.refresh_callback()
            self.reset_filters()
            self.select_contract_by_id(data['contract_id'])

    # ----------------------------------------------------------------------
    # Удаление договоров (общий метод с прогресс-баром и undo)
    # ----------------------------------------------------------------------
    def delete_contracts(self):
        ids = self.get_selected_contract_ids()
        if not ids:
            QMessageBox.information(self, "Внимание", "Выделите хотя бы один договор.")
            return
        self._delete_entities("contract", ids)

    def _delete_entities(self, entity_type, entity_ids):
        main_win = self.window()
        single = len(entity_ids) == 1
        undo_info = None

        if single:
            cid = entity_ids[0]
            contract = self.db.fetch_one("SELECT * FROM contract WHERE id = %s", (cid,))
            if not contract:
                return
            objects = self.db.fetch_all(
                "SELECT real_estate_id, start_date, months, price_per_month FROM report WHERE contract_id = %s", (cid,)
            )[0] or []
            undo_info = {
                "contract": {"id": cid, "date": str(contract["date"]), "tenant_passport": contract["tenant_passport"]},
                "objects": [{"real_estate_id": r[0], "start_date": str(r[1]), "months": r[2], "price_per_month": r[3]} for r in objects]
            }

        if single:
            msg = f"Удалить договор от {contract['date']}?\n\nВсе связанные записи аренды будут удалены."
        else:
            stats = self.db.fetch_one("""
                SELECT COUNT(DISTINCT c.id) AS cnt, COUNT(r.real_estate_id) AS rcnt,
                       COUNT(DISTINCT r.real_estate_id) AS objects_cnt
                FROM contract c
                LEFT JOIN report r ON r.contract_id = c.id
                WHERE c.id = ANY(%s)
            """, (entity_ids,))
            msg = (f"Удалить {stats['cnt']} договоров?\n\n"
                   f"Записей аренды: {stats['rcnt']}\n"
                   f"Уникальных объектов: {stats['objects_cnt']}\n\n"
                   f"ВНИМАНИЕ: отменить массовое удаление будет невозможно!")
        if QMessageBox.question(self, "Подтверждение удаления", msg,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        try:
            main_win.start_progress(maximum=1 if single else 2, text="Удаление...")
            with self.db.conn.cursor() as cur:
                if single:
                    cur.execute("DELETE FROM report WHERE contract_id = %s", (entity_ids[0],))
                    cur.execute("DELETE FROM contract WHERE id = %s", (entity_ids[0],))
                else:
                    cur.execute("DELETE FROM report WHERE contract_id = ANY(%s)", (entity_ids,))
                    main_win.update_progress(1)
                    cur.execute("DELETE FROM contract WHERE id = ANY(%s)", (entity_ids,))
                self.db.conn.commit()
            main_win.update_progress(1 if single else 2)

            if single and undo_info:
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

    # ----------------------------------------------------------------------
    # Вспомогательные методы
    # ----------------------------------------------------------------------
    def refresh(self):
        self.load_data()
        self._detail_subtable.clear()
        self.current_contract_ids = []
        self.copy_btn.setEnabled(False)

    def open_edit_dialog(self, contract_id):
        self.edit_contract_by_id(contract_id)

    def select_contract_by_id(self, contract_id):
        self._scroll_to_contract_in_upper_table(contract_id)
        self.current_contract_ids = [contract_id]

    @staticmethod
    def _show_error(e):
        if isinstance(e, psycopg2.Error):
            QMessageBox.critical(None, "Ошибка БД", parse_db_error(e))
        else:
            QMessageBox.critical(None, "Ошибка", str(e))