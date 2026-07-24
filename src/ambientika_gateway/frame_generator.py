from __future__ import annotations

from dataclasses import dataclass
<<<<<<< HEAD
from enum import Enum

from .protocol import (
    Mode,
    Phase,
    SequenceStep,
    alternating_sequence,
    fixed_command_frame,
    monitoring_command_frame,
)


class ProgramKind(str, Enum):
    FIXED = "fixed"
    ALTERNATING = "alternating"


@dataclass(frozen=True)
class ControlProgram:
    """Executable RS485 program for one desired logical control state."""

    kind: ProgramKind
    mode: Mode
    speed: int
    humidity_level: int
=======

from .protocol import (
    Mode,
    SequenceStep,
    alternating_sequence,
    fixed_command_frame,
    make_packet,
)


@dataclass(frozen=True)
class ControlSelection:
    """Logical target selected through MQTT/Home Assistant."""

    mode: Mode
    speed: int
    humidity: int


@dataclass(frozen=True)
class ControlPlan:
    """Validated protocol plan for one logical target."""

    selection: ControlSelection
>>>>>>> c859a38 (Add stateful control architecture)
    fixed_frame: str | None = None
    sequence: tuple[SequenceStep, ...] = ()

    @property
<<<<<<< HEAD
    def initial_phase(self) -> Phase:
        if self.kind is ProgramKind.FIXED:
            return Phase.FIXED
        if self.sequence:
            return self.sequence[0].phase
        return Phase.UNKNOWN


class FrameGenerator:
    """Translate logical control selections into confirmed protocol frames.

    Keeping this mapping in one place prevents MQTT and gateway code from
    embedding raw hexadecimal frames. Unsupported or insufficiently confirmed
    selections fail explicitly instead of sending guessed commands.
    """

    def build(
=======
    def alternating(self) -> bool:
        return bool(self.sequence)


class FrameGenerator:
    """Central translation from logical state to Ambientika frames.

    Keeping this translation outside the gateway makes future control
    policies (notably Assist mode) reuse the same validation and frame
    generation without duplicating protocol constants.
    """

    def plan(
>>>>>>> c859a38 (Add stateful control architecture)
        self,
        *,
        mode: Mode,
        speed: int,
<<<<<<< HEAD
        humidity_level: int,
    ) -> ControlProgram:
        self._validate(speed=speed, humidity_level=humidity_level)

        if mode is Mode.AUTOMATIC:
            if humidity_level != 2:
                raise ValueError(
                    "Automatic override is currently confirmed only for "
                    "humidity level 2"
                )
            return ControlProgram(
                kind=ProgramKind.FIXED,
                mode=mode,
                speed=speed,
                humidity_level=humidity_level,
                fixed_frame="01720073",
            )

        if mode is Mode.MONITORING:
            return ControlProgram(
                kind=ProgramKind.FIXED,
                mode=mode,
                speed=speed,
                humidity_level=humidity_level,
                fixed_frame=monitoring_command_frame(humidity_level),
            )
=======
        humidity: int,
    ) -> ControlPlan:
        if speed not in (1, 2, 3):
            raise ValueError(f"Unsupported Ambientika speed: {speed}")

        if humidity not in (1, 2, 3):
            raise ValueError(
                f"Unsupported Ambientika humidity threshold: {humidity}"
            )

        selection = ControlSelection(
            mode=mode,
            speed=speed,
            humidity=humidity,
        )
>>>>>>> c859a38 (Add stateful control architecture)

        try:
            frame = fixed_command_frame(mode, speed)
        except ValueError:
            frame = None

        if frame is not None:
<<<<<<< HEAD
            return ControlProgram(
                kind=ProgramKind.FIXED,
                mode=mode,
                speed=speed,
                humidity_level=humidity_level,
=======
            return ControlPlan(
                selection=selection,
>>>>>>> c859a38 (Add stateful control architecture)
                fixed_frame=frame,
            )

        try:
            sequence = alternating_sequence(mode, speed)
<<<<<<< HEAD
        except ValueError as exc:
            raise ValueError(
                "Unsupported Ambientika control selection: "
                f"{mode.value}, speed {speed}, humidity {humidity_level}"
            ) from exc

        return ControlProgram(
            kind=ProgramKind.ALTERNATING,
            mode=mode,
            speed=speed,
            humidity_level=humidity_level,
            sequence=sequence,
=======
        except ValueError:
            sequence = ()

        if sequence:
            return ControlPlan(
                selection=selection,
                sequence=sequence,
            )

        raise ValueError(
            "Unsupported Ambientika control selection: "
            f"{mode.value}, speed {speed}, humidity {humidity}"
>>>>>>> c859a38 (Add stateful control architecture)
        )

    def supports(
        self,
        *,
        mode: Mode,
        speed: int,
<<<<<<< HEAD
        humidity_level: int,
    ) -> bool:
        try:
            self.build(
                mode=mode,
                speed=speed,
                humidity_level=humidity_level,
            )
        except ValueError:
            return False
        return True

    @staticmethod
    def _validate(*, speed: int, humidity_level: int) -> None:
        if speed not in (1, 2, 3):
            raise ValueError(f"Unsupported Ambientika speed: {speed}")
        if humidity_level not in (1, 2, 3):
            raise ValueError(f"Unsupported humidity level: {humidity_level}")
=======
        humidity: int,
    ) -> bool:
        try:
            self.plan(
                mode=mode,
                speed=speed,
                humidity=humidity,
            )
        except ValueError:
            return False

        return True

    @staticmethod
    def packet(frame: str) -> bytes:
        return make_packet(frame)
>>>>>>> c859a38 (Add stateful control architecture)
