from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

from .protocol import (
    DecodedFrame,
    FrameCategory,
    Mode,
    Phase,
)


@dataclass(frozen=True)
class PanelState:
    """
    Zuletzt vom Wandpanel beobachteter Steuerzustand.
    """

    raw_frame: str | None = None
    mode: Mode = Mode.UNKNOWN
    speed: int | None = None
    phase: Phase = Phase.UNKNOWN
    last_seen_monotonic: float | None = None

    @property
    def available(self) -> bool:
        return self.last_seen_monotonic is not None


@dataclass(frozen=True)
class OverrideState:
    """
    Von Home Assistant beziehungsweise MQTT gewünschter Zustand.
    """

    enabled: bool = False
    mode: Mode = Mode.EXTRACT
    speed: int = 3
    phase: Phase = Phase.UNKNOWN
    raw_frame: str | None = None
    generation: int = 0


@dataclass(frozen=True)
class ActiveState:
    """
    Zustand, der aktuell tatsächlich an den Lüfterbus gesendet wird.

    source:
        panel    = Steuerung stammt vom Wandpanel
        override = Steuerung stammt vom Gateway
        unknown  = noch kein Zustand bekannt
    """

    source: str = "unknown"
    raw_frame: str | None = None
    mode: Mode = Mode.UNKNOWN
    speed: int | None = None
    phase: Phase = Phase.UNKNOWN
    last_sent_monotonic: float | None = None


@dataclass(frozen=True)
class FanReplyState:
    """
    Zuletzt empfangene Rückmeldung vom Master/Lüfterbus.
    """

    raw_frame: str | None = None
    category: FrameCategory = FrameCategory.UNKNOWN
    description: str = ""
    last_seen_monotonic: float | None = None


@dataclass(frozen=True)
class GatewaySnapshot:
    """
    Unveränderliche Momentaufnahme des gesamten Gateway-Zustands.
    """

    panel: PanelState
    override: OverrideState
    active: ActiveState
    fan_reply: FanReplyState


class GatewayState:
    """
    Thread-sicherer zentraler Zustand des Gateways.

    Die seriellen Empfangsthreads, der MQTT-Thread und der Override-Sender
    greifen gleichzeitig darauf zu. Deshalb werden sämtliche Änderungen
    über ein gemeinsames Lock geschützt.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

        self._panel = PanelState()
        self._override = OverrideState()
        self._active = ActiveState()
        self._fan_reply = FanReplyState()

    def snapshot(self) -> GatewaySnapshot:
        """
        Liefert eine konsistente Momentaufnahme aller Zustände.
        """

        with self._lock:
            return GatewaySnapshot(
                panel=self._panel,
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
        """
        Übernimmt einen dekodierten Steuerframe des Wandpanels.

        Nur echte oder noch unbekannte gültige Steuerframes verändern den
        Panelzustand. Statusabfragen wie 020002 werden hier nicht gespeichert.
        """

        if frame.category not in {
            FrameCategory.CONTROL,
            FrameCategory.UNKNOWN_CONTROL,
        }:
            return self.panel_state()

        timestamp = (
            time.monotonic()
            if seen_at is None
            else seen_at
        )

        with self._lock:
            self._panel = PanelState(
                raw_frame=frame.raw,
                mode=frame.mode,
                speed=frame.speed,
                phase=frame.phase,
                last_seen_monotonic=timestamp,
            )
            return self._panel

    def panel_state(self) -> PanelState:
        with self._lock:
            return self._panel

    def configure_override(
        self,
        *,
        enabled: bool | None = None,
        mode: Mode | None = None,
        speed: int | None = None,
    ) -> OverrideState:
        """
        Ändert den gewünschten Override-Zustand.

        Bei jeder wirksamen Änderung wird generation erhöht. Laufende
        Override-Sequenzen können dadurch erkennen, dass sie beendet oder
        neu gestartet werden müssen.
        """

        if speed is not None and speed not in (1, 2, 3):
            raise ValueError(
                f"Unsupported Ambientika speed: {speed}"
            )

        with self._lock:
            new_enabled = (
                self._override.enabled
                if enabled is None
                else enabled
            )
            new_mode = (
                self._override.mode
                if mode is None
                else mode
            )
            new_speed = (
                self._override.speed
                if speed is None
                else speed
            )

            changed = (
                new_enabled != self._override.enabled
                or new_mode != self._override.mode
                or new_speed != self._override.speed
            )

            generation = self._override.generation

            if changed:
                generation += 1

            self._override = OverrideState(
                enabled=new_enabled,
                mode=new_mode,
                speed=new_speed,
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
        """
        Aktualisiert die gerade aktive Phase einer Override-Sequenz.

        Die Änderung wird nur übernommen, wenn generation noch der aktuellen
        Override-Generation entspricht. Ein alter Sequenz-Thread kann damit
        keinen neuen Zustand überschreiben.
        """

        with self._lock:
            if generation != self._override.generation:
                return self._override

            if not self._override.enabled:
                return self._override

            self._override = replace(
                self._override,
                phase=phase,
                raw_frame=raw_frame,
            )

            return self._override

    def override_generation_is_current(
        self,
        generation: int,
    ) -> bool:
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
        """
        Markiert einen an die Lüfter weitergeleiteten Panel-Steuerframe.
        """

        timestamp = (
            time.monotonic()
            if sent_at is None
            else sent_at
        )

        with self._lock:
            self._active = ActiveState(
                source="panel",
                raw_frame=frame.raw,
                mode=frame.mode,
                speed=frame.speed,
                phase=frame.phase,
                last_sent_monotonic=timestamp,
            )
            return self._active

    def mark_active_override_frame(
        self,
        *,
        raw_frame: str,
        mode: Mode,
        speed: int,
        phase: Phase,
        sent_at: float | None = None,
    ) -> ActiveState:
        """
        Markiert einen vom Gateway erzeugten und gesendeten Override-Frame.
        """

        if speed not in (1, 2, 3):
            raise ValueError(
                f"Unsupported Ambientika speed: {speed}"
            )

        timestamp = (
            time.monotonic()
            if sent_at is None
            else sent_at
        )

        with self._lock:
            self._active = ActiveState(
                source="override",
                raw_frame=raw_frame,
                mode=mode,
                speed=speed,
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
        """
        Speichert die letzte Rückmeldung oder Startmeldung des Lüfterbusses.
        """

        timestamp = (
            time.monotonic()
            if seen_at is None
            else seen_at
        )

        with self._lock:
            self._fan_reply = FanReplyState(
                raw_frame=frame.raw,
                category=frame.category,
                description=frame.description,
                last_seen_monotonic=timestamp,
            )
            return self._fan_reply

    def fan_reply_state(self) -> FanReplyState:
        with self._lock:
            return self._fan_reply

    def control_source(self) -> str:
        """
        Liefert die momentan vorgesehene Steuerquelle.

        Das bedeutet nicht zwingend, dass bereits ein entsprechender Frame
        gesendet wurde.
        """

        with self._lock:
            return (
                "override"
                if self._override.enabled
                else "panel"
            )

    def panel_age_seconds(
        self,
        *,
        now: float | None = None,
    ) -> float | None:
        """
        Sekunden seit dem letzten Steuerframe des Wandpanels.
        """

        with self._lock:
            last_seen = self._panel.last_seen_monotonic

        if last_seen is None:
            return None

        current = (
            time.monotonic()
            if now is None
            else now
        )

        return max(0.0, current - last_seen)

    def fan_reply_age_seconds(
        self,
        *,
        now: float | None = None,
    ) -> float | None:
        """
        Sekunden seit der letzten Rückmeldung vom Lüfterbus.
        """

        with self._lock:
            last_seen = self._fan_reply.last_seen_monotonic

        if last_seen is None:
            return None

        current = (
            time.monotonic()
            if now is None
            else now
        )

        return max(0.0, current - last_seen)
