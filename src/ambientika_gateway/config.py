from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)

    if value is None:
        raise ValueError(
            f"Required environment variable is missing: {name}"
        )

    return value.strip()


def _get_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = _get_env(name, str(default))

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an integer, got: {raw!r}"
        ) from exc

    if minimum is not None and value < minimum:
        raise ValueError(
            f"{name} must be at least {minimum}, got: {value}"
        )

    if maximum is not None and value > maximum:
        raise ValueError(
            f"{name} must be at most {maximum}, got: {value}"
        )

    return value


def _get_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = _get_env(name, str(default))

    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a number, got: {raw!r}"
        ) from exc

    if minimum is not None and value < minimum:
        raise ValueError(
            f"{name} must be at least {minimum}, got: {value}"
        )

    if maximum is not None and value > maximum:
        raise ValueError(
            f"{name} must be at most {maximum}, got: {value}"
        )

    return value


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_env(
        name,
        "true" if default else "false",
    ).lower()

    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}

    if raw in truthy:
        return True

    if raw in falsy:
        return False

    raise ValueError(
        f"{name} must be one of "
        f"{sorted(truthy | falsy)}, got: {raw!r}"
    )


@dataclass(frozen=True)
class SerialConfig:
    panel_port: str
    fans_port: str
    baudrate: int
    timeout: float
    write_timeout: float
    read_size: int


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    username: str
    password: str
    keepalive: int
    base_topic: str
    client_id: str
    retain_state: bool


@dataclass(frozen=True)
class GatewayConfig:
    serial: SerialConfig
    mqtt: MqttConfig
    control_send_interval: float
    panel_timeout: float
    fan_reply_timeout: float
    log_level: str


def load_config() -> GatewayConfig:
    panel_port = _get_env(
        "AMBIENTIKA_PANEL_PORT",
        "/dev/ambientika-panel",
    )

    fans_port = _get_env(
        "AMBIENTIKA_FANS_PORT",
        "/dev/ambientika-fans",
    )

    baudrate = _get_int(
        "AMBIENTIKA_BAUDRATE",
        9600,
        minimum=300,
        maximum=1_000_000,
    )

    serial_timeout = _get_float(
        "AMBIENTIKA_SERIAL_TIMEOUT",
        0.02,
        minimum=0.001,
        maximum=10.0,
    )

    serial_write_timeout = _get_float(
        "AMBIENTIKA_SERIAL_WRITE_TIMEOUT",
        1.0,
        minimum=0.01,
        maximum=30.0,
    )

    serial_read_size = _get_int(
        "AMBIENTIKA_SERIAL_READ_SIZE",
        256,
        minimum=1,
        maximum=4096,
    )

    mqtt_host = _get_env(
        "AMBIENTIKA_MQTT_HOST",
        "192.0.2.204",
    )

    mqtt_port = _get_int(
        "AMBIENTIKA_MQTT_PORT",
        1883,
        minimum=1,
        maximum=65535,
    )

    mqtt_username = _get_env(
        "AMBIENTIKA_MQTT_USER",
        "",
    )

    mqtt_password = _get_env(
        "AMBIENTIKA_MQTT_PASSWORD",
        "",
    )

    mqtt_keepalive = _get_int(
        "AMBIENTIKA_MQTT_KEEPALIVE",
        60,
        minimum=5,
        maximum=3600,
    )

    mqtt_base_topic = _get_env(
        "AMBIENTIKA_MQTT_BASE_TOPIC",
        "ambientika",
    ).strip("/")

    if not mqtt_base_topic:
        raise ValueError(
            "AMBIENTIKA_MQTT_BASE_TOPIC must not be empty"
        )

    mqtt_client_id = _get_env(
        "AMBIENTIKA_MQTT_CLIENT_ID",
        "ambientika-gateway",
    )

    mqtt_retain_state = _get_bool(
        "AMBIENTIKA_MQTT_RETAIN_STATE",
        True,
    )

    control_send_interval = _get_float(
        "AMBIENTIKA_CONTROL_SEND_INTERVAL",
        0.5,
        minimum=0.05,
        maximum=5.0,
    )

    panel_timeout = _get_float(
        "AMBIENTIKA_PANEL_TIMEOUT",
        3.0,
        minimum=0.5,
        maximum=60.0,
    )

    fan_reply_timeout = _get_float(
        "AMBIENTIKA_FAN_REPLY_TIMEOUT",
        15.0,
        minimum=1.0,
        maximum=300.0,
    )

    log_level = _get_env(
        "AMBIENTIKA_LOG_LEVEL",
        "INFO",
    ).upper()

    allowed_log_levels = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if log_level not in allowed_log_levels:
        raise ValueError(
            "AMBIENTIKA_LOG_LEVEL must be one of "
            f"{sorted(allowed_log_levels)}, got: {log_level!r}"
        )

    return GatewayConfig(
        serial=SerialConfig(
            panel_port=panel_port,
            fans_port=fans_port,
            baudrate=baudrate,
            timeout=serial_timeout,
            write_timeout=serial_write_timeout,
            read_size=serial_read_size,
        ),
        mqtt=MqttConfig(
            host=mqtt_host,
            port=mqtt_port,
            username=mqtt_username,
            password=mqtt_password,
            keepalive=mqtt_keepalive,
            base_topic=mqtt_base_topic,
            client_id=mqtt_client_id,
            retain_state=mqtt_retain_state,
        ),
        control_send_interval=control_send_interval,
        panel_timeout=panel_timeout,
        fan_reply_timeout=fan_reply_timeout,
        log_level=log_level,
    )
