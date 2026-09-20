from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from enum import Enum

from .protocol import (
    DecodedFrame,
    FrameCategory,
    Mode,
    OperatingState,
    Phase,
)


def carry_over_humidity_alarm(
    previous: bool | None,
    operating_state: OperatingState,
) -> bool | None:
    """Decide what remains of a known humidity alarm after a frame that
    carries no alarm information of its own.

    * Frame describes no physical state (threshold/button frames,
      unmapped control frames): the alarm state is left untouched
      (architecture rule E: a threshold frame is not a physical state).
    * Frame describes a definite physical state (alternating, transition,
      extract, supply, ...) but has no alarm information: a previously
      observed alarm is no longer supported by the bus traffic and is
      retracted to ``False``. Observed on 30.07.2026: Home Assistant kept
      showing "Feuchtealarm: nass" during clean alternating operation.
    * An alarm state that was never asserted (``None``) stays ``None``;
      nothing is invented (an unknown state is not "no alarm").
    """
    if previous is True and operating_state is not OperatingState.UNKNOWN:
        return False
    return previous


class ControlPolicy(str, Enum):
    """How the gateway arbitrates panel and software control."""

    TRANSPARENT = "transparent"
    OVERRIDE = "override"
    ASSIST = "assist"


@dataclass(frozen=True)
class PanelState:
    raw_frame: str | None = None
    mode: Mode = Mode.UNKNOWN
    speed: int | None = None
    humidity: int | None = None
    operating_state: OperatingState = OperatingState.UNKNOWN
    humidity_alarm: bool | None = None
    phase: Phase = Phase.UNKNOWN
    last_seen_monotonic: float | None = None

    @property
    def available(self) -> bool:
        return self.last_seen_monotonic is not None


@dataclass(frozen=True)
class DesiredState:
    """Logical target selected through MQTT/Home Assistant."""

    desired_mode: Mode = Mode.EXTRACT
    desired_speed: int = 3
    desired_humidity: int = 2
    generation: int = 0


@dataclass(frozen=True)
class OverrideState:
    """Runtime state of software control.

    The desired values live in :class:`DesiredState`; this object only
    tracks arbitration and the frame currently emitted by the controller.
    """

    enabled: bool = False
    policy: ControlPolicy = ControlPolicy.TRANSPARENT
    phase: Phase = Phase.UNKNOWN
    raw_frame: str | None = None
    generation: int = 0


@dataclass(frozen=True)
class ActiveState:
    source: str = "unknown"
    raw_frame: str | None = None
    mode: Mode = Mode.UNKNOWN
    speed: int | None = None
    humidity: int | None = None
    operating_state: OperatingState = OperatingState.UNKNOWN
    humidity_alarm: bool | None = None
    phase: Phase = Phase.UNKNOWN
    last_sent_monotonic: float | None = None


@dataclass(frozen=True)
class FanReplyState:
    raw_frame: str | None = None
    category: FrameCategory = FrameCategory.UNKNOWN
    description: str = ""
    status_byte: int | None = None
    filter_alarm: bool | None = None
    humidity_alarm: bool | None = None
    last_seen_monotonic: float | None = None


@dataclass(frozen=True)
class GatewaySnapshot:
    panel: PanelState
    desired: DesiredState
    override: OverrideState
    active: ActiveState
    fan_reply: FanReplyState

    @property
    def desired_mode(self) -> Mode:
        return self.desired.desired_mode

    @property
    def desired_speed(self) -> int:
        return self.desired.desired_speed

    @property
    def desired_humidity(self) -> int:
        return self.desired.desired_humidity

    @property
    def operating_state(self) -> OperatingState:
        return self.active.operating_state

    @property
    def humidity_alarm(self) -> bool | None:
        return self.active.humidity_alarm

    @property
    def phase(self) -> Phase:
        return self.active.phase


class GatewayState:
    """Thread-safe source of truth for desired and observed state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._panel = PanelState()
        self._desired = DesiredState()
        self._override = OverrideState()
        self._active = ActiveState()
        self._fan_reply = FanReplyState()

    def snapshot(self) -> GatewaySnapshot:
        with self._lock:
            return GatewaySnapshot(
                panel=self._panel,
                desired=self._desired,
                override=self._override,
                active=self._active,
                fan_reply=self._fan_reply,
            )

    def update_panel_frame(
        self,
        frame: DecodedFrame,
        *,
        seen_at: float | None = None,
    ) -> PanelState:
        if frame.category not in {
            FrameCategory.CONTROL,
            FrameCategory.UNKNOWN_CONTROL,
        }:
            return self.panel_state()

        timestamp = time.monotonic() if seen_at is None else seen_at

        with self._lock:
            previous = self._panel
            self._panel = PanelState(
                raw_frame=frame.raw,
                mode=(
                    frame.mode
                    if frame.mode is not Mode.UNKNOWN
                    else previous.mode
                ),
                speed=frame.speed if frame.speed is not None else previous.speed,
                humidity=(
                    frame.humidity_level
                    if frame.humidity_level is not None
                    else previous.humidity
                ),
                operating_state=(
                    frame.operating_state
                    if frame.operating_state is not OperatingState.UNKNOWN
                    else previous.operating_state
                ),
                humidity_alarm=(
                    frame.humidity_alarm
                    if frame.humidity_alarm is not None
                    else carry_over_humidity_alarm(
                        previous.humidity_alarm,
                        frame.operating_state,
                    )
                ),
                phase=(
                    frame.phase
                    if frame.phase is not Phase.UNKNOWN
                    else previous.phase
                ),
                last_seen_monotonic=timestamp,
            )
            return self._panel

    def panel_state(self) -> PanelState:
        with self._lock:
            return self._panel

    def desired_state(self) -> DesiredState:
        with self._lock:
            return self._desired

    def configure_desired(
        self,
        *,
        mode: Mode | None = None,
        speed: int | None = None,
        humidity: int | None = None,
    ) -> DesiredState:
        if speed is not None and speed not in (1, 2, 3):
            raise ValueError(f"Unsupported Ambientika speed: {speed}")
        if humidity is not None and humidity not in (1, 2, 3):
            raise ValueError(
                f"Unsupported Ambientika humidity threshold: {humidity}"
            )

        with self._lock:
            new_mode = self._desired.desired_mode if mode is None else mode
            new_speed = self._desired.desired_speed if speed is None else speed
            new_humidity = (
                self._desired.desired_humidity
                if humidity is None
                else humidity
            )
            changed = (
                new_mode != self._desired.desired_mode
                or new_speed != self._desired.desired_speed
                or new_humidity != self._desired.desired_humidity
            )
            generation = self._desired.generation + (1 if changed else 0)
            self._desired = DesiredState(
                desired_mode=new_mode,
                desired_speed=new_speed,
                desired_humidity=new_humidity,
                generation=generation,
            )

            if changed:
                self._override = replace(
                    self._override,
                    phase=Phase.UNKNOWN,
                    raw_frame=None,
                    generation=max(
                        self._override.generation + 1,
                        generation,
                    ),
                )

            return self._desired

    def configure_override(self, *, enabled: bool) -> OverrideState:
        with self._lock:
            policy = (
                ControlPolicy.OVERRIDE
                if enabled
                else ControlPolicy.TRANSPARENT
            )
            changed = (
                enabled != self._override.enabled
                or policy != self._override.policy
            )
            generation = max(
                self._override.generation,
                self._desired.generation,
            ) + (1 if changed else 0)
            self._override = OverrideState(
                enabled=enabled,
                policy=policy,
                phase=Phase.UNKNOWN,
                raw_frame=None,
                generation=generation,
            )
            return self._override

    def override_state(self) -> OverrideState:
        with self._lock:
            return self._override

    def set_override_runtime(
        self,
        *,
        phase: Phase,
        raw_frame: str,
        generation: int,
    ) -> OverrideState:
        with self._lock:
            if (
                generation != self._override.generation
                or not self._override.enabled
            ):
                return self._override
            self._override = replace(
                self._override,
                phase=phase,
                raw_frame=raw_frame,
            )
            return self._override

    def override_generation_is_current(self, generation: int) -> bool:
        with self._lock:
            return (
                self._override.enabled
                and self._override.generation == generation
            )

    def mark_active_panel_frame(
        self,
        frame: DecodedFrame,
        *,
        sent_at: float | None = None,
    ) -> ActiveState:
        timestamp = time.monotonic() if sent_at is None else sent_at
        with self._lock:
            panel = self._panel
            self._active = ActiveState(
                source="panel",
                raw_frame=frame.raw,
                mode=panel.mode,
                speed=panel.speed,
                humidity=panel.humidity,
                operating_state=panel.operating_state,
                humidity_alarm=panel.humidity_alarm,
                phase=panel.phase,
                last_sent_monotonic=timestamp,
            )
            return self._active

    def mark_active_override_frame(
        self,
        *,
        raw_frame: str,
        mode: Mode,
        speed: int,
        humidity: int,
        operating_state: OperatingState,
        phase: Phase,
        humidity_alarm: bool | None = None,
        sent_at: float | None = None,
    ) -> ActiveState:
        timestamp = time.monotonic() if sent_at is None else sent_at
        with self._lock:
            observed_humidity_alarm = humidity_alarm
            if observed_humidity_alarm is None:
                observed_humidity_alarm = self._fan_reply.humidity_alarm
            if observed_humidity_alarm is None:
                observed_humidity_alarm = carry_over_humidity_alarm(
                    self._active.humidity_alarm,
                    operating_state,
                )

            self._active = ActiveState(
                source="override",
                raw_frame=raw_frame,
                mode=mode,
                speed=speed,
                humidity=humidity,
                operating_state=operating_state,
                humidity_alarm=observed_humidity_alarm,
                phase=phase,
                last_sent_monotonic=timestamp,
            )
            return self._active

    def active_state(self) -> ActiveState:
        with self._lock:
            return self._active

    def update_fan_reply(
        self,
        frame: DecodedFrame,
        *,
        seen_at: float | None = None,
    ) -> FanReplyState:
        timestamp = time.monotonic() if seen_at is None else seen_at
        with self._lock:
            self._fan_reply = FanReplyState(
                raw_frame=frame.raw,
                category=frame.category,
                description=frame.description,
                status_byte=frame.status_byte,
                filter_alarm=frame.filter_alarm,
                humidity_alarm=frame.humidity_alarm,
                last_seen_monotonic=timestamp,
            )
            if frame.humidity_alarm is not None:
                self._active = replace(
                    self._active,
                    humidity_alarm=frame.humidity_alarm,
                )
            return self._fan_reply

    def fan_reply_state(self) -> FanReplyState:
        with self._lock:
            return self._fan_reply

    def control_source(self) -> str:
        with self._lock:
            return self._override.policy.value

    def panel_age_seconds(self, *, now: float | None = None) -> float | None:
        with self._lock:
            last_seen = self._panel.last_seen_monotonic
        if last_seen is None:
            return None
        current = time.monotonic() if now is None else now
        return max(0.0, current - last_seen)

    def fan_reply_age_seconds(
        self,
        *,
        now: float | None = None,
    ) -> float | None:
        with self._lock:
            last_seen = self._fan_reply.last_seen_monotonic
        if last_seen is None:
            return None
        current = time.monotonic() if now is None else now
        return max(0.0, current - last_seen)
