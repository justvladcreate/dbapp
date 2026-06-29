project_root/
│
├── main.py                      # точка входа
├── config.py                    # конфигурация БД (хост, пароль и т.д.)
│
├── database/                    # пакет работы с базой данных
│   ├── __init__.py              # экспорт connection и queries
│   ├── connection.py            # класс Database
│   └── queries.py               # SQL-запросы (константы)
│
├── ui/                          # пакет пользовательского интерфейса
│   ├── __init__.py              # экспорт main_page, contracts_page, landlords_page, real_estate_page, tenants_page
│   ├── main_window.py           # главное окно приложения
│   ├── dialogs.py               # диалоговые окна (LandlordDialog, TenantDialog, RealEstateDialog, ContractDialog)
│   ├── widgets.py               # вспомогательные виджеты (фильтр, экспорт CSV)
│   │
│   ├── pages/                   # страницы приложения (наследники QWidget)
│   │   ├── __init__.py          # экспорт всех страниц
│   │   ├── main_page.py         # главная страница со сводной таблицей
│   │   ├── contracts_page.py    # страница договоров аренды
│   │   ├── landlords_page.py    # страница собственников
│   │   ├── tenants_page.py      # страница арендаторов
│   │   └── real_estate_page.py  # страница объектов недвижимости


~~~~PyCharm latest + python 3.14.3 + qt/pyside6 + postgresql