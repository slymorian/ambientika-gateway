from __future__ import annotations

import threading
import unittest
from unittest import mock

from ambientika_gateway.config import (
    GatewayConfig,
    MqttConfig,
    SerialConfig,
)
from ambientika_gateway.gateway import AmbientikaGateway
from ambientika_gateway.serial_bus import SerialBus


def _build_gateway() -> AmbientikaGateway:
    """
    Baut ein AmbientikaGateway ohne jede echte I/O auf.

    AmbientikaMqttClient verbindet nicht im Konstruktor (das passiert
    erst in start()), und SerialBus.open()/start() werden hier bewusst
    nicht aufgerufen. Diese Tests prüfen ausschließlich wait(), unabhängig
    vom restlichen Lebenszyklus.
    """

    config = GatewayConfig(
        serial=SerialConfig(
            panel_port="/dev/null",
            fans_port="/dev/null",
            baudrate=9600,
            timeout=0.1,
            write_timeout=0.1,
            read_size=64,
        ),
        mqtt=MqttConfig(
            host="localhost",
            port=1883,
            username="",
            password="",
            keepalive=60,
            base_topic="ambientika-test",
            client_id="ambientika-gateway-test",
            retain_state=True,
        ),
        control_send_interval=0.1,
        panel_timeout=3.0,
        fan_reply_timeout=15.0,
        log_level="INFO",
    )

    return AmbientikaGateway(config)


class GatewayWaitSerialFailureTests(unittest.TestCase):
    def test_wait_returns_when_serial_bus_stops_running(self) -> None:
        # Bildet den beobachteten Fehlerfall nach: ein TCP-Verbindungs-
        # abbruch beim RS485-zu-Ethernet-Konverter lässt beide Lese-
        # Threads in SerialBus sich beenden (SerialBus.running wird
        # False), ohne dass stop() aufgerufen wurde. wait() muss das
        # erkennen und zurückkehren, damit der Prozess sich beenden und
        # systemd (Restart=always) ihn neu starten kann.
        gateway = _build_gateway()

        with mock.patch.object(
            SerialBus,
            "running",
            new_callable=mock.PropertyMock,
            return_value=False,
        ):
            thread = threading.Thread(
                target=gateway.wait,
                daemon=True,
            )
            thread.start()
            thread.join(timeout=2.0)

            self.assertFalse(thread.is_alive())

    def test_wait_keeps_blocking_while_serial_bus_is_running(self) -> None:
        # Gegenprobe: solange SerialBus.running True ist, darf wait()
        # nicht vorzeitig zurückkehren -- nur ein expliziter stop()
        # darf das.
        gateway = _build_gateway()

        with mock.patch.object(
            SerialBus,
            "running",
            new_callable=mock.PropertyMock,
            return_value=True,
        ):
            thread = threading.Thread(
                target=gateway.wait,
                daemon=True,
            )
            thread.start()
            thread.join(timeout=1.0)

            self.assertTrue(thread.is_alive())

            gateway.stop()
            thread.join(timeout=2.0)

            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
