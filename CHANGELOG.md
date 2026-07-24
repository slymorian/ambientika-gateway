## Unreleased

### Added

- Added a central `FrameGenerator` that translates logical mode, speed and humidity selections into confirmed RS485 control programs.
- Added a separate immutable `DesiredState` to distinguish the Home Assistant target from panel state, override runtime state and active bus state.
- Added explicit MQTT state topics `state/desired_mode`, `state/desired_speed`, `state/desired_humidity_level` and `state/desired_generation`.
- Added unit smoke tests for frame generation and desired-state synchronization.

### Changed

- Gateway override execution now consumes generated control programs instead of embedding protocol frames in `gateway.py`.
- Home Assistant Discovery selects now use the explicit desired-state topics; the former `state/selected_*` topics remain published as compatibility aliases.
- Monitoring control generation is centralized and uses the humidity-specific confirmed frames for levels 1–3.
- Automatic override remains intentionally restricted to the confirmed humidity level 2 frame.

# Changelog

## Unreleased

- Decode the confirmed automatic humidity-alarm lifecycle (`01720073`, `016A046F`, `01620467`, `01760473`, `000808`).
- Publish humidity threshold, physical operating state, humidity alarm, pending extract transition and status byte over MQTT.
- Add Home Assistant Discovery entities for humidity threshold and alarm state.
- Add experimental Automatic override for the confirmed humidity threshold 2 frame. Other automatic thresholds remain blocked until verified on the bus.

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
