"""Find the festivals and family occasions that fall within a date range."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FestivalDate, Occasion, Person
from .festivals import FESTIVALS


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def on_year(month: int, day: int, year: int) -> date:
    """The occasion's date in `year`; 29 Feb falls on 28 Feb in other years."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


@dataclass
class Hit:
    kind: str  # festival | birthday | anniversary | other
    key: str  # festival key, "occasion:<id>" or "person:<id>"
    name: str  # display label, e.g. "Deepavali 2024", "Aadhya's 3rd birthday"
    date: date
    person_id: int | None = None

    def as_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key, "name": self.name, "date": self.date, "person_id": self.person_id}


@dataclass
class _Recurring:
    kind: str
    key: str
    name: str
    month: int
    day: int
    first_year: int | None
    person_id: int | None

    def label(self, year: int) -> str:
        n = year - self.first_year if self.first_year else None
        if self.kind == "birthday":
            if n == 0:
                return f"{self.name} is born"
            return f"{self.name}'s {ordinal(n)} birthday" if n and n > 0 else f"{self.name}'s birthday"
        if self.kind == "anniversary":
            if n == 0:
                return f"{self.name}: wedding day"
            return f"{self.name}: {ordinal(n)} anniversary" if n and n > 0 else f"{self.name}: anniversary"
        return self.name


class OccasionIndex:
    """Festival dates and family occasions, loaded once."""

    def __init__(self, s: Session) -> None:
        self.festivals = list(s.scalars(select(FestivalDate).order_by(FestivalDate.start)))
        self.recurring: list[_Recurring] = []
        linked_birthdays = set()
        for o in s.scalars(select(Occasion)):
            if o.kind == "birthday" and o.person_id:
                linked_birthdays.add(o.person_id)
            self.recurring.append(_Recurring(o.kind, f"occasion:{o.id}", o.name, o.month, o.day, o.year, o.person_id))
        # people with a name and birth date get a birthday automatically
        for p in s.scalars(select(Person).where(Person.birth_date.is_not(None), Person.name.is_not(None), ~Person.hidden)):
            if p.id not in linked_birthdays:
                b = p.birth_date
                self.recurring.append(_Recurring("birthday", f"person:{p.id}", p.name, b.month, b.day, b.year, p.id))

    def between(self, start: date, end: date) -> list[Hit]:
        hits: list[Hit] = []
        for f in self.festivals:
            if f.start <= end and f.end >= start:
                hits.append(Hit("festival", f.festival, f"{FESTIVALS.get(f.festival, f.festival)} {f.year}", f.date))
        for year in range(start.year, end.year + 1):
            for r in self.recurring:
                d = on_year(r.month, r.day, year)
                if r.first_year and year < r.first_year:
                    continue
                if start <= d <= end:
                    hits.append(Hit(r.kind, r.key, r.label(year), d, r.person_id))
        hits.sort(key=lambda h: (h.kind == "festival", h.date))  # family occasions first
        return hits


def span_days(start: date, end: date) -> int:
    return (end - start).days + 1


def nearby(start: date, end: date, slack_days: int = 0) -> tuple[date, date]:
    return start - timedelta(days=slack_days), end + timedelta(days=slack_days)
