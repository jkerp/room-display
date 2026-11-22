"""Ansteuerung des Waveshare e-Papers inkl. Preview-Modus.

Unterstuetzte Modelle (config.yaml: display.model):
- epd7in5b_V2 : 7.5" e-Paper HAT (B), Schwarz/Weiss/ROT - auch fuer Boards
                mit V3-Logo (SKU 13505); Waveshare verwendet fuer V3 den
                gleichnamigen V2-Treiber.
- epd7in5_V2  : 7.5" e-Paper HAT, Schwarz/Weiss
- weitere Modelle der Waveshare-Bibliothek in gleicher Namenskonvention.

Ohne Hardware sorgt der Preview-Modus dafuer, dass gerenderte Ansichten
als PNG erscheinen und die Logik trotzdem testbar bleibt.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from PIL import Image

from .config import Config
from .render import split_channels

log = logging.getLogger(__name__)

try:
    import spidev  # noqa: F401
    import RPi.GPIO  # noqa: F401

    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False


class Display:
    """Abstraktion: echte Hardware oder PNG-Preview."""

    def __init__(self, cfg: Config, preview: bool = False):
        self.cfg = cfg
        self.preview = preview or not HARDWARE_AVAILABLE
        self._epd = None
        self._tri_color = bool(re.match(r"epd\d+in\d+b", cfg.display.model or ""))
        if not self.preview:
            self._init_hardware()

    def _init_hardware(self) -> None:
        try:
            module = importlib.import_module(f"waveshare_epd.{self.cfg.display.model}")
            self._epd = module.EPD()
            self._epd.init()
            self._epd.Clear()
            log.info("E-Paper initialisiert: %s (%dx%d, %s)",
                     self.cfg.display.model, self._epd.width, self._epd.height,
                     "S/W/R" if self._tri_color else "S/W")
        except Exception as exc:
            log.warning("E-Paper nicht erreichbar (%s) - weiter im Preview-Modus", exc)
            self._epd = None
            self.preview = True

    @property
    def is_preview(self) -> bool:
        return self._epd is None

    def show(self, image: Image.Image) -> None:
        rotated = self._apply_rotation(image)
        if self._epd is not None:
            if self._tri_color:
                black, red = split_channels(rotated)
                self._epd.display(self._epd.getbuffer(black), self._epd.getbuffer(red))
            else:
                self._epd.display(self._epd.getbuffer(rotated.convert("L")))
            self._last_refresh = datetime.now()
            return
        out_dir = Path(os.environ.get("ROOMDISPLAY_PREVIEW_DIR", str(self.cfg.base_dir / "preview")))
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        rotated.save(out_dir / name)
        log.info("Preview gespeichert: %s", out_dir / name)

    def sleep(self) -> None:
        """Panel in den Schlafmodus setzen (Waveshare-Empfehlung zwischen Refreshes)."""
        if self._epd is None:
            return
        try:
            self._epd.sleep()
        except Exception:
            self._epd = None

    def wake(self) -> None:
        """Panel wieder aufwecken; bei Fehler Hardware neu initialisieren."""
        if self._epd is None:
            self._init_hardware()
            return
        try:
            self._epd.init()
        except Exception as exc:
            log.warning("E-Paper-Wake fehlgeschlagen (%s) - Reinit", exc)
            self._epd = None
            self._init_hardware()

    def _apply_rotation(self, image: Image.Image) -> Image.Image:
        rotation = int(self.cfg.display.rotation) % 360
        if rotation == 90:
            return image.rotate(90, expand=True)
        if rotation == 180:
            return image.rotate(180)
        if rotation == 270:
            return image.rotate(270, expand=True)
        return image
