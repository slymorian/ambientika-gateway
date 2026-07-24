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
    AUTOMATIC = "automatic"
    MONITORING = "monitoring"
    MANUAL_ALTERNATING = "manual_alternating"
    SILENT = "silent"
    TIMED_EXTRACT = "timed_extract"

    MASTER_EXTRACT_SLAVE_SUPPLY = "master_extract_slave_supply"
    MASTER_SUPPLY_SLAVE_EXTRACT = "master_supply_slave_extract"

    EXTRACT = "extract"
    SUPPLY = "supply"

    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ModeInfo:
    mqtt_value: str
    label_de: str
    icon: str
    supports_speed: bool = False
    supports_humidity_level: bool = False
    alternating: bool = False


MODE_INFO: dict[Mode, ModeInfo] = {
    Mode.AUTOMATIC: ModeInfo(
        mqtt_value="automatic",
        label_de="Automatisch",
        icon="mdi:fan-auto",
        supports_humidity_level=True,
        alternating=True,
    ),
    Mode.MONITORING: ModeInfo(
        mqtt_value="monitoring",
        label_de="Überwachung",
        icon="mdi:eye-outline",
        supports_humidity_level=True,
    ),
    Mode.MANUAL_ALTERNATING: ModeInfo(
        mqtt_value="manual_alternating",
        label_de="Manuell",
        icon="mdi:fan",
        supports_speed=True,
        alternating=True,
    ),
    Mode.SILENT: ModeInfo(
        mqtt_value="silent",
        label_de="Silent",
        icon="mdi:weather-night",
        alternating=True,
    ),
    Mode.TIMED_EXTRACT: ModeInfo(
        mqtt_value="timed_extract",
        label_de="Zeitgeschaltete Abluft",
        icon="mdi:timer-outline",
    ),
    Mode.MASTER_EXTRACT_SLAVE_SUPPLY: ModeInfo(
        mqtt_value="master_extract_slave_supply",
        label_de="Master Abluft, Slave Zuluft",
        icon="mdi:swap-horizontal",
        supports_speed=True,
    ),
    Mode.MASTER_SUPPLY_SLAVE_EXTRACT: ModeInfo(
        mqtt_value="master_supply_slave_extract",
        label_de="Master Zuluft, Slave Abluft",
        icon="mdi:swap-horizontal",
        supports_speed=True,
    ),
    Mode.EXTRACT: ModeInfo(
        mqtt_value="extract",
        label_de="Abluft",
        icon="mdi:arrow-collapse-up",
        supports_speed=True,
    ),
    Mode.SUPPLY: ModeInfo(
        mqtt_value="supply",
        label_de="Zuluft",
        icon="mdi:arrow-collapse-down",
        supports_speed=True,
    ),
}


def selectable_modes() -> tuple[Mode, ...]:
    return tuple(MODE_INFO)


def mqtt_mode_values() -> list[str]:
    return [
        MODE_INFO[mode].mqtt_value
        for mode in selectable_modes()
    ]


def mode_from_mqtt(value: str) -> Mode:
    normalized = value.strip().lower()

    # Alias für bisherige MQTT-Befehle
    if normalized == "manual":
        return Mode.MANUAL_ALTERNATING

    for mode, info in MODE_INFO.items():
        if info.mqtt_value == normalized:
            return mode

    supported = ", ".join(mqtt_mode_values())

    raise ValueError(
        f"Unknown Ambientika mode {value!r}; supported: {supported}"
    )


def mode_label_de(mode: Mode) -> str:
    info = MODE_INFO.get(mode)

    if info is None:
        return "Unbekannt"

    return info.label_de


def mode_icon(mode: Mode) -> str:
    info = MODE_INFO.get(mode)

    if info is None:
        return "mdi:help-circle-outline"

    return info.icon


class Phase(str, Enum):
    PHASE_A = "phase_a"
    PHASE_B = "phase_b"
    TRANSITION = "transition"
    FIXED = "fixed"
    UNKNOWN = "unknown"


class OperatingState(str, Enum):
    """Physical operating state commanded on the fan bus.

    The selected panel mode and the physical fan state are not always the
    same. Automatic and Monitoring, for example, share the same extract
    state while a humidity alarm is active.
    """

    ALTERNATING = "alternating"
    EXTRACT = "extract"
    SUPPLY = "supply"
    IDLE = "idle"
    TRANSITION = "transition"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DecodedFrame:
    raw: str
    category: FrameCategory
    mode: Mode = Mode.UNKNOWN
    speed: int | None = None
    humidity_level: int | None = None
    phase: Phase = Phase.UNKNOWN
    checksum_valid: bool = False
    description: str = ""
    button_press: bool = False
    filter_reset: bool = False
    filter_alarm: bool | None = None
    status_byte: int | None = None
    operating_state: OperatingState = OperatingState.UNKNOWN
    possible_modes: tuple[Mode, ...] = ()


@dataclass(frozen=True)
class SequenceStep:
    frame: str
    duration: float
    phase: Phase


CONTROL_FRAMES: dict[str, DecodedFrame] = {
    # Wechselbetrieb, Stufe 1 (z. B. Automatic oder manuell)
    "01A500A4": DecodedFrame(
        raw="01A500A4",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=1,
        phase=Phase.PHASE_A,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),
    "01A100A0": DecodedFrame(
        raw="01A100A0",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=1,
        phase=Phase.TRANSITION,
        checksum_valid=True,
        operating_state=OperatingState.TRANSITION,
    ),
    "01A900A8": DecodedFrame(
        raw="01A900A8",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=1,
        phase=Phase.PHASE_B,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),

    # Wechselbetrieb, Stufe 2 (z. B. Automatic oder manuell)
    "01AA00AB": DecodedFrame(
        raw="01AA00AB",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=2,
        phase=Phase.PHASE_A,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),
    "01A200A3": DecodedFrame(
        raw="01A200A3",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=2,
        phase=Phase.TRANSITION,
        checksum_valid=True,
        operating_state=OperatingState.TRANSITION,
    ),
    "01A600A7": DecodedFrame(
        raw="01A600A7",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=2,
        phase=Phase.PHASE_B,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),

    # Wechselbetrieb, Stufe 3 (z. B. Automatic oder manuell)
    "01A700A6": DecodedFrame(
        raw="01A700A6",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=3,
        phase=Phase.PHASE_A,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),
    "01A300A2": DecodedFrame(
        raw="01A300A2",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        possible_modes=(Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING),
        speed=3,
        phase=Phase.TRANSITION,
        checksum_valid=True,
        operating_state=OperatingState.TRANSITION,
    ),

    # Beide Lüfter dauerhaft Abluft
    "01750074": DecodedFrame(
        raw="01750074",
        category=FrameCategory.CONTROL,
        mode=Mode.EXTRACT,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
        operating_state=OperatingState.EXTRACT,
    ),
    "01760077": DecodedFrame(
        raw="01760077",
        category=FrameCategory.CONTROL,
        mode=Mode.EXTRACT,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
        operating_state=OperatingState.EXTRACT,
    ),
    "01770076": DecodedFrame(
        raw="01770076",
        category=FrameCategory.CONTROL,
        mode=Mode.EXTRACT,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
        operating_state=OperatingState.EXTRACT,
    ),

    # Beide Lüfter dauerhaft Zuluft
    "01790078": DecodedFrame(
        raw="01790078",
        category=FrameCategory.CONTROL,
        mode=Mode.SUPPLY,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
        operating_state=OperatingState.SUPPLY,
    ),
    "017A007B": DecodedFrame(
        raw="017A007B",
        category=FrameCategory.CONTROL,
        mode=Mode.SUPPLY,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
        operating_state=OperatingState.SUPPLY,
    ),
    "017B007A": DecodedFrame(
        raw="017B007A",
        category=FrameCategory.CONTROL,
        mode=Mode.SUPPLY,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
        operating_state=OperatingState.SUPPLY,
    ),

    # Master Zuluft, Slave Abluft
    "01690068": DecodedFrame(
        raw="01690068",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "016A006B": DecodedFrame(
        raw="016A006B",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "016B006A": DecodedFrame(
        raw="016B006A",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),

    # Master Abluft, Slave Zuluft
    "01650064": DecodedFrame(
        raw="01650064",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
        speed=1,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "01660067": DecodedFrame(
        raw="01660067",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
        speed=2,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),
    "01670066": DecodedFrame(
        raw="01670066",
        category=FrameCategory.CONTROL,
        mode=Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
        speed=3,
        phase=Phase.FIXED,
        checksum_valid=True,
    ),

    # Feuchteschwellen-/Modusrahmen für Automatic und Monitoring.
    #
    # Diese Frames enthalten die gewählte Feuchteschwelle. Sie beweisen
    # weder einen aktiven Feuchtealarm noch einen bestimmten physischen
    # Lüfterzustand. Insbesondere wurde 01B604B3 bei Auto, Schwelle 3,
    # Feuchtealarm AUS und gleichzeitigem Wechselbetrieb beobachtet.
    #
    # Byte 3 = 0x0C wurde beim Tastendruck beobachtet, Byte 3 = 0x04
    # im anschließend stabilen Zustand. Der Filteralarm wird ausschließlich
    # aus den Master-Antworten 000808 / 000A0A abgeleitet.
    "01360C3B": DecodedFrame(
        raw="01360C3B",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        humidity_level=1,
        checksum_valid=True,
        description="Feuchteschwelle 1, Automatic oder Monitoring (Tastendruck)",
        button_press=True,
        possible_modes=(Mode.AUTOMATIC, Mode.MONITORING),
    ),
    "01360433": DecodedFrame(
        raw="01360433",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        humidity_level=1,
        checksum_valid=True,
        description="Feuchteschwelle 1, Automatic oder Monitoring",
        possible_modes=(Mode.AUTOMATIC, Mode.MONITORING),
    ),
    "01760C7B": DecodedFrame(
        raw="01760C7B",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        humidity_level=2,
        checksum_valid=True,
        description="Feuchteschwelle 2, Automatic oder Monitoring (Tastendruck)",
        button_press=True,
        possible_modes=(Mode.AUTOMATIC, Mode.MONITORING),
    ),
    "01760473": DecodedFrame(
        raw="01760473",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        humidity_level=2,
        checksum_valid=True,
        description="Feuchteschwelle 2, Automatic oder Monitoring",
        possible_modes=(Mode.AUTOMATIC, Mode.MONITORING),
    ),
    "01B60CBB": DecodedFrame(
        raw="01B60CBB",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        humidity_level=3,
        checksum_valid=True,
        description="Feuchteschwelle 3, Automatic oder Monitoring (Tastendruck)",
        button_press=True,
        possible_modes=(Mode.AUTOMATIC, Mode.MONITORING),
    ),
    "01B604B3": DecodedFrame(
        raw="01B604B3",
        category=FrameCategory.CONTROL,
        mode=Mode.UNKNOWN,
        humidity_level=3,
        checksum_valid=True,
        description="Feuchteschwelle 3, Automatic oder Monitoring",
        possible_modes=(Mode.AUTOMATIC, Mode.MONITORING),
    ),

    # Filter-Reset im Überwachungsmodus, beobachtet bei Schwelle 1.
    # 0x0D = Reset-Bit + Tastendruckbit, 0x05 = Reset-Bit ohne Tastendruckbit.
    "01360D3A": DecodedFrame(
        raw="01360D3A",
        category=FrameCategory.CONTROL,
        mode=Mode.MONITORING,
        humidity_level=1,
        phase=Phase.FIXED,
        checksum_valid=True,
        description="Filter-Reset (Tastendruck)",
        button_press=True,
        filter_reset=True,
        possible_modes=(Mode.MONITORING,),
    ),
    "01360532": DecodedFrame(
        raw="01360532",
        category=FrameCategory.CONTROL,
        mode=Mode.MONITORING,
        humidity_level=1,
        phase=Phase.FIXED,
        checksum_valid=True,
        description="Filter-Reset",
        button_press=False,
        filter_reset=True,
        possible_modes=(Mode.MONITORING,),
    ),

    # Silent
    "01280029": DecodedFrame(
        raw="01280029",
        category=FrameCategory.CONTROL,
        mode=Mode.SILENT,
        speed=1,
        phase=Phase.PHASE_A,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),
    "01200021": DecodedFrame(
        raw="01200021",
        category=FrameCategory.CONTROL,
        mode=Mode.SILENT,
        speed=1,
        phase=Phase.TRANSITION,
        checksum_valid=True,
        operating_state=OperatingState.TRANSITION,
    ),
    "01240025": DecodedFrame(
        raw="01240025",
        category=FrameCategory.CONTROL,
        mode=Mode.SILENT,
        speed=1,
        phase=Phase.PHASE_B,
        checksum_valid=True,
        operating_state=OperatingState.ALTERNATING,
    ),
}


SHORT_FRAMES: dict[tuple[str, str], DecodedFrame] = {
    ("panel", "020002"): DecodedFrame(
        raw="020002",
        category=FrameCategory.REQUEST,
        description="Kurze Statusabfrage des Wandpanels",
    ),
    ("panel", "020406"): DecodedFrame(
        raw="020406",
        category=FrameCategory.REQUEST,
        description="Erweiterte Statusabfrage des Wandpanels",
    ),
    ("panel", "020507"): DecodedFrame(
        raw="020507",
        category=FrameCategory.REQUEST,
        description="Erweiterte Statusabfrage mit Filter-Reset-Bit",
        filter_reset=True,
    ),
    ("fans", "000202"): DecodedFrame(
        raw="000202",
        category=FrameCategory.REPLY,
        description="Kurze Statusantwort des Masters",
        status_byte=0x02,
    ),
    ("fans", "000808"): DecodedFrame(
        raw="000808",
        category=FrameCategory.REPLY,
        description="Erweiterte Statusantwort des Masters",
        filter_alarm=False,
        status_byte=0x08,
    ),
    ("fans", "000A0A"): DecodedFrame(
        raw="000A0A",
        category=FrameCategory.REPLY,
        description="Erweiterte Statusantwort des Masters; Filteralarm aktiv",
        filter_alarm=True,
        status_byte=0x0A,
    ),
    ("fans", "000000"): DecodedFrame(
        raw="000000",
        category=FrameCategory.STARTUP,
        description="Start-/Initialisierungstelegramm",
        status_byte=0x00,
    ),
    ("fans", "000101"): DecodedFrame(
        raw="000101",
        category=FrameCategory.STARTUP,
        description="Start-/Initialisierungstelegramm",
        status_byte=0x01,
    ),
}


FIXED_COMMAND_FRAMES: dict[tuple[Mode, int], str] = {
    (Mode.EXTRACT, 1): "01750074",
    (Mode.EXTRACT, 2): "01760077",
    (Mode.EXTRACT, 3): "01770076",

    (Mode.SUPPLY, 1): "01790078",
    (Mode.SUPPLY, 2): "017A007B",
    (Mode.SUPPLY, 3): "017B007A",

    (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 1): "01650064",
    (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 2): "01660067",
    (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 3): "01670066",

    (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 1): "01690068",
    (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 2): "016A006B",
    (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 3): "016B006A",
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
    (Mode.SILENT, 1): (
        SequenceStep("01280029", 60.0, Phase.PHASE_A),
        SequenceStep("01200021", 10.0, Phase.TRANSITION),
        SequenceStep("01240025", 60.0, Phase.PHASE_B),
        SequenceStep("01200021", 10.0, Phase.TRANSITION),
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


def candidate_modes(frame: DecodedFrame) -> tuple[Mode, ...]:
    """Return all selected panel modes compatible with a frame."""
    if frame.possible_modes:
        return frame.possible_modes

    if frame.mode is not Mode.UNKNOWN:
        return (frame.mode,)

    return ()


def filter_alarm_from_reply(payload: str) -> bool | None:
    """Return the decoded filter-alarm state for a known master reply.

    The result is ``None`` for frames for which the filter bit has not yet
    been verified. Currently the comparison 0x0A -> 0x08 after a physical
    filter reset proves bit 0x02 for the extended master status reply.
    """
    normalized = normalize_payload(payload)

    if normalized == "000A0A":
        return True

    if normalized == "000808":
        return False

    return None


def monitoring_command_frame(humidity_level: int) -> str:
    """Return the stable monitoring command for humidity level 1..3."""
    frames = {
        1: "01360433",
        2: "01760473",
        3: "01B604B3",
    }

    try:
        return frames[humidity_level]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported monitoring humidity level: {humidity_level}"
        ) from exc


def monitoring_button_frame(humidity_level: int) -> str:
    """Return the observed button/transition frame for level 1..3."""
    frames = {
        1: "01360C3B",
        2: "01760C7B",
        3: "01B60CBB",
    }

    try:
        return frames[humidity_level]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported monitoring humidity level: {humidity_level}"
        ) from exc


def filter_reset_frames() -> tuple[str, str, str]:
    """Return the observed filter-reset sequence for monitoring level 1.

    Sequence:
      1. control frame with reset + button bit
      2. control frame with reset bit
      3. one extended status request with reset bit
    The panel then returned to the ordinary stable command/status request.
    """
    return ("01360D3A", "01360532", "020507")


def fixed_command_frame(mode: Mode, speed: int) -> str:
    try:
        return FIXED_COMMAND_FRAMES[(mode, speed)]
    except KeyError as exc:
        mode_name = (
            mode.value
            if isinstance(mode, Mode)
            else repr(mode)
        )

        raise ValueError(
            f"Unsupported fixed mode/speed: {mode_name}/{speed}"
        ) from exc


def alternating_sequence(
    mode: Mode,
    speed: int,
) -> tuple[SequenceStep, ...]:
    try:
        return ALTERNATING_SEQUENCES[(mode, speed)]
    except KeyError as exc:
        mode_name = (
            mode.value
            if isinstance(mode, Mode)
            else repr(mode)
        )

        raise ValueError(
            f"Unsupported alternating mode/speed: {mode_name}/{speed}"
        ) from exc


