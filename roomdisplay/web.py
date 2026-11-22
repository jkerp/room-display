"""Web-Server fuer ICS-Upload im LAN.

Upload ueber http://<display-ip>:8080/ - die Datei wird geprueft und
nur bei gueltigem Kalender atomar uebernommen; die Vorversion bleibt
als Backup liegen.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from flask import (Flask, Response, flash, redirect, render_template_string,
                   request, url_for)

from .config import Config
from .schedule import IcsError, parse_calendar

log = logging.getLogger(__name__)

PAGE = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ room }} - Kalender-Upload</title>
  <style>
    body { font-family: sans-serif; background: #f2f2f2; margin: 0; }
    .card { max-width: 560px; margin: 8vh auto; background: #fff; border-radius: 10px;
            padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,.12); }
    h1 { font-size: 1.4rem; margin-top: 0; }
    .info { color: #555; font-size: .95rem; }
    .drop { border: 2px dashed #999; border-radius: 8px; padding: 26px; text-align: center;
            margin: 18px 0; }
    input[type=file] { width: 100%; }
    button { background: #111; color: #fff; border: 0; border-radius: 6px;
             padding: 12px 26px; font-size: 1rem; cursor: pointer; }
    button:hover { background: #333; }
    .flash { padding: 10px 14px; border-radius: 6px; margin: 10px 0; }
    .flash.ok { background: #e2f4e2; }
    .flash.err { background: #fbe3e3; }
    .meta { font-size: .85rem; color: #777; }
  </style>
</head>
<body>
<div class="card">
  <h1>{{ room }} &mdash; Kalender aktualisieren</h1>
  {% for category, message in get_flashed_messages(with_categories=true) %}
    <div class="flash {{ 'ok' if category == 'ok' else 'err' }}">{{ message }}</div>
  {% endfor %}
  <p class="info">ICS-Datei (HISinOne-Export) auswaehlen. Nach dem Speichern zeigt
     das Display den aktualisierten Stand beim naechsten Refresh.</p>
  <form method="post" enctype="multipart/form-data"
        action="{{ url_for('upload') }}">
    <div class="drop"><input type="file" name="ics" accept=".ics,text/calendar" required></div>
    <button type="submit">Hochladen</button>
  </form>
  <p class="meta">
    Aktuelle Datei: {{ current_name or "-" }}<br>
    Letzte Aenderung: {{ current_mtime or "-" }}<br>
    Groesse: {{ current_size }}
  </p>
</div>
</body>
</html>"""


def create_app(cfg: Config) -> Flask:
    app = Flask(__name__)
    app.secret_key = "raumbelegung-display-local"
    ics_path = cfg.ics_path

    def _auth_required(fn):
        from functools import wraps

        protected = bool(cfg.web.username and cfg.web.password)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            if protected:
                auth = request.authorization
                if (not auth or auth.username != cfg.web.username
                        or auth.password != cfg.web.password):
                    return Response(
                        "Authentifizierung erforderlich", 401,
                        {"WWW-Authenticate": 'Basic realm="Kalender-Upload"'},
                    )
            return fn(*args, **kwargs)

        return wrapper

    @app.route("/", methods=["GET"])
    @_auth_required
    def index():
        status = _current_status(ics_path)
        return render_template_string(
            PAGE,
            room=cfg.room.name,
            current_name=status.get("name"),
            current_mtime=status.get("mtime"),
            current_size=status.get("size", "-"),
        )

    @app.route("/upload", methods=["POST"])
    @_auth_required
    def upload():
        file = request.files.get("ics")
        if file is None or not file.filename:
            flash("Keine Datei erhalten", "err")
            return redirect(url_for("index"))
        raw = file.read()
        if not raw:
            flash("Datei ist leer", "err")
            return redirect(url_for("index"))
        if len(raw) > 2_000_000:
            flash("Datei zu gross (> 2 MB)", "err")
            return redirect(url_for("index"))
        try:
            parse_calendar(raw)
        except IcsError as exc:
            log.info("Upload abgelehnt: %s", exc)
            flash(f"Upload abgelehnt: {exc}", "err")
            return redirect(url_for("index"))
        ics_path.parent.mkdir(parents=True, exist_ok=True)
        if ics_path.exists():
            shutil.copy2(ics_path, ics_path.with_suffix(".ics.bak"))
        tmp = ics_path.with_suffix(".ics.tmp")
        tmp.write_bytes(raw)
        tmp.replace(ics_path)
        log.info("ICS-Upload uebernommen: %d Bytes", len(raw))
        flash("Kalender erfolgreich aktualisiert", "ok")
        return redirect(url_for("index"))

    return app


def _current_status(ics_path: Path) -> dict:
    if not ics_path.exists():
        return {}
    stat = ics_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime)
    return {
        "name": ics_path.name,
        "mtime": mtime.strftime("%d.%m.%Y %H:%M"),
        "size": f"{stat.st_size / 1024:.1f} kB",
    }


def run_web(cfg: Config) -> None:
    app = create_app(cfg)
    app.run(host=cfg.web.host, port=cfg.web.port, debug=False, use_reloader=False)
