from __future__ import annotations

from dataclasses import dataclass

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
    fixed_frame: str | None = None
    sequence: tuple[SequenceStep, ...] = ()

    @property
    def alternating(self) -> bool:
        return bool(self.sequence)


class FrameGenerator:
    """Central translation from logical state to Ambientika frames.

    Keeping this translation outside the gateway makes future control
    policies (notably Assist mode) reuse the same validation and frame
    generation without duplicating protocol constants.
    """

    def plan(
        self,
        *,
        mode: Mode,
        speed: int,
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

        try:
            frame = fixed_command_frame(mode, speed)
        except ValueError:
            frame = None

        if frame is not None:
            return ControlPlan(
                selection=selection,
                fixed_frame=frame,
            )

        try:
            sequence = alternating_sequence(mode, speed)
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
        )

    def supports(
        self,
        *,
        mode: Mode,
        speed: int,
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
