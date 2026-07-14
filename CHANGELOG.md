# Changelog

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
