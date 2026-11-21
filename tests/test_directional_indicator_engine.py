from __future__ import annotations

import unittest

from core.directional_indicator_engine import (
    classify_direction,
    driver_state_from_signal,
    scenario_transmission,
)


class DirectionalIndicatorEngineTests(unittest.TestCase):
    def test_higher_is_better_supports_both_sides(self) -> None:
        self.assertEqual(classify_direction(10,orientation="HIGHER_IS_BETTER"),"BENEFICIAL")
        self.assertEqual(classify_direction(-10,orientation="HIGHER_IS_BETTER"),"ADVERSE")
        self.assertEqual(driver_state_from_signal("BENEFICIAL"),"IMPROVING")
        self.assertEqual(driver_state_from_signal("ADVERSE"),"DETERIORATING")

    def test_lower_is_better_for_future_cost_indicators(self) -> None:
        self.assertEqual(classify_direction(-5,orientation="LOWER_IS_BETTER"),"BENEFICIAL")
        self.assertEqual(classify_direction(5,orientation="LOWER_IS_BETTER"),"ADVERSE")

    def test_neutral_band(self) -> None:
        self.assertEqual(classify_direction(0.4,orientation="HIGHER_IS_BETTER",neutral_band=0.5),"NEUTRAL")

    def test_sensitivity_is_bidirectional(self) -> None:
        self.assertAlmostEqual(scenario_transmission(0.8,10),8.0)
        self.assertAlmostEqual(scenario_transmission(0.8,-10),-8.0)


if __name__=="__main__":
    unittest.main()
