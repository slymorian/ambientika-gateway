# Ambientika Gateway

Lokales RS485-/MQTT-Gateway für kabelgebundene Südwind-Ambientika-Lüfter
mit Wandpanel.

## Architektur

```text
Wandpanel
    |
USB-RS485 (Panel-Segment)
    |
Ambientika Gateway
    |
USB-RS485 (Lüfter-Segment)
    |
Master + Slave
```

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

Die serielle und MQTT-Konfiguration erfolgt über die bestehenden
Umgebungsvariablen in `config.py`. Für einen dauerhaften Betrieb liegt eine
systemd-Unit unter `systemd/ambientika-gateway.service`.

## Tests

```bash
python3 -m compileall -q src
python3 -m unittest discover -s tests -v
```

Die Smoke-Tests prüfen Sollzustand, Override-Strategie, zentrale
Frame-Erzeugung, Zustandsdekodierung und Home-Assistant-Discovery.
