# ui/main_window.py
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStatusBar, QMessageBox,
    QTableView, QAbstractItemView, QToolBar, QSplitter, QWidget, QVBoxLayout,
    QSizePolicy, QProgressBar, QStyle
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QAction, QActionGroup
import psycopg2
from database.connection import Database
from database.error_handler import parse_db_error
from ui.pages.main_page import MainPage
from ui.pages.contracts_page import ContractsPage
from ui.pages.landlords_page import LandlordsPage
from ui.pages.tenants_page import TenantsPage
from ui.pages.real_estate_page import RealEstatePage
from ui.history_sidebar import HistorySidebar
from ui.history_manager import HistoryManager
import sys
import os
from PySide6.QtGui import QIcon

import ctypes
from config import STYLE_SHEET

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.db = Database()
        except ConnectionError as e:
            QMessageBox.critical(self, "Ошибка подключения", str(e))
            sys.exit(1)
        if not self.db.is_connected:
            QMessageBox.critical(self, "Ошибка", "Нет подключения к базе данных.")
            sys.exit(1)

        self.setWindowTitle("Учёт аренды недвижимости")
        self.resize(1400, 800)

        self.history_manager = HistoryManager()

        # Прогресс-бар в строке состояния
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumWidth(200)
        self.statusBar().addPermanentWidget(self.progress_bar)

        # Основной контейнер
        self.central_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.central_splitter)

        self.tabs = QTabWidget()
        # Скрываем стандартные вкладки – навигация теперь в тулбаре
        self.tabs.tabBar().hide()
        self.central_splitter.addWidget(self.tabs)

        # Сайдбар истории
        self.history_sidebar = HistorySidebar()
        self.history_sidebar.setMinimumWidth(470)
        self.central_splitter.addWidget(self.history_sidebar)

        self.history_sidebar.hide()
        self.central_splitter.setSizes([1200, 600])

        self.central_splitter.splitterMoved.connect(self._clamp_sidebar)

        self.history_sidebar.show_requested.connect(self._handle_show_target)
        self.history_sidebar.repeat_requested.connect(self._handle_repeat)
        self.history_sidebar.undo_requested.connect(self._handle_undo)

        refresh_callback = self.refresh_all
        self.main_page = MainPage(self.db)
        self.contracts_page = ContractsPage(self.db, refresh_callback)
        self.landlords_page = LandlordsPage(self.db, refresh_callback)
        self.tenants_page = TenantsPage(self.db, refresh_callback)
        self.real_estate_page = RealEstatePage(self.db, refresh_callback)

        self.main_page.edit_requested.connect(self.handle_edit_request)
        self.main_page.view_requested.connect(self.handle_view_request)
        self.contracts_page.view_estate_requested.connect(lambda eid: self.handle_view_request("estate", eid))
        self.contracts_page.edit_estate_requested.connect(lambda eid: self.handle_edit_request("estate", eid))
        self.landlords_page.view_estate_requested.connect(lambda eid: self.handle_view_request("estate", eid))
        self.landlords_page.edit_estate_requested.connect(lambda eid: self.handle_edit_request("estate", eid))
        self.landlords_page.view_contract_requested.connect(lambda cid: self.handle_view_request("contract", cid))
        self.landlords_page.edit_contract_requested.connect(lambda cid: self.handle_edit_request("contract", cid))
        self.tenants_page.view_contract_requested.connect(lambda cid: self.handle_view_request("contract", cid))
        self.tenants_page.edit_contract_requested.connect(lambda cid: self.handle_edit_request("contract", cid))
        self.real_estate_page.view_contract_requested.connect(lambda cid: self.handle_view_request("contract", cid))
        self.real_estate_page.edit_contract_requested.connect(lambda cid: self.handle_edit_request("contract", cid))

        # Добавляем страницы, но вкладки не видны
        self.tabs.addTab(self.main_page, "Главная")
        self.tabs.addTab(self.contracts_page, "Договоры")
        self.tabs.addTab(self.landlords_page, "Собственники")
        self.tabs.addTab(self.tenants_page, "Арендаторы")
        self.tabs.addTab(self.real_estate_page, "Объекты недвижимости")

        # Настройка тулбара
        toolbar = QToolBar("Навигация")
        self.addToolBar(toolbar)

        # Группа действий для навигации (работает как меню)
        self.nav_group = QActionGroup(self)
        self.nav_group.setExclusive(True)

        pages = [
            ("Главная", 0),
            ("Договоры", 1),
            ("Собственники", 2),
            ("Арендаторы", 3),
            ("Объекты недвижимости", 4),
        ]

        for name, index in pages:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setData(index)               # сохраним индекс вкладки
            action.toggled.connect(lambda checked, idx=index: self._on_nav_toggled(checked, idx))
            self.nav_group.addAction(action)
            toolbar.addAction(action)
        for action in self.nav_group.actions():
            btn = toolbar.widgetForAction(action)
            if btn is not None:
                btn.setObjectName("NavButton")


        self.nav_actions = self.nav_group.actions()

        # Устанавливаем начальную активную кнопку (Главная)
        self.nav_group.actions()[0].setChecked(True)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Вертикальный разделитель перед служебными кнопками
        toolbar.addSeparator()

        # Новый код:
        self.about_action = QAction(self)
        # Берём стандартную иконку "Информация" из темы Windows
        self.about_action.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.about_action.setToolTip("О программе")
        self.about_action.triggered.connect(self._about)
        toolbar.addAction(self.about_action)

        self.history_action = QAction("📋 История", self)
        self.history_action.setCheckable(True)
        self.history_action.toggled.connect(self._toggle_history_sidebar)
        toolbar.addAction(self.history_action)

        # Задаём кнопкам служебных действий объектное имя для стилизации
        for action in (self.about_action, self.history_action):
            btn = toolbar.widgetForAction(action)
            if btn is not None:
                btn.setObjectName("ToolButton")

        self.statusBar().showMessage("Готово")
        self.installEventFilter(self)
        self.refresh_all()

    def _on_nav_toggled(self, checked, index):
        """Переключение вкладки по нажатию кнопки навигации."""
        if checked:
            self.tabs.setCurrentIndex(index)

    def _sync_nav_buttons(self, index):
        """Выделить нужную кнопку в тулбаре при программном переключении вкладок."""
        if 0 <= index < len(self.nav_actions):
            self.nav_actions[index].setChecked(True)

    def start_progress(self, maximum=0, text="Выполнение..."):
        self.progress_bar.setVisible(True)
        if maximum > 0:
            self.progress_bar.setMaximum(maximum)
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.setMaximum(0)
        self.statusBar().showMessage(text)
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def update_progress(self, value, max_value=None):
        if max_value is not None:
            self.progress_bar.setMaximum(max_value)
        self.progress_bar.setValue(value)

    def stop_progress(self, message="Готово"):
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(message)
        QApplication.restoreOverrideCursor()

    def refresh_all(self):
        try:
            self.statusBar().showMessage("Обновление данных...")
            self.main_page.load_data()
            self.contracts_page.refresh()
            self.landlords_page.refresh()
            self.tenants_page.refresh()
            self.real_estate_page.refresh()
            self.statusBar().showMessage("Готово")
        except Exception as e:
            if isinstance(e, psycopg2.Error):
                QMessageBox.critical(self, "Ошибка загрузки", parse_db_error(e))
            else:
                QMessageBox.critical(self, "Ошибка загрузки", str(e))

    def _clamp_sidebar(self):
        if not self.history_sidebar.isVisible():
            return
        min_w = self.history_sidebar.minimumWidth()
        sizes = self.central_splitter.sizes()
        if len(sizes) == 2 and sizes[1] < min_w:
            total = sizes[0] + sizes[1]
            sizes[1] = min_w
            sizes[0] = total - min_w
            self.central_splitter.setSizes(sizes)

    def _toggle_history_sidebar(self, checked):
        self.history_sidebar.setVisible(checked)
        if checked:
            self._clamp_sidebar()

    def _handle_show_target(self, entity_type, identifier):
        self.handle_view_request(entity_type, identifier)

    def _handle_repeat(self, data):
        if not data:
            return
        action_type = data[0]
        if action_type == 'contract':
            self.tabs.setCurrentWidget(self.contracts_page)
            self._sync_nav_buttons(1)
            contract_data = data[1] if len(data) > 1 else None
            self.contracts_page.add_contract(initial_data=contract_data)
        elif action_type == 'tenant':
            self.tabs.setCurrentWidget(self.tenants_page)
            self._sync_nav_buttons(3)
            tenant_data = data[1] if len(data) > 1 else None
            self.tenants_page.add_tenant(initial_data=tenant_data)
        elif action_type == 'landlord':
            self.tabs.setCurrentWidget(self.landlords_page)
            self._sync_nav_buttons(2)
            landlord_data = data[1] if len(data) > 1 else None
            self.landlords_page.add_landlord(initial_data=landlord_data)
        elif action_type == 'estate':
            self.tabs.setCurrentWidget(self.real_estate_page)
            self._sync_nav_buttons(4)
            estate_data = data[1] if len(data) > 1 else None
            self.real_estate_page.add_estate(initial_data=estate_data)

    def _handle_undo(self, undo_data):
        if not undo_data:
            return
        try:
            action = undo_data.get("action")

            # ---------- вспомогательные функции ----------
            def safe_list(lst):
                """Возвращает список, содержащий только элементы-словари (без None)."""
                if not lst:
                    return []
                return [item for item in lst if isinstance(item, dict)]

            def safe_dict(d):
                """Возвращает сам словарь, если он действительно dict, иначе None."""
                return d if isinstance(d, dict) else None

            # ---------- удаление договора ----------
            if action == "delete_contract":
                contract = safe_dict(undo_data.get("contract"))
                objects = safe_list(undo_data.get("objects"))
                if not contract or not contract.get("id"):
                    raise ValueError("Недостаточно данных для восстановления договора")
                with self.db.conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO contract (id, date, tenant_passport) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s)",
                        (contract.get("id"), contract.get("date"), contract.get("tenant_passport"))
                    )
                    for obj in objects:
                        cur.execute("INSERT INTO report (real_estate_id, contract_id, start_date, months, price_per_month) VALUES (%s,%s,%s,%s,%s)",
                                    (obj.get("real_estate_id"), contract.get("id"),
                                     obj.get("start_date"), obj.get("months"), obj.get("price_per_month")))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- удаление арендатора ----------
            elif action == "delete_tenant":
                tenant = safe_dict(undo_data.get("tenant"))
                contracts = safe_list(undo_data.get("contracts"))
                if not tenant or not tenant.get("passport"):
                    raise ValueError("Недостаточно данных для восстановления арендатора")
                with self.db.conn.cursor() as cur:
                    cur.execute("INSERT INTO tenant (passport, name) VALUES (%s, %s)",
                                (tenant.get("passport"), tenant.get("name")))
                    for c in contracts:
                        cur.execute(
                            "INSERT INTO contract (id, date, tenant_passport) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s)",
                            (c.get("id"), c.get("date"), tenant.get("passport"))
                        )
                        for obj in safe_list(c.get("objects")):
                            cur.execute("INSERT INTO report (real_estate_id, contract_id, start_date, months, price_per_month) VALUES (%s,%s,%s,%s,%s)",
                                        (obj.get("real_estate_id"), c.get("id"),
                                         obj.get("start_date"), obj.get("months"), obj.get("price_per_month")))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- удаление собственника ----------
            elif action == "delete_landlord":
                landlord = safe_dict(undo_data.get("landlord"))
                estates = safe_list(undo_data.get("estates"))
                contracts = safe_list(undo_data.get("contracts"))
                if not landlord or not landlord.get("id"):
                    raise ValueError("Недостаточно данных для восстановления собственника")
                with self.db.conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO landlord_info (id, name, contact_info) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s)",
                        (landlord.get("id"), landlord.get("name"), landlord.get("contact_info"))
                    )
                    for e in estates:
                        cur.execute(
                            "INSERT INTO real_estate_info (id, address, overall_space, living_space, floor, date_of_construction, elevator, rooms_amount, landlord_id) OVERRIDING SYSTEM VALUE VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (e.get("id"), e.get("address"), e.get("overall_space"), e.get("living_space"),
                             e.get("floor"), e.get("date_of_construction"), e.get("elevator"),
                             e.get("rooms_amount"), landlord.get("id"))
                        )
                    for c in contracts:
                        cur.execute(
                            "INSERT INTO contract (id, date, tenant_passport) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s)",
                            (c.get("id"), c.get("date"), c.get("tenant_passport"))
                        )
                        for obj in safe_list(c.get("objects")):
                            cur.execute("INSERT INTO report (real_estate_id, contract_id, start_date, months, price_per_month) VALUES (%s,%s,%s,%s,%s)",
                                        (obj.get("real_estate_id"), c.get("id"),
                                         obj.get("start_date"), obj.get("months"), obj.get("price_per_month")))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- удаление объекта ----------
            elif action == "delete_estate":
                estate = safe_dict(undo_data.get("estate"))
                reports = safe_list(undo_data.get("reports"))
                contracts = safe_list(undo_data.get("contracts"))
                if not estate or not estate.get("id"):
                    raise ValueError("Недостаточно данных для восстановления объекта")
                with self.db.conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO real_estate_info (id, address, overall_space, living_space, floor, date_of_construction, elevator, rooms_amount, landlord_id) OVERRIDING SYSTEM VALUE VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (estate.get("id"), estate.get("address"), estate.get("overall_space"),
                         estate.get("living_space"), estate.get("floor"), estate.get("date_of_construction"),
                         estate.get("elevator"), estate.get("rooms_amount"), estate.get("landlord_id"))
                    )
                    for rep in reports:
                        cur.execute("INSERT INTO report (real_estate_id, contract_id, start_date, months, price_per_month) VALUES (%s,%s,%s,%s,%s)",
                                    (estate.get("id"), rep.get("contract_id"),
                                     rep.get("start_date"), rep.get("months"), rep.get("price_per_month")))
                    for c in contracts:
                        cur.execute(
                            "INSERT INTO contract (id, date, tenant_passport) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                            (c.get("id"), c.get("date"), c.get("tenant_passport"))
                        )
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- редактирование договора ----------
            elif action == "edit_contract":
                old = safe_dict(undo_data.get("old"))
                if not old or not old.get("id"):
                    raise ValueError("Недостаточно данных для отмены изменений договора")
                cid = old.get("id")
                with self.db.conn.cursor() as cur:
                    cur.execute("UPDATE contract SET date=%s, tenant_passport=%s WHERE id=%s",
                                (old.get("date"), old.get("tenant_passport"), cid))
                    cur.execute("DELETE FROM report WHERE contract_id=%s", (cid,))
                    for obj in safe_list(old.get("objects")):
                        cur.execute("INSERT INTO report (real_estate_id, contract_id, start_date, months, price_per_month) VALUES (%s,%s,%s,%s,%s)",
                                    (obj.get("real_estate_id"), cid,
                                     obj.get("start_date"), obj.get("months"), obj.get("price_per_month")))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- редактирование объекта ----------
            elif action == "edit_estate":
                old = safe_dict(undo_data.get("old"))
                if not old or not old.get("id"):
                    raise ValueError("Недостаточно данных для отмены изменений объекта")
                eid = old.get("id")
                with self.db.conn.cursor() as cur:
                    cur.execute("UPDATE real_estate_info SET address=%s, overall_space=%s, living_space=%s, floor=%s, date_of_construction=%s, elevator=%s, rooms_amount=%s, landlord_id=%s WHERE id=%s",
                                (old.get("address"), old.get("overall_space"), old.get("living_space"),
                                 old.get("floor"), old.get("date_of_construction"), old.get("elevator"),
                                 old.get("rooms_amount"), old.get("landlord_id"), eid))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- редактирование арендатора ----------
            elif action == "edit_tenant":
                old = safe_dict(undo_data.get("old"))
                if not old or not old.get("passport"):
                    raise ValueError("Недостаточно данных для отмены изменений арендатора")
                with self.db.conn.cursor() as cur:
                    cur.execute("UPDATE tenant SET name=%s WHERE passport=%s",
                                (old.get("name"), old.get("passport")))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- редактирование собственника ----------
            elif action == "edit_landlord":
                old = safe_dict(undo_data.get("old"))
                if not old or not old.get("id"):
                    raise ValueError("Недостаточно данных для отмены изменений собственника")
                with self.db.conn.cursor() as cur:
                    cur.execute("UPDATE landlord_info SET name=%s, contact_info=%s WHERE id=%s",
                                (old.get("name"), old.get("contact_info"), old.get("id")))
                    self.db.conn.commit()
                self.refresh_all()

            # ---------- добавление ----------
            elif action == "add_contract":
                cid = undo_data.get("contract_id")
                if not cid:
                    raise ValueError("Недостаточно данных для отмены добавления договора")
                with self.db.conn.cursor() as cur:
                    cur.execute("DELETE FROM report WHERE contract_id=%s", (cid,))
                    cur.execute("DELETE FROM contract WHERE id=%s", (cid,))
                    self.db.conn.commit()
                self.refresh_all()

            elif action == "add_tenant":
                passport = undo_data.get("passport")
                if not passport:
                    raise ValueError("Недостаточно данных для отмены добавления арендатора")
                with self.db.conn.cursor() as cur:
                    cur.execute("DELETE FROM tenant WHERE passport=%s", (passport,))
                    self.db.conn.commit()
                self.refresh_all()

            elif action == "add_landlord":
                lid = undo_data.get("landlord_id")
                if not lid:
                    raise ValueError("Недостаточно данных для отмены добавления собственника")
                with self.db.conn.cursor() as cur:
                    cur.execute("DELETE FROM landlord_info WHERE id=%s", (lid,))
                    self.db.conn.commit()
                self.refresh_all()

            elif action == "add_estate":
                eid = undo_data.get("estate_id")
                if not eid:
                    raise ValueError("Недостаточно данных для отмены добавления объекта")
                with self.db.conn.cursor() as cur:
                    cur.execute("DELETE FROM real_estate_info WHERE id=%s", (eid,))
                    self.db.conn.commit()
                self.refresh_all()

            else:
                QMessageBox.information(self, "Отмена", "Невозможно отменить это действие.")

        except ValueError as ve:
            QMessageBox.warning(self, "Ошибка отмены", str(ve))
        except Exception as e:
            self.db.conn.rollback()
            if isinstance(e, psycopg2.Error):
                QMessageBox.critical(self, "Ошибка отмены", parse_db_error(e))
            else:
                QMessageBox.critical(self, "Ошибка отмены", str(e))

    def handle_edit_request(self, item_type, identifier):
        if item_type == "contract":
            self.tabs.setCurrentWidget(self.contracts_page)
            self._sync_nav_buttons(1)
            self.contracts_page.open_edit_dialog(identifier)
        elif item_type == "tenant":
            self.tabs.setCurrentWidget(self.tenants_page)
            self._sync_nav_buttons(3)
            self.tenants_page.open_edit_dialog(identifier)
        elif item_type == "landlord":
            self.tabs.setCurrentWidget(self.landlords_page)
            self._sync_nav_buttons(2)
            self.landlords_page.open_edit_dialog(identifier)
        elif item_type == "estate":
            self.tabs.setCurrentWidget(self.real_estate_page)
            self._sync_nav_buttons(4)
            self.real_estate_page.open_edit_dialog(identifier)

    def handle_view_request(self, item_type, identifier):
        if item_type == "contract":
            self.tabs.setCurrentWidget(self.contracts_page)
            self._sync_nav_buttons(1)
            self.contracts_page.select_contract_by_id(identifier)
        elif item_type == "tenant":
            self.tabs.setCurrentWidget(self.tenants_page)
            self._sync_nav_buttons(3)
            self.tenants_page.select_tenant_by_passport(identifier)
        elif item_type == "landlord":
            self.tabs.setCurrentWidget(self.landlords_page)
            self._sync_nav_buttons(2)
            self.landlords_page.select_landlord_by_id(identifier)
        elif item_type == "estate":
            self.tabs.setCurrentWidget(self.real_estate_page)
            self._sync_nav_buttons(4)
            self.real_estate_page.select_estate_by_id(identifier)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Delete:
                self._handle_delete_key()
                return True
            elif key == Qt.Key_Insert:
                self._handle_insert_key()
                return True
            elif key == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                self._handle_copy_key()
                return True
        return super().eventFilter(obj, event)

    def _handle_copy_key(self):
        widget = self._focused_table_widget()
        if widget is None:
            return
        page = self._page_for_table(widget)
        if page is None:
            return
        if isinstance(page, ContractsPage):
            page.copy_contract()
        elif isinstance(page, TenantsPage):
            page.copy_tenant()
        elif isinstance(page, LandlordsPage):
            page.copy_landlord()
        elif isinstance(page, RealEstatePage):
            page.copy_estate()

    def _handle_delete_key(self):
        widget = self._focused_table_widget()
        if widget is None:
            return
        page = self._page_for_table(widget)
        if page is None:
            return
        if isinstance(page, ContractsPage):
            page.delete_contracts()
        elif isinstance(page, LandlordsPage):
            page.delete_landlords()
        elif isinstance(page, TenantsPage):
            page.delete_tenants()
        elif isinstance(page, RealEstatePage):
            page.delete_estates()

    def _handle_insert_key(self):
        widget = self._focused_table_widget()
        if widget is None:
            return
        page = self._page_for_table(widget)
        if page is None:
            return
        if isinstance(page, ContractsPage):
            page.add_contract()
        elif isinstance(page, LandlordsPage):
            page.add_landlord()
        elif isinstance(page, TenantsPage):
            page.add_tenant()
        elif isinstance(page, RealEstatePage):
            page.add_estate()

    def _focused_table_widget(self):
        focus_widget = self.focusWidget()
        while focus_widget is not None:
            if isinstance(focus_widget, QTableView):
                return focus_widget
            focus_widget = focus_widget.parentWidget()
        return None

    def _page_for_table(self, table):
        parent = table.parentWidget()
        while parent is not None:
            if isinstance(parent, (MainPage, ContractsPage, LandlordsPage, TenantsPage, RealEstatePage)):
                return parent
            parent = parent.parentWidget()
        return None

    def _about(self):
        QMessageBox.about(self, "О программе",
                          "Учёт аренды недвижимости\n"
                          "Версия 1.0\n\n"
                          "Разработчик: Старцев Владислав Игоревич\n"
                          "Для внутреннего использования."
                          )

    def closeEvent(self, event):
        self.db.close()
        event.accept()



def launch_app():
    app = QApplication(sys.argv)

    app.setApplicationName("DBApp")        # или "Учёт аренды"
    app.setOrganizationName("Jvcreate")     # любое название вашей компании

    # Определяем базовый путь: в onefile-режиме sys._MEIPASS указывает на временную папку
    if hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS   # Nuitka onefile
    else:
        base_dir = os.path.dirname(__file__)  # Обычный запуск

    icon_path = os.path.join(base_dir, "app_icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    app.setStyleSheet(STYLE_SHEET)
    # применяем встроенный стиль


    window = MainWindow()
    window.showMaximized()
    # window.show()
    sys.exit(app.exec())