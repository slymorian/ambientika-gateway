from __future__ import annotations

import logging
import threading
import time

from .config import GatewayConfig
from .frame_generator import ControlPlan, FrameGenerator
from .mqtt_client import AmbientikaMqttClient
from .protocol import (
    DecodedFrame,
    FrameCategory,
    Mode,
    OperatingState,
    Phase,
    SequenceStep,
    decode_frame,
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
        self._frame_generator = FrameGenerator()

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
            on_humidity=self._handle_humidity_command,
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
        Blockiert den Hauptthread, bis stop() aufgerufen wird, oder die
        serielle Anbindung ausgefallen ist.

        Bei einem Lesefehler (z. B. ein TCP-Verbindungsabbruch beim
        RS485-zu-Ethernet-Konverter) beenden sich beide Lese-Threads in
        SerialBus von selbst (siehe SerialBus._panel_to_fans_loop /
        _fans_to_panel_loop); SerialBus.running wird dann False, obwohl
        der Python-Prozess selbst weiterläuft. Ohne diese Prüfung würde
        der Dienst für systemd dauerhaft als "aktiv" gelten, aber keine
        Frames mehr durchreichen, und Restart=always würde nie greifen.
        Deshalb kehrt wait() hier zurück; __main__.py ruft danach stop()
        auf und beendet den Prozess, systemd startet ihn über
        Restart=always neu.
        """

        while not self._stop_event.wait(0.5):
            if not self._serial_bus.running:
                LOGGER.error(
                    "Serielle Anbindung ausgefallen (Panel- oder "
                    "Lüfter-Lesethread beendet); Gateway wird "
                    "beendet, damit systemd es per Restart=always "
                    "neu startet"
                )
                return

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
            if frame.humidity_alarm is not None:
                self._mqtt.publish_active_state()

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
        desired = self._state.desired_state()

        if enabled and not self._selection_supported(
            desired.desired_mode,
            desired.desired_speed,
            desired.desired_humidity,
        ):
            message = (
                "Override nicht aktiviert: "
                f"{desired.desired_mode.value}, "
                f"Stufe {desired.desired_speed}, "
                f"Feuchteschwelle {desired.desired_humidity} "
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
        desired = self._state.desired_state()

        if current.enabled and not self._selection_supported(
            mode,
            desired.desired_speed,
            desired.desired_humidity,
        ):
            message = (
                "Modusänderung abgelehnt: "
                f"{mode.value}, Stufe {desired.desired_speed}, "
                f"Feuchteschwelle {desired.desired_humidity} "
                "wird noch nicht unterstützt"
            )
            LOGGER.warning(message)
            self._mqtt.publish_error(message)
            return

        updated = self._state.configure_desired(
            mode=mode,
        )

        LOGGER.info(
            "Override-Modus gewählt: %s; Generation %s",
            updated.desired_mode.value,
            updated.generation,
        )

        self._mqtt.clear_error()
        self._mqtt.publish_desired_state()

        self._override_changed_event.set()

    def _handle_speed_command(
        self,
        speed: int,
    ) -> None:
        current = self._state.override_state()
        desired = self._state.desired_state()

        if current.enabled and not self._selection_supported(
            desired.desired_mode,
            speed,
            desired.desired_humidity,
        ):
            message = (
                "Stufenänderung abgelehnt: "
                f"{desired.desired_mode.value}, Stufe {speed}, "
                f"Feuchteschwelle {desired.desired_humidity} "
                "wird noch nicht unterstützt"
            )
            LOGGER.warning(message)
            self._mqtt.publish_error(message)
            return

        updated = self._state.configure_desired(
            speed=speed,
        )

        LOGGER.info(
            "Override-Stufe gewählt: %s; Generation %s",
            updated.desired_speed,
            updated.generation,
        )

        self._mqtt.clear_error()
        self._mqtt.publish_desired_state()

        self._override_changed_event.set()

    def _handle_humidity_command(
        self,
        humidity: int,
    ) -> None:
        current = self._state.override_state()
        desired = self._state.desired_state()

        if current.enabled and not self._selection_supported(
            desired.desired_mode,
            desired.desired_speed,
            humidity,
        ):
            message = (
                "Feuchteschwelle abgelehnt: "
                f"{desired.desired_mode.value}, "
                f"Stufe {desired.desired_speed}, "
                f"Feuchteschwelle {humidity} wird noch nicht unterstützt"
            )
            LOGGER.warning(message)
            self._mqtt.publish_error(message)
            return

        updated = self._state.configure_desired(
            humidity=humidity,
        )
        LOGGER.info(
            "Override-Feuchteschwelle gewählt: %s; Generation %s",
            updated.desired_humidity,
            updated.generation,
        )
        self._mqtt.clear_error()
        self._mqtt.publish_desired_state()
        self._override_changed_event.set()

    # ---------------------------------------------------------
    # Override-Sequenzen
    # ---------------------------------------------------------

    def _selection_supported(
        self,
        mode: Mode,
        speed: int,
        humidity: int,
    ) -> bool:
        return self._frame_generator.supports(
            mode=mode,
            speed=speed,
            humidity=humidity,
        )

    def _override_loop(self) -> None:
        """
        Dauerhafter Worker für feste und alternierende Override-Zustände.

        Jede Änderung an Modus, Stufe oder Override erhöht die Generation
        im GatewayState. Laufende Sequenzen werden dadurch sofort beendet.
        """

        while not self._stop_event.is_set():
            override = self._state.override_state()
            desired = self._state.desired_state()

            if not override.enabled:
                self._override_changed_event.wait(timeout=0.5)
                self._override_changed_event.clear()
                continue

            generation = override.generation
            try:
                plan = self._frame_generator.plan(
                    mode=desired.desired_mode,
                    speed=desired.desired_speed,
                    humidity=desired.desired_humidity,
                )
            except ValueError as exc:
                message = str(exc)
                LOGGER.error(message)
                self._mqtt.publish_error(message)
                self._state.configure_override(enabled=False)
                self._mqtt.publish_override_state()
                continue

            if plan.fixed_frame is not None:
                self._run_fixed_override(
                    generation=generation,
                    plan=plan,
                )
                continue

            if plan.sequence:
                self._run_alternating_override(
                    generation=generation,
                    plan=plan,
                )
                continue

            # Sollte wegen der Validierung in den MQTT-Callbacks
            # normalerweise nicht auftreten.
            message = (
                "Nicht unterstützter Override-Zustand: "
                f"{desired.desired_mode.value}, "
                f"Stufe {desired.desired_speed}, "
                f"Feuchteschwelle {desired.desired_humidity}"
            )
            LOGGER.error(message)
            self._mqtt.publish_error(message)

            self._state.configure_override(enabled=False)
            self._mqtt.publish_override_state()

    def _run_fixed_override(
        self,
        *,
        generation: int,
        plan: ControlPlan,
    ) -> None:
        frame = plan.fixed_frame
        assert frame is not None
        LOGGER.info(
            "Starte festen Override: %s, Stufe %s, Frame %s",
            plan.selection.mode.value,
            plan.selection.speed,
            frame,
        )

        first_send = True

        while (
            not self._stop_event.is_set()
            and self._state.override_generation_is_current(generation)
        ):
            self._send_override_frame(
                generation=generation,
                mode=plan.selection.mode,
                speed=plan.selection.speed,
                humidity=plan.selection.humidity,
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
        plan: ControlPlan,
    ) -> None:
        sequence = plan.sequence
        LOGGER.info(
            "Starte alternierenden Override: %s, Stufe %s",
            plan.selection.mode.value,
            plan.selection.speed,
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
                    mode=plan.selection.mode,
                    speed=plan.selection.speed,
                    humidity=plan.selection.humidity,
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
        humidity: int,
        phase: Phase,
        frame: str,
        publish: bool,
    ) -> None:
        if not self._state.override_generation_is_current(
            generation
        ):
            return

        packet = self._frame_generator.packet(frame)
        self._serial_bus.send_to_fans(packet)
        decoded = decode_frame("panel", frame)

        self._state.set_override_runtime(
            phase=phase,
            raw_frame=frame,
            generation=generation,
        )

        self._state.mark_active_override_frame(
            raw_frame=frame,
            mode=mode,
            speed=speed,
            humidity=humidity,
            operating_state=decoded.operating_state,
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
