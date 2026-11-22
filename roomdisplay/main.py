"""Hauptloop: ICS beobachten, Ansichten abwechselnd auf das E-Paper bringen.

Nur bei tatsaechlicher Aenderung wird neu gezeichnet (E-Paper schonen):
- ICS-Datei geaendert (Web-Upload oder manueller Austausch),
- Ansichtswechsel im konfigurierten Rhythmus,
- Terminbeginn oder -ende.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

from .config import Config, load_config
from .display import Display
from .render import Fonts, render
from .schedule import IcsError, Schedule, load_calendar

log = logging.getLogger("roomdisplay")

CHECK_INTERVAL = 10
RELOAD_RETRY = 300


def _current_view(cfg: Config) -> str:
    views = cfg.views.sequence or ["status"]
    cycle_seconds = max(30, int(cfg.views.interval))
    slot = int(datetime.now().timestamp() // cycle_seconds) % len(views)
    return views[slot]


def _fingerprint(cfg: Config) -> tuple[int, int] | None:
    try:
        stat = cfg.ics_path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _signature(cfg: Config, schedule: Schedule, fingerprint) -> tuple:
    view = _current_view(cfg)
    current, upcoming = schedule.current_or_next()
    occ_key = (
        current.end.strftime("%Y%m%d%H%M") if current else None,
        upcoming.start.strftime("%Y%m%d%H%M") if upcoming else None,
    )
    return (view, fingerprint, occ_key)


def run_loop(cfg: Config, preview: bool, once: bool, view: str | None) -> int:
    display = Display(cfg, preview=preview)
    fonts = Fonts.load(cfg.base_dir)

    schedule: Schedule | None = None
    last_fingerprint = object()
    last_signature = None
    last_attempt = 0.0
    last_draw = 0.0

    while True:
        fingerprint = _fingerprint(cfg)
        need_draw = False

        if fingerprint != last_fingerprint:
            try:
                schedule = Schedule(load_calendar(cfg.ics_path), days=7)
                last_fingerprint = fingerprint
                last_attempt = time.time()
                need_draw = True
                log.info("ICS-Datei uebernommen (%s)", cfg.ics_path)
            except IcsError as exc:
                log.warning("ICS nicht verwendbar: %s - Anzeige bleibt", exc)
                last_attempt = time.time()
        elif schedule is None and time.time() - last_attempt > RELOAD_RETRY:
            last_attempt = time.time()
            try:
                schedule = Schedule(load_calendar(cfg.ics_path), days=7)
                need_draw = True
                log.info("ICS-Datei spaeter geladen")
            except IcsError:
                pass

        if schedule is not None:
            signature = _signature(cfg, schedule, fingerprint)
            if view is not None:
                signature = (view,) + signature[1:]
            if signature != last_signature:
                need_draw = True
            if need_draw:
                since = time.time() - last_draw
                if not display.is_preview and since < cfg.display.min_refresh_interval:
                    need_draw = False
                else:
                    target = view or signature[0]
                    try:
                        image = render(cfg, schedule, target, fonts)
                        display.wake()
                        display.show(image)
                        display.sleep()
                        last_signature = signature
                        last_draw = time.time()
                        log.info("Anzeige aktualisiert: %s", target)
                    except Exception:
                        log.exception("Zeichnen fehlgeschlagen - naechster Versuch folgt")

        if once:
            return 0
        time.sleep(CHECK_INTERVAL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Raumbelegungs-Display")
    parser.add_argument("--config", help="Pfad zur config.yaml")
    parser.add_argument("--preview", action="store_true",
                        help="ohne E-Paper: Ansichten als PNG speichern")
    parser.add_argument("--once", action="store_true",
                        help="einmalig zeichnen und beenden")
    parser.add_argument("--view", choices=["status", "day", "week"],
                        help="feste Ansicht statt automatischem Wechsel")
    parser.add_argument("--web", action="store_true",
                        help="Web-Upload-Server starten statt Display-Loop")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    if args.web:
        from .web import run_web

        run_web(cfg)
        return 0
    return run_loop(cfg, preview=args.preview, once=args.once, view=args.view)


if __name__ == "__main__":
    sys.exit(main())
