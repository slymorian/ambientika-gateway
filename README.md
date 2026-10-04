# Ambientika Gateway

Lokales RS485-/MQTT-Gateway für kabelgebundene Südwind-Ambientika-Lüfter
mit Wandpanel.

## Architektur

```text
Wandpanel
    |
RS485 (Panel-Segment)
    |
Ambientika Gateway
    |
RS485 (Lüfter-Segment)
    |
Master + Slave
```

Für die RS485-Anbindung werden sowohl lokale USB-RS485-Dongles als auch
RS485-zu-Ethernet-Konverter unterstützt, siehe Abschnitt
"Installation und Start".

Das Gateway arbeitet standardmäßig transparent. Bei aktiviertem Override
werden Panel-Steuerframes blockiert und ein zentral erzeugter Steuerplan an
die Lüfter gesendet. Statusabfragen und Antworten bleiben weiterhin
transparent.

Die Software trennt drei Zustände:

- `DesiredState`: von MQTT/Home Assistant gewünschter Modus, Stufe und
  Feuchteschwelle.
- `OverrideState`: aktive Steuerstrategie sowie aktuell gesendeter
  Override-Frame.
- `ActiveState`: tatsächlich an den Lüfterbus gesendeter bzw. beobachteter
  Betriebszustand, einschließlich Phase und Feuchtealarm.

`ControlPolicy.ASSIST` ist als Architektur vorbereitet. Eine aktive
Assist-Arbitrierung zwischen Wandpanel und Home Assistant ist noch nicht
implementiert.

## Zentrale Frame-Erzeugung

`FrameGenerator` übersetzt einen logischen Sollzustand in einen validierten
festen Frame oder eine zeitgesteuerte Sequenz. Gateway- und MQTT-Code
enthalten dadurch keine verteilten Protokollkonstanten. Die bekannten
Frame-Tabellen bleiben ausschließlich in `protocol.py`.

Nicht vollständig bestätigte Kombinationen werden abgelehnt, bevor Override
aktiviert oder ein Frame gesendet wird.

## MQTT

Der Basis-Topic ist standardmäßig `ambientika`.

### Befehle

| Topic | Werte |
|---|---|
| `ambientika/override/set` | `ON`, `OFF` |
| `ambientika/mode/set` | Werte aus der Home-Assistant-Modusauswahl |
| `ambientika/speed/set` | `1`, `2`, `3` |
| `ambientika/humidity/set` | `1`, `2`, `3` |

Mode, speed und humidity aktualisieren immer zuerst den Sollzustand. Erst bei
aktiviertem Override erzeugt der Controller daraus Busframes.

### Wesentliche Status-Topics

| Topic | Bedeutung |
|---|---|
| `ambientika/state/desired_mode` | gewünschter Modus |
| `ambientika/state/desired_speed` | gewünschte Lüfterstufe |
| `ambientika/state/desired_humidity` | gewünschte Feuchteschwelle |
| `ambientika/state/control_policy` | `transparent`, `override`, später `assist` |
| `ambientika/state/operating_state` | beobachteter physischer Betriebszustand |
| `ambientika/state/phase` | aktuelle Phase |
| `ambientika/state/humidity_alarm` | `ON`, `OFF` oder unbekannt |
| `ambientika/state/active_frame` | aktuell aktiver Steuerframe |

Die bisherigen `state/selected_*`-Topics bleiben aus Kompatibilitätsgründen
erhalten.

## Home Assistant

MQTT Device Discovery erzeugt unter anderem:

- Override-Schalter
- Modus-, Lüfterstufen- und Feuchteschwellen-Auswahl
- Betriebszustand
- aktuelle Phase
- Feuchtealarm
- Steuerstrategie
- Diagnose-Entitäten für Panel- und Lüfterframes

## Installation und Start

```bash
python3 -m pip install .
ambientika-gateway
```

Die serielle und MQTT-Konfiguration erfolgt über Umgebungsvariablen (per
`.env`, siehe `EnvironmentFile` in der systemd-Unit), die von `config.py`
gelesen werden.

### Serielle Anbindung: USB-RS485-Dongle oder RS485-zu-Ethernet-Konverter

`AMBIENTIKA_PANEL_PORT` und `AMBIENTIKA_FANS_PORT` akzeptieren wahlweise:

**USB-RS485-Dongles** (lokaler Gerätepfad, z. B. per udev-Regel auf
`/dev/ambientika-panel` / `/dev/ambientika-fans` abgebildet):

```
AMBIENTIKA_PANEL_PORT=/dev/ambientika-panel
AMBIENTIKA_FANS_PORT=/dev/ambientika-fans
```

**RS485-zu-Ethernet-Konverter** (z. B. ein Gerät mit zwei unabhängigen
RS485-Kanälen, jeder Kanal im TCP-Server-/transparenten Modus mit eigener
IP und Port):

```
AMBIENTIKA_PANEL_PORT=socket://192.0.2.138:4196
AMBIENTIKA_FANS_PORT=socket://192.0.2.137:4196
```

In beiden Fällen gelten dieselben seriellen Einstellungen: 9600 Baud,
8 Datenbits, keine Parität, 1 Stoppbit (8N1). Beim Konverter übernimmt
dessen Firmware das eigentliche RS485-Framing auf dem Bus; das Gateway
öffnet die Verbindung intern über `serial.serial_for_url()`, sodass
Panel- und Lüfter-Port unabhängig voneinander als lokaler Gerätepfad oder
als `socket://`-URL konfiguriert werden können.

Um bei einem neu angeschlossenen Konverter herauszufinden, welcher
physische Kanal Panel bzw. Lüfter ist, und ob die A/B-Polarität stimmt,
kann rein lesend (ohne etwas auf den Bus zu senden) mitgehört werden:

```bash
python3 tools/probe_converter.py <ip> <port>
```

Panel-Traffic zeigt sich an kurzen Abfrage-Frames (`02xxxx`) und
4-Byte-Steuerframes (`01xxxxxx`), Lüfter-Traffic an kurzen
Master-Antworten (`00xxxx`). Kommen gar keine oder nur unlesbare Bytes an,
sind meist A und B am jeweiligen Konverterkanal vertauscht.

Für einen dauerhaften Betrieb liegt eine systemd-Unit unter
`systemd/ambientika-gateway.service`. Deren `ExecStartPre`-Prüfungen
überspringen die Existenzprüfung automatisch, wenn der jeweilige Port
eine `socket://`- oder `rfc2217://`-URL ist.

## Tests

```bash
python3 -m compileall -q src
python3 -m unittest discover -s tests -v
```

Die Smoke-Tests prüfen Sollzustand, Override-Strategie, zentrale
Frame-Erzeugung, Zustandsdekodierung und Home-Assistant-Discovery.
