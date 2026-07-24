from __future__ import annotations
from .protocol import mqtt_mode_values

import json
import re
from typing import Any

from .config import MqttConfig


DEFAULT_DISCOVERY_PREFIX = "homeassistant"

DEVICE_MANUFACTURER = "Südwind"
DEVICE_MODEL = "Ambientika RS485 Gateway"
PROJECT_NAME = "Ambientika Gateway"
PROJECT_URL = "https://github.com/slymorian/ambientika-gateway"


def _safe_id(value: str) -> str:
    """
    Erzeugt eine für MQTT-Discovery geeignete ID.

    Zulässig sind Buchstaben, Zahlen, Unterstriche und Bindestriche.
    """

    normalized = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        value.strip(),
    )

    normalized = normalized.strip("_").lower()

    return normalized or "ambientika_gateway"


def device_id(config: MqttConfig) -> str:
    return _safe_id(config.client_id)


def discovery_topic(
    config: MqttConfig,
    *,
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
) -> str:
    """
    MQTT Device Discovery Topic:

        homeassistant/device/<device_id>/config
    """

    prefix = discovery_prefix.strip("/")
    return f"{prefix}/device/{device_id(config)}/config"


def _unique_id(
    config: MqttConfig,
    component: str,
) -> str:
    return f"{device_id(config)}_{component}"


def _topic(
    config: MqttConfig,
    suffix: str,
) -> str:
    return (
        f"{config.base_topic.strip('/')}/"
        f"{suffix.strip('/')}"
    )


def build_discovery_payload(
    config: MqttConfig,
    *,
    software_version: str,
) -> dict[str, Any]:
    """
    Erstellt eine Home-Assistant-MQTT-Device-Discovery-Konfiguration.

    Alle Komponenten werden Home Assistant als ein gemeinsames Gerät
    präsentiert.
    """

    identifier = device_id(config)

    device = {
        "identifiers": [identifier],
        "name": "Ambientika Gateway",
        "manufacturer": DEVICE_MANUFACTURER,
        "model": DEVICE_MODEL,
        "sw_version": software_version,
        "serial_number": identifier,
        "configuration_url": PROJECT_URL,
    }


    origin = {
        "name": PROJECT_NAME,
        "sw_version": software_version,
        "support_url": PROJECT_URL,
    }




    components: dict[str, dict[str, Any]] = {
        # -------------------------------------------------
        # Bedienung
        # -------------------------------------------------

        "fan_control": {
            "p": "fan",
            "name": "Lüftungssteuerung",
            "unique_id": _unique_id(
                config,
                "fan_control",
            ),
            "command_topic": _topic(
                config,
                "override/set",
            ),
            "state_topic": _topic(
                config,
                "state/override",
            ),
            "payload_on": "ON",
            "payload_off": "OFF",

            "percentage_command_topic": _topic(
                config,
                "speed/set",
            ),
            "percentage_state_topic": _topic(
                config,
                "state/desired_speed",
            ),
            "speed_range_min": 1,
            "speed_range_max": 3,

            "preset_mode_command_topic": _topic(
                config,
                "mode/set",
            ),
            "preset_mode_state_topic": _topic(
                config,
                "state/desired_mode",
            ),
            "preset_modes": [
                "manual_alternating",
                "silent",
                "extract",
                "supply",
                "master_extract_slave_supply",
                "master_supply_slave_extract",
            ],
            "icon": "mdi:hvac",
        },



        "override": {
            "p": "switch",
            "name": "Override",
            "unique_id": _unique_id(
                config,
                "override",
            ),
            "command_topic": _topic(
                config,
                "override/set",
            ),
            "state_topic": _topic(
                config,
                "state/override",
            ),
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
            "icon": "mdi:account-switch",
        },

        "mode": {
            "p": "select",
            "name": "Modus",
            "unique_id": _unique_id(
                config,
                "mode",
            ),
            "command_topic": _topic(
                config,
                "mode/set",
            ),
            "state_topic": _topic(
                config,
                "state/desired_mode",
            ),
            "options": mqtt_mode_values(),


            "icon": "mdi:fan-auto",
        },

        "speed": {
            "p": "select",
            "name": "Lüfterstufe",
            "unique_id": _unique_id(
                config,
                "speed",
            ),
            "command_topic": _topic(
                config,
                "speed/set",
            ),
            "state_topic": _topic(
                config,
                "state/desired_speed",
            ),
            "options": [
                "1",
                "2",
                "3",
            ],
            "icon": "mdi:fan-chevron-up",
        },


        "humidity_level": {
            "p": "select", "name": "Feuchteschwelle",
            "unique_id": _unique_id(config, "humidity_level"),
            "command_topic": _topic(config, "humidity_level/set"),
            "state_topic": _topic(config, "state/desired_humidity_level"),
            "options": ["1", "2", "3"], "icon": "mdi:water-percent",
        },
        "operating_state": {
            "p": "sensor", "name": "Betriebszustand",
            "unique_id": _unique_id(config, "operating_state"),
            "state_topic": _topic(config, "state/operating_state"),
            "icon": "mdi:state-machine",
        },
        "humidity_alarm": {
            "p": "binary_sensor", "name": "Feuchtealarm",
            "unique_id": _unique_id(config, "humidity_alarm"),
            "state_topic": _topic(config, "state/humidity_alarm"),
            "payload_on": "ON", "payload_off": "OFF",
            "device_class": "moisture",
        },
        "pending_extract": {
            "p": "binary_sensor", "name": "Abluft-Umschaltung vorgemerkt",
            "unique_id": _unique_id(config, "pending_extract"),
            "state_topic": _topic(config, "state/pending_extract"),
            "payload_on": "ON", "payload_off": "OFF",
            "icon": "mdi:timer-sand",
        },
        # -------------------------------------------------
        # Aktiver Zustand
        # -------------------------------------------------

        "control_source": {
            "p": "sensor",
            "name": "Steuerquelle",
            "unique_id": _unique_id(
                config,
                "control_source",
            ),
            "state_topic": _topic(
                config,
                "state/control_source",
            ),
            "icon": "mdi:source-branch",
        },

        "active_mode": {
            "p": "sensor",
            "name": "Aktiver Modus",
            "unique_id": _unique_id(
                config,
                "active_mode",
            ),
            "state_topic": _topic(
                config,
                "state/active_mode",
            ),
            "icon": "mdi:fan-auto",
        },

        "active_speed": {
            "p": "sensor",
            "name": "Aktive Lüfterstufe",
            "unique_id": _unique_id(
                config,
                "active_speed",
            ),
            "state_topic": _topic(
                config,
                "state/active_speed",
            ),
            "icon": "mdi:fan-speed-2",
        },

        "active_phase": {
            "p": "sensor",
            "name": "Aktive Phase",
            "unique_id": _unique_id(
                config,
                "active_phase",
            ),
            "state_topic": _topic(
                config,
                "state/active_phase",
            ),
            "icon": "mdi:swap-horizontal",
        },

        # -------------------------------------------------
        # Zustand des Wandpanels
        # -------------------------------------------------

        "panel_mode": {
            "p": "sensor",
            "name": "Panel-Modus",
            "unique_id": _unique_id(
                config,
                "panel_mode",
            ),
            "state_topic": _topic(
                config,
                "state/panel_mode",
            ),
            "icon": "mdi:view-dashboard-outline",
        },

        "panel_speed": {
            "p": "sensor",
            "name": "Panel-Lüfterstufe",
            "unique_id": _unique_id(
                config,
                "panel_speed",
            ),
            "state_topic": _topic(
                config,
                "state/panel_speed",
            ),
            "icon": "mdi:fan-speed-1",
        },

        "panel_phase": {
            "p": "sensor",
            "name": "Panel-Phase",
            "unique_id": _unique_id(
                config,
                "panel_phase",
            ),
            "state_topic": _topic(
                config,
                "state/panel_phase",
            ),
            "icon": "mdi:swap-horizontal",
        },

        # -------------------------------------------------
        # Diagnose
        # -------------------------------------------------

        "panel_frame": {
            "p": "sensor",
            "name": "Letzter Panel-Frame",
            "unique_id": _unique_id(
                config,
                "panel_frame",
            ),
            "state_topic": _topic(
                config,
                "state/panel_frame",
            ),
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:code-braces",
        },

        "active_frame": {
            "p": "sensor",
            "name": "Aktiver Steuerframe",
            "unique_id": _unique_id(
                config,
                "active_frame",
            ),
            "state_topic": _topic(
                config,
                "state/active_frame",
            ),
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:code-tags",
        },

        "fan_reply": {
            "p": "sensor",
            "name": "Letzte Lüfterantwort",
            "unique_id": _unique_id(
                config,
                "fan_reply",
            ),
            "state_topic": _topic(
                config,
                "state/fan_reply",
            ),
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:message-reply-text-outline",
        },

        "fan_reply_category": {
            "p": "sensor",
            "name": "Kategorie der Lüfterantwort",
            "unique_id": _unique_id(
                config,
                "fan_reply_category",
            ),
            "state_topic": _topic(
                config,
                "state/fan_reply_category",
            ),
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:format-list-bulleted-type",
        },

        "override_frame": {
            "p": "sensor",
            "name": "Override-Frame",
            "unique_id": _unique_id(
                config,
                "override_frame",
            ),
            "state_topic": _topic(
                config,
                "state/override_frame",
            ),
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:code-json",
        },

        "panel_age": {
            "p": "sensor",
            "name": "Alter des Panel-Signals",
            "unique_id": _unique_id(
                config,
                "panel_age",
            ),
            "state_topic": _topic(
                config,
                "diagnostic/panel_age_seconds",
            ),
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:timer-outline",
        },

        "fan_reply_age": {
            "p": "sensor",
            "name": "Alter der Lüfterantwort",
            "unique_id": _unique_id(
                config,
                "fan_reply_age",
            ),
            "state_topic": _topic(
                config,
                "diagnostic/fan_reply_age_seconds",
            ),
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:timer-sync-outline",
        },
    }

    return {
        "device": device,
        "origin": origin,
        "availability_topic": _topic(
            config,
            "availability",
        ),
        "payload_available": "online",
        "payload_not_available": "offline",
        "components": components,
    }


def serialize_discovery_payload(
    config: MqttConfig,
    *,
    software_version: str,
) -> str:
    """
    Serialisiert die Discovery-Konfiguration kompakt als JSON.
    """

    return json.dumps(
        build_discovery_payload(
            config,
            software_version=software_version,
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
