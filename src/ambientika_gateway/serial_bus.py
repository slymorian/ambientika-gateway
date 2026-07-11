from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import serial

from .config import SerialConfig
from .protocol import ETX, STX, DecodedFrame, decode_frame


LOGGER = logging.getLogger(__name__)


FrameCallback = Callable[[str, DecodedFrame, bytes], None]


class FrameParser:
    """
    Extrahiert STX/ETX-gerahmte ASCII-Telegramme aus einem Byte-Strom.

    Rohdaten außerhalb eines Frames werden ignoriert. Der eigentliche
    transparente Durchleiter arbeitet davon unabhängig mit den Originalbytes.
    """

    def __init__(
        self,
        source: str,
        callback: FrameCallback,
        *,
        max_payload_length: int = 128,
    ) -> None:
        self._source = source
        self._callback = callback
        self._max_payload_length = max_payload_length

        self._buffer = bytearray()
        self._in_frame = False

    def reset(self) -> None:
        self._buffer = bytearray()
        self._in_frame = False

    def feed(self, data: bytes) -> None:
        for value in data:
            if value == STX:
                self._buffer = bytearray()
                self._in_frame = True
                continue

            if not self._in_frame:
                continue

            if value == ETX:
                payload_bytes = bytes(self._buffer)

                try:
                    payload = payload_bytes.decode("ascii").upper()
                except UnicodeDecodeError:
                    LOGGER.warning(
                        "Nicht-ASCII-Frame von %s: %s",
                        self._source,
                        payload_bytes.hex(" ").upper(),
                    )
                    self.reset()
                    continue

                decoded = decode_frame(self._source, payload)

                packet = (
                    bytes([STX])
                    + payload_bytes
                    + bytes([ETX])
                )

                self._callback(
                    self._source,
                    decoded,
                    packet,
                )

                self.reset()
                continue

            self._buffer.append(value)

            if len(self._buffer) > self._max_payload_length:
                LOGGER.warning(
                    "Zu langer Frame von %s; Parser wird zurückgesetzt",
                    self._source,
                )
                self.reset()


class SerialBus:
    """
    Bidirektionale RS485-Verbindung zwischen Wandpanel und Lüfterbus.

    Standardmäßig werden sämtliche Rohbytes transparent weitergereicht.
    Über den Panel-Filter kann das Gateway einzelne Panel-Frames blockieren,
    beispielsweise während eines Home-Assistant-Overrides.
    """

    def __init__(
        self,
        config: SerialConfig,
        *,
        on_frame: FrameCallback | None = None,
    ) -> None:
        self._config = config
        self._on_frame = on_frame or self._default_frame_callback

        self._panel: serial.Serial | None = None
        self._fans: serial.Serial | None = None

        self._stop_event = threading.Event()

        self._panel_write_lock = threading.Lock()
        self._fans_write_lock = threading.Lock()

        self._threads: list[threading.Thread] = []

        self._panel_control_filter: (
            Callable[[DecodedFrame], bool] | None
        ) = None

    @staticmethod
    def _default_frame_callback(
        source: str,
        frame: DecodedFrame,
        packet: bytes,
    ) -> None:
        LOGGER.debug(
            "Frame von %s: %s (%s)",
            source,
            frame.raw,
            frame.category.value,
        )

    @property
    def running(self) -> bool:
        return (
            self._panel is not None
            and self._fans is not None
            and not self._stop_event.is_set()
        )

    def set_panel_control_filter(
        self,
        callback: Callable[[DecodedFrame], bool] | None,
    ) -> None:
        """
        Legt einen Filter für vollständige Panel-Frames fest.

        Rückgabewert des Callbacks:
            True  -> Frame an den Lüfterbus weiterleiten
            False -> Frame blockieren

        Bei None werden alle Panel-Frames transparent weitergeleitet.
        """

        self._panel_control_filter = callback

    def open(self) -> None:
        if self._panel is not None or self._fans is not None:
            raise RuntimeError("SerialBus ist bereits geöffnet")

        LOGGER.info(
            "Öffne Panel-Port %s und Lüfter-Port %s",
            self._config.panel_port,
            self._config.fans_port,
        )

        try:
            panel = serial.Serial(
                port=self._config.panel_port,
                baudrate=self._config.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._config.timeout,
                write_timeout=self._config.write_timeout,
            )

            fans = serial.Serial(
                port=self._config.fans_port,
                baudrate=self._config.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._config.timeout,
                write_timeout=self._config.write_timeout,
            )

        except Exception:
            if "panel" in locals():
                panel.close()

            raise

        panel.reset_input_buffer()
        panel.reset_output_buffer()
        fans.reset_input_buffer()
        fans.reset_output_buffer()

        self._panel = panel
        self._fans = fans
        self._stop_event.clear()

    def start(self) -> None:
        if self._panel is None or self._fans is None:
            raise RuntimeError(
                "SerialBus muss vor start() mit open() geöffnet werden"
            )

        if self._threads:
            raise RuntimeError("SerialBus läuft bereits")

        panel_thread = threading.Thread(
            target=self._panel_to_fans_loop,
            name="ambientika-panel-to-fans",
            daemon=True,
        )

        fans_thread = threading.Thread(
            target=self._fans_to_panel_loop,
            name="ambientika-fans-to-panel",
            daemon=True,
        )

        self._threads = [
            panel_thread,
            fans_thread,
        ]

        for thread in self._threads:
            thread.start()

        LOGGER.info("Serielle Gateway-Threads gestartet")

    def stop(self) -> None:
        self._stop_event.set()

        for thread in self._threads:
            thread.join(timeout=2.0)

        self._threads = []

        if self._panel is not None:
            self._panel.close()
            self._panel = None

        if self._fans is not None:
            self._fans.close()
            self._fans = None

        LOGGER.info("Serielle Schnittstellen geschlossen")

    def send_to_fans(self, packet: bytes) -> None:
        fans = self._fans

        if fans is None:
            raise RuntimeError("Lüfter-Port ist nicht geöffnet")

        with self._fans_write_lock:
            fans.write(packet)
            fans.flush()

    def send_to_panel(self, packet: bytes) -> None:
        panel = self._panel

        if panel is None:
            raise RuntimeError("Panel-Port ist nicht geöffnet")

        with self._panel_write_lock:
            panel.write(packet)
            panel.flush()

    def _handle_panel_packet(
        self,
        frame: DecodedFrame,
        packet: bytes,
    ) -> None:
        self._on_frame(
            "panel",
            frame,
            packet,
        )

        should_forward = True

        if self._panel_control_filter is not None:
            should_forward = self._panel_control_filter(frame)

        if should_forward:
            self.send_to_fans(packet)
        else:
            LOGGER.debug(
                "Panel-Frame blockiert: %s",
                frame.raw,
            )

    def _handle_fans_packet(
        self,
        frame: DecodedFrame,
        packet: bytes,
    ) -> None:
        self._on_frame(
            "fans",
            frame,
            packet,
        )

        self.send_to_panel(packet)

    def _panel_to_fans_loop(self) -> None:
        panel = self._panel

        if panel is None:
            return

        parser = FrameParser(
            "panel",
            lambda source, frame, packet: (
                self._handle_panel_packet(frame, packet)
            ),
        )

        try:
            while not self._stop_event.is_set():
                data = panel.read(self._config.read_size)

                if not data:
                    continue

                parser.feed(data)

        except serial.SerialException:
            LOGGER.exception(
                "Serieller Fehler auf dem Panel-Port"
            )
            self._stop_event.set()

        except Exception:
            LOGGER.exception(
                "Unerwarteter Fehler im Panel-Empfangsthread"
            )
            self._stop_event.set()

    def _fans_to_panel_loop(self) -> None:
        fans = self._fans

        if fans is None:
            return

        parser = FrameParser(
            "fans",
            lambda source, frame, packet: (
                self._handle_fans_packet(frame, packet)
            ),
        )

        try:
            while not self._stop_event.is_set():
                data = fans.read(self._config.read_size)

                if not data:
                    continue

                parser.feed(data)

        except serial.SerialException:
            LOGGER.exception(
                "Serieller Fehler auf dem Lüfter-Port"
            )
            self._stop_event.set()

        except Exception:
            LOGGER.exception(
                "Unerwarteter Fehler im Lüfter-Empfangsthread"
            )
            self._stop_event.set()

    def __enter__(self) -> SerialBus:
        self.open()
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.stop()
