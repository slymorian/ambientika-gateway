#!/usr/bin/env python3
"""
Diagnose-Tool: liest roh von einem RS485-zu-Ethernet-Konverterkanal und
zeigt an, ob überhaupt lesbare Ambientika-Frames ankommen, und wenn ja,
ob es eher nach Panel- oder nach Lüfterbus-Traffic aussieht.

Rein lesend (sendet nichts auf den Bus) -- kann parallel zum laufenden
Gateway (USB-Dongles) verwendet werden, ohne etwas zu stören.

Verwendung:
    python3 probe_converter.py <ip> <port> [--seconds 20]

Beispiel:
    python3 probe_converter.py 192.0.2.138 4196

Interpretation der Ausgabe:
  - Gar keine Bytes in der Laufzeit:
      Entweder falsche IP/Port, Konverter steht nicht im richtigen
      Modus (TCP Server, richtiger Kanal), oder A/B ist so verdreht,
      dass der Empfänger-Chip des Konverters nichts Sinnvolles sieht.
      -> A oder B am Konverter-Kanal vertauschen und erneut testen.
  - Rohbytes kommen an, aber keine saubere STX/ETX-Rahmung (0x02 ... 0x03)
    bzw. kein gültiges ASCII-Hex dazwischen:
      Deutet ebenfalls auf vertauschte A/B-Polarität hin (Differenzsignal
      invertiert -> Empfänger liest Müll statt "01AA00AB" etc.).
  - Saubere Frames kommen an:
      A/B ist richtig. Schau dir die Klassifizierung an:
        "vermutlich PANEL"  -> viele 4-Byte-Steuerframes (01xxxxxx) und/
                               oder kurze Abfrage-Frames (02xxxx), meist
                               alle ~500ms ein Frame.
        "vermutlich FANS"   -> viele kurze Masterantworten (00xxxx, z.B.
                               000202 / 000808 / 000A0A).
      Zum Gegenchecken parallel die laufende alarmtest.py (MQTT) im Auge
      behalten: wenn sich panel_frame im MQTT-Log zeitgleich mit den hier
      angezeigten Frames ändert, ist dieser Konverterkanal der Panel-Bus;
      wenn stattdessen fan_reply zeitgleich wechselt, ist es der Fans-Bus.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

STX = 0x02
ETX = 0x03


def classify(payload: str) -> str:
    """Grobe Einordnung rein nach Byte-Muster, ohne protocol.py zu
    importieren (dieses Skript soll auch standalone, ohne das Projekt-
    Package, lauffähig sein)."""

    if len(payload) == 8 and payload.upper().startswith("01"):
        return "vermutlich PANEL (4-Byte-Steuerframe)"

    if len(payload) == 6 and payload.upper().startswith("02"):
        return "vermutlich PANEL (kurze Abfrage)"

    if len(payload) == 6 and payload.upper().startswith("00"):
        return "vermutlich FANS (kurze Masterantwort)"

    return "unklar (unbekanntes Muster)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="IP-Adresse des Konverterkanals")
    parser.add_argument("port", type=int, help="TCP-Port des Konverterkanals")
    parser.add_argument(
        "--seconds",
        type=float,
        default=20.0,
        help="Wie lange mitgelesen wird (Default: 20s)",
    )
    args = parser.parse_args()

    print(f"Verbinde zu {args.host}:{args.port} ...")

    try:
        sock = socket.create_connection((args.host, args.port), timeout=5.0)
    except OSError as exc:
        print(f"Verbindung fehlgeschlagen: {exc}")
        return 1

    sock.settimeout(0.5)

    print(f"Verbunden. Lese {args.seconds:.0f}s lang mit (nichts wird gesendet).\n")

    buffer = bytearray()
    in_frame = False
    frame_count = 0
    byte_count = 0
    deadline = time.monotonic() + args.seconds

    try:
        while time.monotonic() < deadline:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue

            if not data:
                print("Verbindung vom Konverter geschlossen.")
                break

            byte_count += len(data)

            for value in data:
                if value == STX:
                    buffer = bytearray()
                    in_frame = True
                    continue

                if not in_frame:
                    continue

                if value == ETX:
                    try:
                        payload = bytes(buffer).decode("ascii").upper()
                    except UnicodeDecodeError:
                        payload = None

                    if payload is not None:
                        frame_count += 1
                        now = time.strftime("%H:%M:%S")
                        print(
                            f"{now}  Frame #{frame_count}: {payload}  "
                            f"-> {classify(payload)}"
                        )
                    else:
                        print(
                            time.strftime("%H:%M:%S")
                            + "  Nicht-ASCII-Frame empfangen (vermutlich"
                            " A/B vertauscht): "
                            + bytes(buffer).hex(" ").upper()
                        )

                    in_frame = False
                    buffer = bytearray()
                    continue

                buffer.append(value)

                if len(buffer) > 128:
                    # Offensichtlich kein gültiges Telegramm mehr --
                    # zurücksetzen statt endlos zu sammeln.
                    in_frame = False
                    buffer = bytearray()

    except KeyboardInterrupt:
        print("\nAbgebrochen.")
    finally:
        sock.close()

    print(f"\n{byte_count} Rohbytes empfangen, {frame_count} gültige ASCII-Frames erkannt.")

    if byte_count == 0:
        print(
            "-> Keine Bytes angekommen: IP/Port prüfen, Konverter-Modus"
            " (TCP Server, richtiger Kanal) prüfen, oder A/B am Konverter"
            " vertauschen und erneut testen."
        )
    elif frame_count == 0:
        print(
            "-> Bytes kommen an, aber keine saubere STX/ETX-Rahmung."
            " Das spricht für vertauschte A/B-Polarität -- A und B am"
            " Konverter-Kanal tauschen und erneut testen."
        )
    else:
        print(
            "-> A/B scheint richtig zu sein. Schau dir die Klassifizierung"
            " oben an und vergleiche mit panel_frame/fan_reply in"
            " alarmtest.py, um sicher zu sein, welcher Bus das ist."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
