import psycopg2
import re

def parse_db_error(e: Exception) -> str:
    """
    Преобразует исключение базы данных в понятное пользователю сообщение.
    """
    if not isinstance(e, psycopg2.Error):
        return str(e)

    pgcode = e.pgcode if hasattr(e, 'pgcode') else None
    pgerror = str(e).strip()

    # Уникальность (23505)
    if pgcode == '23505':
        match = re.search(r'unique constraint "(\w+)"', pgerror)
        constraint = match.group(1) if match else None
        if constraint == 'landlord_name_unique':
            return "Собственник с таким именем уже существует."
        elif constraint == 'real_estate_address_unique':
            return "Объект недвижимости с таким адресом уже существует."
        elif constraint == 'contract_date_tenant_unique':
            return "Договор для этого арендатора на эту дату уже существует (возможно, повторное добавление)."
        else:
            return "Запись с такими данными уже существует. Проверьте уникальность полей."

    # Нарушение внешнего ключа (23503)
    if pgcode == '23503':
        if 'landlord_id' in pgerror or 'landlord' in pgerror:
            return "Выбранный собственник не существует. Возможно, он был удалён. Обновите список и попробуйте снова."
        elif 'tenant_passport' in pgerror or 'tenant' in pgerror:
            return "Указанный арендатор не найден в базе. Добавьте арендатора перед созданием договора."
        elif 'real_estate_id' in pgerror:
            return "Выбранный объект недвижимости не существует. Обновите список."
        else:
            return "Связанная запись не найдена. Возможно, данные были удалены другим пользователем."

    # NOT NULL (23502)
    if pgcode == '23502':
        if 'name' in pgerror:
            return "Поле «Имя» обязательно для заполнения."
        elif 'passport' in pgerror:
            return "Поле «Паспорт» обязательно для заполнения."
        elif 'address' in pgerror:
            return "Поле «Адрес» обязательно для заполнения."
        else:
            return "Заполните все обязательные поля."

    # Ошибка, возбуждённая нашим триггером (RAISE EXCEPTION)
    if pgcode == 'P0001' or 'Объект (id=' in pgerror:
        # Извлекаем понятный текст, убираем CONTEXT
        match = re.search(r'Объект \(id=\d+\) уже сдаётся другому арендатору в этот день', pgerror)
        if match:
            return match.group(0)
        else:
            # На случай другого сообщения RAISE – показываем только первую строку
            return pgerror.split('\n')[0]

    # Прочие ошибки
    return f"Ошибка базы данных: {pgerror.split('CONTEXT:')[0].strip()}"