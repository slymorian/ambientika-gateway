from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


STX = 0x02
ETX = 0x03


class FrameCategory(str, Enum):
    CONTROL = "control"
    REQUEST = "request"
    REPLY = "reply"
    STARTUP = "startup"
    UNKNOWN_CONTROL = "unknown_control"
    UNKNOWN = "unknown"


class Mode(str, Enum):
    MANUAL_ALTERNATING = "manual_alternating"
    EXTRACT = "extract"
    SUPPLY = "supply"
    MASTER_EXTRACT_SLAVE_SUPPLY = "master_extract_slave_supply"
    MASTER_SUPPLY_SLAVE_EXTRACT = "master_supply_slave_extract"
    SILENT = "silent"
    UNKNOWN = "unknown"


class Phase(str, Enum):
    PHASE_A = "phase_a"
    PHASE_B = "phase_b"
    TRANSITION = "transition"
    FIXED = "fixed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DecodedFrame:
    raw: str
    category: FrameCategory
    mode: Mode = Mode.UNKNOWN
    speed: int | None = None
    phase: Phase = Phase.UNKNOWN
    checksum_valid: bool = False
    description: str = ""


@dataclass(frozen=True)
class SequenceStep:
    frame: str
    duration: float
    phase: Phase


CONTROL_FRAMES: dict[str, DecodedFrame] = {
    # Manuell alternierend, Stufe 1
    "01A500A4": DecodedFrame(
        raw="01A500A4",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=1,
        phase=Phase.PHASE_A,
        checksum_valid=True,
    ),
    "01A100A0": DecodedFrame(
        raw="01A100A0",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=1,
        phase=Phase.TRANSITION,
        checksum_valid=True,
    ),
    "01A900A8": DecodedFrame(
        raw="01A900A8",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=1,
        phase=Phase.PHASE_B,
        checksum_valid=True,
    ),

    # Manuell alternierend, Stufe 2
    "01AA00AB": DecodedFrame(
        raw="01AA00AB",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=2,
        phase=Phase.PHASE_A,
        checksum_valid=True,
    ),
    "01A200A3": DecodedFrame(
        raw="01A200A3",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=2,
        phase=Phase.TRANSITION,
        checksum_valid=True,
    ),
    "01A600A7": DecodedFrame(
        raw="01A600A7",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=2,
        phase=Phase.PHASE_B,
        checksum_valid=True,
    ),

    # Manuell alternierend, Stufe 3
    "01A700A6": DecodedFrame(
        raw="01A700A6",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=3,
        phase=Phase.PHASE_A,
        checksum_valid=True,
    ),
    "01A300A2": DecodedFrame(
        raw="01A300A2",
        category=FrameCategory.CONTROL,
        mode=Mode.MANUAL_ALTERNATING,
        speed=3,
        phase=Phase.TRANSITION,
        checksum_valid=True,
    ),

    # Beide Lüfter dauerhaft Abluft
    "01750074": DecodedFrame(
        raw="01750074",
        category=FrameCategory.CONTROL,
        mode=Mode.EXTRACT,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "01760077": DecodedFrame(
        raw="01760077",
        category=FrameCategory.CONTROL,
        mode=Mode.EXTRACT,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "01770076": DecodedFrame(
        raw="01770076",
        category=FrameCategory.CONTROL,
        mode=Mode.EXTRACT,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),

    # Beide Lüfter dauerhaft Zuluft
    "01790078": DecodedFrame(
        raw="01790078",
        category=FrameCategory.CONTROL,
        mode=Mode.SUPPLY,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "017A007B": DecodedFrame(
        raw="017A007B",
        category=FrameCategory.CONTROL,
        mode=Mode.SUPPLY,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "017B007A": DecodedFrame(
        raw="017B007A",
        category=FrameCategory.CONTROL,
        mode=Mode.SUPPLY,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),

    # Master Abluft, Slave Zuluft
    "01690068": DecodedFrame(
        raw="01690068",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "016A006B": DecodedFrame(
        raw="016A006B",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "016B006A": DecodedFrame(
        raw="016B006A",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),

    # Master Zuluft, Slave Abluft
    "01650064": DecodedFrame(
        raw="01650064",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "01660067": DecodedFrame(
        raw="01660067",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "01670066": DecodedFrame(
        raw="01670066",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),

    # Silent
    "01A400A5": DecodedFrame(
        raw="01A400A5",
        category=FrameCategory.CONTROL,
        mode=Mode.SILENT,
        speed=1,
        phase=Phase.PHASE_A,
        checksum_valid=True,
    ),
    "01A000A1": DecodedFrame(
        raw="01A000A1",
        category=FrameCategory.CONTROL,
        mode=Mode.SILENT,
        speed=1,
        phase=Phase.TRANSITION,
        checksum_valid=True,
    ),
    "01A800A9": DecodedFrame(
        raw="01A800A9",
        category=FrameCategory.CONTROL,
        mode=Mode.SILENT,
        speed=1,
        phase=Phase.PHASE_B,
        checksum_valid=True,
    ),
}


SHORT_FRAMES: dict[tuple[str, str], DecodedFrame] = {
    ("panel", "020002"): DecodedFrame(
        raw="020002",
        category=FrameCategory.REQUEST,
        description="Statusabfrage des Wandpanels",
    ),
    ("panel", "020406"): DecodedFrame(
        raw="020406",
        category=FrameCategory.REQUEST,
        description="Erweiterte Statusabfrage des Wandpanels",
    ),
    ("fans", "000202"): DecodedFrame(
        raw="000202",
        category=FrameCategory.REPLY,
        description="Statusantwort des Masters",
    ),
    ("fans", "000A0A"): DecodedFrame(
        raw="000A0A",
        category=FrameCategory.REPLY,
        description="Erweiterte Statusantwort des Masters",
    ),
    ("fans", "000000"): DecodedFrame(
        raw="000000",
        category=FrameCategory.STARTUP,
        description="Start-/Initialisierungstelegramm",
    ),
    ("fans", "000101"): DecodedFrame(
        raw="000101",
        category=FrameCategory.STARTUP,
        description="Start-/Initialisierungstelegramm",
    ),
}


FIXED_COMMAND_FRAMES: dict[tuple[Mode, int], str] = {
    (Mode.EXTRACT, 1): "01750074",
    (Mode.EXTRACT, 2): "01760077",
    (Mode.EXTRACT, 3): "01770076",

    (Mode.SUPPLY, 1): "01790078",
    (Mode.SUPPLY, 2): "017A007B",
    (Mode.SUPPLY, 3): "017B007A",

    (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 1): "01690068",
    (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 2): "016A006B",
    (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 3): "016B006A",

    (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 1): "01650064",
    (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 2): "01660067",
    (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 3): "01670066",
}


ALTERNATING_SEQUENCES: dict[
    tuple[Mode, int],
    tuple[SequenceStep, ...],
] = {
    (Mode.MANUAL_ALTERNATING, 1): (
        SequenceStep("01A500A4", 60.0, Phase.PHASE_A),
        SequenceStep("01A100A0", 10.0, Phase.TRANSITION),
        SequenceStep("01A900A8", 60.0, Phase.PHASE_B),
        SequenceStep("01A100A0", 10.0, Phase.TRANSITION),
    ),
    (Mode.MANUAL_ALTERNATING, 2): (
        SequenceStep("01AA00AB", 60.0, Phase.PHASE_A),
        SequenceStep("01A200A3", 10.0, Phase.TRANSITION),
        SequenceStep("01A600A7", 60.0, Phase.PHASE_B),
        SequenceStep("01A200A3", 10.0, Phase.TRANSITION),
    ),
}


def normalize_payload(payload: str) -> str:
    return payload.upper().replace(" ", "")


def checksum_for(data_bytes: bytes) -> int:
    checksum = 0

    for value in data_bytes:
        checksum ^= value

    return checksum


def is_valid_control_frame(payload: str) -> bool:
    normalized = normalize_payload(payload)

    try:
        data = bytes.fromhex(normalized)
    except ValueError:
        return False

    if len(data) != 4:
        return False

    return checksum_for(data[:3]) == data[3]


def make_packet(payload: str) -> bytes:
    normalized = normalize_payload(payload)

    if not is_valid_control_frame(normalized):
        raise ValueError(f"Invalid Ambientika control frame: {normalized}")

    return bytes([STX]) + normalized.encode("ascii") + bytes([ETX])


def decode_frame(source: str, payload: str) -> DecodedFrame:
    source_normalized = source.lower()
    normalized = normalize_payload(payload)

    short_frame = SHORT_FRAMES.get((source_normalized, normalized))

    if short_frame is not None:
        return short_frame

    known_control = CONTROL_FRAMES.get(normalized)

    if known_control is not None:
        return known_control

    if is_valid_control_frame(normalized):
        return DecodedFrame(
            raw=normalized,
            category=FrameCategory.UNKNOWN_CONTROL,
            checksum_valid=True,
            description="Valid but not yet mapped control frame",
        )

    return DecodedFrame(
        raw=normalized,
        category=FrameCategory.UNKNOWN,
        checksum_valid=False,
        description="Unknown or malformed frame",
    )


def fixed_command_frame(mode: Mode, speed: int) -> str:
    try:
        return FIXED_COMMAND_FRAMES[(mode, speed)]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported fixed mode/speed: {mode.value}/{speed}"
        ) from exc


def alternating_sequence(
    mode: Mode,
    speed: int,
) -> tuple[SequenceStep, ...]:
    try:
        return ALTERNATING_SEQUENCES[(mode, speed)]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported alternating mode/speed: {mode.value}/{speed}"
        ) from exc
