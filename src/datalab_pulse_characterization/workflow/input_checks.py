"""Fast checks of Pulse recipe inputs, run by hosts before any computation.

They reuse the validation of the recipe conversions (shot metadata, sampled
arrays) without extracting features, so that DataLab can tell whether the
current selection suits a method while the user selects signals.
"""

from __future__ import annotations

from collections.abc import Sequence

import guidata.dataset as gds
from datalab.recipes import RecipeDiagnostic, RecipeInputs
from sigima.objects import SignalObj

from .campaign import _acquisitions
from .two_channel import _channel, suggest_channel_roles

#: Minimum number of samples of a step acquisition (rise, plateau, settling)
MINIMUM_STEP_SAMPLES = 20


def check_shot_signals(
    inputs: RecipeInputs, _parameters: gds.DataSet | None
) -> list[RecipeDiagnostic]:
    """Check that every signal is a sampled pulse with a valid shot number."""
    _acquisitions(inputs["signals"])
    return []


def check_step_signals(
    inputs: RecipeInputs, _parameters: gds.DataSet | None
) -> list[RecipeDiagnostic]:
    """Check that every step acquisition is sampled finely enough."""
    acquisitions = _acquisitions(inputs["signals"])
    short = [
        acquisition.title
        for acquisition in acquisitions
        if len(acquisition.x) < MINIMUM_STEP_SAMPLES
    ]
    if short:
        return [
            RecipeDiagnostic(
                "error",
                "too-few-samples",
                f"{len(short)} step acquisition(s) have fewer than "
                f"{MINIMUM_STEP_SAMPLES} samples: {', '.join(short[:3])}",
            )
        ]
    return []


def check_two_channel_signals(
    inputs: RecipeInputs, _parameters: gds.DataSet | None
) -> list[RecipeDiagnostic]:
    """Check shot numbering of both channels and their common time unit."""
    for slot in ("reference", "measured"):
        _channel(inputs[slot], slot)
    units = {signal.xunit or "" for slot in inputs.values() for signal in slot}
    if len(units) > 1:
        return [
            RecipeDiagnostic(
                "error",
                "inconsistent-time-unit",
                "Both channels must share the same X unit",
            )
        ]
    return []


def suggest_two_channel_bindings(
    candidates: Sequence[SignalObj],
) -> dict[str, tuple[SignalObj, ...]]:
    """Split candidates into reference and measured channels from metadata."""
    return suggest_channel_roles(tuple(candidates))


__all__ = [
    "MINIMUM_STEP_SAMPLES",
    "check_shot_signals",
    "check_step_signals",
    "check_two_channel_signals",
    "suggest_two_channel_bindings",
]
