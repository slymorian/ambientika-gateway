from __future__ import annotations

from dataclasses import dataclass

from .protocol import (
    Mode,
    SequenceStep,
    alternating_sequence,
    fixed_command_frame,
    make_packet,
    monitoring_command_frame,
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

    def normalize(
        self,
        *,
        mode: Mode,
        speed: int,
        humidity: int,
    ) -> ControlSelection:
        """Normalize irrelevant values to a confirmed protocol selection.

        Home Assistant publishes mode, speed and humidity independently. A
        mode change must therefore not fail merely because the retained speed
        or humidity value is irrelevant for the new mode. The desired state
        itself remains unchanged, so switching back restores the user's last
        speed/threshold selection.
        """
        if speed not in (1, 2, 3):
            raise ValueError(f"Unsupported Ambientika speed: {speed}")

        if humidity not in (1, 2, 3):
            raise ValueError(
                f"Unsupported Ambientika humidity threshold: {humidity}"
            )

        if mode is Mode.SILENT:
            return ControlSelection(mode=mode, speed=1, humidity=2)

        if mode is Mode.AUTOMATIC:
            # Only the stable automatic command for threshold 2 is confirmed.
            return ControlSelection(mode=mode, speed=2, humidity=2)

        if mode is Mode.MONITORING:
            return ControlSelection(mode=mode, speed=2, humidity=humidity)

        return ControlSelection(mode=mode, speed=speed, humidity=humidity)

    def plan(
        self,
        *,
        mode: Mode,
        speed: int,
        humidity: int,
    ) -> ControlPlan:
        selection = self.normalize(
            mode=mode,
            speed=speed,
            humidity=humidity,
        )

        if selection.mode is Mode.AUTOMATIC:
            return ControlPlan(
                selection=selection,
                fixed_frame="01720073",
            )

        if selection.mode is Mode.MONITORING:
            return ControlPlan(
                selection=selection,
                fixed_frame=monitoring_command_frame(selection.humidity),
            )

        try:
            frame = fixed_command_frame(selection.mode, selection.speed)
        except ValueError:
            frame = None

        if frame is not None:
            return ControlPlan(
                selection=selection,
                fixed_frame=frame,
            )

        try:
            sequence = alternating_sequence(
                selection.mode,
                selection.speed,
            )
        except ValueError:
            sequence = ()

        if sequence:
            return ControlPlan(
                selection=selection,
                sequence=sequence,
            )

        raise ValueError(
            "Unsupported Ambientika control selection: "
            f"{selection.mode.value}, speed {selection.speed}, "
            f"humidity {selection.humidity}"
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
