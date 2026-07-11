from __future__ import annotations

import logging
import signal
import sys

from .config import load_config
from .gateway import AmbientikaGateway


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name),
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s: "
            "%(message)s"
        ),
    )


def main() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        print(
            f"Konfigurationsfehler: {exc}",
            file=sys.stderr,
        )
        return 2

    configure_logging(config.log_level)

    logger = logging.getLogger(__name__)
    gateway = AmbientikaGateway(config)

    def request_stop(signum, frame) -> None:
        logger.info(
            "Beenden angefordert durch Signal %s",
            signum,
        )
        gateway.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        gateway.start()

        print()
        print("Ambientika Gateway läuft.")
        print(f"Panel:  {config.serial.panel_port}")
        print(f"Lüfter: {config.serial.fans_port}")
        print(
            f"MQTT:   {config.mqtt.host}:"
            f"{config.mqtt.port}/"
            f"{config.mqtt.base_topic}"
        )
        print("Abbruch mit Strg+C.")
        print()

        gateway.wait()

    except KeyboardInterrupt:
        gateway.stop()

    except Exception:
        logger.exception(
            "Unbehandelter Fehler im Ambientika Gateway"
        )
        gateway.stop()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
