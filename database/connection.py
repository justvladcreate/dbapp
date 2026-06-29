# database/connection.py
import psycopg2
from psycopg2 import OperationalError, extras
from config import DB_CONFIG

class Database:
    def __init__(self):
        self.conn = None
        self._ensure_database_exists()
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.conn.autocommit = False
            self._create_tables()
            self._create_views()
            self._apply_constraints()
        except OperationalError as e:
            raise ConnectionError(
                f"Не удалось подключиться к базе данных.\n"
                f"Проверьте, запущен ли PostgreSQL.\nТехническая информация: {e}"
            ) from e

    def _ensure_database_exists(self):
        """Проверяет существование БД из config.py и создаёт её при необходимости."""
        db_name = DB_CONFIG['database']
        # Параметры подключения к служебной базе 'postgres'
        conn_params = DB_CONFIG.copy()
        conn_params.pop('database', None)  # убираем целевую БД
        try:
            # Подключаемся к системной БД postgres
            conn = psycopg2.connect(**conn_params, database='postgres')
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone()
            if not exists:
                # Создаём базу с именем из конфига (безопасно, т.к. имя не из пользовательского ввода)
                cur.execute(f'CREATE DATABASE "{db_name}"')
                print(f"База данных '{db_name}' успешно создана.")
            cur.close()
            conn.close()
        except OperationalError as e:
            raise ConnectionError(
                f"Не удалось подключиться к серверу PostgreSQL для проверки существования БД.\n"
                f"Убедитесь, что PostgreSQL запущен и параметры подключения в config.py верны.\n"
                f"Ошибка: {e}"
            ) from e

    def _create_tables(self):
        """Создаёт все таблицы, если они ещё не существуют."""
        ddl_commands = [
            """
            CREATE TABLE IF NOT EXISTS tenant (
                passport TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS landlord_info (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                contact_info TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS real_estate_info (
                id SERIAL PRIMARY KEY,
                address TEXT NOT NULL,
                overall_space INTEGER,
                living_space INTEGER,
                floor INTEGER,
                date_of_construction DATE,
                elevator BOOLEAN,
                rooms_amount INTEGER,
                landlord_id INTEGER REFERENCES landlord_info(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS contract (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                tenant_passport TEXT NOT NULL REFERENCES tenant(passport)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS report (
                real_estate_id INTEGER NOT NULL REFERENCES real_estate_info(id) ON DELETE CASCADE,
                contract_id INTEGER NOT NULL REFERENCES contract(id) ON DELETE CASCADE,
                start_date DATE,
                months INTEGER,
                price_per_month INTEGER,
                PRIMARY KEY (real_estate_id, contract_id)
            );
            """
        ]
        try:
            old_autocommit = self.conn.autocommit
            self.conn.autocommit = True
            with self.conn.cursor() as cur:
                for sql in ddl_commands:
                    cur.execute(sql)
            self.conn.autocommit = old_autocommit
        except Exception as e:
            print("Ошибка при создании таблиц:", e)
            raise

    def _apply_constraints(self):
        """Добавляет недостающие ограничения базы данных для предотвращения дублирования."""
        constraints = [
            # Убираем старые ограничения и создаём индексы с LOWER(TRIM(...))
            """
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'landlord_name_unique') THEN
                    ALTER TABLE landlord_info DROP CONSTRAINT landlord_name_unique;
                END IF;
                DROP INDEX IF EXISTS landlord_name_unique_idx;
                CREATE UNIQUE INDEX landlord_name_unique_idx 
                ON landlord_info (LOWER(TRIM(name)));
            END $$;
            """,
            """
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'real_estate_address_unique') THEN
                    ALTER TABLE real_estate_info DROP CONSTRAINT real_estate_address_unique;
                END IF;
                DROP INDEX IF EXISTS real_estate_address_unique_idx;
                CREATE UNIQUE INDEX real_estate_address_unique_idx 
                ON real_estate_info (LOWER(TRIM(address)));
            END $$;
            """,
            """
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'contract_date_tenant_unique') THEN
                    ALTER TABLE contract DROP CONSTRAINT contract_date_tenant_unique;
                END IF;
                DROP INDEX IF EXISTS contract_date_tenant_unique_idx;
                CREATE UNIQUE INDEX contract_date_tenant_unique_idx 
                ON contract (date, LOWER(TRIM(tenant_passport)));
            END $$;
            """,
            """
            DO $$ BEGIN
                DROP INDEX IF EXISTS tenant_name_unique_idx;
                CREATE UNIQUE INDEX tenant_name_unique_idx 
                ON tenant (LOWER(TRIM(name)));
            END $$;
            """,
            # Триггер для запрета двойной аренды (тот же, что и раньше, для целостности оставим)
            """
            DO $$ BEGIN
                DROP TRIGGER IF EXISTS trg_report_no_double_booking ON report;
                DROP FUNCTION IF EXISTS check_real_estate_unique_tenant_per_day CASCADE;
                CREATE OR REPLACE FUNCTION check_real_estate_unique_tenant_per_day()
                RETURNS trigger AS $func$
                DECLARE
                    v_date date;
                    v_tenant_passport text;
                    v_address text;
                    v_conflict_tenant_name text;
                    v_conflict_date date;
                BEGIN
                    SELECT c.date, c.tenant_passport INTO v_date, v_tenant_passport
                    FROM contract c
                    WHERE c.id = NEW.contract_id;
        
                    SELECT re.address, c2.date, t.name
                    INTO v_address, v_conflict_date, v_conflict_tenant_name
                    FROM report r
                    JOIN contract c2 ON r.contract_id = c2.id
                    JOIN real_estate_info re ON r.real_estate_id = re.id
                    JOIN tenant t ON c2.tenant_passport = t.passport
                    WHERE r.real_estate_id = NEW.real_estate_id
                      AND c2.date = v_date
                      AND c2.tenant_passport <> v_tenant_passport
                      AND r.contract_id <> NEW.contract_id
                    LIMIT 1;
        
                    IF FOUND THEN
                        RAISE EXCEPTION 'Объект (адрес: %) уже сдаётся арендатору % на дату %',
                            v_address, v_conflict_tenant_name, v_conflict_date;
                    END IF;
        
                    RETURN NEW;
                END;
                $func$ LANGUAGE plpgsql;
        
                CREATE TRIGGER trg_report_no_double_booking
                BEFORE INSERT OR UPDATE ON report
                FOR EACH ROW EXECUTE FUNCTION check_real_estate_unique_tenant_per_day();
            END $$;
            """,
        ]
        if self.conn is None:
            return
        try:
            old_autocommit = self.conn.autocommit
            self.conn.autocommit = True
            with self.conn.cursor() as cursor:
                for sql in constraints:
                    cursor.execute(sql)
            self.conn.autocommit = old_autocommit
        except Exception as e:
            # Не прерываем работу, просто печатаем (ограничения могут уже существовать)
            print("Предупреждение при добавлении ограничений:", e)

    def _create_views(self):
        """Создаёт представления, необходимые для работы приложения."""
        drop_sql = "DROP VIEW IF EXISTS rental_details CASCADE;"
        create_sql = """
        CREATE VIEW rental_details AS
        SELECT
            r.contract_id,
            c.tenant_passport,
            re.landlord_id,
            re.id AS real_estate_id,
            re.address AS "Адрес объекта",
            re.overall_space AS "Общая площадь",
            re.rooms_amount AS "Комнат",
            l.name AS "Собственник",
            l.contact_info AS "Контакты собственника",
            t.name AS "Арендатор",
            t.passport AS "Паспорт арендатора",
            c.date AS "Дата договора",
            r.start_date AS "Начало аренды",
            r.months AS "Срок (мес.)",
            r.price_per_month AS "Цена за месяц",
            (r.price_per_month * r.months) AS "Общая сумма"
        FROM report r
        JOIN contract c ON r.contract_id = c.id
        JOIN real_estate_info re ON r.real_estate_id = re.id
        JOIN landlord_info l ON re.landlord_id = l.id
        JOIN tenant t ON c.tenant_passport = t.passport;
        """
        if self.conn is None:
            return
        try:
            old_autocommit = self.conn.autocommit
            self.conn.autocommit = True
            with self.conn.cursor() as cursor:
                cursor.execute(drop_sql)
                cursor.execute(create_sql)
            self.conn.autocommit = old_autocommit
        except psycopg2.Error as e:
            print("Ошибка создания представления:", e)

    @property
    def is_connected(self):
        return self.conn is not None

    def execute(self, query: str, params=None) -> int:
        if self.conn is None:
            raise ConnectionError("Нет подключения к БД")
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, params or ())
                self.conn.commit()
                return cursor.rowcount
        except psycopg2.Error:
            if self.conn:
                self.conn.rollback()
            raise

    def execute_returning(self, query: str, params=None):
        if self.conn is None:
            raise ConnectionError("Нет подключения к БД")
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute(query, params or ())
                self.conn.commit()
                row = cursor.fetchone()
                return row
        except psycopg2.Error:
            if self.conn:
                self.conn.rollback()
            raise

    def fetch_all(self, query: str, params=None):
        if self.conn is None:
            raise ConnectionError("Нет подключения к БД")
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, params or ())
                rows = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description] if cursor.description else []
                return rows, col_names
        except psycopg2.Error:
            if self.conn:
                self.conn.rollback()
            raise

    def fetch_one(self, query: str, params=None):
        if self.conn is None:
            raise ConnectionError("Нет подключения к БД")
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute(query, params or ())
                return cursor.fetchone()
        except psycopg2.Error:
            if self.conn:
                self.conn.rollback()
            raise

    def transaction(self, queries_with_params, return_last=False):
        if self.conn is None:
            raise ConnectionError("Нет подключения к БД")
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                last_result = None
                for sql, params in queries_with_params:
                    cursor.execute(sql, params or ())
                    if return_last and sql.strip().upper().startswith("INSERT") and "RETURNING" in sql.upper():
                        last_result = cursor.fetchone()
                self.conn.commit()
                return last_result
        except psycopg2.Error:
            if self.conn:
                self.conn.rollback()
            raise

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None