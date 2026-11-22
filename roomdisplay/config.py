"""Konfiguration laden."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DisplayConfig:
    model: str = "epd7in5_V3"
    width: int = 800
    height: int = 480
    rotation: int = 0
    min_refresh_interval: int = 20


@dataclass
class ViewsConfig:
    sequence: list = field(default_factory=lambda: ["status", "day", "status", "week"])
    interval: int = 180


@dataclass
class CalendarConfig:
    data_dir: str = "data"
    filename: str = "raumbelegung.ics"
    stale_days: int = 35


@dataclass
class RoomConfig:
    name: str = "Raum"
    location: str = ""


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    username: str = "admin"
    password: str = ""


@dataclass
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    views: ViewsConfig = field(default_factory=ViewsConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    room: RoomConfig = field(default_factory=RoomConfig)
    web: WebConfig = field(default_factory=WebConfig)
    base_dir: Path = Path(".")

    @property
    def ics_path(self) -> Path:
        return self.base_dir / self.calendar.data_dir / self.calendar.filename


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Konfiguration aus YAML lesen; fehlende Werte durch Defaults ersetzen."""
    cfg = Config()
    if path is None:
        path = os.environ.get("ROOMDISPLAY_CONFIG", "config.yaml")
    path = Path(path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        for section in ("display", "views", "calendar", "room", "web"):
            values = raw.get(section) or {}
            target = getattr(cfg, section)
            for key, value in values.items():
                if hasattr(target, key):
                    setattr(target, key, value)
    cfg.base_dir = path.resolve().parent
    cfg.ics_path.parent.mkdir(parents=True, exist_ok=True)
    env_password = os.environ.get("ROOMDISPLAY_WEB_PASSWORD")
    if env_password:
        cfg.web.password = env_password
    return cfg
