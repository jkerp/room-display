"""Rendering der drei Ansichten mit Pillow (800x480, Schwarz/Weiss).

Das 7.5" HAT B (V3) ist zweifarbig. 'Invertierte' Flaechen (schwarzer
Grund, weisse Schrift) erzeugen visuelle Abstufung ohne Grautoene.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config
from .schedule import Occurrence, Schedule, _local_tz

log = logging.getLogger(__name__)

WHITE = 255
BLACK = 0

_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


@dataclass
class Fonts:
    tiny: ImageFont.FreeTypeFont
    regular: ImageFont.FreeTypeFont
    bold: ImageFont.FreeTypeFont
    big: ImageFont.FreeTypeFont
    huge: ImageFont.FreeTypeFont
    header: ImageFont.FreeTypeFont
    sub: ImageFont.FreeTypeFont

    @classmethod
    def load(cls, base_dir: Path) -> "Fonts":
        search = [base_dir / "fonts", Path("/usr/share/fonts/truetype/dejavu")]
        folder = next((f for f in search if (f / "DejaVuSans.ttf").exists()), None)
        if folder is None:
            log.warning("Keine DejaVu-Fonts gefunden - Fallback auf Pixelschrift")
            default = ImageFont.load_default()
            return cls(tiny=default, regular=default, bold=default, big=default,
                       huge=default, header=default, sub=default)
        path = lambda name: str(folder / name)  # noqa: E731
        return cls(
            tiny=ImageFont.truetype(path("DejaVuSans.ttf"), 20),
            regular=ImageFont.truetype(path("DejaVuSans.ttf"), 26),
            bold=ImageFont.truetype(path("DejaVuSans-Bold.ttf"), 28),
            big=ImageFont.truetype(path("DejaVuSans-Bold.ttf"), 46),
            huge=ImageFont.truetype(path("DejaVuSans-Bold.ttf"), 132),
            header=ImageFont.truetype(path("DejaVuSans-Bold.ttf"), 38),
            sub=ImageFont.truetype(path("DejaVuSans.ttf"), 26),
        )


def _fmt_day(day: date) -> str:
    return f"{_WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.')}"


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "\u2026", font=font) > max_w:
        text = text[:-1]
    return text + "\u2026"


def render(cfg: Config, schedule: Schedule, view: str, fonts: Fonts) -> Image.Image:
    if view == "status":
        return render_status(cfg, schedule, fonts)
    if view == "day":
        return render_day(cfg, schedule, fonts)
    if view == "week":
        return render_week(cfg, schedule, fonts)
    raise ValueError(f"Unbekannte Ansicht: {view}")


def _header(draw: ImageDraw.ImageDraw, cfg: Config, fonts: Fonts, subtitle: str, width: int) -> int:
    """Schwarzer Kopfbalken mit Raumnamen; gibt Unterkante zurueck."""
    top, height = 0, 72
    draw.rectangle([0, top, width - 1, top + height - 1], fill=BLACK)
    draw.text((24, top + 17), cfg.room.name, font=fonts.header, fill=WHITE)
    sub_w = draw.textlength(subtitle, font=fonts.sub)
    draw.text((width - 24 - sub_w, top + 23), subtitle, font=fonts.sub, fill=WHITE)
    return top + height


def _footer(draw: ImageDraw.ImageDraw, cfg: Config, fonts: Fonts, schedule: Schedule, width: int, height: int) -> None:
    age_days = (datetime.now(_local_tz()).date() - schedule.loaded_at.date()).days
    text = f"{cfg.room.location}   \u00b7   ICS vom {schedule.loaded_at.strftime('%d.%m.%Y %H:%M')}"
    if age_days >= cfg.calendar.stale_days:
        text += "   \u00b7   Kalenderdatei alt - bitte aktualisieren"
    y = height - 40
    draw.line([16, y - 10, width - 16, y - 10], fill=BLACK, width=2)
    draw.text((24, y), _truncate(draw, text, fonts.tiny, width - 48), font=fonts.tiny, fill=BLACK)


def render_status(cfg: Config, schedule: Schedule, fonts: Fonts) -> Image.Image:
    image = Image.new("L", (cfg.display.width, cfg.display.height), WHITE)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    now = datetime.now(_local_tz())
    current, upcoming = schedule.current_or_next(now)

    subtitle = f"Stand {schedule.loaded_at.strftime('%H:%M')}"
    y = _header(draw, cfg, fonts, subtitle, width)

    if current is not None:
        busy = f"bis {current.end.strftime('%H:%M')} Uhr"
        title = _truncate(draw, current.summary, fonts.big, width - 48)
        time_str = (f"{current.start.strftime('%H:%M')} - {current.end.strftime('%H:%M')} Uhr"
                    + (f"   \u00b7   {current.category}" if current.category else ""))
        remaining = int((current.end - now).total_seconds() // 60)
        remaining_text = f"noch {remaining} min"
        rem_w = draw.textlength(remaining_text, font=fonts.header)
        draw.text((28, y + 24), "BELEGT", font=fonts.huge, fill=BLACK)
        draw.text((28, y + 208), busy, font=fonts.big, fill=BLACK)
        draw.text((width - 28 - rem_w, y + 216), remaining_text, font=fonts.header, fill=BLACK)
        draw.text((28, y + 300), title, font=fonts.regular, fill=BLACK)
        draw.text((28, y + 340), _truncate(draw, time_str, fonts.regular, width - 56), font=fonts.regular, fill=BLACK)
        return image

    if upcoming is not None and upcoming.start.date() == now.date():
        free = f"frei bis {upcoming.start.strftime('%H:%M')} Uhr"
    elif upcoming is not None:
        ahead = (upcoming.start.date() - now.date()).days
        free = "frei - nächster Termin heute" if ahead == 0 else (
            "frei - nächster Termin morgen" if ahead == 1
            else f"frei - nächster Termin in {ahead} Tagen")
    else:
        free = "frei - keine Termine diese Woche"
    draw.text((28, y + 24), "FREI", font=fonts.huge, fill=BLACK)
    draw.text((28, y + 208), _truncate(draw, free, fonts.header, width - 56), font=fonts.header, fill=BLACK)
    if upcoming is not None:
        title = _truncate(draw, upcoming.summary, fonts.regular, width - 56)
        time_str = (f"{_fmt_day(upcoming.start.date())}   "
                    f"{upcoming.start.strftime('%H:%M')} - {upcoming.end.strftime('%H:%M')} Uhr")
        draw.text((28, y + 300), title, font=fonts.regular, fill=BLACK)
        draw.text((28, y + 340), _truncate(draw, time_str, fonts.regular, width - 56), font=fonts.regular, fill=BLACK)
    return image


def render_day(cfg: Config, schedule: Schedule, fonts: Fonts) -> Image.Image:
    image = Image.new("L", (cfg.display.width, cfg.display.height), WHITE)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    today = date.today()
    y = _header(draw, cfg, fonts, _fmt_day(today), width)

    occurrences = schedule.for_day(today)
    if not occurrences:
        draw.text((28, y + 80), "Heute keine Termine", font=fonts.big, fill=BLACK)
        _footer(draw, cfg, fonts, schedule, width, height)
        return image

    row_h = 76
    for occ in occurrences:
        if y > height - 96:
            break
        ongoing = occ.is_ongoing
        if ongoing:
            draw.rectangle([12, y - 6, width - 12, y + row_h - 14], fill=BLACK)
        fg = WHITE if ongoing else BLACK
        draw.text((24, y), occ.start.strftime("%H:%M"), font=fonts.bold, fill=fg)
        draw.text((24, y + 34), occ.end.strftime("%H:%M"), font=fonts.tiny, fill=fg)
        title = _truncate(draw, occ.summary, fonts.regular, width - 260)
        draw.text((150, y), title, font=fonts.regular, fill=fg)
        if occ.category:
            draw.text((150, y + 34), occ.category, font=fonts.tiny, fill=fg)
        duration = int(occ.duration.total_seconds() // 60)
        dur = f"{duration} min"
        dur_w = draw.textlength(dur, font=fonts.regular)
        draw.text((width - 40 - dur_w, y), dur, font=fonts.regular, fill=fg)
        y += row_h

    _footer(draw, cfg, fonts, schedule, width, height)
    return image


def render_week(cfg: Config, schedule: Schedule, fonts: Fonts) -> Image.Image:
    image = Image.new("L", (cfg.display.width, cfg.display.height), WHITE)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    today = date.today()
    y = _header(draw, cfg, fonts, "Nächste 7 Tage", width)

    body_top = y + 8
    row_h = (height - body_top - 56) / 7.0

    for offset in range(7):
        day = today + _timedelta_days(offset)
        occurrences = schedule.for_day(day)
        top = int(body_top + offset * row_h)
        draw.line([16, top, width - 16, top], fill=BLACK, width=2)
        label = f"{_WEEKDAYS[day.weekday()][:2]}  {day.strftime('%d.%m.')}"
        draw.text((24, top + 6), label, font=fonts.bold, fill=BLACK)
        if not occurrences:
            draw.text((200, top + 8), "frei", font=fonts.regular, fill=BLACK)
            continue
        yy = top + 6
        max_rows = max(1, int((row_h - 12) // 30))
        for text in _compact_lines(occurrences)[:max_rows]:
            draw.text((200, yy), _truncate(draw, text, fonts.tiny, width - 224), font=fonts.tiny, fill=BLACK)
            yy += 28
        if len(occurrences) > max_rows:
            more = f"+ {len(occurrences) - max_rows} weitere"
            draw.text((200, yy), more, font=fonts.tiny, fill=BLACK)

    _footer(draw, cfg, fonts, schedule, width, height)
    return image


def _compact_lines(occurrences: list[Occurrence]) -> list[str]:
    texts = []
    for occ in occurrences:
        times = f"{occ.start.strftime('%H:%M')}-{occ.end.strftime('%H:%M')}"
        title = occ.summary if len(occ.summary) <= 36 else occ.summary[:35] + "\u2026"
        texts.append(f"{times}  {title}")
    return texts


def _timedelta_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)
