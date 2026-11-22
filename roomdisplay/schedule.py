"""ICS-Datei bereinigen, validieren und Termine expandieren.

Die HISinOne-Exporte enthalten einige Sonderheiten, die hier abgefangen
werden:
- harte Zeilenumbrueche nach RFC 5545 inkl. Fortsetzungszeilen,
- EXDATE-Zeilen, deren Fortsetzung nur aus einem Leerzeichen besteht
  (danach haengen an Datumswerten Leerzeichen),
- Zeitzonen-Definition (VTIMEZONE) und RRULE/EXDATE-Aufloesung, die
  recurring-ical-events uebernimmt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

import icalendar
import recurring_ical_events

log = logging.getLogger(__name__)

_EMPTY_FOLD = re.compile(r"\r?\n[ \t]+(?=\r?\n)")
_DUPLICATED_CODE = re.compile(r"^(\S+) \1: ")


class IcsError(Exception):
    """Die ICS-Datei ist unlesbar oder ungueltig."""


def sanitize(raw: str) -> str:
    """Leere Fortsetzungszeilen entfernen (HISinOne haengt leerzeilen mit
    Leerzeichen an EXDATE-Zeilen); datentragende Leerzeichen vor Umbruechen
    bleiben erhalten."""
    return _EMPTY_FOLD.sub("\r\n", raw)


def clean_summary(text: str) -> str:
    """HISinOne wiederholt den Kurscode, z. B. 'astro8402 astro8402: ...'."""
    return _DUPLICATED_CODE.sub(r"\1: ", text)


def parse_calendar(raw: bytes | str) -> icalendar.Calendar:
    """Kalender einlesen und auf Grobstruktur pruefen."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            raw = raw.decode("latin-1")
    cleaned = sanitize(raw)
    try:
        calendar = icalendar.Calendar.from_ical(cleaned)
    except Exception as exc:  # icalendar wirft diverse Fehlertypen
        raise IcsError(f"ICS nicht parsebar: {exc}") from exc
    if not any(component.name == "VEVENT" for component in calendar.walk()):
        raise IcsError("ICS enthaelt keine Termine (VEVENT)")
    return calendar


def load_calendar(path: Path) -> icalendar.Calendar:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IcsError(f"ICS nicht lesbar: {exc}") from exc
    return parse_calendar(raw)


@dataclass
class Occurrence:
    """Ein konkreter Termin-Auftritt an einem Tag."""

    start: datetime
    end: datetime
    summary: str
    category: str = ""
    location: str = ""

    @property
    def is_ongoing(self) -> bool:
        now = datetime.now(self.start.tzinfo)
        return self.start <= now < self.end

    @property
    def is_past(self) -> bool:
        now = datetime.now(self.start.tzinfo)
        return now >= self.end

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


class Schedule:
    """Auf einen Zeitraum expandierte Termine eines Kalenders."""

    def __init__(self, calendar: icalendar.Calendar, days: int = 7):
        self._calendar = calendar
        self.days = days
        self.loaded_at = datetime.now().astimezone()

    @staticmethod
    def _fmt_time(moment: datetime) -> str:
        return moment.strftime("%H:%M")

    def occurrences_between(self, begin: datetime, end: datetime) -> list[Occurrence]:
        raw_events = recurring_ical_events.of(self._calendar).between(begin, end)
        result: list[Occurrence] = []
        for event in raw_events:
            try:
                start = self._as_datetime(event["DTSTART"].dt)
                end_raw = event.get("DTEND")
                stop = self._as_datetime(end_raw.dt) if end_raw else start + timedelta(hours=1)
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Termin ohne gueltige Zeit uebersprungen: %s", exc)
                continue
            result.append(
                Occurrence(
                    start=start,
                    end=stop,
                    summary=clean_summary(str(event.get("SUMMARY") or "Termin").strip()),
                    category=_categories(event),
                    location=str(event.get("LOCATION") or "").strip(),
                )
            )
        result.sort(key=lambda occ: occ.start)
        return result

    @staticmethod
    def _as_datetime(value) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=_local_tz())
            return value
        if isinstance(value, date):
            return datetime.combine(value, time(0, 0), tzinfo=_local_tz())
        raise TypeError(f"Unerwarteter Datumstyp: {type(value)!r}")

    def for_day(self, day: date) -> list[Occurrence]:
        begin = datetime.combine(day, time(0, 0), tzinfo=_local_tz())
        end = begin + timedelta(days=1)
        return self.occurrences_between(begin, end)

    def week_overview(self, first_day: date, days: int = 7) -> list[list[Occurrence]]:
        return [self.for_day(first_day + timedelta(days=offset)) for offset in range(days)]

    def current_or_next(self, now: datetime | None = None) -> tuple[Occurrence | None, Occurrence | None]:
        """Laufenden und naechsten Termin relativ zu *now* liefern."""
        now = now or datetime.now(_local_tz())
        day = now.date()
        candidates = self.for_day(day)
        if not candidates:
            candidates = self.occurrences_between(now, now + timedelta(days=7))
        current = next((occ for occ in candidates if occ.is_ongoing), None)
        upcoming = next((occ for occ in candidates if occ.start > now), None)
        return current, upcoming

    def last_modified_raw(self) -> datetime | None:
        stamps = [
            self._as_datetime(ev["LAST-MODIFIED"].dt)
            for ev in self._calendar.walk("VEVENT")
            if ev.get("LAST-MODIFIED")
        ]
        return max(stamps) if stamps else None


def _local_tz():
    return datetime.now().astimezone().tzinfo


def _categories(event) -> str:
    cats = event.get("CATEGORIES")
    if cats is None:
        return ""
    if hasattr(cats, "cats"):
        return ", ".join(str(c) for c in cats.cats)
    if isinstance(cats, (list, tuple)):
        return ", ".join(str(c) for c in cats)
    return str(cats)


def expand_days(occurrences: Iterable[Occurrence], day: date) -> list[Occurrence]:
    """ Mehrtaegige Termine auf Folgetage aufteilen (fuer Tageslisten)."""
    result = []
    for occ in occurrences:
        cursor = occ.start.date()
        while cursor <= occ.end.date():
            if cursor == day:
                result.append(occ)
            cursor += timedelta(days=1)
    return result
