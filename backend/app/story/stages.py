"""Life stages ("chapters") of Our Story: suggested from known dates, then user-editable."""

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Occasion, Person, StoryStage

EARLY_YEARS = "Early years"


def add_years(d: date, years: int) -> date:
    y = d.year + years
    return date(y, d.month, min(d.day, calendar.monthrange(y, d.month)[1]))


def suggest_stages(s: Session, person: Person, today: date | None = None) -> list[StoryStage]:
    """Replace earlier suggestions with stages derived from `person`'s birth date,
    their wedding anniversary and their children's birth dates. User-edited stages stay."""
    if person.birth_date is None:
        raise ValueError(f"Add a birth date for {person.name or 'this person'} first")
    today = today or date.today()
    b = person.birth_date

    for st in s.scalars(select(StoryStage).where(StoryStage.suggested)).all():
        s.delete(st)
    s.flush()
    kept_kinds = set(s.scalars(select(StoryStage.kind)))

    wedding = None
    for o in s.scalars(select(Occasion).where(Occasion.kind == "anniversary", Occasion.year.is_not(None))):
        d = date(o.year, o.month, min(o.day, calendar.monthrange(o.year, o.month)[1]))
        if d >= add_years(b, 16) and (wedding is None or d < wedding):
            wedding = d
    adult = wedding or add_years(b, 18)
    kids = sorted(
        p.birth_date for p in s.scalars(
            select(Person).where(Person.birth_date.is_not(None), ~Person.hidden, Person.id != person.id)
        )
        if p.birth_date >= adult
    )

    plan = [
        ("childhood", "Childhood", b),
        ("school", "School days", add_years(b, 5)),
        ("college", "College", add_years(b, 17)),
    ]
    if wedding is None or wedding > add_years(b, 23):
        plan.append(("career", "Finding my way", add_years(b, 22)))
    if wedding:
        plan.append(("marriage", "Marriage", wedding))
    if kids:
        plan.append(("kids", "Our little ones", kids[0]))

    created = []
    for kind, name, start in plan:
        if kind in kept_kinds or start > today:
            continue
        st = StoryStage(name=name, start=start, kind=kind, suggested=True)
        s.add(st)
        created.append(st)
    s.commit()
    return created


@dataclass
class Chapter:
    stage_id: int | None
    name: str
    kind: str
    start: date | None  # None = open start (early years)
    end: date | None  # exclusive; None = open end

    def contains(self, d: date) -> bool:
        return (self.start is None or d >= self.start) and (self.end is None or d < self.end)


def chapters(s: Session) -> list[Chapter]:
    stages = sorted(s.scalars(select(StoryStage)).all(), key=lambda st: (st.start, st.id))
    if not stages:
        return [Chapter(None, "", "all", None, None)]
    out = [Chapter(None, EARLY_YEARS, "early", None, stages[0].start)]
    for i, st in enumerate(stages):
        end = stages[i + 1].start if i + 1 < len(stages) else None
        out.append(Chapter(st.id, st.name, st.kind, st.start, end))
    return out


def age_range(birth: date | None, ch: Chapter) -> str | None:
    """'Age 5 – 17' style label for a chapter, relative to the story owner's birth."""
    if birth is None or ch.start is None:
        return None

    def age(d: date) -> int:
        return d.year - birth.year - ((d.month, d.day) < (birth.month, birth.day))

    a = max(0, age(ch.start))
    if ch.end is None:
        return f"From age {a}"
    z = age(ch.end)
    return f"Age {a}" if z <= a else f"Age {a} – {z}"
