#!/usr/bin/env python3

import os
import signal
import sys
import threading
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt
import serial


# ---------------------------------------------------------
# Serielle Schnittstellen
# ---------------------------------------------------------

PANEL_PORT = "/dev/ambientika-panel"
FANS_PORT = "/dev/ambientika-fans"

BAUDRATE = 9600
SERIAL_TIMEOUT = 0.02

# Das Panel sendet seinen Steuerzustand ungefähr zweimal pro Sekunde.
CONTROL_SEND_INTERVAL = 0.5


# ---------------------------------------------------------
# MQTT
# ---------------------------------------------------------

MQTT_HOST = "192.0.2.204"
MQTT_PORT = 1883
MQTT_USER = os.environ.get("AMBIENTIKA_MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("AMBIENTIKA_MQTT_PASSWORD", "")

BASE_TOPIC = "ambientika"


# ---------------------------------------------------------
# Bekannte Frames
# ---------------------------------------------------------

FIXED_FRAMES = {
    ("extract", 1): "01750074",
    ("extract", 2): "01760077",
    ("extract", 3): "01770076",

    ("supply", 1): "01790078",
    ("supply", 2): "017A007B",
    ("supply", 3): "017B007A",

    ("master_extract_slave_supply", 1): "01690068",
    ("master_extract_slave_supply", 2): "016A006B",
    ("master_extract_slave_supply", 3): "016B006A",

    ("master_supply_slave_extract", 1): "01650064",
    ("master_supply_slave_extract", 2): "01660067",
    ("master_supply_slave_extract", 3): "01670066",
}


@dataclass(frozen=True)
class SequenceStep:
    frame: str
    duration: float
    phase: str


# Durch Deine Messung bestätigt:
# 60 s Richtung A, 10 s Übergang, 60 s Richtung B, 10 s Übergang.
ALTERNATING_SEQUENCES = {
    ("manual", 1): (
        SequenceStep("01A500A4", 60.0, "phase_a"),
        SequenceStep("01A100A0", 10.0, "transition"),
        SequenceStep("01A900A8", 60.0, "phase_b"),
        SequenceStep("01A100A0", 10.0, "transition"),
    ),

    ("manual", 2): (
        SequenceStep("01AA00AB", 60.0, "phase_a"),
        SequenceStep("01A200A3", 10.0, "transition"),
        SequenceStep("01A600A7", 60.0, "phase_b"),
        SequenceStep("01A200A3", 10.0, "transition"),
    ),
}


# ---------------------------------------------------------
# Gemeinsamer Zustand
# ---------------------------------------------------------

stop_event = threading.Event()
fans_write_lock = threading.Lock()
panel_write_lock = threading.Lock()
state_lock = threading.Lock()

override_enabled = False
selected_mode = "extract"
selected_speed = 3

sequence_generation = 0


# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def mqtt_topic(suffix: str) -> str:
    return f"{BASE_TOPIC}/{suffix}"


def publish(
    client: mqtt.Client,
    suffix: str,
    payload,
    retain: bool = True,
) -> None:
    client.publish(
        mqtt_topic(suffix),
        str(payload),
        retain=retain,
    )


def valid_xor_frame(payload: str) -> bool:
    try:
        data = bytes.fromhex(payload)
    except ValueError:
        return False

    return (
        len(data) == 4
        and (data[0] ^ data[1] ^ data[2]) == data[3]
    )


def make_packet(payload: str) -> bytes:
    payload = payload.upper().replace(" ", "")

    if not valid_xor_frame(payload):
        raise ValueError(f"Ungültiger Steuerframe: {payload}")

    return b"\x02" + payload.encode("ascii") + b"\x03"


def is_panel_control_frame(payload: str) -> bool:
    """
    Die zyklischen Soll-/Steuerframes des Panels:
    8 Hex-Zeichen, beginnen bislang mit 01 und haben gültige XOR-Prüfsumme.
    """
    return (
        len(payload) == 8
        and payload.startswith("01")
        and valid_xor_frame(payload)
    )


def current_selection_is_supported() -> bool:
    key = (selected_mode, selected_speed)

    return (
        key in FIXED_FRAMES
        or key in ALTERNATING_SEQUENCES
    )


def publish_control_state(client: mqtt.Client) -> None:
    with state_lock:
        enabled = override_enabled
        mode = selected_mode
        speed = selected_speed
        supported = current_selection_is_supported()

    publish(client, "availability", "online")
    publish(client, "state/override", "ON" if enabled else "OFF")
    publish(client, "state/selected_mode", mode)
    publish(client, "state/selected_speed", speed)
    publish(client, "state/selection_supported", "ON" if supported else "OFF")


def send_to_fans(fans: serial.Serial, packet: bytes) -> None:
    with fans_write_lock:
        fans.write(packet)
        fans.flush()


# ---------------------------------------------------------
# Panel -> Lüfter
# ---------------------------------------------------------

def panel_to_fans_loop(
    panel: serial.Serial,
    fans: serial.Serial,
    client: mqtt.Client,
) -> None:
    """
    Liest vollständige STX/ETX-Frames vom Wandpanel.

    Override AUS:
        Alles wird transparent an die Lüfter weitergegeben.

    Override EIN:
        01-Steuerframes werden blockiert.
        02-Statusabfragen und andere Frames werden weitergereicht.
    """

    buffer = bytearray()
    in_frame = False

    while not stop_event.is_set():
        try:
            byte = panel.read(1)

            if not byte:
                continue

            value = byte[0]

            if value == 0x02:
                buffer = bytearray([value])
                in_frame = True
                continue

            if not in_frame:
                # Unerwartetes Byte außerhalb eines Frames:
                # im transparenten Sinne trotzdem weitergeben.
                send_to_fans(fans, byte)
                continue

            buffer.append(value)

            if value != 0x03:
                continue

            packet = bytes(buffer)
            payload = buffer[1:-1].decode(
                "ascii",
                errors="replace",
            ).upper()

            with state_lock:
                enabled = override_enabled

            blocked = enabled and is_panel_control_frame(payload)

            timestamp = time.strftime("%H:%M:%S")

            if blocked:
                print(
                    f"{timestamp}  PANEL  {payload}  BLOCKED",
                    flush=True,
                )
            else:
                send_to_fans(fans, packet)

                if payload.startswith("01"):
                    print(
                        f"{timestamp}  PANEL  {payload}  FORWARDED",
                        flush=True,
                    )

            publish(client, "state/panel_frame", payload)

            if is_panel_control_frame(payload):
                publish(client, "state/panel_control_frame", payload)
                publish(
                    client,
                    "state/panel_control_blocked",
                    "ON" if blocked else "OFF",
                )

            buffer = bytearray()
            in_frame = False

        except serial.SerialException as exc:
            print(
                f"Serieller Fehler am Panel-Port: {exc}",
                file=sys.stderr,
                flush=True,
            )
            stop_event.set()

        except Exception as exc:
            print(
                f"Fehler Panel -> Lüfter: {exc}",
                file=sys.stderr,
                flush=True,
            )
            stop_event.set()


# ---------------------------------------------------------
# Lüfter -> Panel
# ---------------------------------------------------------

def fans_to_panel_loop(
    fans: serial.Serial,
    panel: serial.Serial,
    client: mqtt.Client,
) -> None:
    """
    Leitet sämtliche Antworten der Lüfter immer unverändert zum Panel zurück.
    """

    frame_buffer = bytearray()
    in_frame = False

    while not stop_event.is_set():
        try:
            data = fans.read(256)

            if not data:
                continue

            with panel_write_lock:
                panel.write(data)
                panel.flush()

            for value in data:
                if value == 0x02:
                    frame_buffer = bytearray()
                    in_frame = True

                elif value == 0x03 and in_frame:
                    payload = frame_buffer.decode(
                        "ascii",
                        errors="replace",
                    ).upper()

                    timestamp = time.strftime("%H:%M:%S")
                    print(
                        f"{timestamp}  FANS   {payload}  REPLY",
                        flush=True,
                    )

                    publish(client, "state/fan_reply", payload)

                    frame_buffer = bytearray()
                    in_frame = False

                elif in_frame:
                    frame_buffer.append(value)

        except serial.SerialException as exc:
            print(
                f"Serieller Fehler am Lüfter-Port: {exc}",
                file=sys.stderr,
                flush=True,
            )
            stop_event.set()

        except Exception as exc:
            print(
                f"Fehler Lüfter -> Panel: {exc}",
                file=sys.stderr,
                flush=True,
            )
            stop_event.set()


# ---------------------------------------------------------
# Override-Sender
# ---------------------------------------------------------

def fixed_override_loop(
    fans: serial.Serial,
    client: mqtt.Client,
    generation: int,
    frame: str,
) -> None:
    packet = make_packet(frame)

    publish(client, "state/override_phase", "fixed")
    publish(client, "state/override_frame", frame)

    while not stop_event.is_set():
        with state_lock:
            still_valid = (
                override_enabled
                and generation == sequence_generation
            )

        if not still_valid:
            return

        send_to_fans(fans, packet)
        time.sleep(CONTROL_SEND_INTERVAL)


def alternating_override_loop(
    fans: serial.Serial,
    client: mqtt.Client,
    generation: int,
    sequence: tuple[SequenceStep, ...],
) -> None:
    step_index = 0

    while not stop_event.is_set():
        with state_lock:
            still_valid = (
                override_enabled
                and generation == sequence_generation
            )

        if not still_valid:
            return

        step = sequence[step_index]
        packet = make_packet(step.frame)

        publish(client, "state/override_phase", step.phase)
        publish(client, "state/override_frame", step.frame)

        print(
            f"{time.strftime('%H:%M:%S')}  OVERRIDE  "
            f"{step.frame}  phase={step.phase}",
            flush=True,
        )

        step_ends = time.monotonic() + step.duration

        while (
            not stop_event.is_set()
            and time.monotonic() < step_ends
        ):
            with state_lock:
                still_valid = (
                    override_enabled
                    and generation == sequence_generation
                )

            if not still_valid:
                return

            send_to_fans(fans, packet)

            remaining = step_ends - time.monotonic()
            time.sleep(
                min(CONTROL_SEND_INTERVAL, max(0.0, remaining))
            )

        step_index = (step_index + 1) % len(sequence)


def start_override_sender(
    fans: serial.Serial,
    client: mqtt.Client,
) -> None:
    global sequence_generation

    with state_lock:
        sequence_generation += 1
        generation = sequence_generation

        enabled = override_enabled
        mode = selected_mode
        speed = selected_speed

    if not enabled:
        publish(client, "state/override_phase", "panel")
        publish(client, "state/override_frame", "")
        return

    key = (mode, speed)

    if key in FIXED_FRAMES:
        thread = threading.Thread(
            target=fixed_override_loop,
            args=(
                fans,
                client,
                generation,
                FIXED_FRAMES[key],
            ),
            daemon=True,
            name="fixed-override",
        )
        thread.start()
        return

    if key in ALTERNATING_SEQUENCES:
        thread = threading.Thread(
            target=alternating_override_loop,
            args=(
                fans,
                client,
                generation,
                ALTERNATING_SEQUENCES[key],
            ),
            daemon=True,
            name="alternating-override",
        )
        thread.start()
        return

    print(
        f"Nicht unterstützter Override: {mode}, Stufe {speed}",
        flush=True,
    )

    publish(client, "state/error", f"unsupported:{mode}:{speed}")


# ---------------------------------------------------------
# MQTT-Callbacks
# ---------------------------------------------------------

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties=None,
) -> None:
    print(f"MQTT verbunden: {reason_code}", flush=True)

    client.subscribe(mqtt_topic("override/set"))
    client.subscribe(mqtt_topic("mode/set"))
    client.subscribe(mqtt_topic("speed/set"))

    publish_control_state(client)


def on_message(
    client,
    userdata,
    message,
) -> None:
    global override_enabled
    global selected_mode
    global selected_speed

    topic = message.topic
    payload = message.payload.decode(
        "utf-8",
        errors="replace",
    ).strip().lower()

    changed = False

    if topic == mqtt_topic("override/set"):
        new_value = payload.upper() in {
            "ON",
            "1",
            "TRUE",
            "YES",
        }

        with state_lock:
            override_enabled = new_value

        print(f"Override: {new_value}", flush=True)
        changed = True

    elif topic == mqtt_topic("mode/set"):
        with state_lock:
            selected_mode = payload

        print(f"Modus: {payload}", flush=True)
        changed = True

    elif topic == mqtt_topic("speed/set"):
        try:
            speed = int(payload)

            if speed not in (1, 2, 3):
                raise ValueError

        except ValueError:
            print(
                f"Ungültige Stufe: {payload}",
                flush=True,
            )
            return

        with state_lock:
            selected_speed = speed

        print(f"Stufe: {speed}", flush=True)
        changed = True

    if changed:
        publish_control_state(client)
        start_override_sender(userdata["fans"], client)


# ---------------------------------------------------------
# Programmstart
# ---------------------------------------------------------

def request_stop(signum=None, frame=None) -> None:
    stop_event.set()


def main() -> int:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        panel = serial.Serial(
            PANEL_PORT,
            BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
            write_timeout=1,
        )

        fans = serial.Serial(
            FANS_PORT,
            BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
            write_timeout=1,
        )

    except serial.SerialException as exc:
        print(
            f"Serielle Ports konnten nicht geöffnet werden: {exc}",
            file=sys.stderr,
        )
        return 1

    panel.reset_input_buffer()
    panel.reset_output_buffer()
    fans.reset_input_buffer()
    fans.reset_output_buffer()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        userdata={"fans": fans},
    )

    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASSWORD,
    )

    client.will_set(
        mqtt_topic("availability"),
        "offline",
        retain=True,
    )

    try:
        client.connect(
            MQTT_HOST,
            MQTT_PORT,
            60,
        )
    except Exception as exc:
        print(
            f"MQTT-Verbindung fehlgeschlagen: {exc}",
            file=sys.stderr,
        )
        panel.close()
        fans.close()
        return 1

    client.loop_start()

    panel_thread = threading.Thread(
        target=panel_to_fans_loop,
        args=(panel, fans, client),
        daemon=True,
        name="panel-to-fans",
    )

    fans_thread = threading.Thread(
        target=fans_to_panel_loop,
        args=(fans, panel, client),
        daemon=True,
        name="fans-to-panel",
    )

    panel_thread.start()
    fans_thread.start()

    publish(client, "availability", "online")
    publish_control_state(client)

    print("Ambientika MQTT-Gateway läuft.")
    print(f"Panel:  {PANEL_PORT}")
    print(f"Lüfter: {FANS_PORT}")
    print()
    print("MQTT:")
    print(f"  {mqtt_topic('mode/set')}")
    print(f"  {mqtt_topic('speed/set')}")
    print(f"  {mqtt_topic('override/set')}")
    print()
    print("Abbruch mit Strg+C.")

    try:
        while not stop_event.wait(0.5):
            pass

    finally:
        stop_event.set()

        with state_lock:
            global sequence_generation
            sequence_generation += 1

        publish(client, "availability", "offline")

        panel_thread.join(timeout=1)
        fans_thread.join(timeout=1)

        client.loop_stop()
        client.disconnect()

        panel.close()
        fans.close()

        print("\nGateway beendet.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
