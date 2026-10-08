"""Generate backend/app/occasions/festivals_telugu.json (dev tool, not used at runtime).

    backend\\.venv\\Scripts\\python -m pip install ephem
    backend\\.venv\\Scripts\\python scripts\\gen_festival_dates.py [--check]

Computes festival days from sun/moon positions using common Panchang rules
for Hyderabad (amanta lunar months, Lahiri ayanamsa, IST):

- Sankranti         sun enters sidereal Makara; next day if after sunset.
                    Bhogi = day before, Kanuma = day after.
- Ugadi             Chaitra shukla pratipada: first sunrise after the new moon
                    that starts Chaitra (adhika Chaitra if there is one).
- Holi              day after Phalguna purnima prevailing at sunset (Holika dahan).
- Raksha Bandhan    Shravana purnima prevailing in the afternoon (aparahna).
- Ganesh Chaturthi  Bhadrapada shukla chaturthi prevailing at midday (madhyahna).
- Vijayadashami     Ashvin shukla dashami prevailing in the afternoon.
- Deepavali         Ashvin amavasya prevailing at dusk (pradosh);
                    Naraka Chaturdashi = day before.

Regional practice sometimes differs by a day; the app lets the user edit dates.
"""

import argparse
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import ephem

LAT, LON, ELEV = "17.385", "78.4867", 500  # Hyderabad
IST = timedelta(hours=5, minutes=30)
YEARS = range(2000, 2031)
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "occasions" / "festivals_telugu.json"

MONTHS = ["Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
          "Ashvin", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna"]


# ---------- astronomy helpers (times are ephem UTC dates) ----------

def to_ist(d: ephem.Date) -> datetime:
    return ephem.Date(d).datetime() + IST


def from_ist(dt: datetime) -> ephem.Date:
    return ephem.Date(dt - IST)


def ecl_lon(body, when) -> float:
    body.compute(when, epoch=when)
    return math.degrees(ephem.Ecliptic(body, epoch=when).lon)


def elongation(when) -> float:
    return (ecl_lon(ephem.Moon(), when) - ecl_lon(ephem.Sun(), when)) % 360


def tithi(when) -> int:
    """0..29: 0 = shukla pratipada, 14 = purnima, 29 = amavasya."""
    return int(elongation(when) // 12)


def ayanamsa(when) -> float:
    """Lahiri ayanamsa (degrees), linear approximation, accurate to ~0.01 deg in this range."""
    years = (ephem.Date(when) - ephem.Date("2000/1/1 12:00")) / 365.25
    return 23.85306 + years * (50.2876 / 3600)


def sidereal_sun(when) -> float:
    return (ecl_lon(ephem.Sun(), when) - ayanamsa(when)) % 360


def observer(day: date) -> ephem.Observer:
    o = ephem.Observer()
    o.lat, o.lon, o.elevation = LAT, LON, ELEV
    o.horizon = "-0:34"
    o.pressure = 0
    o.date = from_ist(datetime(day.year, day.month, day.day))
    return o


def sunrise(day: date) -> ephem.Date:
    return observer(day).next_rising(ephem.Sun())


def sunset(day: date) -> ephem.Date:
    return observer(day).next_setting(ephem.Sun())


def at_ist(day: date, hour: float) -> ephem.Date:
    return from_ist(datetime(day.year, day.month, day.day) + timedelta(hours=hour))


# ---------- lunar months ----------

def lunar_months(year: int) -> list[dict]:
    """Amanta months starting from new moons between Nov of year-1 and Feb of year+1."""
    nms = []
    d = ephem.Date(f"{year - 1}/11/1")
    while d < ephem.Date(f"{year + 1}/2/1"):
        d = ephem.next_new_moon(d)
        nms.append(ephem.Date(d))
        d = ephem.Date(d + 1)
    months = []
    for a, b in zip(nms, nms[1:]):
        rasi = int(sidereal_sun(a) // 30)
        rasi_next = int(sidereal_sun(b) // 30)
        months.append({
            "name": MONTHS[(rasi + 1) % 12],
            "start": a,  # new moon
            "end": b,
            "adhika": rasi == rasi_next,  # sun didn't change sign during the month
        })
    return months


def find_month(year: int, name: str, nija: bool = True) -> dict:
    """The month `name` whose span falls mostly in `year` (nija unless asked otherwise)."""
    cands = [m for m in lunar_months(year) if m["name"] == name and to_ist(m["end"]).year == year]
    if nija:
        cands = [m for m in cands if not m["adhika"]] or cands
    return cands[0] if nija else cands[0]


def month_days(month: dict, want: int) -> list[date]:
    """Civil days on which tithi `want` of this month can fall."""
    start, end = to_ist(month["start"]).date(), to_ist(month["end"]).date()
    if want == 29:  # amavasya ends the month
        start = end - timedelta(days=2)
    days, d = [], start
    while d <= end + timedelta(days=1):
        days.append(d)
        d += timedelta(days=1)
    return days


def matching_days(month: dict, want: int, moment) -> list[date]:
    return [d for d in month_days(month, want) if tithi(moment(d)) == want]


def tithi_day(month: dict, want: int, moment, last: bool = False) -> date:
    """First (or last) day where the tithi at moment(day) is `want`; else the sunrise tithi."""
    days = matching_days(month, want, moment) or matching_days(month, want, sunrise)
    return days[-1] if last else days[0]


def in_bhadra(when) -> bool:
    """Vishti karana during purnima: the first half of the tithi."""
    return 168 <= elongation(when) < 174


# ---------- festivals ----------

def sankranti(year: int) -> date:
    # bisect for the sun crossing sidereal 270 deg in mid-January
    lo, hi = ephem.Date(f"{year}/1/10"), ephem.Date(f"{year}/1/18")
    for _ in range(40):
        mid = ephem.Date((lo + hi) / 2)
        if (sidereal_sun(mid) - 270) % 360 < 180:
            hi = mid
        else:
            lo = mid
    t = to_ist(hi)
    day = t.date()
    if hi > sunset(day):
        day += timedelta(days=1)
    return day


def ugadi(year: int) -> date:
    chaitra = find_month(year, "Chaitra", nija=False)  # year starts with adhika Chaitra if any
    day = to_ist(chaitra["start"]).date()
    if sunrise(day) > chaitra["start"]:
        return day
    nxt = day + timedelta(days=1)
    # kshaya pratipada (never at a sunrise) is observed on the day it begins
    return nxt if tithi(sunrise(nxt)) == 0 else day


def raksha_bandhan(shravana: dict) -> date:
    """Purnima in the afternoon, avoiding Bhadra: then next day if purnima is there at sunrise."""
    day = tithi_day(shravana, 14, lambda d: at_ist(d, 14.5))
    nxt = day + timedelta(days=1)
    if in_bhadra(at_ist(day, 14.5)) and tithi(sunrise(nxt)) == 14:
        return nxt
    return day


def festivals(year: int) -> dict[str, dict]:
    phalguna = find_month(year, "Phalguna")
    shravana = find_month(year, "Shravana")
    bhadrapada = find_month(year, "Bhadrapada")
    ashvin = find_month(year, "Ashvin")

    pradosh = lambda d: ephem.Date(sunset(d) + 40 * ephem.minute)  # noqa: E731
    aparahna_start = lambda d: at_ist(d, 13.25)  # noqa: E731
    madhyahna = lambda d: at_ist(d, 12.25)  # noqa: E731

    s = sankranti(year)
    holika = tithi_day(phalguna, 14, sunset)
    diwali = tithi_day(ashvin, 29, pradosh)
    return {
        "sankranti": {"date": s, "start": s - timedelta(days=1), "end": s + timedelta(days=1)},
        "ugadi": {"date": ugadi(year)},
        "holi": {"date": holika + timedelta(days=1), "start": holika},
        "raksha_bandhan": {"date": raksha_bandhan(shravana)},
        "ganesh_chaturthi": {"date": tithi_day(bhadrapada, 3, madhyahna)},
        # dashami at the start of aparahna; if on two days, the later one
        "dussehra": {"date": tithi_day(ashvin, 9, aparahna_start, last=True)},
        "diwali": {"date": diwali, "start": diwali - timedelta(days=1)},
    }


# Published dates for recent years (Telugu states where they differ). A set means either is accepted.
KNOWN = {
    "sankranti": {2018: "01-14", 2019: "01-15", 2020: "01-15", 2021: "01-14", 2022: {"01-14", "01-15"},
                  2023: "01-15", 2024: "01-15", 2025: "01-14"},
    "ugadi": {2018: "03-18", 2019: "04-06", 2020: "03-25", 2021: "04-13", 2022: "04-02", 2023: "03-22",
              2024: "04-09", 2025: "03-30"},
    "holi": {2018: "03-02", 2019: "03-21", 2020: "03-10", 2021: "03-29", 2022: "03-18", 2023: "03-08",
             2024: "03-25", 2025: "03-14"},
    "raksha_bandhan": {2018: "08-26", 2019: "08-15", 2020: "08-03", 2021: "08-22", 2022: {"08-11", "08-12"},
                       2023: {"08-30", "08-31"}, 2024: "08-19", 2025: "08-09"},
    "ganesh_chaturthi": {2018: "09-13", 2019: "09-02", 2020: "08-22", 2021: "09-10", 2022: "08-31",
                         2023: {"09-18", "09-19"}, 2024: "09-07", 2025: "08-27"},
    "dussehra": {2018: {"10-18", "10-19"}, 2019: "10-08", 2020: {"10-25", "10-26"}, 2021: "10-15",
                 2022: "10-05", 2023: {"10-23", "10-24"}, 2024: "10-12", 2025: "10-02"},
    "diwali": {2018: {"11-06", "11-07"}, 2019: "10-27", 2020: "11-14", 2021: "11-04", 2022: "10-24",
               2023: "11-12", 2024: {"10-31", "11-01"}, 2025: {"10-20", "10-21"}},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only compare with known dates")
    args = ap.parse_args()

    table: dict[str, dict] = {}
    for y in (sorted({y for v in KNOWN.values() for y in v}) if args.check else YEARS):
        for key, v in festivals(y).items():
            table.setdefault(key, {})[str(y)] = {k: d.isoformat() for k, d in v.items()}

    bad = 0
    for key, years in KNOWN.items():
        for y, want in years.items():
            got = table[key][str(y)]["date"][5:]
            ok = got in (want if isinstance(want, set) else {want})
            bad += not ok
            if not ok or args.check:
                print(f"{'ok ' if ok else 'BAD'} {key:17} {y}: computed {got}, published {want}")
            if not ok and not args.check and isinstance(want, str):
                # published date wins; shift the optional start/end by the same amount
                entry = table[key][str(y)]
                shift = date.fromisoformat(f"{y}-{want}") - date.fromisoformat(entry["date"])
                for k in list(entry):
                    entry[k] = (date.fromisoformat(entry[k]) + shift).isoformat()
                entry["source"] = "published"
                print(f"    using published date {y}-{want}")
    print(f"{bad} mismatches against {sum(len(v) for v in KNOWN.values())} published dates")
    if args.check:
        return 1 if bad else 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "region": "telugu",
        "location": "Hyderabad",
        "generated_by": "scripts/gen_festival_dates.py",
        "festivals": table,
    }, indent=1))
    print(f"wrote {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
