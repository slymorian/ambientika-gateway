# Ambientika Gateway

Lokales RS485-Gateway für kabelgebundene Südwind-Ambientika-Lüfter mit Wandpanel.

## Architektur

Das Wandpanel und der Lüfterbus sind durch zwei USB-RS485-Adapter getrennt:

```text
Wandpanel
    │
USB-RS485
    │
Raspberry Pi Gateway
    │
USB-RS485
    │
Master + Slave


## MQTT state additions (Unreleased)

The gateway publishes the decoded physical state separately from the selected mode:

- `state/operating_state`
- `state/humidity_alarm`
- `state/pending_extract`
- `state/selected_humidity_level`
- `state/fan_status_byte`

Commands use `humidity_level/set` with values `1`, `2`, or `3`. Automatic override is currently enabled only for the experimentally confirmed threshold-2 command. This restriction prevents unverified inferred frames from being sent to the ventilation bus.

## Zustandsorientierte Steuerung

Das Gateway trennt vier verschiedene Zustände voneinander:

- **Panel State** – zuletzt am Wandpanel beobachteter Zustand,
- **Desired State** – über MQTT/Home Assistant gewünschter Zustand,
- **Override Runtime State** – aktuelle Phase und Generation des Overrides,
- **Active State** – tatsächlich zuletzt an den Lüfterbus gesendeter Zustand.

Die zentrale Klasse `FrameGenerator` übersetzt `mode`, `speed` und
`humidity_level` in ein bestätigtes festes Frame oder eine alternierende
Sequenz. Dadurch bleiben rohe Hex-Frames aus der MQTT- und Gateway-Logik
heraus. Nicht bestätigte Kombinationen werden abgelehnt; insbesondere ist
der Automatik-Override derzeit nur für Feuchteschwelle 2 freigegeben.

Zusätzliche MQTT-Zustandstopics:

```text
ambientika/state/desired_mode
ambientika/state/desired_speed
ambientika/state/desired_humidity_level
ambientika/state/desired_generation
```

Die bisherigen `state/selected_*`-Topics bleiben als kompatible Aliase
erhalten. Diese Trennung bereitet einen späteren Assist-Modus vor, ohne ihn
in diesem Entwicklungsschritt bereits zu aktivieren.
