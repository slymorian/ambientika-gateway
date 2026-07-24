import unittest

from ambientika_gateway.protocol import Mode
from ambientika_gateway.state import GatewayState


class GatewayStateTests(unittest.TestCase):
    def test_desired_state_is_separate_and_synchronized(self) -> None:
        state = GatewayState()
        state.configure_desired(
            mode=Mode.MONITORING,
            speed=1,
            humidity_level=3,
        )
        snapshot = state.snapshot()
        self.assertEqual(snapshot.desired.mode, Mode.MONITORING)
        self.assertEqual(snapshot.desired.speed, 1)
        self.assertEqual(snapshot.desired.humidity_level, 3)
        self.assertFalse(snapshot.override.enabled)
        self.assertEqual(snapshot.override.mode, Mode.MONITORING)

    def test_enabling_override_preserves_desired_selection(self) -> None:
        state = GatewayState()
        state.configure_desired(mode=Mode.SUPPLY, speed=2)
        state.configure_override(enabled=True)
        snapshot = state.snapshot()
        self.assertTrue(snapshot.override.enabled)
        self.assertEqual(snapshot.desired.mode, Mode.SUPPLY)
        self.assertEqual(snapshot.desired.speed, 2)


if __name__ == "__main__":
    unittest.main()
