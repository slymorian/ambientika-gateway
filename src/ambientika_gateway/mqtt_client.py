from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from .config import MqttConfig
from .protocol import Mode
from .state import GatewaySnapshot, GatewayState


LOGGER = logging.getLogger(__name__)


OverrideCallback = Callable[[bool], None]
ModeCallback = Callable[[Mode], None]
SpeedCallback = Callable[[int], None]


MQTT_MODE_NAMES: dict[str, Mode] = {
    "manual": Mode.MANUAL_ALTERNATING,
    "manual_alternating": Mode.MANUAL_ALTERNATING,
    "extract": Mode.EXTRACT,
    "supply": Mode.SUPPLY,
    "master_extract_slave_supply": Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
    "master_supply_slave_extract": Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
    "silent": Mode.SILENT,
}


class AmbientikaMqttClient:
    """
    MQTT-Anbindung des Ambientika-Gateways.

    Das Modul verwaltet ausschließlich MQTT-Kommunikation. Änderungen
    an der seriellen Verbindung oder der Override-Sequenz werden über
    Callbacks an die Gateway-Schicht weitergegeben.
    """

    def __init__(
        self,
        config: MqttConfig,
        state: GatewayState,
        *,
        on_override: OverrideCallback | None = None,
        on_mode: ModeCallback | None = None,
        on_speed: SpeedCallback | None = None,
    ) -> None:
        self._config = config
        self._state = state

        self._on_override = on_override
        self._on_mode = on_mode
        self._on_speed = on_speed

        self._connected_event = threading.Event()
        self._stopped = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._config.client_id,
            protocol=mqtt.MQTTv311,
        )

        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._client.on_message = self._handle_message

        if self._config.username:
            self._client.username_pw_set(
                self._config.username,
                self._config.password,
            )

        self._client.will_set(
            self.topic("availability"),
            "offline",
            qos=1,
            retain=True,
        )

    @property
    def connected(self) -> bool:
        return self._connected_event.is_set()

    def topic(self, suffix: str) -> str:
        suffix = suffix.strip("/")
        return f"{self._config.base_topic}/{suffix}"

    def start(self) -> None:
        """
        Baut die MQTT-Verbindung auf und startet den Netzwerk-Thread.
        """

        if self._stopped:
            raise RuntimeError(
                "Ein bereits gestoppter MQTT-Client kann nicht neu gestartet werden"
            )

        LOGGER.info(
            "Verbinde MQTT mit %s:%s als %s",
            self._config.host,
            self._config.port,
            self._config.client_id,
        )

        self._client.connect(
            self._config.host,
            self._config.port,
            self._config.keepalive,
        )

        self._client.loop_start()

    def stop(self) -> None:
        """
        Veröffentlicht den Offline-Status und beendet die MQTT-Verbindung.
        """

        if self._stopped:
            return

        self._stopped = True

        try:
            if self.connected:
                self.publish(
                    "availability",
                    "offline",
                    retain=True,
                    qos=1,
                )
                self._client.disconnect()
        finally:
            self._client.loop_stop()
            self._connected_event.clear()

        LOGGER.info("MQTT-Client beendet")

    def wait_until_connected(
        self,
        timeout: float = 10.0,
    ) -> bool:
        return self._connected_event.wait(timeout)

    def publish(
        self,
        suffix: str,
        payload: Any,
        *,
        retain: bool | None = None,
        qos: int = 0,
    ) -> mqtt.MQTTMessageInfo:
        """
        Veröffentlicht einen Wert unterhalb des konfigurierten Base-Topics.
        """

        if retain is None:
            retain = self._config.retain_state

        if payload is None:
            text = ""
        elif isinstance(payload, bool):
            text = "ON" if payload else "OFF"
        else:
            text = str(payload)

        return self._client.publish(
            self.topic(suffix),
            text,
            qos=qos,
            retain=retain,
        )

    def publish_snapshot(
        self,
        snapshot: GatewaySnapshot | None = None,
    ) -> None:
        """
        Veröffentlicht den vollständigen aktuellen Gateway-Zustand.
        """

        if snapshot is None:
            snapshot = self._state.snapshot()

        panel = snapshot.panel
        override = snapshot.override
        active = snapshot.active
        fan_reply = snapshot.fan_reply

        self.publish("availability", "online", qos=1)

        self.publish("state/control_source", active.source)

        self.publish(
            "state/override",
            override.enabled,
        )
        self.publish(
            "state/selected_mode",
            override.mode.value,
        )
        self.publish(
            "state/selected_speed",
            override.speed,
        )
        self.publish(
            "state/override_phase",
            override.phase.value,
        )
        self.publish(
            "state/override_frame",
            override.raw_frame or "",
        )
        self.publish(
            "state/override_generation",
            override.generation,
        )

        self.publish(
            "state/panel_frame",
            panel.raw_frame or "",
        )
        self.publish(
            "state/panel_mode",
            panel.mode.value,
        )
        self.publish(
            "state/panel_speed",
            panel.speed if panel.speed is not None else "",
        )
        self.publish(
            "state/panel_phase",
            panel.phase.value,
        )

        self.publish(
            "state/active_frame",
            active.raw_frame or "",
        )
        self.publish(
            "state/active_mode",
            active.mode.value,
        )
        self.publish(
            "state/active_speed",
            active.speed if active.speed is not None else "",
        )
        self.publish(
            "state/active_phase",
            active.phase.value,
        )

        self.publish(
            "state/fan_reply",
            fan_reply.raw_frame or "",
        )
        self.publish(
            "state/fan_reply_category",
            fan_reply.category.value,
        )
        self.publish(
            "state/fan_reply_description",
            fan_reply.description,
        )

        panel_age = self._state.panel_age_seconds()
        fan_reply_age = self._state.fan_reply_age_seconds()

        self.publish(
            "diagnostic/panel_age_seconds",
            (
                f"{panel_age:.1f}"
                if panel_age is not None
                else ""
            ),
        )
        self.publish(
            "diagnostic/fan_reply_age_seconds",
            (
                f"{fan_reply_age:.1f}"
                if fan_reply_age is not None
                else ""
            ),
        )

    def publish_panel_state(self) -> None:
        snapshot = self._state.snapshot()
        panel = snapshot.panel

        self.publish(
            "state/panel_frame",
            panel.raw_frame or "",
        )
        self.publish(
            "state/panel_mode",
            panel.mode.value,
        )
        self.publish(
            "state/panel_speed",
            panel.speed if panel.speed is not None else "",
        )
        self.publish(
            "state/panel_phase",
            panel.phase.value,
        )

    def publish_override_state(self) -> None:
        snapshot = self._state.snapshot()
        override = snapshot.override

        self.publish(
            "state/override",
            override.enabled,
        )
        self.publish(
            "state/selected_mode",
            override.mode.value,
        )
        self.publish(
            "state/selected_speed",
            override.speed,
        )
        self.publish(
            "state/override_phase",
            override.phase.value,
        )
        self.publish(
            "state/override_frame",
            override.raw_frame or "",
        )

    def publish_active_state(self) -> None:
        snapshot = self._state.snapshot()
        active = snapshot.active

        self.publish(
            "state/control_source",
            active.source,
        )
        self.publish(
            "state/active_frame",
            active.raw_frame or "",
        )
        self.publish(
            "state/active_mode",
            active.mode.value,
        )
        self.publish(
            "state/active_speed",
            active.speed if active.speed is not None else "",
        )
        self.publish(
            "state/active_phase",
            active.phase.value,
        )

    def publish_fan_reply_state(self) -> None:
        snapshot = self._state.snapshot()
        reply = snapshot.fan_reply

        self.publish(
            "state/fan_reply",
            reply.raw_frame or "",
        )
        self.publish(
            "state/fan_reply_category",
            reply.category.value,
        )
        self.publish(
            "state/fan_reply_description",
            reply.description,
        )

    def publish_error(self, message: str) -> None:
        LOGGER.error("%s", message)
        self.publish(
            "diagnostic/error",
            message,
            retain=False,
        )

    def clear_error(self) -> None:
        self.publish(
            "diagnostic/error",
            "",
            retain=False,
        )

    def _handle_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            LOGGER.error(
                "MQTT-Verbindung abgelehnt: %s",
                reason_code,
            )
            self._connected_event.clear()
            return

        LOGGER.info("MQTT verbunden: %s", reason_code)
        self._connected_event.set()

        client.subscribe(
            [
                (
                    self.topic("override/set"),
                    0,
                ),
                (
                    self.topic("mode/set"),
                    0,
                ),
                (
                    self.topic("speed/set"),
                    0,
                ),
            ]
        )

        self.publish_snapshot()

    def _handle_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        self._connected_event.clear()

        if self._stopped:
            LOGGER.info("MQTT regulär getrennt")
        else:
            LOGGER.warning(
                "MQTT-Verbindung unterbrochen: %s",
                reason_code,
            )

    def _handle_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = message.payload.decode(
                "utf-8",
                errors="strict",
            ).strip()
        except UnicodeDecodeError:
            self.publish_error(
                f"Ungültige UTF-8-Nutzlast auf {message.topic}"
            )
            return

        LOGGER.debug(
            "MQTT empfangen: %s = %r",
            message.topic,
            payload,
        )

        if message.topic == self.topic("override/set"):
            self._process_override_command(payload)
            return

        if message.topic == self.topic("mode/set"):
            self._process_mode_command(payload)
            return

        if message.topic == self.topic("speed/set"):
            self._process_speed_command(payload)
            return

        LOGGER.warning(
            "Unbekanntes MQTT-Topic empfangen: %s",
            message.topic,
        )

    def _process_override_command(
        self,
        payload: str,
    ) -> None:
        normalized = payload.strip().lower()

        truthy = {"on", "1", "true", "yes"}
        falsy = {"off", "0", "false", "no"}

        if normalized in truthy:
            enabled = True
        elif normalized in falsy:
            enabled = False
        else:
            self.publish_error(
                f"Ungültiger Override-Wert: {payload!r}"
            )
            return

        if self._on_override is not None:
            self._on_override(enabled)
        else:
            self._state.configure_override(
                enabled=enabled,
            )

        self.clear_error()
        self.publish_override_state()

    def _process_mode_command(
        self,
        payload: str,
    ) -> None:
        normalized = payload.strip().lower()

        try:
            mode = MQTT_MODE_NAMES[normalized]
        except KeyError:
            supported = ", ".join(
                sorted(MQTT_MODE_NAMES)
            )
            self.publish_error(
                f"Unbekannter Modus {payload!r}; "
                f"erlaubt: {supported}"
            )
            return

        if self._on_mode is not None:
            self._on_mode(mode)
        else:
            self._state.configure_override(
                mode=mode,
            )

        self.clear_error()
        self.publish_override_state()

    def _process_speed_command(
        self,
        payload: str,
    ) -> None:
        try:
            speed = int(payload)
        except ValueError:
            self.publish_error(
                f"Ungültige Lüfterstufe: {payload!r}"
            )
            return

        if speed not in (1, 2, 3):
            self.publish_error(
                f"Lüfterstufe muss 1, 2 oder 3 sein, erhalten: {speed}"
            )
            return

        if self._on_speed is not None:
            self._on_speed(speed)
        else:
            self._state.configure_override(
                speed=speed,
            )

        self.clear_error()
        self.publish_override_state()

    def __enter__(self) -> AmbientikaMqttClient:
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.stop()
