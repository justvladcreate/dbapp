# ui/pages/main_page.py
from PySide6.QtWidgets import QHeaderView, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QAction
from database.connection import Database
from database.queries import GET_RENTAL_DETAILS_WITH_IDS
from ui.pages.base_page import BasePage
from ui.utils import format_currency
from ui.widgets import DateFilterWidget


class MainPage(BasePage):
    edit_requested = Signal(str, object)
    view_requested = Signal(str, object)

    _COLUMN_TYPE_MAP = [
        "estate", "estate", "estate", "landlord", "landlord",
        "tenant", "tenant", "contract", "contract", "contract",
        "contract", "contract"
    ]
    _COLUMN_FILTER_TYPES = [
        'text', 'numeric', 'numeric', 'text', 'text',
        'text', 'text', 'date', 'date', 'numeric',
        'numeric', 'numeric'
    ]
    _MONEY_COLUMNS = {10, 11}
    DATE_COLUMNS = {7, 8}

    def __init__(self, db: Database, parent=None):
        super().__init__(db, parent)
        self.add_clear_filters_button()
        self.add_export_button()
        self.setup_table_with_filterbar(self._COLUMN_FILTER_TYPES)
        self.table.doubleClicked.connect(self._on_cell_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.load_data()

    def load_data(self):
        def extractor(row):
            # row[0]=contract_id, row[1]=tenant_passport, row[2]=landlord_id, row[3]=real_estate_id,
            # row[4:] = видимые значения
            return {
                "contract_id": row[0],
                "tenant_passport": row[1],
                "landlord_id": row[2],
                "real_estate_id": row[3]
            }

        self.load_query_into_model(
            query=GET_RENTAL_DETAILS_WITH_IDS,
            headers=None,               # берём cols[4:] благодаря id_column=3
            id_extractor=extractor,     # сохраняем словарь ID в UserRole
            id_column=3,                # пропускаем первые 4 столбца для заголовков
            format_money_columns=self._MONEY_COLUMNS
        )

        # Дополнительно подгоняем ширину столбцов с датами
        header = self.table.horizontalHeader()
        for col in self.DATE_COLUMNS:
            if col < header.count() and header.sectionSize(col) < 180:
                header.resizeSection(col, 180)

    def _get_ids_for_index(self, proxy_index):
        src_idx = self.proxy.mapToSource(proxy_index)
        if not src_idx.isValid():
            return None, None
        item = self.model.item(src_idx.row(), 0)
        if not item:
            return None, None
        ids = item.data(Qt.UserRole)
        if not ids:
            return None, None
        col = src_idx.column()
        entity_type = self._COLUMN_TYPE_MAP[col] if 0 <= col < len(self._COLUMN_TYPE_MAP) else "contract"
        return entity_type, ids

    def _on_cell_double_clicked(self, index):
        entity_type, ids = self._get_ids_for_index(index)
        if entity_type and ids:
            self.edit_requested.emit(entity_type, self._identifier_for(entity_type, ids))

    def _on_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        entity_type, ids = self._get_ids_for_index(index)
        if not entity_type or not ids:
            return
        menu = QMenu(self)
        view_action = QAction("Просмотреть", self)
        edit_action = QAction("Редактировать", self)
        view_action.triggered.connect(lambda checked=False, t=entity_type, d=ids: self._on_view(t, d))
        edit_action.triggered.connect(lambda checked=False, t=entity_type, d=ids: self._on_edit(t, d))
        menu.addAction(view_action)
        menu.addAction(edit_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_view(self, entity_type, ids):
        self.view_requested.emit(entity_type, self._identifier_for(entity_type, ids))

    def _on_edit(self, entity_type, ids):
        self.edit_requested.emit(entity_type, self._identifier_for(entity_type, ids))

    @staticmethod
    def _identifier_for(entity_type, ids):
        if entity_type == "contract":
            return ids["contract_id"]
        elif entity_type == "tenant":
            return ids["tenant_passport"]
        elif entity_type == "landlord":
            return ids["landlord_id"]
        elif entity_type == "estate":
            return ids["real_estate_id"]
        return None