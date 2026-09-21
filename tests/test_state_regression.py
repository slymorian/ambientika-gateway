from __future__ import annotations

import unittest
from dataclasses import replace

from ambientika_gateway.protocol import (
    DecodedFrame,
    Mode,
    OperatingState,
    Phase,
    decode_frame,
)
from ambientika_gateway.state import GatewayState


def automatic_selection(raw: str) -> DecodedFrame:
    """Frame, der Automatic eindeutig auswählt (künstlich gesetzt).

    Seit der Messung vom 21.09.2026 wählt kein zugeordneter Panelframe
    AUTOMATIC eindeutig aus: 01720073, bisher als solcher geführt, ist das
    Neutralframe beim Verlassen von Auto. Wie im Manual-Test wird ein
    bereits sicher bekannter Panelmodus deshalb künstlich gesetzt, ohne die
    Produktions-API zu ändern.
    """
    return replace(
        decode_frame("panel", raw),
        mode=Mode.AUTOMATIC,
        possible_modes=(Mode.AUTOMATIC,),
    )


def alarm_frame(raw: str, alarm: bool = True) -> DecodedFrame:
    """Panelframe mit künstlich gesetzter Alarminformation.

    Nur für explizite "kein Alarm"-Werte (False) nötig: Es gibt bisher keinen
    Panelframe, der Alarm ausdrücklich verneint (Flag 0x00 ist bei
    Wechselbetriebsframes mit Manuell mehrdeutig).
    """
    return replace(decode_frame("panel", raw), humidity_alarm=alarm)


class StateRegressionTests(unittest.TestCase):
    """Regression tests for state reconstruction across ambiguous frames."""

    def test_ambiguous_frame_after_startup_keeps_mode_unknown(self) -> None:
        state = GatewayState()
        ambiguous = decode_frame("panel", "01AA00AB")

        state.update_panel_frame(ambiguous)
        state.mark_active_panel_frame(ambiguous)

        self.assertEqual(state.panel_state().mode, Mode.UNKNOWN)
        self.assertEqual(state.active_state().mode, Mode.UNKNOWN)
        self.assertEqual(state.active_state().speed, 2)
        self.assertEqual(state.active_state().phase, Phase.PHASE_A)
        self.assertEqual(
            state.active_state().operating_state,
            OperatingState.ALTERNATING,
        )

    def test_ambiguous_frame_preserves_automatic_mode(self) -> None:
        state = GatewayState()
        automatic = automatic_selection("01B604B3")
        ambiguous = decode_frame("panel", "01AA00AB")

        state.update_panel_frame(automatic)
        state.update_panel_frame(ambiguous)
        state.mark_active_panel_frame(ambiguous)

        self.assertEqual(state.panel_state().mode, Mode.AUTOMATIC)
        self.assertEqual(state.active_state().mode, Mode.AUTOMATIC)
        self.assertEqual(state.active_state().speed, 2)
        self.assertEqual(state.active_state().phase, Phase.PHASE_A)
        self.assertEqual(
            state.active_state().operating_state,
            OperatingState.ALTERNATING,
        )

    def test_ambiguous_frame_preserves_manual_mode(self) -> None:
        state = GatewayState()
        ambiguous = decode_frame("panel", "01AA00AB")

        # No currently mapped frame uniquely selects manual alternating mode.
        # Seed that already-known panel mode without changing the production API.
        manual_selection = replace(
            ambiguous,
            mode=Mode.MANUAL_ALTERNATING,
            possible_modes=(Mode.MANUAL_ALTERNATING,),
        )

        state.update_panel_frame(manual_selection)
        state.update_panel_frame(ambiguous)
        state.mark_active_panel_frame(ambiguous)

        self.assertEqual(state.panel_state().mode, Mode.MANUAL_ALTERNATING)
        self.assertEqual(state.active_state().mode, Mode.MANUAL_ALTERNATING)
        self.assertEqual(state.active_state().speed, 2)
        self.assertEqual(state.active_state().phase, Phase.PHASE_A)

    def test_humidity_threshold_preserves_automatic_mode(self) -> None:
        state = GatewayState()
        automatic = automatic_selection("01720073")
        threshold = decode_frame("panel", "01B604B3")

        state.update_panel_frame(automatic)
        state.update_panel_frame(threshold)
        state.mark_active_panel_frame(threshold)

        self.assertEqual(state.panel_state().mode, Mode.AUTOMATIC)
        self.assertEqual(state.active_state().mode, Mode.AUTOMATIC)
        self.assertEqual(state.active_state().humidity, 3)

    def test_auto_exit_neutral_frame_does_not_select_automatic(self) -> None:
        # Beobachtete Serie beim Wechsel Auto -> Nacht, Schwelle 2
        # (21.09.2026): 0172087B -> 01720073 -> 01680069.
        state = GatewayState()
        self._feed_panel(state, "0172087B", "01720073")
        self.assertEqual(state.panel_state().mode, Mode.UNKNOWN)
        self.assertEqual(state.active_state().mode, Mode.UNKNOWN)
        self.assertEqual(state.panel_state().humidity, 2)

        self._feed_panel(state, "01680069")
        self.assertEqual(state.panel_state().mode, Mode.SILENT)
        self.assertEqual(state.active_state().mode, Mode.SILENT)

    def test_unambiguous_fixed_frame_replaces_previous_mode(self) -> None:
        state = GatewayState()
        state.update_panel_frame(automatic_selection("01720073"))

        # Hinweis: 016A006B ist bei Schwelle 2 bitgleich mit dem manuellen
        # Wechselbetrieb Stufe 2 (Messung 21.09.2026). Die Zuordnung zu
        # MASTER_SUPPLY_SLAVE_EXTRACT ist unverändert (offen).
        fixed = decode_frame("panel", "016A006B")
        state.update_panel_frame(fixed)
        state.mark_active_panel_frame(fixed)

        self.assertEqual(
            state.panel_state().mode,
            Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        )
        self.assertEqual(
            state.active_state().mode,
            Mode.MASTER_SUPPLY_SLAVE_EXTRACT,
        )
        self.assertEqual(state.active_state().speed, 2)
        self.assertEqual(state.active_state().phase, Phase.FIXED)


    # ------------------------------------------------------------------
    # humidity_alarm darf nicht "kleben bleiben"
    #
    # Hintergrund: Am 30.07.2026 zeigte Home Assistant "Feuchtealarm: nass",
    # obwohl die Lüfter sauber im alarmfreien Wechselbetrieb liefen. Ein
    # Frame, der einen physischen Betriebszustand beschreibt, aber keine
    # Alarminformation trägt (z. B. 01AA00AB), belegt einen zuvor
    # gesehenen Alarm nicht mehr. Reine Schwellen-/Tastendruckframes
    # beschreiben dagegen keinen physischen Zustand (Architekturregel E)
    # und lassen den Alarmzustand unberührt.
    #
    # Stand 21.09.2026: Byte 3 = 0x04 im Panelframe ist der Feuchtealarm
    # (Auto, LED an). Die Tests verwenden echte Alarmframes; ein explizites
    # "kein Alarm" wird künstlich gesetzt (alarm_frame(..., False)).
    # ------------------------------------------------------------------

    def _feed_panel(
        self,
        state: GatewayState,
        *frames: str | DecodedFrame,
    ) -> None:
        for item in frames:
            frame = (
                decode_frame("panel", item)
                if isinstance(item, str)
                else item
            )
            state.update_panel_frame(frame)
            state.mark_active_panel_frame(frame)

    def test_alarm_is_retracted_by_alternating_frame_without_alarm_info(
        self,
    ) -> None:
        state = GatewayState()
        self._feed_panel(
            state,
            alarm_frame("01720073", False),
            "01620467",
            "01760473",
        )
        self.assertTrue(state.panel_state().humidity_alarm)
        self.assertTrue(state.active_state().humidity_alarm)

        for raw in ("01AA00AB", "01A200A3", "01A600A7"):
            with self.subTest(raw=raw):
                self._feed_panel(state, raw)
                self.assertIs(state.panel_state().humidity_alarm, False)
                self.assertIs(state.active_state().humidity_alarm, False)

    def test_alarm_survives_frames_without_physical_state(self) -> None:
        state = GatewayState()
        self._feed_panel(state, "01760473")

        # Tastendruck- und Schwellenframe beschreiben keinen physischen
        # Zustand und dürfen einen erkannten Alarm nicht löschen.
        self._feed_panel(state, "01760C7B")
        self.assertIs(state.panel_state().humidity_alarm, True)
        self.assertIs(state.active_state().humidity_alarm, True)

    def test_unmapped_control_frame_does_not_retract_alarm(self) -> None:
        state = GatewayState()
        self._feed_panel(state, "01760473")

        # 01AC00AD ist formal gültig, aber nicht zugeordnet (UNKNOWN_CONTROL).
        self._feed_panel(state, "01AC00AD")
        self.assertIs(state.panel_state().humidity_alarm, True)

    def test_alarm_is_not_invented_without_prior_evidence(self) -> None:
        state = GatewayState()

        # Nach Gatewaystart ist der Alarmzustand unbekannt (None), nicht
        # "kein Alarm". Ein alarmfreier Wechselbetriebsframe ändert daran
        # nichts: es wird nichts zurückgenommen, was nie behauptet wurde.
        self._feed_panel(state, "01AA00AB")
        self.assertIsNone(state.panel_state().humidity_alarm)
        self.assertIsNone(state.active_state().humidity_alarm)

    def test_explicit_alarm_information_overrides_carry_over(self) -> None:
        state = GatewayState()
        self._feed_panel(state, alarm_frame("01720073", False))
        self.assertIs(state.panel_state().humidity_alarm, False)

        # 016A046F / 01620467 sind ALTERNATING bzw. TRANSITION, tragen aber
        # explizit humidity_alarm=True und dürfen nicht zurückgesetzt werden.
        for raw in (
            "016A046F",
            "01620467",
            "01760473",
            "01740471",
            "01AA04AF",
            "01A204A7",
            "01B604B3",
        ):
            with self.subTest(raw=raw):
                self._feed_panel(state, raw)
                self.assertIs(state.panel_state().humidity_alarm, True)
                self.assertIs(state.active_state().humidity_alarm, True)

        self._feed_panel(state, alarm_frame("01720073", False))
        self.assertIs(state.panel_state().humidity_alarm, False)

    def test_alarm_cycle_measured_on_2026_09_21(self) -> None:
        # Auto, Schwelle 3: Wechselbetrieb ohne Alarm, Alarm beginnt,
        # Abluftzustand, Alarm endet (Rohdaten in messung_M2.txt).
        state = GatewayState()
        self._feed_panel(state, "01AA00AB", "01A200A3", "01A600A7")
        self.assertIsNone(state.panel_state().humidity_alarm)

        self._feed_panel(state, "01AA04AF", "01A204A7", "01B604B3")
        self.assertIs(state.panel_state().humidity_alarm, True)
        self.assertIs(state.active_state().humidity_alarm, True)

        # Alarm vorbei: Übergangsframe (definiter Zustand) nimmt den Alarm zurück.
        self._feed_panel(state, "01B200B3")
        self.assertIs(state.panel_state().humidity_alarm, False)

        self._feed_panel(state, "01AA00AB")
        self.assertIs(state.panel_state().humidity_alarm, False)

    def test_override_alternating_frame_does_not_inherit_stale_alarm(
        self,
    ) -> None:
        state = GatewayState()
        self._feed_panel(state, "01760473")
        self.assertIs(state.active_state().humidity_alarm, True)

        # Override-Frame ohne Alarminfo und ohne Fan-Antwort mit Alarminfo.
        state.mark_active_override_frame(
            raw_frame="01AA00AB",
            mode=Mode.MANUAL_ALTERNATING,
            speed=2,
            humidity=2,
            operating_state=OperatingState.ALTERNATING,
            phase=Phase.PHASE_A,
        )
        self.assertIs(state.active_state().humidity_alarm, False)

    def test_override_keeps_alarm_when_state_is_not_physical(self) -> None:
        state = GatewayState()
        self._feed_panel(state, "01760473")

        state.mark_active_override_frame(
            raw_frame="01760C7B",
            mode=Mode.MONITORING,
            speed=2,
            humidity=2,
            operating_state=OperatingState.UNKNOWN,
            phase=Phase.UNKNOWN,
        )
        self.assertIs(state.active_state().humidity_alarm, True)


    def test_fan_reply_sets_and_clears_humidity_alarm(self) -> None:
        # 000808 = Feuchte über Schwelle, 000000 = darunter (Messungen
        # 20./21.09.2026). Die Antwort eilt dem Panelframe um ca. 5-6 s voraus.
        state = GatewayState()
        self._feed_panel(state, "01AA00AB")

        state.update_fan_reply(decode_frame("fans", "000808"))
        self.assertIs(state.fan_reply_state().humidity_alarm, True)
        self.assertIs(state.active_state().humidity_alarm, True)

        state.update_fan_reply(decode_frame("fans", "000000"))
        self.assertIs(state.fan_reply_state().humidity_alarm, False)
        self.assertIs(state.active_state().humidity_alarm, False)

    def test_override_takes_alarm_from_fan_reply(self) -> None:
        state = GatewayState()
        state.update_fan_reply(decode_frame("fans", "000808"))
        state.mark_active_override_frame(
            raw_frame="01AA00AB",
            mode=Mode.MANUAL_ALTERNATING,
            speed=2,
            humidity=2,
            operating_state=OperatingState.ALTERNATING,
            phase=Phase.PHASE_A,
        )
        self.assertIs(state.active_state().humidity_alarm, True)

        state.update_fan_reply(decode_frame("fans", "000000"))
        state.mark_active_override_frame(
            raw_frame="01AA00AB",
            mode=Mode.MANUAL_ALTERNATING,
            speed=2,
            humidity=2,
            operating_state=OperatingState.ALTERNATING,
            phase=Phase.PHASE_A,
        )
        self.assertIs(state.active_state().humidity_alarm, False)


if __name__ == "__main__":
    unittest.main()
