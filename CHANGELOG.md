# Changelog

## [Unreleased] - 2026-07-25

### Added

- Zustandsorientierter `DesiredState` mit `desired_mode`,
  `desired_speed` und `desired_humidity`
- Beobachteter `operating_state`, `humidity_alarm` und `phase` im zentralen
  Gateway-Snapshot
- Zentraler `FrameGenerator` für feste und alternierende Steuerpläne
- MQTT-Set-Topic `humidity/set`
- Konsistente Desired-/Runtime-Status-Topics
- Home-Assistant-Discovery für Feuchteschwelle, Betriebszustand,
  Feuchtealarm, Phase und Steuerstrategie
- `ControlPolicy.ASSIST` als Vorbereitung für eine spätere Assist-Arbitrierung
- Smoke-Tests für State, FrameGenerator und Discovery

### Changed

- Override-Laufzeit und gewünschte Auswahl sind getrennte Zustände
- Gateway-Code erzeugt Protokollframes ausschließlich über `FrameGenerator`
- Nicht bestätigte Modus-/Stufen-/Feuchtekombinationen werden zentral
  validiert und sicher abgelehnt

## [0.1.0] - 2026-07-14

### Added

- Transparentes bidirektionales RS485-Gateway
- Getrennte Bussegmente für Wandpanel und Master/Slave-Lüfter
- MQTT-Steuerung für Modus, Lüfterstufe und Override
- Home Assistant MQTT Device Discovery
- Feste Zuluft-, Abluft- und Master/Slave-Richtungsmodi
- Alternierender manueller Betrieb mit 60/10/60/10-Sekunden-Sequenz
- Dekodierung bekannter Steuer-, Anfrage- und Antwortframes
- systemd-Dienst für automatischen Start
- Umgebungsbasierte Konfiguration
- Zentrale Modusdefinitionen und Zustandsverwaltung

### Known limitations

- Automatik, Überwachung und zeitgeschaltete Abluft noch nicht als
  Override implementiert
- Manuell Stufe 3 noch nicht vollständig entschlüsselt
- Kein automatischer Hardware-Failsafe-Bypass
