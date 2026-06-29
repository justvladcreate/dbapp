# config.py
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'real_estate',   # замените на имя вашей БД
    'user': 'postgres',            # замените на вашего пользователя
    'password': '1234'         # замените на пароль
}

STYLE_SHEET = """
QWidget {
    background-color: #F5F6FA;
    color: #2C3E50;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #F5F6FA;
}
QTableView {
    background-color: #FFFFFF;
    alternate-background-color: #F8F9FC;
    selection-background-color: #D4E6F1;
    selection-color: #2C3E50;
    border: 1px solid #DEE2E6;
    border-radius: 4px;
    gridline-color: #EAECEE;
    outline: none;
}
QTableView::item {
    padding: 4px 8px;
}
QTableView::item:hover {
    background-color: #EBF5FB;
}

QHeaderView::section {
    background-color: #EAEEF2;
    color: #2C3E50;
    font-weight: bold;
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid #BDC3C7;
    border-right: 1px solid #D5D8DC;
}
QHeaderView::section:hover {
    background-color: #DCE1E7;
}
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #BDC3C7;
    border-radius: 5px;
    padding: 6px 16px;
    color: #2C3E50;
    font-weight: normal;
}
QPushButton:hover {
    background-color: #EAF2F8;
    border-color: #3498DB;
}
QPushButton:pressed {
    background-color: #D4E6F1;
}
QPushButton:disabled {
    background-color: #F0F0F0;
    color: #A0A0A0;
    border-color: #D0D0D0;
    opacity: 0.6;
}
QPushButton[objectName="primary"],
QPushButton[text="Добавить"],
QPushButton[text="Сохранить"] {
    background-color: #2980B9;
    color: white;
    border: 1px solid #2471A3;
    font-weight: bold;
}
QPushButton[objectName="primary"]:hover,
QPushButton[text="Добавить"]:hover,
QPushButton[text="Сохранить"]:hover {
    background-color: #3498DB;
}
QLineEdit, QSpinBox, QDateEdit, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #BDC3C7;
    border-radius: 4px;
    padding: 4px 8px;
    color: #2C3E50;
    selection-background-color: #AED6F1;
}
QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {
    border-color: #3498DB;
}
QTabWidget::pane {
    border: 1px solid #BDC3C7;
    background-color: #FFFFFF;
    border-radius: 4px;
    top: -1px;
}
QTabBar::tab {
    background-color: #E5E7E9;
    color: #2C3E50;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #2980B9;
    font-weight: bold;
    border-bottom: 2px solid #2980B9;
}
QTabBar::tab:hover:!selected {
    background-color: #D5DBDB;
}
QToolBar {
    background-color: transparent;
    border: none;
    spacing: 8px;
    padding: 4px;
}
QToolBar QPushButton {
    background-color: transparent;
    border: none;
    font-weight: bold;
    padding: 4px 12px;
}
QToolBar QPushButton:hover {
    background-color: #E0E4E8;
    border-radius: 4px;
}
QGroupBox {
    border: 1px solid #BDC3C7;
    border-radius: 6px;
    margin-top: 14px;
    font-weight: bold;
    padding-top: 10px;
    background-color: #FBFCFD;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #2C3E50;
}
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #BDC3C7;
    border-radius: 4px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
}
QMenu::item:selected {
    background-color: #D4E6F1;
}
QToolTip {
    background-color: #FCF8E3 !important;
    color: #2C3E50 !important;
    border: 1px solid #F0C36D;
    padding: 4px;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: #DEE2E6;
    width: 2px;
    height: 2px;
}
QStatusBar {
    background-color: #EAEEF2;
    color: #2C3E50;
    border-top: 1px solid #BDC3C7;
}
QStatusBar QLabel {
    padding: 2px 6px;
}
QScrollBar:vertical {
    background: #F0F0F0;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #BDC3C7;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #3498DB;
}
QScrollBar:horizontal {
    background: #F0F0F0;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #BDC3C7;
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #3498DB;
}
QCalendarWidget {
    background-color: #FFFFFF;
    font-size: 11px;
    min-width: 250px;
    max-width: 280px;
    min-height: 200px;
    max-height: 240px;
}
QCalendarWidget QToolButton {
    color: #2C3E50;
    background-color: #EAEEF2;
    border: 1px solid #BDC3C7;
    border-radius: 3px;
    padding: 2px 6px;
    font-weight: bold;
    font-size: 11px;
}
QCalendarWidget QToolButton:hover {
    background-color: #D4E6F1;
}
QCalendarWidget QSpinBox {
    font-size: 11px;
    padding: 2px;
}
QCalendarWidget QTableView {
    outline: none;
}
QCalendarWidget QTableView::item {
    min-width: 28px;
    min-height: 24px;
    padding: 2px;
    font-size: 11px;
}
QCalendarWidget QAbstractItemView:enabled {
    color: #2C3E50;
    selection-background-color: #D4E6F1;
    selection-color: #2C3E50;
}
QWidget#FilterBar {
    background-color: #d0d0d0;
}
QLineEdit#FilterLineEdit {
    border: none;
    background: transparent;
}
QCalendarWidget QAbstractItemView::item:disabled {
    color: #B0B0B0;
    background-color: #F5F5F5;
}
/* ===== Кнопки навигации в тулбаре (стиль вкладок) ===== */
QToolButton#NavButton {
    background: transparent;
    color: #2C3E50;
    padding: 8px 20px;
    margin-right: 2px;
    border: none;
    border-bottom: 3px solid transparent;
    font-size: 13px;
}
QToolButton#NavButton:checked {
    color: #2980B9;
    font-weight: bold;
    border-bottom: 3px solid #2980B9;
}
QToolButton#NavButton:hover:!checked {
    color: #2471A3;
    border-bottom: 3px solid #D5DBDB;
}
/* ===== Служебные кнопки тулбара (О программе, История) ===== */
QToolButton#ToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 12px;
    margin-left: 4px;
    color: #2C3E50;
    font-weight: normal;
    font-size: 13px;
}
QToolButton#ToolButton:hover {
    background: #EAF2F8;
    border-color: #BDC3C7;
}
QToolButton#ToolButton:checked {
    background: #D4E6F1;
    border-color: #3498DB;
    font-weight: bold;
}
"""