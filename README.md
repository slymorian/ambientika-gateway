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
