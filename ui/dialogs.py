# ui/dialogs.py
import sys
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox,
    QDateEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QCheckBox,
    QMessageBox, QLabel, QHeaderView, QSpinBox,
    QSplitter, QTableView, QWidget,
    QAbstractItemView, QCompleter, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import QDate, Qt, QRegularExpression, QSortFilterProxyModel, QStringListModel, Signal, QModelIndex
from PySide6.QtGui import QRegularExpressionValidator, QStandardItemModel, QStandardItem
import psycopg2
from database.connection import Database
from database.queries import (
    GET_OBJECTS_BY_LANDLORD,
    INSERT_TENANT, INSERT_LANDLORD, INSERT_REAL_ESTATE,
    INSERT_CONTRACT, INSERT_REPORT_ITEM,
    UPDATE_CONTRACT, UPDATE_REPORT_ITEM,
    DELETE_REPORT_ITEM, UPDATE_TENANT, UPDATE_REAL_ESTATE, UPDATE_LANDLORD
)
from database.error_handler import parse_db_error
from ui.widgets import MultiFilterProxy, DateFilterWidget, NumericFilterWidget, FilterLineEdit
from ui.history_manager import HistoryManager

class SearchableComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self._all_items = []
        self.lineEdit().textEdited.connect(self._on_text_edited)
        self._updating = False

    def add_search_item(self, text, data):
        self._all_items.append((text, data))
        self.addItem(text, data)

    def clear_search_items(self):
        self._all_items.clear()
        self.clear()

    def _on_text_edited(self, text):
        if self._updating:
            return
        self._filter_and_show(text)

    def _filter_and_show(self, text):
        self._updating = True
        self.clear()
        lower = text.lower()
        for item_text, item_data in self._all_items:
            if lower in item_text.lower():
                self.addItem(item_text, item_data)
        self.setCurrentText(text)
        self.lineEdit().selectAll()
        self.showPopup()
        self._updating = False

    def showPopup(self):
        self._filter_and_show(self.lineEdit().text())
        super().showPopup()

    def set_current_by_data(self, data):
        for i in range(self.count()):
            if self.itemData(i) == data:
                self.setCurrentIndex(i)
                return
        for text, d in self._all_items:
            if d == data:
                self.setCurrentText(text)
                self.setCurrentIndex(self.findText(text))
                break


class LandlordDialog(QDialog):
    def __init__(self, db: Database, landlord=None, parent=None, initial_data=None):
        super().__init__(parent)
        self.db = db
        self.landlord = landlord
        self._initial_data = initial_data
        self._initial_name = landlord["name"] if landlord else (initial_data.get("name") if initial_data else "")
        self._initial_contact = landlord["contact_info"] if landlord else (initial_data.get("contact_info") if initial_data else "")
        self.setWindowTitle("Собственник")
        self.setup_ui()
        if landlord:
            self.name_edit.setText(landlord["name"])
            self.contact_edit.setText(landlord["contact_info"])
        elif initial_data:
            self.name_edit.setText(initial_data.get("name", ""))
            self.contact_edit.setText(initial_data.get("contact_info", ""))

    def setup_ui(self):
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Имя собственника")
        self.name_edit.setToolTip("Введите полное имя собственника. Поле обязательно для заполнения.")
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("Телефон или email")
        self.contact_edit.setToolTip("Контактная информация собственника (необязательно).")
        layout.addRow("Имя:", self.name_edit)
        layout.addRow("Контакты:", self.contact_edit)
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        save_btn.setToolTip("Сохранить данные (Ctrl+S)")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setToolTip("Отменить изменения (Esc)")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addRow(btn_box)

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Имя собственника не может быть пустым.")
            self.name_edit.setFocus()
            return
        try:
            self._save_to_db()
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка сохранения", parse_db_error(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        else:
            self.accept()

    def _save_to_db(self):
        data = self.get_data()
        try:
            if self.landlord is None:
                result = self.db.execute_returning(INSERT_LANDLORD, (data["name"], data["contact_info"]))
                if result:
                    data["id"] = result["id"]
            else:
                self.db.execute(UPDATE_LANDLORD, (data["name"], data["contact_info"], self.landlord["id"]))
                data["id"] = self.landlord["id"]
            self.saved_data = data
        except psycopg2.Error:
            if self.db.conn:
                self.db.conn.rollback()
            raise
        except Exception:
            if self.db.conn:
                self.db.conn.rollback()
            raise

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_save()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_S:
            self._on_save()
        else:
            super().keyPressEvent(event)

    def get_data(self):
        name = ' '.join(self.name_edit.text().strip().split())
        contact = ' '.join(self.contact_edit.text().strip().split())
        return {"name": name, "contact_info": contact}

    def is_modified(self):
        if self.landlord is None and self._initial_data is None:
            return bool(self.name_edit.text().strip() or self.contact_edit.text().strip())
        return (self.name_edit.text().strip() != self._initial_name or
                self.contact_edit.text().strip() != self._initial_contact)

    def reject(self):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение", "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        super().reject()

    def closeEvent(self, event):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение", "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
        event.accept()


class TenantDialog(QDialog):
    def __init__(self, db: Database, tenant=None, parent=None, initial_data=None):
        super().__init__(parent)
        self.db = db
        self.tenant = tenant
        self._initial_data = initial_data
        self._initial_passport = tenant["passport"] if tenant else (initial_data.get("passport") if initial_data else "")
        self._initial_name = tenant["name"] if tenant else (initial_data.get("name") if initial_data else "")
        self.setWindowTitle("Арендатор")
        self.setup_ui()
        if tenant:
            self.passport_edit.setText(tenant["passport"])
            self.passport_edit.setReadOnly(True)
            self.name_edit.setText(tenant["name"])
        elif initial_data:
            self.passport_edit.setText(initial_data.get("passport", ""))
            self.name_edit.setText(initial_data.get("name", ""))

    def setup_ui(self):
        layout = QFormLayout(self)
        self.passport_edit = QLineEdit()
        self.passport_edit.setMaxLength(10)
        self.passport_edit.setPlaceholderText("10 цифр")
        self.passport_edit.setToolTip("Серия и номер паспорта (ровно 10 цифр). Обязательное поле.")
        passport_validator = QRegularExpressionValidator(QRegularExpression("\\d{10}"))
        self.passport_edit.setValidator(passport_validator)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Фамилия Имя Отчество")
        self.name_edit.setToolTip("Полное ФИО арендатора. Обязательное поле.")
        layout.addRow("Паспорт (10 цифр):", self.passport_edit)
        layout.addRow("ФИО:", self.name_edit)
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        save_btn.setToolTip("Сохранить данные (Ctrl+S)")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setToolTip("Отменить изменения (Esc)")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addRow(btn_box)

    def _on_save(self):
        passport = self.passport_edit.text().strip()
        name = self.name_edit.text().strip()
        if len(passport) != 10 or not passport.isdigit():
            QMessageBox.warning(self, "Ошибка", "Паспорт должен содержать ровно 10 цифр.")
            self.passport_edit.setFocus()
            return
        if not name:
            QMessageBox.warning(self, "Ошибка", "ФИО арендатора не может быть пустым.")
            self.name_edit.setFocus()
            return
        try:
            existing = self.db.fetch_one("SELECT * FROM tenant WHERE passport = %s", (passport,))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        if existing:
            if self.tenant is None and self._initial_data is None:
                reply = QMessageBox.question(self, "Паспорт существует",
                                             f"Арендатор с паспортом {passport} уже существует:\n{existing['name']}\n\nЗагрузить его данные для редактирования?",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self._load_existing(existing)
                return
            else:
                if passport != self._initial_passport:
                    QMessageBox.warning(self, "Ошибка", f"Арендатор с паспортом {passport} уже существует.")
                    return
        try:
            self._save_to_db()
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка сохранения", parse_db_error(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        else:
            self.accept()

    def _save_to_db(self):
        data = self.get_data()
        try:
            if self.tenant is None:
                self.db.execute(INSERT_TENANT, (data["passport"], data["name"]))
            else:
                self.db.execute(UPDATE_TENANT, (data["name"], data["passport"], self.tenant["passport"]))
            self.saved_data = data
        except psycopg2.Error:
            if self.db.conn:
                self.db.conn.rollback()
            raise
        except Exception:
            if self.db.conn:
                self.db.conn.rollback()
            raise

    def _load_existing(self, tenant_dict):
        self.tenant = tenant_dict
        self._initial_passport = tenant_dict["passport"]
        self._initial_name = tenant_dict["name"]
        self.setWindowTitle("Редактирование арендатора")
        self.passport_edit.setText(tenant_dict["passport"])
        self.passport_edit.setReadOnly(True)
        self.name_edit.setText(tenant_dict["name"])
        self.name_edit.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_save()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_S:
            self._on_save()
        else:
            super().keyPressEvent(event)

    def get_data(self):
        passport = self.passport_edit.text().strip()
        name = ' '.join(self.name_edit.text().strip().split())
        return {"passport": passport, "name": name}

    def is_modified(self):
        if self.tenant is None and self._initial_data is None:
            return bool(self.passport_edit.text().strip() or self.name_edit.text().strip())
        return (self.passport_edit.text().strip() != self._initial_passport or
                self.name_edit.text().strip() != self._initial_name)

    def reject(self):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение", "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        super().reject()

    def closeEvent(self, event):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение", "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
        event.accept()


class RealEstateDialog(QDialog):
    def __init__(self, db: Database, estate=None, landlord_id=None, parent=None, initial_data=None):
        super().__init__(parent)
        self.db = db
        self.estate = estate
        self.landlord_id = landlord_id
        self._initial_data = initial_data
        self._initial_values = {}
        if estate:
            self._initial_values = {
                "address": estate["address"],
                "overall_space": estate["overall_space"],
                "living_space": estate["living_space"],
                "floor": estate["floor"],
                "date_of_construction": estate["date_of_construction"],
                "elevator": estate["elevator"],
                "rooms_amount": estate["rooms_amount"],
                "landlord_id": estate["landlord_id"]
            }
        elif initial_data:
            self._initial_values = initial_data
        self.setWindowTitle("Объект недвижимости")
        self.setup_ui()
        self.load_landlords()
        if estate:
            self.address_edit.setText(estate["address"])
            self.overall_spin.setValue(int(estate["overall_space"]))
            self.living_spin.setValue(int(estate["living_space"]))
            self.floor_spin.setValue(int(estate["floor"]))
            self.date_edit.setDate(QDate.fromString(str(estate["date_of_construction"]), "yyyy-MM-dd"))
            self.elevator_check.setChecked(estate["elevator"])
            self.rooms_spin.setValue(int(estate["rooms_amount"]))
            idx = self.landlord_combo.findData(estate["landlord_id"])
            if idx >= 0:
                self.landlord_combo.setCurrentIndex(idx)
        elif initial_data:
            self.address_edit.setText(initial_data.get("address", ""))
            self.overall_spin.setValue(int(initial_data.get("overall_space", 1)))
            self.living_spin.setValue(int(initial_data.get("living_space", 1)))
            self.floor_spin.setValue(int(initial_data.get("floor", 1)))
            date_val = initial_data.get("date_of_construction")
            if date_val:
                if isinstance(date_val, str):
                    self.date_edit.setDate(QDate.fromString(date_val, "yyyy-MM-dd"))
                else:
                    self.date_edit.setDate(QDate.fromString(str(date_val), "yyyy-MM-dd"))
            self.elevator_check.setChecked(initial_data.get("elevator", False))
            self.rooms_spin.setValue(int(initial_data.get("rooms_amount", 1)))
            lid = initial_data.get("landlord_id")
            if lid:
                idx = self.landlord_combo.findData(lid)
                if idx >= 0:
                    self.landlord_combo.setCurrentIndex(idx)
        elif landlord_id is not None:
            idx = self.landlord_combo.findData(landlord_id)
            if idx >= 0:
                self.landlord_combo.setCurrentIndex(idx)

    def setup_ui(self):
        layout = QFormLayout(self)
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Город, улица, дом")
        self.address_edit.setToolTip("Полный адрес объекта. Обязательное поле.")
        self.overall_spin = QSpinBox(); self.overall_spin.setRange(1, 1000000); self.overall_spin.setSuffix(" м²")
        self.overall_spin.setToolTip("Общая площадь объекта в квадратных метрах (целое число).")
        self.living_spin = QSpinBox(); self.living_spin.setRange(1, 1000000); self.living_spin.setSuffix(" м²")
        self.living_spin.setToolTip("Жилая площадь объекта в квадратных метрах.")
        self.floor_spin = QSpinBox(); self.floor_spin.setRange(-10, 500)
        self.floor_spin.setToolTip("Этаж, на котором расположен объект. Может быть отрицательным (подвал).")
        self.date_edit = QDateEdit(); self.date_edit.setCalendarPopup(True); self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setToolTip("Год постройки объекта (можно выбрать из календаря).")
        self.elevator_check = QCheckBox("Есть лифт")
        self.elevator_check.setToolTip("Отметьте, если в здании есть лифт.")
        self.rooms_spin = QSpinBox(); self.rooms_spin.setRange(1, 500)
        self.rooms_spin.setToolTip("Количество комнат в объекте.")
        self.landlord_combo = QComboBox()
        self.landlord_combo.setToolTip("Выберите собственника из списка. Обязательное поле.")
        layout.addRow("Адрес:", self.address_edit)
        layout.addRow("Общая площадь:", self.overall_spin)
        layout.addRow("Жилая площадь:", self.living_spin)
        layout.addRow("Этаж:", self.floor_spin)
        layout.addRow("Год постройки:", self.date_edit)
        layout.addRow("", self.elevator_check)
        layout.addRow("Количество комнат:", self.rooms_spin)
        layout.addRow("Собственник:", self.landlord_combo)
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Сохранить"); save_btn.setToolTip("Сохранить данные (Ctrl+S)"); save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Отмена"); cancel_btn.setToolTip("Отменить изменения (Esc)"); cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(save_btn); btn_box.addWidget(cancel_btn)
        layout.addRow(btn_box)

    def load_landlords(self):
        try:
            rows, _ = self.db.fetch_all("SELECT id, name FROM landlord_info ORDER BY name")
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        for row in rows:
            self.landlord_combo.addItem(row[1], row[0])

    def _on_save(self):
        if not self.address_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Адрес объекта не может быть пустым.")
            self.address_edit.setFocus()
            return
        if self.landlord_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Ошибка", "Не выбран собственник объекта.")
            return
        try:
            self._save_to_db()
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка сохранения", parse_db_error(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        else:
            self.accept()

    def _save_to_db(self):
        data = self.get_data()
        try:
            if self.estate is None:
                result = self.db.execute_returning(INSERT_REAL_ESTATE, (
                    data["address"], data["overall_space"], data["living_space"],
                    data["floor"], data["date_of_construction"], data["elevator"],
                    data["rooms_amount"], data["landlord_id"]
                ))
                if result:
                    data["id"] = result["id"]
            else:
                self.db.execute(UPDATE_REAL_ESTATE, (
                    data["address"], data["overall_space"], data["living_space"],
                    data["floor"], data["date_of_construction"], data["elevator"],
                    data["rooms_amount"], data["landlord_id"], self.estate["id"]
                ))
                data["id"] = self.estate["id"]
            self.saved_data = data
        except psycopg2.Error:
            if self.db.conn:
                self.db.conn.rollback()
            raise
        except Exception:
            if self.db.conn:
                self.db.conn.rollback()
            raise

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_save()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_S:
            self._on_save()
        else:
            super().keyPressEvent(event)

    def get_data(self):
        address = ' '.join(self.address_edit.text().strip().split())
        return {
            "address": address,
            "overall_space": self.overall_spin.value(),
            "living_space": self.living_spin.value(),
            "floor": self.floor_spin.value(),
            "date_of_construction": self.date_edit.date().toPython(),
            "elevator": self.elevator_check.isChecked(),
            "rooms_amount": self.rooms_spin.value(),
            "landlord_id": self.landlord_combo.currentData()
        }

    def is_modified(self):
        if self.estate is None and self._initial_data is None:
            return any([self.address_edit.text().strip(), self.overall_spin.value(), self.living_spin.value(),
                        self.floor_spin.value(), self.date_edit.date() != QDate.currentDate(),
                        self.elevator_check.isChecked(), self.rooms_spin.value(), self.landlord_combo.currentIndex() >= 0])
        current = self.get_data()
        return (current["address"] != self._initial_values.get("address") or
                current["overall_space"] != int(self._initial_values.get("overall_space", 0)) or
                current["living_space"] != int(self._initial_values.get("living_space", 0)) or
                current["floor"] != int(self._initial_values.get("floor", 0)) or
                current["date_of_construction"] != self._initial_values.get("date_of_construction") or
                current["elevator"] != self._initial_values.get("elevator") or
                current["rooms_amount"] != int(self._initial_values.get("rooms_amount", 0)) or
                current["landlord_id"] != self._initial_values.get("landlord_id"))

    def reject(self):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение", "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        super().reject()

    def closeEvent(self, event):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение", "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
        event.accept()


class ContractDialog(QDialog):
    NUMERIC_RIGHT_COLS = {"Общая площадь", "Жилая площадь", "Этаж", "Год постр.", "Комнат"}

    def __init__(self, db: Database, contract=None, parent=None,
                 initial_landlord_id=None, initial_tenant_passport=None, initial_estate_id=None,
                 initial_data=None):
        super().__init__(parent)
        self.db = db
        self.contract = contract
        self._initial_landlord_id = initial_landlord_id
        self._initial_tenant_passport = initial_tenant_passport
        self._initial_estate_id = initial_estate_id
        self._initial_data = initial_data
        self._modified = False
        self._initial_tenant = None
        self._initial_landlord = None
        self._initial_date = QDate.currentDate()
        self._previous_landlord_id = None
        self._changing_landlord = False
        self.history = HistoryManager()

        self.setWindowTitle("Договор аренды")
        self.resize(1000, 650)
        self.setup_ui()
        self.load_combos()

        if contract:
            self._initial_date = QDate.fromString(str(contract["date"]), "yyyy-MM-dd")
            self.date_edit.setDate(self._initial_date)
            idx = self.tenant_combo.findData(contract["tenant_passport"])
            if idx >= 0:
                self.tenant_combo.setCurrentIndex(idx)
                self._initial_tenant = contract["tenant_passport"]
            self._load_contract_objects(contract["id"])
        elif self._initial_data is not None:
            self._apply_initial_data(self._initial_data)
        else:
            # Устанавливаем сегодняшнюю дату по умолчанию
            self.date_edit.setDate(QDate.currentDate())

            if initial_landlord_id is not None:
                idx = self.landlord_combo.findData(initial_landlord_id)
                if idx >= 0:
                    self.landlord_combo.setCurrentIndex(idx)
                    self._on_landlord_changed()
                    # Автоматически добавляем единственный объект, если он есть
                    self._auto_add_single_object(initial_landlord_id)
            else:
                self.landlord_combo.setCurrentIndex(-1)

            if initial_tenant_passport is not None:
                idx = self.tenant_combo.findData(initial_tenant_passport)
                if idx >= 0:
                    self.tenant_combo.setCurrentIndex(idx)
                    self._initial_tenant = initial_tenant_passport
            else:
                self.tenant_combo.setCurrentIndex(-1)

            if initial_estate_id is not None and initial_landlord_id is not None:
                self._add_estate_to_contract(initial_estate_id)

        self.date_edit.dateChanged.connect(self._mark_modified)
        self.tenant_combo.currentIndexChanged.connect(self._mark_modified)

    def _auto_add_single_object(self, landlord_id):
        """Если у выбранного собственника ровно один объект, он сразу попадает в договор."""
        try:
            rows, _ = self.db.fetch_all(
                "SELECT id FROM real_estate_info WHERE landlord_id = %s ORDER BY address",
                (landlord_id,)
            )
        except psycopg2.Error:
            return
        if len(rows) == 1:
            self._add_estate_to_contract(rows[0][0])

    def _apply_initial_data(self, data):
        if data.get("date"):
            self.date_edit.setDate(QDate.fromString(str(data["date"]), "yyyy-MM-dd"))
        tp = data.get("tenant_passport")
        if tp:
            idx = self.tenant_combo.findData(tp)
            if idx >= 0:
                self.tenant_combo.setCurrentIndex(idx)
                self._initial_tenant = tp
        lid = data.get("landlord_id")
        if lid:
            idx = self.landlord_combo.findData(lid)
            if idx >= 0:
                self.landlord_combo.blockSignals(True)
                self.landlord_combo.setCurrentIndex(idx)
                self.landlord_combo.blockSignals(False)
                self._previous_landlord_id = lid
                self._load_available_objects(lid)
                self.add_obj_btn.setEnabled(True)
        for obj in data.get("objects", []):
            self._add_estate_to_contract(
                obj["real_estate_id"],
                price=obj.get("price_per_month", 1000),
                start_date=obj.get("start_date"),
                months=obj.get("months", 12)
            )
        self._update_objects_warning()
        self.left_table.resizeRowsToContents()

    def _add_estate_to_contract(self, estate_id, price=1000, start_date=None, months=12):
        try:
            obj_data = self.db.fetch_one(
                "SELECT address, overall_space, living_space, floor, date_of_construction, elevator, rooms_amount "
                "FROM real_estate_info WHERE id = %s", (estate_id,))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        if not obj_data:
            return
        row = self.left_table.rowCount()
        self.left_table.insertRow(row)
        addr_item = QTableWidgetItem(obj_data["address"])
        addr_item.setFlags(addr_item.flags() & ~Qt.ItemIsEditable)
        addr_item.setData(Qt.UserRole, estate_id)
        self.left_table.setItem(row, 0, addr_item)

        price_spin = QSpinBox()
        price_spin.setRange(1, 1000000000)
        price_spin.setSuffix(" ₽")
        price_spin.setValue(price)
        price_spin.valueChanged.connect(self._mark_modified)
        self.left_table.setCellWidget(row, 1, price_spin)

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        if start_date:
            date_edit.setDate(QDate.fromString(str(start_date), "yyyy-MM-dd"))
        else:
            date_edit.setDate(self.date_edit.date())
            self._configure_date_edit(date_edit)

        self.left_table.setCellWidget(row, 2, date_edit)

        months_spin = QSpinBox()
        months_spin.setRange(1, 600)
        months_spin.setValue(months)
        months_spin.valueChanged.connect(self._mark_modified)
        self.left_table.setCellWidget(row, 3, months_spin)

        for src_row in range(self.right_model.rowCount()):
            if self.right_model.item(src_row, 0).data(Qt.UserRole) == estate_id:
                self.right_model.removeRow(src_row)
                break
        self.left_table.resizeRowToContents(row)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        form = QFormLayout()
        self.date_edit = QDateEdit()
        self.date_edit.dateChanged.connect(self._on_contract_date_changed)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setToolTip("Дата заключения договора. Обязательное поле.")


        # Добавляем кнопку "Сегодня" справа от поля даты
        date_layout = QHBoxLayout()
        date_layout.addWidget(self.date_edit)
        today_btn = QPushButton("Сегодня")
        today_btn.setFixedWidth(100)
        today_btn.setToolTip("Установить сегодняшнюю дату")
        today_btn.clicked.connect(lambda: self.date_edit.setDate(QDate.currentDate()))
        date_layout.addWidget(today_btn)
        form.addRow("Дата заключения договора:", date_layout)

        tenant_layout = QVBoxLayout()
        tenant_row = QHBoxLayout()
        self.tenant_combo = QComboBox()
        self.tenant_combo.setEditable(True)
        self.tenant_combo.setInsertPolicy(QComboBox.NoInsert)
        self.tenant_model = QStringListModel()
        self.tenant_proxy = QSortFilterProxyModel()
        self.tenant_proxy.setSourceModel(self.tenant_model)
        self.tenant_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.tenant_completer = QCompleter()
        self.tenant_completer.setModel(self.tenant_proxy)
        self.tenant_completer.setCompletionColumn(0)
        self.tenant_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.tenant_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.tenant_completer.setFilterMode(Qt.MatchContains)
        self.tenant_combo.setCompleter(self.tenant_completer)

        self.tenant_completer.activated.connect(self._on_tenant_completer_activated)

        tenant_add_btn = QPushButton("+")
        tenant_add_btn.setFixedWidth(34)
        tenant_add_btn.setStyleSheet("color: #2C3E50; font-weight: bold; padding: 0px; border: 1px solid #BDC3C7; border-radius: 4px;")
        tenant_add_btn.setToolTip("Добавить нового арендатора")
        tenant_add_btn.clicked.connect(self._add_tenant)
        tenant_row.addWidget(self.tenant_combo)
        tenant_row.addWidget(tenant_add_btn)
        tenant_layout.addLayout(tenant_row)
        self.tenant_warning = QLabel("⚠️ Выберите арендатора")
        self.tenant_warning.setStyleSheet("color: red; font-size: 12px;")
        self.tenant_warning.setVisible(True)
        tenant_layout.addWidget(self.tenant_warning)
        form.addRow("Арендатор:", tenant_layout)

        landlord_layout = QVBoxLayout()
        landlord_row = QHBoxLayout()
        self.landlord_combo = QComboBox()
        self.landlord_combo.setEditable(True)
        self.landlord_combo.setInsertPolicy(QComboBox.NoInsert)
        self.landlord_model = QStringListModel()
        self.landlord_proxy = QSortFilterProxyModel()
        self.landlord_proxy.setSourceModel(self.landlord_model)
        self.landlord_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.landlord_completer = QCompleter()
        self.landlord_completer.setModel(self.landlord_proxy)
        self.landlord_completer.setCompletionColumn(0)
        self.landlord_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.landlord_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.landlord_completer.setFilterMode(Qt.MatchContains)
        self.landlord_combo.setCompleter(self.landlord_completer)
        self.landlord_completer.activated.connect(self._on_landlord_completer_activated)
        landlord_add_btn = QPushButton("+")
        landlord_add_btn.setFixedWidth(34)
        landlord_add_btn.setStyleSheet("color: #2C3E50; font-weight: bold; padding: 0px; border: 1px solid #BDC3C7; border-radius: 4px;")
        landlord_add_btn.setToolTip("Добавить нового собственника")
        landlord_add_btn.clicked.connect(self._add_landlord)
        landlord_row.addWidget(self.landlord_combo)
        landlord_row.addWidget(landlord_add_btn)
        landlord_layout.addLayout(landlord_row)
        self.landlord_warning = QLabel("⚠️ Выберите собственника")
        self.landlord_warning.setStyleSheet("color: red; font-size: 12px;")
        self.landlord_warning.setVisible(True)
        landlord_layout.addWidget(self.landlord_warning)
        form.addRow("Собственник:", landlord_layout)

        self.tenant_combo.currentIndexChanged.connect(self._update_tenant_warning)
        self.landlord_combo.currentIndexChanged.connect(self._on_landlord_changed)
        self.landlord_combo.currentIndexChanged.connect(self._update_landlord_warning)
        main_layout.addLayout(form)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        left_layout.addWidget(QLabel("Выбранные объекты"))
        left_btn_row = QHBoxLayout()
        self.remove_btn = QPushButton("Удалить")
        self.remove_btn.setToolTip("Удалить выбранные объекты из договора")
        self.remove_btn.clicked.connect(self._remove_selected_from_left)
        self.clear_btn = QPushButton("Очистить всё")
        self.clear_btn.setToolTip("Удалить все объекты из договора")
        self.clear_btn.clicked.connect(self._clear_left)
        left_btn_row.addWidget(self.remove_btn)
        left_btn_row.addWidget(self.clear_btn)
        left_btn_row.addStretch()
        left_layout.addLayout(left_btn_row)

        self.left_table = QTableWidget(0, 4)
        self.left_table.setHorizontalHeaderLabels(["Адрес", "Цена за месяц", "Начало аренды", "Срок (мес.)"])
        self.left_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.left_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.left_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.left_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.left_table.verticalHeader().setVisible(False)
        self.left_table.verticalHeader().setDefaultSectionSize(30) # комфортная высота
        self.left_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.left_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left_layout.addWidget(self.left_table)
        self.objects_warning = QLabel("⚠️ Добавьте хотя бы один объект недвижимости")
        self.objects_warning.setStyleSheet("color: red; font-size: 12px;")
        self.objects_warning.setVisible(True)
        left_layout.addWidget(self.objects_warning)
        self.splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_top = QHBoxLayout()
        right_top.addWidget(QLabel("Доступные объекты"))
        self.add_obj_btn = QPushButton("+")
        self.add_obj_btn.setFixedWidth(34)
        self.add_obj_btn.setStyleSheet("color: #2C3E50; font-weight: bold; padding: 0px; border: 1px solid #BDC3C7; border-radius: 4px;")
        self.add_obj_btn.setToolTip("Добавить новый объект недвижимости")
        self.add_obj_btn.setEnabled(False)
        self.add_obj_btn.clicked.connect(self._add_real_estate)
        right_top.addWidget(self.add_obj_btn)
        right_top.addStretch()
        right_layout.addLayout(right_top)

        add_btn_row = QHBoxLayout()
        self.add_to_contract_btn = QPushButton("Добавить в договор")
        self.add_to_contract_btn.setToolTip("Перенести выделенные объекты в договор")
        self.add_to_contract_btn.clicked.connect(self._move_selected_to_left)
        add_btn_row.addWidget(self.add_to_contract_btn)
        add_btn_row.addStretch()
        self.clear_right_filters_btn = QPushButton("Очистить фильтры")
        self.clear_right_filters_btn.setToolTip("Убрать все фильтры")
        self.clear_right_filters_btn.clicked.connect(self._reset_right_filters)
        add_btn_row.addWidget(self.clear_right_filters_btn)
        right_layout.addLayout(add_btn_row)

        self.right_filter_bar = QWidget()
        self.right_filter_bar.setFixedHeight(30)
        self.right_filter_bar.setContentsMargins(0, 0, 0, 0)
        self.right_filter_bar.setStyleSheet("background-color: #d0d0d0;")
        self.right_filter_bar.setVisible(False)
        right_layout.addWidget(self.right_filter_bar)

        self.right_table = QTableView()
        self.right_model = QStandardItemModel()
        self.right_proxy = MultiFilterProxy()
        self.right_proxy.setSourceModel(self.right_model)
        self.right_table.setModel(self.right_proxy)
        self.right_table.setSortingEnabled(True)
        self.right_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.right_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.right_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.right_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.right_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self.right_table)
        self.right_filter_widgets = []
        self.splitter.addWidget(right_widget)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        left_widget.setMinimumWidth(200)
        right_widget.setMinimumWidth(200)
        self.splitter.setSizes([450, 500])

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.setFixedWidth(100)
        self.save_btn.clicked.connect(self._validate_and_accept)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        header = self.right_table.horizontalHeader()
        header.sectionResized.connect(self._sync_right_filter_geometry)
        header.sectionMoved.connect(self._sync_right_filter_geometry)
        header.geometriesChanged.connect(self._sync_right_filter_geometry)
        self.right_table.horizontalScrollBar().valueChanged.connect(self._sync_right_filter_geometry)
        self.right_table.verticalScrollBar().valueChanged.connect(self._sync_right_filter_geometry)


        self._update_tenant_warning()
        self._update_landlord_warning()
        self._update_objects_warning()

    def _update_tenant_warning(self):
        self.tenant_warning.setVisible(self.tenant_combo.currentIndex() < 0)

    def _update_landlord_warning(self):
        self.landlord_warning.setVisible(self.landlord_combo.currentIndex() < 0)

    def _update_objects_warning(self):
        self.objects_warning.setVisible(self.left_table.rowCount() == 0)

    def _load_tenants(self):
        """Загружает список арендаторов, сохраняя текущий выбор."""
        try:
            tenants, _ = self.db.fetch_all("SELECT passport, name FROM tenant ORDER BY name")
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        tenant_strings = []
        tenant_data = {}
        for passport, name in tenants:
            text = f"{name} ({passport})"
            tenant_strings.append(text)
            tenant_data[text] = passport

        # Сохраняем текущий выбор
        current = self.tenant_combo.currentData()

        self.tenant_combo.blockSignals(True)
        self.tenant_model.setStringList(tenant_strings)
        self.tenant_combo.clear()
        self.tenant_combo.addItems(tenant_strings)
        for i, text in enumerate(tenant_strings):
            self.tenant_combo.setItemData(i, tenant_data[text])
        # Восстанавливаем выбор, если он был
        if current is not None:
            idx = self.tenant_combo.findData(current)
            if idx >= 0:
                self.tenant_combo.setCurrentIndex(idx)
        self.tenant_combo.blockSignals(False)
        self._update_tenant_warning()

    def _load_landlords(self):
        """Загружает список собственников, сохраняя текущий выбор."""
        try:
            landlords, _ = self.db.fetch_all("SELECT id, name FROM landlord_info ORDER BY name")
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        landlord_strings = []
        landlord_data = {}
        for lid, name in landlords:
            landlord_strings.append(name)
            landlord_data[name] = lid

        # Сохраняем текущий выбор
        current = self.landlord_combo.currentData()

        self.landlord_combo.blockSignals(True)
        self.landlord_model.setStringList(landlord_strings)
        self.landlord_combo.clear()
        self.landlord_combo.addItems(landlord_strings)
        for i, text in enumerate(landlord_strings):
            self.landlord_combo.setItemData(i, landlord_data[text])
        # Восстанавливаем выбор, если он был
        if current is not None:
            idx = self.landlord_combo.findData(current)
            if idx >= 0:
                self.landlord_combo.setCurrentIndex(idx)
        self.landlord_combo.blockSignals(False)
        self._update_landlord_warning()

    def load_combos(self):
        """Полная перезагрузка списков (используется при инициализации)."""
        self._load_tenants()
        self._load_landlords()

    def _add_tenant(self):
        dlg = TenantDialog(self.db, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        # Перезагружаем только список арендаторов
        self._load_tenants()
        # Выбираем только что созданного арендатора
        idx = self.tenant_combo.findData(data["passport"])
        if idx >= 0:
            self.tenant_combo.setCurrentIndex(idx)
        self._mark_modified()
        self.history.add_event(
            event_type="tenant",
            text=f"Арендатор добавлен: {data['name']}",
            show_target=('tenant', data['passport']),
            repeat_data=('tenant', data),
            undo_data={"action": "add_tenant", "passport": data['passport']}
        )

    def _add_landlord(self):
        dlg = LandlordDialog(self.db, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        new_id = data["id"]
        # Перезагружаем только список собственников
        self._load_landlords()
        idx = self.landlord_combo.findData(new_id)
        if idx >= 0:
            self.landlord_combo.setCurrentIndex(idx)
        self._mark_modified()
        self.history.add_event(
            event_type="landlord",
            text=f"Собственник добавлен: {data['name']}",
            show_target=('landlord', new_id),
            repeat_data=('landlord', data),
            undo_data={"action": "add_landlord", "landlord_id": new_id}
        )

    def _add_real_estate(self):
        landlord_id = self.landlord_combo.currentData()
        if landlord_id is None:
            return
        dlg = RealEstateDialog(self.db, landlord_id=landlord_id, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.saved_data
        new_id = data["id"]
        self._add_estate_to_contract(new_id)
        self._load_available_objects(landlord_id)
        self._sync_right_with_left()
        self._mark_modified()
        self.history.add_event(
            event_type="estate",
            text=f"Объект добавлен: {data['address']}",
            show_target=('estate', new_id),
            repeat_data=('estate', data),
            undo_data={"action": "add_estate", "estate_id": new_id}
        )

        self._update_objects_warning()

    def _on_tenant_completer_activated(self, text):
        """При выборе варианта из выпадающей подсказки сразу активируем его."""
        idx = self.tenant_combo.findText(text)
        if idx >= 0:
            self.tenant_combo.setCurrentIndex(idx)

    def _on_landlord_completer_activated(self, text):
        idx = self.landlord_combo.findText(text)
        if idx >= 0:
            self.landlord_combo.setCurrentIndex(idx)
    def _sync_right_with_left(self):
        """Удаляет из правой таблицы объекты, которые уже выбраны в левой."""
        for left_row in range(self.left_table.rowCount()):
            left_id = self.left_table.item(left_row, 0).data(Qt.UserRole)
            # Ищем и удаляем соответствующую строку в правой модели
            for src_row in range(self.right_model.rowCount()):
                item = self.right_model.item(src_row, 0)
                if item and item.data(Qt.UserRole) == left_id:
                    self.right_model.removeRow(src_row)
                    break

    def _on_landlord_changed(self):
        if self._changing_landlord:
            return
        new_id = self.landlord_combo.currentData()
        if new_id == self._previous_landlord_id:
            return

        # Определяем количество объектов у нового собственника
        obj_count = 0
        rows = []
        if new_id is not None:
            try:
                rows, _ = self.db.fetch_all(
                    "SELECT id FROM real_estate_info WHERE landlord_id = %s",
                    (new_id,)
                )
                obj_count = len(rows)
            except psycopg2.Error:
                obj_count = 0

        # Предупреждаем только если в левой таблице БОЛЕЕ ОДНОГО объекта и у нового собственника >1 объекта
        if self.left_table.rowCount() > 1 and obj_count > 1:
            reply = QMessageBox.question(
                self, "Смена собственника",
                "При смене собственника все выбранные объекты будут удалены. Продолжить?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                # откатываем выбор собственника
                self._changing_landlord = True
                self.landlord_combo.blockSignals(True)
                if self._previous_landlord_id is not None:
                    idx = self.landlord_combo.findData(self._previous_landlord_id)
                    self.landlord_combo.setCurrentIndex(idx if idx >= 0 else -1)
                else:
                    self.landlord_combo.setCurrentIndex(-1)
                self.landlord_combo.blockSignals(False)
                self._changing_landlord = False
                return

        # Очищаем левую таблицу
        self.left_table.setRowCount(0)

        self._previous_landlord_id = new_id
        if new_id is not None:
            self._load_available_objects(new_id)
            self.add_obj_btn.setEnabled(True)

            # Автоматически добавляем единственный объект, если он есть
            if obj_count == 1:
                self._add_estate_to_contract(rows[0][0])
        else:
            self.right_model.clear()
            self.add_obj_btn.setEnabled(False)
            self._previous_landlord_id = None
            self._reset_right_filters()

        self._mark_modified()
        self._update_objects_warning()
        self._sync_right_with_left()


    def _load_available_objects(self, landlord_id):
        try:
            rows, _ = self.db.fetch_all(
                "SELECT id, address, overall_space, living_space, floor, date_of_construction, elevator, rooms_amount "
                "FROM real_estate_info WHERE landlord_id = %s ORDER BY address",
                (landlord_id,)
            )
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        headers = ["Адрес", "Общая площадь", "Жилая площадь", "Этаж", "Год постр.", "Лифт", "Комнат"]
        self.right_model.clear()
        self.right_model.setHorizontalHeaderLabels(headers)
        for row_data in rows:
            items = [QStandardItem(str(val)) for val in row_data[1:]]
            items[5] = QStandardItem("Да" if row_data[6] else "Нет")
            items[0].setData(row_data[0], Qt.UserRole)
            self.right_model.appendRow(items)
        self._rebuild_right_filters(headers)

    def _rebuild_right_filters(self, headers):
        for w in self.right_filter_widgets:
            w.setParent(None)
            w.deleteLater()
        self.right_filter_widgets = []
        if not headers:
            self.right_filter_bar.setVisible(False)
            return
        for col, col_name in enumerate(headers):
            if col_name in self.NUMERIC_RIGHT_COLS:
                nf = NumericFilterWidget(col, self.right_filter_bar)
                nf.filter_changed.connect(
                    lambda col, op, val: self.right_proxy.set_numeric_filter(col, op, val)
                )
                fw = nf
            else:
                fw = FilterLineEdit(self.right_filter_bar)
                fw.setToolTip(f"Фильтр по столбцу «{col_name}»")
                fw.textChanged.connect(lambda text, c=col: self.right_proxy.set_filter(c, text))
            fw.show()
            self.right_filter_widgets.append(fw)
        self.right_filter_bar.setVisible(True)
        self._sync_right_filter_geometry()

    def _sync_right_filter_geometry(self):
        if not self.right_filter_widgets or not self.right_filter_bar.isVisible():
            return
        header = self.right_table.horizontalHeader()
        scroll = self.right_table.horizontalScrollBar().value()
        vw = self.right_table.verticalHeader().width() if self.right_table.verticalHeader().isVisible() else 0
        for col in range(min(len(self.right_filter_widgets), header.count())):
            x = header.sectionViewportPosition(col) - scroll + vw
            w = header.sectionSize(col)
            self.right_filter_widgets[col].setGeometry(x, 0, w, self.right_filter_bar.height())

    def _reset_right_filters(self):
        self.right_proxy.reset_filters()
        for w in self.right_filter_widgets:
            if isinstance(w, FilterLineEdit) or isinstance(w, QLineEdit):
                w.clear()
            elif isinstance(w, NumericFilterWidget):
                w.edit.clear()

    def _move_selected_to_left(self):
        selection_model = self.right_table.selectionModel()
        if not selection_model.hasSelection():
            QMessageBox.information(self, "Внимание", "Сначала выделите доступные объекты для добавления.")
            return
        proxy_indexes = selection_model.selectedRows()
        if not proxy_indexes:
            return

        source_rows = sorted(set(self.right_proxy.mapToSource(idx).row() for idx in proxy_indexes), reverse=True)
        duplicate_ids = set()
        for source_row in source_rows:
            obj_id = self.right_model.item(source_row, 0).data(Qt.UserRole)
            for lrow in range(self.left_table.rowCount()):
                if self.left_table.item(lrow, 0).data(Qt.UserRole) == obj_id:
                    duplicate_ids.add(obj_id)
                    break
        if duplicate_ids:
            QMessageBox.information(self, "Инфо", "Некоторые объекты уже есть в договоре. Они будут пропущены.")

        for source_row in source_rows:
            obj_id = self.right_model.item(source_row, 0).data(Qt.UserRole)
            if obj_id in duplicate_ids:
                continue
            address = self.right_model.item(source_row, 0).text()
            self.right_model.removeRow(source_row)

            row = self.left_table.rowCount()
            self.left_table.insertRow(row)
            addr_item = QTableWidgetItem(address)
            addr_item.setFlags(addr_item.flags() & ~Qt.ItemIsEditable)
            addr_item.setData(Qt.UserRole, obj_id)
            self.left_table.setItem(row, 0, addr_item)

            price_spin = QSpinBox()
            price_spin.setRange(1, 1000000000)
            price_spin.setSuffix(" ₽")
            price_spin.setValue(1000)
            price_spin.valueChanged.connect(self._mark_modified)
            self.left_table.setCellWidget(row, 1, price_spin)

            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setDate(self.date_edit.date())
            self._configure_date_edit(date_edit)
            self.left_table.setCellWidget(row, 2, date_edit)

            months_spin = QSpinBox()
            months_spin.setRange(1, 600)
            months_spin.setValue(12)
            months_spin.valueChanged.connect(self._mark_modified)
            self.left_table.setCellWidget(row, 3, months_spin)
        self.left_table.resizeRowsToContents()

        self._mark_modified()
        self._update_objects_warning()
        self._select_first_available_right_row()

    def _select_first_available_right_row(self):
        if self.right_proxy.rowCount() > 0:
            self.right_table.selectRow(0)

    def _remove_selected_from_left(self):
        selection_model = self.left_table.selectionModel()
        if not selection_model.hasSelection():
            QMessageBox.information(self, "Внимание", "Сначала выделите объекты для удаления.")
            return
        rows = sorted(set(index.row() for index in selection_model.selectedRows()), reverse=True)
        min_row = rows[-1]
        landlord_id = self.landlord_combo.currentData()

        for row in rows:
            obj_id = self.left_table.item(row, 0).data(Qt.UserRole)
            self.left_table.removeRow(row)

            if landlord_id is not None:
                try:
                    obj_data = self.db.fetch_one(
                        "SELECT address, overall_space, living_space, floor, date_of_construction, elevator, rooms_amount "
                        "FROM real_estate_info WHERE id = %s", (obj_id,)
                    )
                except psycopg2.Error as e:
                    QMessageBox.critical(self, "Ошибка", parse_db_error(e))
                    continue
                if obj_data:
                    items = [
                        QStandardItem(str(obj_data["address"])),
                        QStandardItem(str(obj_data["overall_space"])),
                        QStandardItem(str(obj_data["living_space"])),
                        QStandardItem(str(obj_data["floor"])),
                        QStandardItem(str(obj_data["date_of_construction"])),
                        QStandardItem("Да" if obj_data["elevator"] else "Нет"),
                        QStandardItem(str(obj_data["rooms_amount"]))
                    ]
                    items[0].setData(obj_id, Qt.UserRole)
                    self.right_model.appendRow(items)

        self._mark_modified()
        self._update_objects_warning()

        if self.left_table.rowCount() > 0:
            new_index = min(min_row, self.left_table.rowCount() - 1)
            self.left_table.selectRow(new_index)

    def _clear_left(self):
        if self.left_table.rowCount() == 0:
            return
        reply = QMessageBox.question(self, "Очистка", "Удалить все выбранные объекты?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            ids = []
            for row in range(self.left_table.rowCount()):
                ids.append(self.left_table.item(row, 0).data(Qt.UserRole))
            self.left_table.setRowCount(0)
            if self.landlord_combo.currentData() is not None:
                for obj_id in ids:
                    try:
                        obj_data = self.db.fetch_one(
                            "SELECT address, overall_space, living_space, floor, date_of_construction, elevator, rooms_amount "
                            "FROM real_estate_info WHERE id = %s", (obj_id,)
                        )
                    except psycopg2.Error as e:
                        QMessageBox.critical(self, "Ошибка", parse_db_error(e))
                        continue
                    if obj_data:
                        items = [
                            QStandardItem(str(obj_data["address"])),
                            QStandardItem(str(obj_data["overall_space"])),
                            QStandardItem(str(obj_data["living_space"])),
                            QStandardItem(str(obj_data["floor"])),
                            QStandardItem(str(obj_data["date_of_construction"])),
                            QStandardItem("Да" if obj_data["elevator"] else "Нет"),
                            QStandardItem(str(obj_data["rooms_amount"]))
                        ]
                        items[0].setData(obj_id, Qt.UserRole)
                        self.right_model.appendRow(items)
            self._mark_modified()
            self._update_objects_warning()

    def _load_contract_objects(self, contract_id):
        try:
            items, _ = self.db.fetch_all("""
                SELECT r.real_estate_id, re.address, r.price_per_month,
                       r.start_date, r.months
                FROM report r
                JOIN real_estate_info re ON r.real_estate_id = re.id
                WHERE r.contract_id = %s
            """, (contract_id,))
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка", parse_db_error(e))
            return
        if items:
            first_obj_id = items[0][0]
            landlord_row = self.db.fetch_one(
                "SELECT landlord_id FROM real_estate_info WHERE id = %s", (first_obj_id,))
            if landlord_row:
                self._initial_landlord = landlord_row["landlord_id"]
                self._previous_landlord_id = self._initial_landlord
                idx = self.landlord_combo.findData(self._initial_landlord)
                if idx >= 0:
                    self.landlord_combo.blockSignals(True)
                    self.landlord_combo.setCurrentIndex(idx)
                    self.landlord_combo.blockSignals(False)
                    self._load_available_objects(self._initial_landlord)
                    self.add_obj_btn.setEnabled(True)

        for obj_id, addr, price, start, months in items:
            row = self.left_table.rowCount()
            self.left_table.insertRow(row)
            addr_item = QTableWidgetItem(addr)
            addr_item.setFlags(addr_item.flags() & ~Qt.ItemIsEditable)
            addr_item.setData(Qt.UserRole, obj_id)
            self.left_table.setItem(row, 0, addr_item)

            price_spin = QSpinBox()
            price_spin.setRange(1, 1000000000)
            price_spin.setSuffix(" ₽")
            price_spin.setValue(price)
            price_spin.valueChanged.connect(self._mark_modified)
            self.left_table.setCellWidget(row, 1, price_spin)

            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setDate(QDate.fromString(str(start), "yyyy-MM-dd"))
            date_edit.dateChanged.connect(self._mark_modified)
            self.left_table.setCellWidget(row, 2, date_edit)

            months_spin = QSpinBox()
            months_spin.setRange(1, 600)
            months_spin.setValue(months)
            months_spin.valueChanged.connect(self._mark_modified)
            self.left_table.setCellWidget(row, 3, months_spin)

        if self._initial_landlord:
            for obj_id, _, _, _, _ in items:
                for src_row in range(self.right_model.rowCount()):
                    if self.right_model.item(src_row, 0).data(Qt.UserRole) == obj_id:
                        self.right_model.removeRow(src_row)
                        break
        self._update_objects_warning()
        self.left_table.resizeRowsToContents()

    def _configure_date_edit(self, date_edit: QDateEdit):
        """Настройка поля даты начала аренды: минимум = дата договора, авто‑коррекция."""
        date_edit.setMinimumDate(self.date_edit.date())
        # Если текущая дата оказалась меньше договора — поднимаем
        if date_edit.date() < self.date_edit.date():
            date_edit.setDate(self.date_edit.date())
        # Подключаем валидацию при изменении пользователем
        date_edit.dateChanged.connect(lambda d, de=date_edit: self._validate_estate_date(de))

    def _validate_estate_date(self, date_edit: QDateEdit):
        """Не даём уйти раньше даты договора и фиксируем изменение."""
        if date_edit.date() < self.date_edit.date():
            date_edit.setDate(self.date_edit.date())
        self._mark_modified()

    def _on_contract_date_changed(self, new_date: QDate):
        """При изменении даты договора обновляем ограничения и значения во всех строках."""
        for row in range(self.left_table.rowCount()):
            w = self.left_table.cellWidget(row, 2)  # столбец «Начало аренды»
            if isinstance(w, QDateEdit):
                w.setMinimumDate(new_date)
                if w.date() < new_date:
                    w.setDate(new_date)

    def _mark_modified(self, *args):
        self._modified = True

    def is_modified(self):
        if self._modified:
            return True
        if self.contract:
            if self.date_edit.date() != self._initial_date:
                return True
            if self.tenant_combo.currentData() != self._initial_tenant:
                return True
        else:
            if self.tenant_combo.currentIndex() >= 0 or self.landlord_combo.currentIndex() >= 0 or self.left_table.rowCount() > 0:
                return True
        return False

    def reject(self):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение",
                                         "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        super().reject()

    def closeEvent(self, event):
        if self.is_modified():
            reply = QMessageBox.question(self, "Подтверждение",
                                         "Вы точно хотите выйти из редактирования?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
        event.accept()

    def _validate_and_accept(self):
        self._update_tenant_warning()
        self._update_landlord_warning()
        self._update_objects_warning()

        if self.tenant_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Ошибка", "Не выбран арендатор.")
            return
        if self.landlord_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Ошибка", "Не выбран собственник.")
            return
        if self.left_table.rowCount() == 0:
            QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы один объект недвижимости.")
            return
        for row in range(self.left_table.rowCount()):
            price_widget = self.left_table.cellWidget(row, 1)
            if price_widget and price_widget.value() <= 0:
                QMessageBox.warning(self, "Ошибка", f"Цена для объекта {row+1} должна быть положительной.")
                return
            months_widget = self.left_table.cellWidget(row, 3)
            if months_widget and months_widget.value() <= 0:
                QMessageBox.warning(self, "Ошибка", f"Срок для объекта {row+1} должен быть положительным.")
                return

        # Попытка сохранить в БД – если ошибка, диалог останется открытым
        try:
            self._save_to_db()
        except psycopg2.Error as e:
            QMessageBox.critical(self, "Ошибка сохранения", parse_db_error(e))
            # не закрываем диалог, даём пользователю исправить данные
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        else:
            self.accept()   # сохранение прошло успешно – закрываем диалог

    def _save_to_db(self):
        data = self.get_contract_data()
        try:
            if self.contract is None:
                with self.db.conn.cursor() as cursor:
                    cursor.execute(INSERT_CONTRACT, (data["date"], data["tenant_passport"]))
                    contract_id = cursor.fetchone()[0]
                    for obj in data["objects"]:
                        cursor.execute(INSERT_REPORT_ITEM, (
                            obj["real_estate_id"], contract_id,
                            obj["start_date"], obj["months"], obj["price_per_month"]
                        ))
                    self.db.conn.commit()
                self.saved_data = data
                self.saved_data["contract_id"] = contract_id
            else:
                cid = self.contract["id"]
                with self.db.conn.cursor() as cursor:
                    cursor.execute(UPDATE_CONTRACT, (data["date"], data["tenant_passport"], cid))
                    cursor.execute("SELECT real_estate_id FROM report WHERE contract_id = %s", (cid,))
                    existing_ids = {row[0] for row in cursor.fetchall()}
                    new_ids = {obj["real_estate_id"] for obj in data["objects"]}
                    for old_id in existing_ids - new_ids:
                        cursor.execute(DELETE_REPORT_ITEM, (old_id, cid))
                    for obj in data["objects"]:
                        if obj["real_estate_id"] in existing_ids:
                            cursor.execute(UPDATE_REPORT_ITEM, (
                                obj["start_date"], obj["months"], obj["price_per_month"],
                                obj["real_estate_id"], cid))
                        else:
                            cursor.execute(INSERT_REPORT_ITEM, (
                                obj["real_estate_id"], cid,
                                obj["start_date"], obj["months"], obj["price_per_month"]))
                    self.db.conn.commit()
                self.saved_data = data
                self.saved_data["contract_id"] = cid
        except psycopg2.Error:
            if self.db.conn:
                self.db.conn.rollback()
            raise
        except Exception:
            if self.db.conn:
                self.db.conn.rollback()
            raise

    def get_contract_data(self):
        date = self.date_edit.date().toPython()
        tenant_passport = self.tenant_combo.currentData()
        landlord_id = self.landlord_combo.currentData()
        objects = []
        for row in range(self.left_table.rowCount()):
            obj_id = self.left_table.item(row, 0).data(Qt.UserRole)
            price = self.left_table.cellWidget(row, 1).value()
            start_date = self.left_table.cellWidget(row, 2).date().toPython()
            months = self.left_table.cellWidget(row, 3).value()
            objects.append({
                "real_estate_id": obj_id,
                "price_per_month": price,
                "start_date": start_date,
                "months": months
            })
        return {
            "date": date,
            "tenant_passport": tenant_passport,
            "landlord_id": landlord_id,
            "objects": objects
        }