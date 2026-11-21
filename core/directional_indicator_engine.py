from __future__ import annotations

from typing import Literal

EconomicOrientation = Literal["HIGHER_IS_BETTER","LOWER_IS_BETTER"]
SignalDirection = Literal["BENEFICIAL","NEUTRAL","ADVERSE"]

VALID_ORIENTATIONS={"HIGHER_IS_BETTER","LOWER_IS_BETTER"}


def classify_direction(
    change: float,
    *,
    orientation: str,
    neutral_band: float=0.0,
) -> SignalDirection:
    if orientation not in VALID_ORIENTATIONS:
        raise ValueError(f"Unknown economic orientation: {orientation}")
    if abs(float(change)) <= float(neutral_band):
        return "NEUTRAL"
    positive=float(change)>0
    if orientation=="HIGHER_IS_BETTER":
        return "BENEFICIAL" if positive else "ADVERSE"
    return "ADVERSE" if positive else "BENEFICIAL"


def driver_state_from_signal(direction: SignalDirection) -> str:
    return {
        "BENEFICIAL":"IMPROVING",
        "NEUTRAL":"NEUTRAL",
        "ADVERSE":"DETERIORATING",
    }[direction]


def scenario_transmission(beta: float, shock: float) -> float:
    """Linear candidate transmission. Sign works for both upside and downside shocks."""
    return float(beta)*float(shock)
