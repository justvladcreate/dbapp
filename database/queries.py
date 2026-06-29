# database/queries.py

# ------------- Главная страница (с ID для переходов) -------------
GET_RENTAL_DETAILS_WITH_IDS = """
    SELECT
        r.contract_id,
        c.tenant_passport,
        re.landlord_id,
        re.id AS real_estate_id,
        "Адрес объекта",
        "Общая площадь",
        "Комнат",
        "Собственник",
        "Контакты собственника",
        "Арендатор",
        "Паспорт арендатора",
        "Дата договора",
        "Начало аренды",
        "Срок (мес.)",
        "Цена за месяц",
        "Общая сумма"
    FROM rental_details r
    JOIN contract c ON r.contract_id = c.id
    JOIN real_estate_info re ON r.real_estate_id = re.id
    ORDER BY "Дата договора" DESC;
"""

# ------------- Договоры -------------
GET_CONTRACTS = """
    SELECT c.id, c.date, t.name AS tenant_name, t.passport,
           COUNT(r.real_estate_id) AS objects_count,
           COALESCE(SUM(r.price_per_month * r.months), 0) AS total_sum,
           MIN(l.name) AS landlord_name
    FROM contract c
    JOIN tenant t ON c.tenant_passport = t.passport
    LEFT JOIN report r ON c.id = r.contract_id
    LEFT JOIN real_estate_info re ON r.real_estate_id = re.id
    LEFT JOIN landlord_info l ON re.landlord_id = l.id
    GROUP BY c.id, c.date, t.name, t.passport
    ORDER BY c.date DESC;
"""

GET_CONTRACT_ITEMS = """
    SELECT r.real_estate_id, re.address, l.name AS landlord_name,
           r.price_per_month, r.start_date, r.months,
           (r.price_per_month * r.months) AS total
    FROM report r
    JOIN real_estate_info re ON r.real_estate_id = re.id
    JOIN landlord_info l ON re.landlord_id = l.id
    WHERE r.contract_id = %s
    ORDER BY re.address;
"""

# ------------- Собственники -------------
GET_LANDLORDS = """
    SELECT id, name, contact_info FROM landlord_info ORDER BY name;
"""

GET_LANDLORD_OBJECTS = """
    SELECT id, address, overall_space, rooms_amount
    FROM real_estate_info
    WHERE landlord_id = %s
    ORDER BY address;
"""

GET_LANDLORD_CONTRACTS = """
    SELECT DISTINCT c.id, c.date, t.name AS tenant_name,
           SUM(r.price_per_month * r.months) AS total_sum
    FROM contract c
    JOIN tenant t ON c.tenant_passport = t.passport
    JOIN report r ON c.id = r.contract_id
    JOIN real_estate_info re ON r.real_estate_id = re.id
    WHERE re.landlord_id = %s
    GROUP BY c.id, c.date, t.name
    ORDER BY c.date DESC;
"""

LANDLORD_STATS = """
    SELECT
        COUNT(DISTINCT re.id) AS objects_count,
        COUNT(DISTINCT c.id) AS contracts_count,
        COALESCE(SUM(r.price_per_month * r.months), 0) AS total_income
    FROM landlord_info l
    LEFT JOIN real_estate_info re ON re.landlord_id = l.id
    LEFT JOIN report r ON r.real_estate_id = re.id
    LEFT JOIN contract c ON r.contract_id = c.id
    WHERE l.id = %s;
"""

# ------------- Арендаторы -------------
GET_TENANTS = """
    SELECT t.passport, t.name, COUNT(c.id) AS contracts_count
    FROM tenant t
    LEFT JOIN contract c ON t.passport = c.tenant_passport
    GROUP BY t.passport, t.name
    ORDER BY t.name;
"""

GET_TENANT_CONTRACTS = """
    SELECT c.id, c.date, COUNT(r.real_estate_id) AS objects_count,
           SUM(r.price_per_month * r.months) AS total_sum
    FROM contract c
    JOIN report r ON c.id = r.contract_id
    WHERE c.tenant_passport = %s
    GROUP BY c.id, c.date
    ORDER BY c.date DESC;
"""

TENANT_STATS = """
    SELECT
        COUNT(DISTINCT c.id) AS contracts_count,
        COALESCE(SUM(r.price_per_month * r.months), 0) AS total_spent
    FROM tenant t
    LEFT JOIN contract c ON c.tenant_passport = t.passport
    LEFT JOIN report r ON r.contract_id = c.id
    WHERE t.passport = %s;
"""

# ------------- Объекты недвижимости -------------
GET_REAL_ESTATES = """
    SELECT re.id, re.address, re.overall_space, re.living_space,
           re.floor, re.date_of_construction, re.elevator, re.rooms_amount,
           re.landlord_id, l.name AS landlord_name
    FROM real_estate_info re
    JOIN landlord_info l ON re.landlord_id = l.id
    ORDER BY re.address;
"""

GET_ESTATE_CONTRACTS = """
    SELECT c.id, c.date, t.name AS tenant_name,
           r.price_per_month, r.start_date, r.months,
           (r.price_per_month * r.months) AS total
    FROM report r
    JOIN contract c ON r.contract_id = c.id
    JOIN tenant t ON c.tenant_passport = t.passport
    WHERE r.real_estate_id = %s
    ORDER BY c.date DESC;
"""

# ------------- CRUD -------------
INSERT_LANDLORD = """
    INSERT INTO landlord_info (name, contact_info) VALUES (%s, %s) RETURNING id;
"""
UPDATE_LANDLORD = """
    UPDATE landlord_info SET name = %s, contact_info = %s WHERE id = %s;
"""

INSERT_TENANT = """
    INSERT INTO tenant (passport, name) VALUES (%s, %s);
"""
UPDATE_TENANT = """
    UPDATE tenant SET name = %s, passport = %s WHERE passport = %s;
"""

INSERT_REAL_ESTATE = """
    INSERT INTO real_estate_info
        (address, overall_space, living_space, floor, date_of_construction,
         elevator, rooms_amount, landlord_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
"""
UPDATE_REAL_ESTATE = """
    UPDATE real_estate_info SET
        address = %s, overall_space = %s, living_space = %s, floor = %s,
        date_of_construction = %s, elevator = %s, rooms_amount = %s,
        landlord_id = %s
    WHERE id = %s;
"""

INSERT_CONTRACT = """
    INSERT INTO contract (date, tenant_passport) VALUES (%s, %s) RETURNING id;
"""
UPDATE_CONTRACT = """
    UPDATE contract SET date = %s, tenant_passport = %s WHERE id = %s;
"""

INSERT_REPORT_ITEM = """
    INSERT INTO report (real_estate_id, contract_id, start_date, months, price_per_month)
    VALUES (%s, %s, %s, %s, %s);
"""
UPDATE_REPORT_ITEM = """
    UPDATE report SET start_date = %s, months = %s, price_per_month = %s
    WHERE real_estate_id = %s AND contract_id = %s;
"""
DELETE_REPORT_ITEM = """
    DELETE FROM report WHERE real_estate_id = %s AND contract_id = %s;
"""
GET_OBJECTS_BY_LANDLORD = """
    SELECT id, address FROM real_estate_info WHERE landlord_id = %s ORDER BY address;
"""