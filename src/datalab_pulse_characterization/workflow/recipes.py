"""Headless recipe registry."""

from __future__ import annotations

from datalab.plugins.recipes import (
    RecipeCardinality,
    RecipeDescriptor,
    RecipeInputSlot,
    RecipeMetadataRequirement,
    RecipeObjectType,
)

from .. import PLUGIN_ID, __version__
from .campaign import (
    SHOT_METADATA_KEY,
    PulseCampaignRecipeParameters,
    run_pulse_campaign,
)
from .input_checks import (
    check_shot_signals,
    check_step_signals,
    check_two_channel_signals,
    suggest_two_channel_bindings,
)
from .spectroscopy import PulseHeightRecipeParameters, run_pulse_height_spectrum
from .stability import PulseStabilityRecipeParameters, run_pulse_stability
from .step_response import StepResponseRecipeParameters, run_step_response
from .two_channel import (
    CHANNEL_METADATA_KEY,
    TwoChannelDelayRecipeParameters,
    run_two_channel_delay,
)

SHOT_NUMBER_HINT = RecipeMetadataRequirement(
    SHOT_METADATA_KEY,
    "Shot number (positive integer); the selection order is used without it",
    required=False,
)


def _signals_slot(title: str, description: str, min_count: int = 1) -> RecipeInputSlot:
    """Return one required slot of repeated acquisitions, one signal per shot."""
    return RecipeInputSlot(
        "signals",
        RecipeObjectType.SIGNAL,
        RecipeCardinality.MANY,
        title=title,
        description=description,
        min_count=min_count,
        metadata=(SHOT_NUMBER_HINT,),
    )


def _channel_slot(slot_id: str, title: str, description: str) -> RecipeInputSlot:
    """Return one channel of a two-channel campaign, paired by shot number."""
    return RecipeInputSlot(
        slot_id,
        RecipeObjectType.SIGNAL,
        RecipeCardinality.MANY,
        title=title,
        description=description,
        min_count=3,
        metadata=(
            RecipeMetadataRequirement(
                SHOT_METADATA_KEY,
                "Shot number pairing the acquisitions of both channels",
            ),
            RecipeMetadataRequirement(
                CHANNEL_METADATA_KEY,
                "Channel label; two labels propose the reference/measured split",
                required=False,
            ),
        ),
    )


PULSE_CAMPAIGN_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:single-channel-campaign",
    plugin_version=__version__,
    title="Single-channel pulse campaign",
    version="1.1.0",
    description=(
        "Extract Sigima pulse features, align valid shots at their 50% crossings, "
        "and consolidate explainable diagnostics across repeated acquisitions."
    ),
    inputs=(
        _signals_slot(
            "Pulse acquisitions",
            "One signal per shot, recorded with the same time base, trigger and gain.",
            min_count=2,
        ),
    ),
    parameter_class=PulseCampaignRecipeParameters,
    run=run_pulse_campaign,
    check_inputs=check_shot_signals,
)

PULSE_STABILITY_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:shot-stability",
    plugin_version=__version__,
    title="Shot-to-shot stability",
    version="1.0.0",
    description=(
        "Measure trigger-referenced timing jitter, drifts, amplitude and energy "
        "stability, Allan deviations and a jitter regime change."
    ),
    inputs=(
        _signals_slot(
            "Pulse acquisitions in shot order",
            "One signal per shot, all timed from the same trigger reference so "
            "that arrival times compare from shot to shot.",
            min_count=4,
        ),
    ),
    parameter_class=PulseStabilityRecipeParameters,
    run=run_pulse_stability,
    check_inputs=check_shot_signals,
)

STEP_RESPONSE_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:step-response",
    plugin_version=__version__,
    title="Step response",
    version="1.0.0",
    description=(
        "Average aligned steps and measure rise time, overshoot, settling time, "
        "ringing frequency, damping ratio and bandwidth."
    ),
    inputs=(
        _signals_slot(
            "Step acquisitions",
            "One signal per step, from the baseline before the transition to the "
            "settled level after the ringing.",
        ),
    ),
    parameter_class=StepResponseRecipeParameters,
    run=run_step_response,
    check_inputs=check_step_signals,
)

TWO_CHANNEL_DELAY_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:two-channel-delay",
    plugin_version=__version__,
    title="Two-channel delay and jitter",
    version="1.0.0",
    description=(
        "Pair a reference and a measured channel by shot and measure their "
        "delay, relative and common-mode jitter, and amplitude correlation."
    ),
    inputs=(
        _channel_slot(
            "reference",
            "Reference channel",
            "One signal per shot from the timing reference (e.g. a trigger "
            "photodiode).",
        ),
        _channel_slot(
            "measured",
            "Measured channel",
            "One signal per shot from the detector under test, recorded with "
            "the same time base.",
        ),
    ),
    parameter_class=TwoChannelDelayRecipeParameters,
    run=run_two_channel_delay,
    suggest_bindings=suggest_two_channel_bindings,
    check_inputs=check_two_channel_signals,
)

PULSE_HEIGHT_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:pulse-height-spectrum",
    plugin_version=__version__,
    title="Pulse-height spectrum",
    version="1.0.0",
    description=(
        "Build an energy spectrum from triggered detector events, calibrate it "
        "with known lines and measure the energy resolution."
    ),
    inputs=(
        _signals_slot(
            "Triggered detector events",
            "One signal per triggered event: a pre-trigger baseline followed by "
            "the detector pulse, of either polarity.",
        ),
    ),
    parameter_class=PulseHeightRecipeParameters,
    run=run_pulse_height_spectrum,
    check_inputs=check_shot_signals,
)

RECIPES: tuple[RecipeDescriptor, ...] = (
    PULSE_CAMPAIGN_RECIPE,
    PULSE_STABILITY_RECIPE,
    STEP_RESPONSE_RECIPE,
    TWO_CHANNEL_DELAY_RECIPE,
    PULSE_HEIGHT_RECIPE,
)

__all__ = [
    "PULSE_CAMPAIGN_RECIPE",
    "PULSE_HEIGHT_RECIPE",
    "PULSE_STABILITY_RECIPE",
    "RECIPES",
    "STEP_RESPONSE_RECIPE",
    "TWO_CHANNEL_DELAY_RECIPE",
]
