"""Age at the time a photo was taken."""

from datetime import date


def age_parts(birth: date, when: date) -> tuple[int, int, int] | None:
    """(years, months, days) from birth to when; None if `when` is before birth."""
    if when < birth:
        return None
    months = (when.year - birth.year) * 12 + (when.month - birth.month)
    if when.day < birth.day:
        months -= 1
    years, months = divmod(months, 12)
    days = (when - birth).days if years == 0 and months == 0 else 0
    return years, months, days


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def age_label(birth: date | None, when: date) -> str | None:
    """Friendly label: 'Newborn', '12 days', '8 mos', '3 yrs 2 mos', '34 yrs', 'Before birth'."""
    if birth is None:
        return None
    parts = age_parts(birth, when)
    if parts is None:
        return "Before birth"
    years, months, days = parts
    if years == 0 and months == 0:
        return "Newborn" if days == 0 else _plural(days, "day", "days")
    if years == 0:
        return _plural(months, "mo", "mos")
    if years >= 18 or months == 0:
        return _plural(years, "yr", "yrs")
    return f"{_plural(years, 'yr', 'yrs')} {_plural(months, 'mo', 'mos')}"
