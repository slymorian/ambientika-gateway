#!/usr/bin/env python3

"""Transparentes Ambientika-RS485-Decode-Gateway.

Dateiposition auf dem Raspberry:
    /home/stefan/ambientika/ambientika_gateway_decode.py

Die Protokolldefinition wird aus dem src-Layout geladen:
    /home/stefan/ambientika/src/ambientika_gateway/protocol.py
"""

from __future__ import annotations

import csv
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import serial

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIRECTORY = PROJECT_ROOT / "src"

if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

try:
    from ambientika_gateway.protocol import (
        DecodedFrame,
        FrameCategory,
        Mode,
        OperatingState,
        Phase,
        decode_frame,
    )
except ImportError as exc:
    raise SystemExit(
        "ambientika_gateway.protocol konnte nicht geladen werden. "
        f"Erwarteter Pfad: {SRC_DIRECTORY / 'ambientika_gateway' / 'protocol.py'}"
    ) from exc


PANEL_PORT = "/dev/ambientika-panel"
FANS_PORT = "/dev/ambientika-fans"

BAUDRATE = 9600
READ_TIMEOUT = 0.02
READ_SIZE = 256

LOG_DIRECTORY = PROJECT_ROOT / "logs"
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIRECTORY / time.strftime(
    "ambientika_%Y-%m-%d_%H-%M-%S.csv"
)

stop_event = threading.Event()

panel_write_lock = threading.Lock()
fans_write_lock = threading.Lock()
csv_lock = threading.Lock()


def source_for_protocol(source: str) -> str:
    """Wandelt die lokalen Quellnamen in die protocol.py-Namen um."""
    return source.strip().lower()


def enum_value(value: object) -> str:
    """Gibt für Enums deren Wert und sonst einen lesbaren String zurück."""
    enum_member_value = getattr(value, "value", None)

    if isinstance(enum_member_value, str):
        return enum_member_value

    return str(value)


def optional_bool_text(value: bool | None) -> str:
    if value is True:
        return "true"

    if value is False:
        return "false"

    return ""


def possible_modes_text(state: DecodedFrame) -> str:
    return ",".join(enum_value(mode) for mode in state.possible_modes)


def decode(source: str, payload: str) -> DecodedFrame:
    return decode_frame(
        source_for_protocol(source),
        payload,
    )


class FrameParser:
    """Extrahiert STX/ETX-gerahmte ASCII-Telegramme."""

    def __init__(
        self,
        source: str,
        on_frame: Callable[[str, str], None],
    ) -> None:
        self.source = source
        self.on_frame = on_frame
        self.buffer = bytearray()
        self.in_frame = False

    def feed(self, data: bytes) -> None:
        for value in data:
            if value == 0x02:
                self.buffer = bytearray()
                self.in_frame = True
                continue

            if value == 0x03 and self.in_frame:
                payload = self.buffer.decode(
                    "ascii",
                    errors="replace",
                ).upper()

                self.on_frame(self.source, payload)

                self.buffer = bytearray()
                self.in_frame = False
                continue

            if self.in_frame:
                self.buffer.append(value)

                if len(self.buffer) > 128:
                    self.buffer = bytearray()
                    self.in_frame = False


class StateTracker:
    """Unterdrückt in der Konsole ständig wiederholte Steuerframes."""

    def __init__(self) -> None:
        self.last_control_payload: str | None = None

    def should_print(
        self,
        source: str,
        payload: str,
        state: DecodedFrame,
    ) -> bool:
        if (
            source == "PANEL"
            and state.category
            in {
                FrameCategory.CONTROL,
                FrameCategory.UNKNOWN_CONTROL,
            }
        ):
            if payload == self.last_control_payload:
                return False

            self.last_control_payload = payload
            return True

        return True


state_tracker = StateTracker()


def write_csv(
    source: str,
    payload: str,
    state: DecodedFrame,
) -> None:
    now = time.time()
    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(now),
    )
    milliseconds = int((now % 1) * 1000)

    with csv_lock:
        with LOG_FILE.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as logfile:
            writer = csv.writer(logfile, delimiter=";")
            writer.writerow(
                [
                    timestamp,
                    f"{milliseconds:03d}",
                    source,
                    payload,
                    enum_value(state.category),
                    (
                        ""
                        if state.mode is Mode.UNKNOWN
                        else enum_value(state.mode)
                    ),
                    possible_modes_text(state),
                    (
                        ""
                        if state.operating_state is OperatingState.UNKNOWN
                        else enum_value(state.operating_state)
                    ),
                    state.speed if state.speed is not None else "",
                    (
                        state.humidity_level
                        if state.humidity_level is not None
                        else ""
                    ),
                    (
                        ""
                        if state.phase is Phase.UNKNOWN
                        else enum_value(state.phase)
                    ),
                    state.description,
                    optional_bool_text(state.button_press),
                    optional_bool_text(state.filter_reset),
                    optional_bool_text(state.filter_alarm),
                    (
                        f"0x{state.status_byte:02X}"
                        if state.status_byte is not None
                        else ""
                    ),
                    state.checksum_valid,
                ]
            )


def state_details(state: DecodedFrame) -> list[str]:
    details: list[str] = []

    if state.mode is not Mode.UNKNOWN:
        details.append(f"mode={enum_value(state.mode)}")

    if state.possible_modes:
        details.append(
            "possible_modes="
            + ",".join(enum_value(mode) for mode in state.possible_modes)
        )

    if state.operating_state is not OperatingState.UNKNOWN:
        details.append(
            f"operating_state={enum_value(state.operating_state)}"
        )

    if state.speed is not None:
        details.append(f"speed={state.speed}")

    if state.humidity_level is not None:
        details.append(
            f"humidity_level={state.humidity_level}"
        )

    if state.phase is not Phase.UNKNOWN:
        details.append(f"phase={enum_value(state.phase)}")

    if state.button_press:
        details.append("button_press=true")

    if state.filter_reset:
        details.append("filter_reset=true")

    if state.filter_alarm is True:
        details.append("filter_alarm=true")
    elif state.filter_alarm is False:
        details.append("filter_alarm=false")

    if state.status_byte is not None:
        details.append(f"status_byte=0x{state.status_byte:02X}")

    return details


def handle_frame(source: str, payload: str) -> None:
    state = decode(source, payload)
    write_csv(source, payload, state)

    if not state_tracker.should_print(
        source,
        payload,
        state,
    ):
        return

    timestamp = time.strftime("%H:%M:%S")
    details = state_details(state)

    if state.category is FrameCategory.CONTROL:
        detail_text = "  ".join(details)

        if state.description:
            detail_text = (
                f"{detail_text}  {state.description}"
                if detail_text
                else state.description
            )

        print(
            f"{timestamp}  {source:<5}  {payload}  "
            f"{detail_text}",
            flush=True,
        )
        return

    if state.category is FrameCategory.UNKNOWN_CONTROL:
        print(
            f"{timestamp}  {source:<5}  {payload}  "
            "gültiger, noch unbekannter Steuerframe",
            flush=True,
        )
        return

    description = state.description or "Noch nicht zugeordnet"
    detail_text = ""

    if details:
        detail_text = " [" + ", ".join(details) + "]"

    print(
        f"{timestamp}  {source:<5}  {payload}  "
        f"{enum_value(state.category)}: "
        f"{description}{detail_text}",
        flush=True,
    )


def forward(
    source: serial.Serial,
    destination: serial.Serial,
    destination_lock: threading.Lock,
    parser: FrameParser,
) -> None:
    """Leitet Rohbytes unverändert zum anderen Bussegment weiter."""

    while not stop_event.is_set():
        try:
            data = source.read(READ_SIZE)

            if not data:
                continue

            parser.feed(data)

            with destination_lock:
                destination.write(data)
                destination.flush()

        except serial.SerialException as exc:
            print(
                f"Serieller Fehler auf {parser.source}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            stop_event.set()

        except Exception as exc:
            print(
                f"Unerwarteter Fehler auf {parser.source}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            stop_event.set()


def request_stop(
    signum: int | None = None,
    frame: object | None = None,
) -> None:
    del signum, frame
    stop_event.set()


def create_log_file() -> None:
    with LOG_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as logfile:
        writer = csv.writer(logfile, delimiter=";")
        writer.writerow(
            [
                "timestamp",
                "milliseconds",
                "source",
                "payload",
                "category",
                "mode",
                "possible_modes",
                "operating_state",
                "speed",
                "humidity_level",
                "phase",
                "description",
                "button_press",
                "filter_reset",
                "filter_alarm",
                "status_byte",
                "checksum_valid",
            ]
        )


def open_serial_port(path: str) -> serial.Serial:
    return serial.Serial(
        port=path,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=READ_TIMEOUT,
        write_timeout=1,
    )


def main() -> int:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    create_log_file()

    print("Öffne Ambientika-Busse …")
    print(f"  Panel:      {PANEL_PORT}")
    print(f"  Lüfter:     {FANS_PORT}")
    print(
        "  Protokoll:  "
        f"{SRC_DIRECTORY / 'ambientika_gateway' / 'protocol.py'}"
    )
    print(f"  Log:        {LOG_FILE}")
    print()

    panel: serial.Serial | None = None
    fans: serial.Serial | None = None

    try:
        panel = open_serial_port(PANEL_PORT)
        fans = open_serial_port(FANS_PORT)
    except serial.SerialException as exc:
        if panel is not None and panel.is_open:
            panel.close()

        if fans is not None and fans.is_open:
            fans.close()

        print(
            f"Ports konnten nicht geöffnet werden: {exc}",
            file=sys.stderr,
        )
        return 1

    panel.reset_input_buffer()
    panel.reset_output_buffer()
    fans.reset_input_buffer()
    fans.reset_output_buffer()

    panel_thread = threading.Thread(
        target=forward,
        name="panel-to-fans",
        args=(
            panel,
            fans,
            fans_write_lock,
            FrameParser("PANEL", handle_frame),
        ),
        daemon=True,
    )

    fans_thread = threading.Thread(
        target=forward,
        name="fans-to-panel",
        args=(
            fans,
            panel,
            panel_write_lock,
            FrameParser("FANS", handle_frame),
        ),
        daemon=True,
    )

    panel_thread.start()
    fans_thread.start()

    print("Transparentes Decode-Gateway läuft.")
    print("Abbruch mit Strg+C.\n")

    try:
        while not stop_event.wait(0.5):
            pass

    finally:
        stop_event.set()

        panel_thread.join(timeout=1)
        fans_thread.join(timeout=1)

        panel.close()
        fans.close()

        print("\nGateway beendet.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
