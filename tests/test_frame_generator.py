import unittest

from ambientika_gateway.frame_generator import FrameGenerator, ProgramKind
from ambientika_gateway.protocol import Mode, Phase


class FrameGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = FrameGenerator()

    def test_automatic_level_two_uses_confirmed_idle_frame(self) -> None:
        program = self.generator.build(
            mode=Mode.AUTOMATIC,
            speed=2,
            humidity_level=2,
        )
        self.assertEqual(program.kind, ProgramKind.FIXED)
        self.assertEqual(program.fixed_frame, "01720073")
        self.assertEqual(program.initial_phase, Phase.FIXED)

    def test_automatic_unconfirmed_level_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.generator.build(
                mode=Mode.AUTOMATIC,
                speed=2,
                humidity_level=1,
            )

    def test_monitoring_uses_humidity_specific_frame(self) -> None:
        frames = {
            1: "01360433",
            2: "01760473",
            3: "01B604B3",
        }
        for level, frame in frames.items():
            with self.subTest(level=level):
                program = self.generator.build(
                    mode=Mode.MONITORING,
                    speed=2,
                    humidity_level=level,
                )
                self.assertEqual(program.fixed_frame, frame)

    def test_manual_alternating_returns_sequence(self) -> None:
        program = self.generator.build(
            mode=Mode.MANUAL_ALTERNATING,
            speed=2,
            humidity_level=2,
        )
        self.assertEqual(program.kind, ProgramKind.ALTERNATING)
        self.assertGreaterEqual(len(program.sequence), 3)


if __name__ == "__main__":
    unittest.main()
