"""Ansteuerung des Waveshare e-Papers (7.5 HAT B V3) inkl. Preview-Modus.

Der Waveshare-Treiber (pip-Paket `waveshare-epd` oder lokale Kopie der
Waveshare-e-Paper-Bibliothek) liefert das Modul `waveshare_epd.epd7in5_V3`.
Ohne Hardware sorgt der Preview-Modus dafuer, dass gerenderte Ansichten
als PNG erscheinen und die Logik trotzdem testbar bleibt.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PIL import Image

from .config import Config

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
        self._last_refresh: datetime | None = None
        if not self.preview:
            self._init_hardware()

    def _init_hardware(self) -> None:
        try:
            from waveshare_epd import epd7in5_V3

            self._epd = epd7in5_V3.EPD()
            self._epd.init()
            self._epd.Clear()
            log.info("E-Paper initialisiert: epd7in5_V3 (%dx%d)", self._epd.width, self._epd.height)
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
            self._epd.display(self._epd.getbuffer(rotated))
            self._last_refresh = datetime.now()
            return
        out_dir = Path(os.environ.get("ROOMDISPLAY_PREVIEW_DIR", str(self.cfg.base_dir / "preview")))
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        rotated.save(out_dir / name)
        log.info("Preview gespeichert: %s", out_dir / name)

    def sleep(self) -> None:
        """Panel in den Schlafmodus setzen (Waveshare-Empfehlung zwischen Refreshes)."""
        if self._epd is not None:
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
