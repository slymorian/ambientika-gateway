#!/usr/bin/env python3

import csv
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import serial


PANEL_PORT = "/dev/ambientika-panel"
FANS_PORT = "/dev/ambientika-fans"

BAUDRATE = 9600
READ_TIMEOUT = 0.02
READ_SIZE = 256

LOG_DIRECTORY = Path.home() / "ambientika" / "logs"
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIRECTORY / time.strftime(
    "ambientika_%Y-%m-%d_%H-%M-%S.csv"
)

stop_event = threading.Event()

panel_write_lock = threading.Lock()
fans_write_lock = threading.Lock()
csv_lock = threading.Lock()


@dataclass(frozen=True)
class DecodedState:
    category: str
    mode: str = ""
    speed: int | None = None
    phase: str = ""
    description: str = ""


# Zunächst nur Zustände, die wir hinreichend sicher zugeordnet haben.
#
# phase_a und phase_b sind die beiden festen Gegenrichtungen.
# Welche davon physisch "Master Abluft" ist, bestimmen wir später.
PANEL_CONTROL_FRAMES: dict[str, DecodedState] = {
    # Manuell alternierend, Stufe 1
    "01A500A4": DecodedState(
        "control", "manual_alternating", 1, "phase_a"
    ),
    "01A100A0": DecodedState(
        "control", "manual_alternating", 1, "transition"
    ),
    "01A900A8": DecodedState(
        "control", "manual_alternating", 1, "phase_b"
    ),

    # Manuell alternierend, Stufe 2
    "01AA00AB": DecodedState(
        "control", "manual_alternating", 2, "phase_a"
    ),
    "01A200A3": DecodedState(
        "control", "manual_alternating", 2, "transition"
    ),
    "01A600A7": DecodedState(
        "control", "manual_alternating", 2, "phase_b"
    ),

    # Manuell alternierend, Stufe 3 – bislang nur zwei sicher erfasste Codes
    "01A700A6": DecodedState(
        "control", "manual_alternating", 3, "phase_a"
    ),
    "01A300A2": DecodedState(
        "control", "manual_alternating", 3, "transition"
    ),

    # Beide Lüfter dauerhaft Abluft
    "01750074": DecodedState("control", "extract", 1, "fixed"),
    "01760077": DecodedState("control", "extract", 2, "fixed"),
    "01770076": DecodedState("control", "extract", 3, "fixed"),

    # Beide Lüfter dauerhaft Zuluft
    "01790078": DecodedState("control", "supply", 1, "fixed"),
    "017A007B": DecodedState("control", "supply", 2, "fixed"),
    "017B007A": DecodedState("control", "supply", 3, "fixed"),

    # Master Abluft, Slave Zuluft
    "01690068": DecodedState(
        "control", "master_extract_slave_supply", 1, "fixed"
    ),
    "016A006B": DecodedState(
        "control", "master_extract_slave_supply", 2, "fixed"
    ),
    "016B006A": DecodedState(
        "control", "master_extract_slave_supply", 3, "fixed"
    ),

    # Master Zuluft, Slave Abluft
    "01650064": DecodedState(
        "control", "master_supply_slave_extract", 1, "fixed"
    ),
    "01660067": DecodedState(
        "control", "master_supply_slave_extract", 2, "fixed"
    ),
    "01670066": DecodedState(
        "control", "master_supply_slave_extract", 3, "fixed"
    ),

    # Silent – vorläufig bekannte Phasen
    "01A400A5": DecodedState(
        "control", "silent", 1, "phase_a"
    ),
    "01A000A1": DecodedState(
        "control", "silent", 1, "transition"
    ),
    "01A800A9": DecodedState(
        "control", "silent", 1, "phase_b"
    ),
}


SHORT_FRAMES: dict[tuple[str, str], DecodedState] = {
    ("PANEL", "020002"): DecodedState(
        "request",
        description="Statusabfrage des Wandpanels",
    ),
    ("PANEL", "020406"): DecodedState(
        "request",
        description="Erweiterte Statusabfrage des Wandpanels",
    ),
    ("FANS", "000202"): DecodedState(
        "reply",
        description="Statusantwort des Masters",
    ),
    ("FANS", "000A0A"): DecodedState(
        "reply",
        description="Erweiterte Statusantwort des Masters",
    ),
    ("FANS", "000000"): DecodedState(
        "startup",
        description="Start-/Initialisierungstelegramm",
    ),
    ("FANS", "000101"): DecodedState(
        "startup",
        description="Start-/Initialisierungstelegramm",
    ),
}


def xor_valid(payload: str) -> bool:
    """Prüft die XOR-Prüfsumme eines 4-Byte-Steuerframes."""

    try:
        data = bytes.fromhex(payload)
    except ValueError:
        return False

    return (
        len(data) == 4
        and (data[0] ^ data[1] ^ data[2]) == data[3]
    )


def decode_frame(source: str, payload: str) -> DecodedState:
    """Ordnet einen Frame einem bislang bekannten Zustand zu."""

    payload = payload.upper()

    short_state = SHORT_FRAMES.get((source, payload))
    if short_state is not None:
        return short_state

    if source == "PANEL" and payload in PANEL_CONTROL_FRAMES:
        return PANEL_CONTROL_FRAMES[payload]

    if len(payload) == 8 and xor_valid(payload):
        return DecodedState(
            category="unknown_control",
            description="Gültiger, noch nicht zugeordneter Steuerframe",
        )

    return DecodedState(
        category="unknown",
        description="Noch nicht zugeordnet",
    )


class FrameParser:
    """Extrahiert STX/ETX-gerahmte ASCII-Telegramme."""

    def __init__(self, source: str, on_frame):
        self.source = source
        self.on_frame = on_frame
        self.buffer = bytearray()
        self.in_frame = False

    def feed(self, data: bytes) -> None:
        for value in data:
            if value == 0x02:  # STX
                self.buffer = bytearray()
                self.in_frame = True

            elif value == 0x03 and self.in_frame:  # ETX
                payload = self.buffer.decode(
                    "ascii",
                    errors="replace",
                ).upper()

                self.on_frame(self.source, payload)

                self.buffer = bytearray()
                self.in_frame = False

            elif self.in_frame:
                self.buffer.append(value)


class StateTracker:
    """Unterdrückt in der Konsole ständig wiederholte Steuerframes."""

    def __init__(self):
        self.last_control_payload: str | None = None

    def should_print(
        self,
        source: str,
        payload: str,
        state: DecodedState,
    ) -> bool:
        if source == "PANEL" and state.category in {
            "control",
            "unknown_control",
        }:
            if payload == self.last_control_payload:
                return False

            self.last_control_payload = payload
            return True

        # Abfragen, Antworten, Startmeldungen und unbekannte Frames anzeigen.
        return True


state_tracker = StateTracker()


def write_csv(
    source: str,
    payload: str,
    state: DecodedState,
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
                    state.category,
                    state.mode,
                    (
                        state.speed
                        if state.speed is not None
                        else ""
                    ),
                    state.phase,
                    state.description,
                    xor_valid(payload),
                ]
            )


def handle_frame(source: str, payload: str) -> None:
    state = decode_frame(source, payload)
    write_csv(source, payload, state)

    if not state_tracker.should_print(
        source,
        payload,
        state,
    ):
        return

    timestamp = time.strftime("%H:%M:%S")

    if state.category == "control":
        print(
            f"{timestamp}  {source:<5}  {payload}  "
            f"mode={state.mode}  "
            f"speed={state.speed}  "
            f"phase={state.phase}",
            flush=True,
        )

    elif state.category == "unknown_control":
        print(
            f"{timestamp}  {source:<5}  {payload}  "
            f"gültiger, noch unbekannter Steuerframe",
            flush=True,
        )

    else:
        print(
            f"{timestamp}  {source:<5}  {payload}  "
            f"{state.category}: {state.description}",
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

            # Zuerst analysieren, dann unverändert weiterreichen.
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


def request_stop(signum=None, frame=None) -> None:
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
                "speed",
                "phase",
                "description",
                "xor_valid",
            ]
        )


def main() -> int:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    create_log_file()

    print("Öffne Ambientika-Busse …")
    print(f"  Panel:   {PANEL_PORT}")
    print(f"  Lüfter:  {FANS_PORT}")
    print(f"  Log:     {LOG_FILE}")
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

    print("Transparentes Decoder-Gateway läuft.")
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

