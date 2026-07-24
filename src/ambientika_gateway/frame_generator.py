from __future__ import annotations

from dataclasses import dataclass
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
    fixed_frame: str | None = None
    sequence: tuple[SequenceStep, ...] = ()

    @property
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
        self,
        *,
        mode: Mode,
        speed: int,
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

        try:
            frame = fixed_command_frame(mode, speed)
        except ValueError:
            frame = None

        if frame is not None:
            return ControlProgram(
                kind=ProgramKind.FIXED,
                mode=mode,
                speed=speed,
                humidity_level=humidity_level,
                fixed_frame=frame,
            )

        try:
            sequence = alternating_sequence(mode, speed)
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
        )

    def supports(
        self,
        *,
        mode: Mode,
        speed: int,
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
