from __future__ import annotations

import logging
import threading
import time

from .config import GatewayConfig
from .mqtt_client import AmbientikaMqttClient
from .protocol import (
    DecodedFrame,
    FrameCategory,
    Mode,
    Phase,
    SequenceStep,
    alternating_sequence,
    fixed_command_frame,
    make_packet,
)
from .serial_bus import SerialBus
from .state import GatewayState


LOGGER = logging.getLogger(__name__)


class AmbientikaGateway:
    """
    Verbindet die serielle Gateway-Schicht, den zentralen Zustand
    und die MQTT-Anbindung.

    Transparent:
        Panel-Steuerframes werden an den Lüfterbus weitergeleitet.

    Override:
        Panel-Steuerframes werden blockiert. Statusabfragen und Antworten
        werden weiterhin übertragen. Das Gateway sendet stattdessen den
        gewählten festen Zustand oder eine alternierende Sequenz.
    """

    def __init__(
        self,
        config: GatewayConfig,
    ) -> None:
        self._config = config
        self._state = GatewayState()

        self._stop_event = threading.Event()
        self._override_changed_event = threading.Event()

        self._last_published_panel_frame: str | None = None
        self._last_published_fan_frame: str | None = None

        self._serial_bus = SerialBus(
            config.serial,
            on_frame=self._handle_serial_frame,
        )

        self._serial_bus.set_panel_control_filter(
            self._should_forward_panel_frame
        )

        self._mqtt = AmbientikaMqttClient(
            config.mqtt,
            self._state,
            on_override=self._handle_override_command,
            on_mode=self._handle_mode_command,
            on_speed=self._handle_speed_command,
        )

        self._override_thread: threading.Thread | None = None

    @property
    def state(self) -> GatewayState:
        return self._state

    @property
    def serial_bus(self) -> SerialBus:
        return self._serial_bus

    @property
    def mqtt(self) -> AmbientikaMqttClient:
        return self._mqtt

    def start(self) -> None:
        """
        Startet die seriellen Schnittstellen, MQTT und den Override-Thread.
        """

        LOGGER.info("Starte Ambientika-Gateway")

        self._serial_bus.open()
        self._serial_bus.start()

        try:
            self._mqtt.start()
        except Exception:
            # Die transparente Verbindung soll auch dann weiterlaufen,
            # wenn MQTT beim Programmstart nicht erreichbar ist.
            LOGGER.exception(
                "MQTT konnte nicht gestartet werden; "
                "transparentes Gateway läuft weiter"
            )

        self._override_thread = threading.Thread(
            target=self._override_loop,
            name="ambientika-override",
            daemon=True,
        )
        self._override_thread.start()

        LOGGER.info("Ambientika-Gateway gestartet")

    def stop(self) -> None:
        """
        Beendet alle Threads und schließt die Schnittstellen.
        """

        if self._stop_event.is_set():
            return

        LOGGER.info("Beende Ambientika-Gateway")

        self._stop_event.set()
        self._override_changed_event.set()

        if self._override_thread is not None:
            self._override_thread.join(timeout=2.0)
            self._override_thread = None

        try:
            self._mqtt.stop()
        except Exception:
            LOGGER.exception("Fehler beim Beenden von MQTT")

        self._serial_bus.stop()

        LOGGER.info("Ambientika-Gateway beendet")

    def wait(self) -> None:
        """
        Blockiert den Hauptthread, bis stop() aufgerufen wird.
        """

        while not self._stop_event.wait(0.5):
            pass

    # ---------------------------------------------------------
    # Serielle Frames
    # ---------------------------------------------------------

    def _handle_serial_frame(
        self,
        source: str,
        frame: DecodedFrame,
        packet: bytes,
    ) -> None:
        """
        Wird von SerialBus für jeden vollständig erkannten Frame aufgerufen.
        """

        if source == "panel":
            self._handle_panel_frame(frame)
            return

        if source == "fans":
            self._handle_fan_frame(frame)
            return

        LOGGER.warning(
            "Frame mit unbekannter Quelle erhalten: %s %s",
            source,
            frame.raw,
        )

    def _handle_panel_frame(
        self,
        frame: DecodedFrame,
    ) -> None:
        if frame.category in {
            FrameCategory.CONTROL,
            FrameCategory.UNKNOWN_CONTROL,
        }:
            self._state.update_panel_frame(frame)

            override = self._state.override_state()

            # Nur wenn das Panel tatsächlich die Kontrolle hat,
            # ist sein Frame auch der aktive Zustand.
            if not override.enabled:
                self._state.mark_active_panel_frame(frame)

            if frame.raw != self._last_published_panel_frame:
                self._last_published_panel_frame = frame.raw
                self._mqtt.publish_panel_state()

                if not override.enabled:
                    self._mqtt.publish_active_state()

            LOGGER.debug(
                "Panel-Steuerframe: %s, Modus=%s, Stufe=%s, Phase=%s",
                frame.raw,
                frame.mode.value,
                frame.speed,
                frame.phase.value,
            )

        elif frame.category == FrameCategory.REQUEST:
            LOGGER.debug(
                "Panel-Abfrage: %s (%s)",
                frame.raw,
                frame.description,
            )
            self._mqtt.publish(
                "diagnostic/last_panel_request",
                frame.raw,
            )

        else:
            LOGGER.debug(
                "Sonstiger Panel-Frame: %s (%s)",
                frame.raw,
                frame.category.value,
            )

    def _handle_fan_frame(
        self,
        frame: DecodedFrame,
    ) -> None:
        self._state.update_fan_reply(frame)

        if frame.raw != self._last_published_fan_frame:
            self._last_published_fan_frame = frame.raw
            self._mqtt.publish_fan_reply_state()

        LOGGER.debug(
            "Lüfter-Frame: %s (%s)",
            frame.raw,
            frame.category.value,
        )

    def _should_forward_panel_frame(
        self,
        frame: DecodedFrame,
    ) -> bool:
        """
        Während eines Overrides werden nur gültige Steuerframes blockiert.

        Statusabfragen wie 020002 werden weiterhin an den Master geleitet,
        damit die Kommunikation zwischen Panel und Lüfterbus erhalten bleibt.
        """

        override = self._state.override_state()

        if not override.enabled:
            return True

        if frame.category in {
            FrameCategory.CONTROL,
            FrameCategory.UNKNOWN_CONTROL,
        }:
            LOGGER.debug(
                "Panel-Steuerframe wegen Override blockiert: %s",
                frame.raw,
            )
            return False

        return True

    # ---------------------------------------------------------
    # MQTT-Befehle
    # ---------------------------------------------------------

    def _handle_override_command(
        self,
        enabled: bool,
    ) -> None:
        current = self._state.override_state()

        if enabled and not self._selection_supported(
            current.mode,
            current.speed,
        ):
            message = (
                "Override nicht aktiviert: "
                f"{current.mode.value}, Stufe {current.speed} "
                "wird noch nicht unterstützt"
            )
            LOGGER.warning(message)
            self._mqtt.publish_error(message)
            return

        updated = self._state.configure_override(
            enabled=enabled,
        )

        LOGGER.info(
            "Override %s; Generation %s",
            "aktiviert" if updated.enabled else "deaktiviert",
            updated.generation,
        )

        self._mqtt.clear_error()
        self._mqtt.publish_override_state()

        self._override_changed_event.set()

    def _handle_mode_command(
        self,
        mode: Mode,
    ) -> None:
        current = self._state.override_state()

        if current.enabled and not self._selection_supported(
            mode,
            current.speed,
        ):
            message = (
                "Modusänderung abgelehnt: "
                f"{mode.value}, Stufe {current.speed} "
                "wird noch nicht unterstützt"
            )
            LOGGER.warning(message)
            self._mqtt.publish_error(message)
            return

        updated = self._state.configure_override(
            mode=mode,
        )

        LOGGER.info(
            "Override-Modus gewählt: %s; Generation %s",
            updated.mode.value,
            updated.generation,
        )

        self._mqtt.clear_error()
        self._mqtt.publish_override_state()

        self._override_changed_event.set()

    def _handle_speed_command(
        self,
        speed: int,
    ) -> None:
        current = self._state.override_state()

        if current.enabled and not self._selection_supported(
            current.mode,
            speed,
        ):
            message = (
                "Stufenänderung abgelehnt: "
                f"{current.mode.value}, Stufe {speed} "
                "wird noch nicht unterstützt"
            )
            LOGGER.warning(message)
            self._mqtt.publish_error(message)
            return

        updated = self._state.configure_override(
            speed=speed,
        )

        LOGGER.info(
            "Override-Stufe gewählt: %s; Generation %s",
            updated.speed,
            updated.generation,
        )

        self._mqtt.clear_error()
        self._mqtt.publish_override_state()

        self._override_changed_event.set()

    # ---------------------------------------------------------
    # Override-Sequenzen
    # ---------------------------------------------------------

    @staticmethod
    def _fixed_frame_or_none(
        mode: Mode,
        speed: int,
    ) -> str | None:
        try:
            return fixed_command_frame(mode, speed)
        except ValueError:
            return None

    @staticmethod
    def _alternating_sequence_or_none(
        mode: Mode,
        speed: int,
    ) -> tuple[SequenceStep, ...] | None:
        try:
            return alternating_sequence(mode, speed)
        except ValueError:
            return None

    def _selection_supported(
        self,
        mode: Mode,
        speed: int,
    ) -> bool:
        return (
            self._fixed_frame_or_none(mode, speed) is not None
            or self._alternating_sequence_or_none(mode, speed) is not None
        )

    def _override_loop(self) -> None:
        """
        Dauerhafter Worker für feste und alternierende Override-Zustände.

        Jede Änderung an Modus, Stufe oder Override erhöht die Generation
        im GatewayState. Laufende Sequenzen werden dadurch sofort beendet.
        """

        while not self._stop_event.is_set():
            override = self._state.override_state()

            if not override.enabled:
                self._override_changed_event.wait(timeout=0.5)
                self._override_changed_event.clear()
                continue

            generation = override.generation
            mode = override.mode
            speed = override.speed

            fixed_frame = self._fixed_frame_or_none(
                mode,
                speed,
            )

            if fixed_frame is not None:
                self._run_fixed_override(
                    generation=generation,
                    mode=mode,
                    speed=speed,
                    frame=fixed_frame,
                )
                continue

            sequence = self._alternating_sequence_or_none(
                mode,
                speed,
            )

            if sequence is not None:
                self._run_alternating_override(
                    generation=generation,
                    mode=mode,
                    speed=speed,
                    sequence=sequence,
                )
                continue

            # Sollte wegen der Validierung in den MQTT-Callbacks
            # normalerweise nicht auftreten.
            message = (
                "Nicht unterstützter Override-Zustand: "
                f"{mode.value}, Stufe {speed}"
            )
            LOGGER.error(message)
            self._mqtt.publish_error(message)

            self._state.configure_override(enabled=False)
            self._mqtt.publish_override_state()

    def _run_fixed_override(
        self,
        *,
        generation: int,
        mode: Mode,
        speed: int,
        frame: str,
    ) -> None:
        LOGGER.info(
            "Starte festen Override: %s, Stufe %s, Frame %s",
            mode.value,
            speed,
            frame,
        )

        first_send = True

        while (
            not self._stop_event.is_set()
            and self._state.override_generation_is_current(generation)
        ):
            self._send_override_frame(
                generation=generation,
                mode=mode,
                speed=speed,
                phase=Phase.FIXED,
                frame=frame,
                publish=first_send,
            )

            first_send = False

            if self._override_changed_event.wait(
                timeout=self._config.control_send_interval
            ):
                self._override_changed_event.clear()
                return

    def _run_alternating_override(
        self,
        *,
        generation: int,
        mode: Mode,
        speed: int,
        sequence: tuple[SequenceStep, ...],
    ) -> None:
        LOGGER.info(
            "Starte alternierenden Override: %s, Stufe %s",
            mode.value,
            speed,
        )

        step_index = 0

        while (
            not self._stop_event.is_set()
            and self._state.override_generation_is_current(generation)
        ):
            step = sequence[step_index]

            LOGGER.info(
                "Override-Phase: %s, Frame %s, Dauer %.1f s",
                step.phase.value,
                step.frame,
                step.duration,
            )

            step_end = time.monotonic() + step.duration
            first_send = True

            while (
                not self._stop_event.is_set()
                and self._state.override_generation_is_current(generation)
                and time.monotonic() < step_end
            ):
                self._send_override_frame(
                    generation=generation,
                    mode=mode,
                    speed=speed,
                    phase=step.phase,
                    frame=step.frame,
                    publish=first_send,
                )

                first_send = False

                remaining = max(
                    0.0,
                    step_end - time.monotonic(),
                )

                wait_time = min(
                    self._config.control_send_interval,
                    remaining,
                )

                if self._override_changed_event.wait(
                    timeout=wait_time
                ):
                    self._override_changed_event.clear()
                    return

            step_index = (step_index + 1) % len(sequence)

    def _send_override_frame(
        self,
        *,
        generation: int,
        mode: Mode,
        speed: int,
        phase: Phase,
        frame: str,
        publish: bool,
    ) -> None:
        if not self._state.override_generation_is_current(
            generation
        ):
            return

        packet = make_packet(frame)
        self._serial_bus.send_to_fans(packet)

        self._state.set_override_runtime(
            phase=phase,
            raw_frame=frame,
            generation=generation,
        )

        self._state.mark_active_override_frame(
            raw_frame=frame,
            mode=mode,
            speed=speed,
            phase=phase,
        )

        if publish:
            self._mqtt.publish_override_state()
            self._mqtt.publish_active_state()

    def __enter__(self) -> AmbientikaGateway:
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.stop()
