from __future__ import annotations

import unittest

from ambientika_gateway.protocol import (
    FrameCategory,
    Mode,
    OperatingState,
    Phase,
    alternating_sequence,
    candidate_modes,
    checksum_for,
    decode_frame,
    fixed_command_frame,
    is_valid_control_frame,
)


class ProtocolRegressionTests(unittest.TestCase):
    """Regression tests for frames confirmed during protocol analysis.

    These tests intentionally separate the selected panel mode from the
    physical fan-bus state. Ambiguous alternating frames must not be promoted
    to Automatic or Manual without additional state context.
    """

    def test_fixed_direction_frames_keep_historical_mode_mapping(self) -> None:
        cases = {
            "01650064": (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 1),
            "01660067": (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 2),
            "01670066": (Mode.MASTER_EXTRACT_SLAVE_SUPPLY, 3),
            "01690068": (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 1),
            "016A006B": (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 2),
            "016B006A": (Mode.MASTER_SUPPLY_SLAVE_EXTRACT, 3),
        }

        for raw, (mode, speed) in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.category, FrameCategory.CONTROL)
                self.assertEqual(frame.mode, mode)
                self.assertEqual(frame.speed, speed)
                self.assertEqual(frame.phase, Phase.FIXED)
                self.assertEqual(candidate_modes(frame), (mode,))

    def test_both_fans_extract_frames(self) -> None:
        for speed, raw in enumerate(
            ("01750074", "01760077", "01770076"),
            start=1,
        ):
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.mode, Mode.EXTRACT)
                self.assertEqual(frame.speed, speed)
                self.assertEqual(frame.phase, Phase.FIXED)
                self.assertEqual(frame.operating_state, OperatingState.EXTRACT)

    def test_both_fans_supply_frames(self) -> None:
        for speed, raw in enumerate(
            ("01790078", "017A007B", "017B007A"),
            start=1,
        ):
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.mode, Mode.SUPPLY)
                self.assertEqual(frame.speed, speed)
                self.assertEqual(frame.phase, Phase.FIXED)
                self.assertEqual(frame.operating_state, OperatingState.SUPPLY)

    def test_manual_or_automatic_alternating_frames_remain_ambiguous(self) -> None:
        cases = {
            "01A500A4": (1, Phase.PHASE_A, OperatingState.ALTERNATING),
            "01A100A0": (1, Phase.TRANSITION, OperatingState.TRANSITION),
            "01A900A8": (1, Phase.PHASE_B, OperatingState.ALTERNATING),
            "01AA00AB": (2, Phase.PHASE_A, OperatingState.ALTERNATING),
            "01A200A3": (2, Phase.TRANSITION, OperatingState.TRANSITION),
            "01A600A7": (2, Phase.PHASE_B, OperatingState.ALTERNATING),
            "01A700A6": (3, Phase.PHASE_A, OperatingState.ALTERNATING),
            "01A300A2": (3, Phase.TRANSITION, OperatingState.TRANSITION),
        }
        expected_modes = (Mode.AUTOMATIC, Mode.MANUAL_ALTERNATING)

        for raw, (speed, phase, operating_state) in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.mode, Mode.UNKNOWN)
                self.assertEqual(frame.possible_modes, expected_modes)
                self.assertEqual(candidate_modes(frame), expected_modes)
                self.assertEqual(frame.speed, speed)
                self.assertEqual(frame.phase, phase)
                self.assertEqual(frame.operating_state, operating_state)

    def test_silent_sequence_frames_are_unambiguous(self) -> None:
        cases = {
            "01280029": Phase.PHASE_A,
            "01200021": Phase.TRANSITION,
            "01240025": Phase.PHASE_B,
        }

        for raw, phase in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.mode, Mode.SILENT)
                self.assertEqual(frame.speed, 1)
                self.assertEqual(frame.phase, phase)
                self.assertEqual(candidate_modes(frame), (Mode.SILENT,))

    def test_humidity_threshold_frames_do_not_claim_physical_state(self) -> None:
        cases = {
            "01360433": 1,
            "01760473": 2,
            "01B604B3": 3,
        }

        for raw, humidity in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.humidity_level, humidity)
                self.assertIn(Mode.AUTOMATIC, candidate_modes(frame))
                self.assertIn(Mode.MONITORING, candidate_modes(frame))

                # Threshold selection alone must not prove a unique panel mode.
                self.assertEqual(frame.mode, Mode.UNKNOWN)

    def test_humidity_button_frames_are_marked_as_button_press(self) -> None:
        cases = {
            "01360C3B": 1,
            "01760C7B": 2,
            "01B60CBB": 3,
        }

        for raw, humidity in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertTrue(frame.button_press)
                self.assertEqual(frame.humidity_level, humidity)
                self.assertEqual(
                    candidate_modes(frame),
                    (Mode.AUTOMATIC, Mode.MONITORING),
                )

    def test_confirmed_automatic_normal_frame_is_unambiguous(self) -> None:
        frame = decode_frame("panel", "01720073")
        self.assertEqual(frame.mode, Mode.AUTOMATIC)
        self.assertEqual(candidate_modes(frame), (Mode.AUTOMATIC,))
        self.assertEqual(frame.speed, 2)
        self.assertEqual(frame.humidity_level, 2)
        self.assertFalse(frame.humidity_alarm)

    def test_short_panel_requests(self) -> None:
        cases = {
            "020002": False,
            "020406": False,
            "020507": True,
        }

        for raw, filter_reset in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("panel", raw)
                self.assertEqual(frame.category, FrameCategory.REQUEST)
                self.assertEqual(frame.filter_reset, filter_reset)

    def test_known_fan_replies(self) -> None:
        # 000808 trägt keine Alarminformation: am 20.09.2026 unverändert bei
        # Auto/LED an und Nachtmodus/LED aus (siehe protocol.py).
        # 000909 bleibt vorerst unverändert (dazu liegt keine neue Messung vor).
        cases = {
            "000202": (0x02, None, None),
            "000808": (0x08, False, None),
            "000909": (0x09, None, True),
            "000A0A": (0x0A, True, None),
        }

        for raw, (status_byte, filter_alarm, humidity_alarm) in cases.items():
            with self.subTest(raw=raw):
                frame = decode_frame("fans", raw)
                self.assertEqual(frame.category, FrameCategory.REPLY)
                self.assertEqual(frame.status_byte, status_byte)
                self.assertEqual(frame.filter_alarm, filter_alarm)
                self.assertEqual(frame.humidity_alarm, humidity_alarm)

    def test_manual_alternating_sequences_are_stable(self) -> None:
        expected = {
            1: (
                ("01A500A4", 60.0, Phase.PHASE_A),
                ("01A100A0", 10.0, Phase.TRANSITION),
                ("01A900A8", 60.0, Phase.PHASE_B),
                ("01A100A0", 10.0, Phase.TRANSITION),
            ),
            2: (
                ("01AA00AB", 60.0, Phase.PHASE_A),
                ("01A200A3", 10.0, Phase.TRANSITION),
                ("01A600A7", 60.0, Phase.PHASE_B),
                ("01A200A3", 10.0, Phase.TRANSITION),
            ),
        }

        for speed, expected_steps in expected.items():
            with self.subTest(speed=speed):
                sequence = alternating_sequence(Mode.MANUAL_ALTERNATING, speed)
                actual = tuple(
                    (step.frame, step.duration, step.phase)
                    for step in sequence
                )
                self.assertEqual(actual, expected_steps)

    def test_silent_sequence_is_stable(self) -> None:
        sequence = alternating_sequence(Mode.SILENT, 1)
        actual = tuple(
            (step.frame, step.duration, step.phase)
            for step in sequence
        )
        self.assertEqual(
            actual,
            (
                ("01280029", 60.0, Phase.PHASE_A),
                ("01200021", 10.0, Phase.TRANSITION),
                ("01240025", 60.0, Phase.PHASE_B),
                ("01200021", 10.0, Phase.TRANSITION),
            ),
        )

    def test_fixed_command_lookup_matches_decoder(self) -> None:
        for mode in (
            Mode.EXTRACT,
            Mode.SUPPLY,
            Mode.MASTER_EXTRACT_SLAVE_SUPPLY,
            Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        ):
            for speed in (1, 2, 3):
                with self.subTest(mode=mode, speed=speed):
                    raw = fixed_command_frame(mode, speed)
                    frame = decode_frame("panel", raw)
                    self.assertEqual(frame.mode, mode)
                    self.assertEqual(frame.speed, speed)

    def test_checksum_rule_is_xor_of_first_three_bytes(self) -> None:
        raw = bytes.fromhex("01AA00")
        self.assertEqual(checksum_for(raw), 0xAB)
        self.assertTrue(is_valid_control_frame("01AA00AB"))
        self.assertFalse(is_valid_control_frame("01AA00AA"))

    def test_unknown_valid_control_frame_remains_visible(self) -> None:
        # 01 AC 00 -> checksum AD; deliberately not present in CONTROL_FRAMES.
        frame = decode_frame("panel", "01AC00AD")
        self.assertEqual(frame.category, FrameCategory.UNKNOWN_CONTROL)
        self.assertTrue(frame.checksum_valid)
        self.assertEqual(frame.mode, Mode.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
