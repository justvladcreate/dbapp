

def format_currency(value) -> str:
    """Форматирует число как денежную сумму: 1234567 -> '1 234 567 ₽'."""
    try:
        num = int(float(value))
        return f"{num:,} ₽".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)