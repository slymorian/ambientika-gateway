from __future__ import annotations

import unittest
from dataclasses import replace

from ambientika_gateway.config import MqttConfig
from ambientika_gateway.discovery import build_discovery_payload
from ambientika_gateway.frame_generator import FrameGenerator
from ambientika_gateway.protocol import (
    Mode,
    OperatingState,
    Phase,
    decode_frame,
)
from ambientika_gateway.state import ControlPolicy, GatewayState


class StatefulControlTests(unittest.TestCase):
    def test_desired_state_is_independent_from_override(self) -> None:
        state = GatewayState()
        desired = state.configure_desired(
            mode=Mode.MANUAL_ALTERNATING,
            speed=2,
            humidity=3,
        )

        self.assertEqual(desired.desired_mode, Mode.MANUAL_ALTERNATING)
        self.assertEqual(desired.desired_speed, 2)
        self.assertEqual(desired.desired_humidity, 3)
        self.assertFalse(state.override_state().enabled)

        override = state.configure_override(enabled=True)
        self.assertEqual(override.policy, ControlPolicy.OVERRIDE)

    def test_frame_generator_builds_fixed_and_sequence_plans(self) -> None:
        generator = FrameGenerator()
        fixed = generator.plan(
            mode=Mode.EXTRACT,
            speed=2,
            humidity=2,
        )
        self.assertEqual(fixed.fixed_frame, "01760077")
        self.assertFalse(fixed.alternating)

        sequence = generator.plan(
            mode=Mode.MANUAL_ALTERNATING,
            speed=1,
            humidity=2,
        )
        self.assertTrue(sequence.alternating)
        self.assertEqual(sequence.sequence[0].phase, Phase.PHASE_A)
        self.assertEqual(
            generator.packet(sequence.sequence[0].frame)[0],
            0x02,
        )

    def test_observed_operating_state_is_published_in_snapshot(self) -> None:
        state = GatewayState()
        frame = decode_frame("panel", "01760077")
        state.update_panel_frame(frame)
        state.mark_active_panel_frame(frame)
        snapshot = state.snapshot()

        self.assertEqual(snapshot.operating_state, OperatingState.EXTRACT)
        self.assertEqual(snapshot.phase, Phase.FIXED)

    def test_humidity_alarm_updates_observed_state(self) -> None:
        state = GatewayState()
        # Mechanismus-Test: Eine Master-Antwort mit humidity_alarm=True wird
        # übernommen. Die Antwort ist synthetisch, weil aktuell keine Antwort
        # mit belegter Alarmbedeutung bekannt ist (000808 trägt den Alarm
        # nicht, Messung 20.09.2026; 000909 ist unbelegt).
        alarm = replace(decode_frame("fans", "000808"), humidity_alarm=True)
        state.update_fan_reply(alarm)
        self.assertTrue(state.snapshot().humidity_alarm)

        # 01720073 traegt seit 21.09.2026 keine Alarminformation mehr;
        # ein "alarmfreier" Panelframe wird kuenstlich gesetzt.
        normal = replace(decode_frame("panel", "01720073"), humidity_alarm=False)
        state.update_panel_frame(normal)
        state.mark_active_panel_frame(normal)
        self.assertFalse(state.snapshot().humidity_alarm)

    def test_discovery_contains_stateful_entities(self) -> None:
        config = MqttConfig(
            host="localhost",
            port=1883,
            username="",
            password="",
            keepalive=60,
            base_topic="ambientika",
            client_id="ambientika-gateway",
            retain_state=True,
        )
        payload = build_discovery_payload(
            config,
            software_version="test",
        )
        components = payload["components"]

        self.assertIn("humidity", components)
        self.assertIn("operating_state", components)
        self.assertIn("humidity_alarm", components)
        self.assertEqual(
            components["humidity"]["command_topic"],
            f"{config.base_topic}/humidity/set",
        )


if __name__ == "__main__":
    unittest.main()
