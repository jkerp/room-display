# Raumbelegungs-Display (Waveshare 7.5" e-Paper + Raspberry Pi Zero 2 W)

Zeigt die Raumbelegung aus einer HISinOne-ICS-Datei auf einem Waveshare
7.5-inch e-Paper HAT (B) (V3, 800x480, Schwarz/Weiss/Rot) an. Die ICS-Datei
wird ueber einen Web-Upload im WLAN aktualisiert.

## Ansichten (wechselnd)

| Ansicht   | Inhalt                                                              |
|-----------|---------------------------------------------------------------------|
| `status`  | Grosser Flaeche `FREI` / `BELEGT` mit laufendem bzw. naechstem Termin |
| `day`     | Terminliste des heutigen Tages, laufender Termin invertiert          |
| `week`    | Kompakte 7-Tage-Uebersicht                                           |

Reihenfolge und Wechselrhythmus: `config.yaml` unter `views`.
Wechsel-Logik: nur bei tatsaechlicher Aenderung (Upload, Terminbeginn/-ende,
Ansichtswechsel) wird das Panel neu gezeichnet - das schont die Lebensdauer.

## Funktionsweise

```
Browser (LAN)  --HTTP-->  Web-Upload (Flask, Port 8080)
                              | validiert ICS, ersetzt data/raumbelegung.ics atomar
                              v
Display-Loop (systemd)  -- prueft alle 10 s: Datei geaendert? Terminwechsel?
                              | expandiert RRULE/EXDATE/Zeitzonen
                              v
                        Pillow-Rendering -> epd7in5_V3 (SPI)
```

- **Parser**: `icalendar` + `recurring-ical-events` (RRULE, EXDATE,
  VTIMEZONE Europe/Berlin). HISinOne-Spezialitaeten (Leerzeichen am
  Zeilenende nach EXDATE-Fortsetzungszeilen) werden bereinigt.
- **Robustheit**: Upload wird vor Uebernahme vollstaendig geparst; die
  vorherige Datei bleibt als `raumbelegung.ics.bak` liegen. Ist der
  Kalender aelter als `stale_days` (Default 35), erscheint ein Hinweis
  im Fuss der Anzeige - HISinOne-Exporte laufen nach `UNTIL` ab und
  muessen periodisch neu exportiert werden.

## Hardware-Anschluss (7.5 HAT B V3)

HAT direkt auf die 40-Pin-Leiste stecken, SPI aktivieren
(`raspi-config` → Interface Options → SPI). `deploy/install.sh`
erledigt die Aktivierung ebenfalls.

Wichtig: System-Zeitzone auf Europe/Berlin setzen - alle Anzeigen
(Tagesgrenze, \"heute\", Umlauts-Daten) arbeiten mit der lokalen Zeit:

```bash
sudo raspi-config nonint do_change_timezone Europe/Berlin
```

## Installation (Raspberry Pi OS Bookworm)

```bash
sudo bash deploy/install.sh              # SERVICE_USER=pi voreingestellt
sudo reboot                              # falls SPI frisch aktiviert wurde
sudo systemctl start roomdisplay roomdisplay-web
```

Die Dienste laufen danach automatisch wieder nach Stromausfall/Neustart.

## ICS aktualisieren

Unkompliziert: Im Browser `http://<ip-des-pi>:8080/` aufrufen, ICS-Datei
auswaehlen, hochladen. Das naechste Refresh des Displays uebernimmt den
Stand innerhalb weniger Sekunden bis Minuten.

Optional mit HTTP-Basic-Auth:

```bash
sudo systemctl edit roomdisplay-web
# eintragen:
# [Service]
# Environment=ROOMDISPLAY_WEB_PASSWORD=geheim
sudo systemctl restart roomdisplay-web
```

## Vorschau ohne Hardware

Am Device oder einem beliebigen Rechner mit den Python-Abhaengigkeiten:

```bash
python -m roomdisplay --preview --once      # Ansicht sofort als PNG nach ./preview
python -m roomdisplay --preview             # dauerhafter Vorschau-Loop
python -m roomdisplay --preview --view day  # feste Ansicht
```

## Konfiguration (`config.yaml`)

| Abschnitt | Key                    | Bedeutung                                    |
|-----------|------------------------|----------------------------------------------|
| `display.model` | `epd7in5b_V2` | 7.5" HAT (B) Schwarz/Weiss/Rot - auch fuer Boards mit V3-Logo (SKU 13505); S/W-Variante: `epd7in5_V2` |
| `display.rotation` | 0/90/180/270  | Fuer Hochkant-Montage z. B. `90`             |
| `views.sequence` | Liste           | Wechsel: nicht benoetigte Eintraege entfernen |
| `views.interval` | Sekunden        | Ansichtwechsel-Rhythmus (min. 30)            |
| `calendar.stale_days` | Tage       | Ab wann Fusszeile warnt                      |
| `room.name` / `room.location` | Text | Kopfbalken                                 |
| `web.port` | 8080                  | Web-Upload                                   |

## Projektstruktur

```
roomdisplay/         Python-Paket
  main.py            Loop + CLI (--preview, --once, --view, --web)
  web.py             Flask-Upload (Validierung, atomar, Backup)
  schedule.py        ICS-Sanitizer, Terminlogik, Expansion (RRULE/EXDATE)
  render.py          Pillow-Layout der drei Ansichten
  display.py         epd7in5_V3-Bindung + Preview-Modus + Rotation
  config.py          YAML-Konfiguration + Env-Override (Passwort)
fonts/               DejaVu Sans (SIL-Download-Lizenz, freie Weitergabe)
deploy/              systemd-Units + install.sh
data/                Ablageort der ICS-Datei (raumbelegung.ics)
```

Die DejaVu-Schriften liegen gebündelt bei; alternativ genügt das Paket
`fonts-dejavu-core`.

## Hinweise zur Lebensdauer des Panels

E-Paper-Panels vertragen je nach Modell > 1 Mio. Refreshes; empfohlen
ist ein Mindestabstand zwischen Refreshes. `config.yaml` liefert mit
`views.interval: 180` und `min_refresh_interval: 20` konservative
Voreinstellungen. Geisterbilder beseitigt der periodische Full-Refresh
nach `Clear()` beim Start bzw. Wake des Panels.
