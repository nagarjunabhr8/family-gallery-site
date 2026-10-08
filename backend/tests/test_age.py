from datetime import date

import pytest

from app.people.age import age_label, age_parts


@pytest.mark.parametrize(
    "birth, when, label",
    [
        (date(2024, 1, 10), date(2024, 1, 10), "Newborn"),
        (date(2024, 1, 10), date(2024, 1, 11), "1 day"),
        (date(2024, 1, 10), date(2024, 2, 5), "26 days"),
        (date(2024, 1, 10), date(2024, 2, 10), "1 mo"),
        (date(2024, 1, 10), date(2024, 9, 9), "7 mos"),
        (date(2024, 1, 10), date(2025, 1, 10), "1 yr"),
        (date(2019, 6, 15), date(2022, 11, 26), "3 yrs 5 mos"),
        (date(1990, 3, 1), date(2024, 8, 17), "34 yrs"),
        (date(2024, 1, 10), date(2023, 12, 1), "Before birth"),
    ],
)
def test_age_label(birth, when, label):
    assert age_label(birth, when) == label


def test_leap_day_birthday():
    assert age_parts(date(2020, 2, 29), date(2021, 2, 28)) == (0, 11, 0)
    assert age_parts(date(2020, 2, 29), date(2021, 3, 1)) == (1, 0, 0)


def test_no_birth_date():
    assert age_label(None, date(2024, 1, 1)) is None
