#!/usr/bin/env python3

import signal
import sys
import threading
import time

import serial


PANEL_PORT = "/dev/ambientika-panel"
FANS_PORT = "/dev/ambientika-fans"

BAUDRATE = 9600
READ_TIMEOUT = 0.02
READ_SIZE = 256

stop_event = threading.Event()

# Schreibzugriffe auf jeden Port absichern.
panel_write_lock = threading.Lock()
fans_write_lock = threading.Lock()


class FrameLogger:
    """Erkennt STX/ETX-Frames nur für die lesbare Konsolenausgabe."""

    def __init__(self, label: str):
        self.label = label
        self.buffer = bytearray()
        self.in_frame = False

    def feed(self, data: bytes) -> None:
        for value in data:
            if value == 0x02:  # STX
                self.buffer = bytearray()
                self.in_frame = True

            elif value == 0x03 and self.in_frame:  # ETX
                payload = self.buffer.decode("ascii", errors="replace")
                timestamp = time.strftime("%H:%M:%S")
                print(
                    f"{timestamp}  {self.label:<12}  {payload}",
                    flush=True,
                )
                self.buffer = bytearray()
                self.in_frame = False

            elif self.in_frame:
                self.buffer.append(value)


def forward(
    source: serial.Serial,
    destination: serial.Serial,
    destination_lock: threading.Lock,
    logger: FrameLogger,
) -> None:
    """Leitet Rohbytes unverändert von einem Bussegment zum anderen."""

    while not stop_event.is_set():
        try:
            data = source.read(READ_SIZE)

            if not data:
                continue

            # Logging verändert die übertragenen Daten nicht.
            logger.feed(data)

            with destination_lock:
                destination.write(data)
                destination.flush()

        except serial.SerialException as exc:
            print(f"\nSerieller Fehler bei {logger.label}: {exc}", file=sys.stderr)
            stop_event.set()

        except Exception as exc:
            print(f"\nUnerwarteter Fehler bei {logger.label}: {exc}", file=sys.stderr)
            stop_event.set()


def request_stop(signum=None, frame=None) -> None:
    stop_event.set()


def main() -> int:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print("Öffne RS485-Schnittstellen …")
    print(f"  Panel:   {PANEL_PORT}")
    print(f"  Lüfter:  {FANS_PORT}")
    print(f"  Format:  {BAUDRATE} Baud, 8N1")
    print()

    try:
        panel = serial.Serial(
            port=PANEL_PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=READ_TIMEOUT,
            write_timeout=1,
        )

        fans = serial.Serial(
            port=FANS_PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=READ_TIMEOUT,
            write_timeout=1,
        )

    except serial.SerialException as exc:
        print(f"Ports konnten nicht geöffnet werden: {exc}", file=sys.stderr)
        return 1

    panel.reset_input_buffer()
    panel.reset_output_buffer()
    fans.reset_input_buffer()
    fans.reset_output_buffer()

    panel_to_fans = threading.Thread(
        target=forward,
        name="panel-to-fans",
        args=(
            panel,
            fans,
            fans_write_lock,
            FrameLogger("PANEL -> FAN"),
        ),
        daemon=True,
    )

    fans_to_panel = threading.Thread(
        target=forward,
        name="fans-to-panel",
        args=(
            fans,
            panel,
            panel_write_lock,
            FrameLogger("FAN -> PANEL"),
        ),
        daemon=True,
    )

    panel_to_fans.start()
    fans_to_panel.start()

    print("Transparentes Gateway läuft.")
    print("Abbruch mit Strg+C.\n")

    try:
        while not stop_event.wait(0.5):
            pass
    finally:
        stop_event.set()

        panel_to_fans.join(timeout=1)
        fans_to_panel.join(timeout=1)

        panel.close()
        fans.close()

        print("\nGateway beendet.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
