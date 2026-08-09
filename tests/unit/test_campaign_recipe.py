"""Tests for the headless single-channel pulse campaign recipe."""

from __future__ import annotations

import json

import numpy as np
import pytest
from datalab.recipes import (
    RecipeCancellationError,
    RecipeExecutionContext,
    RecipeValidationError,
)
from sigima.enums import SignalShape
from sigima.objects import SignalObj, TableResult, create_signal

from datalab_pulse_characterization.core import PulseStatus
from datalab_pulse_characterization.workflow import (
    OUTPUT_ROLE_METADATA_KEY,
    PULSE_CAMPAIGN_RECIPE,
    SHOT_METADATA_KEY,
    PulseCampaignRecipeParameters,
)


def _signal(
    title: str,
    amplitude: float,
    shot: int,
    *,
    noise: float = 0.1,
) -> SignalObj:
    """Build one explicit input signal with a stable campaign shot number."""
    x = np.linspace(0.0, 10.0, 101)
    noise_values = np.where(np.arange(x.size) % 2 == 0, noise, -noise)
    y = noise_values + amplitude * ((x >= 3.0) & (x <= 7.0))
    signal = create_signal(
        title,
        x,
        y,
        units=("us", "V"),
        labels=("Time", "Voltage"),
    )
    signal.metadata[SHOT_METADATA_KEY] = shot
    return signal


def test_campaign_recipe_builds_anchored_table_and_diagnostics() -> None:
    """The recipe preserves shot identity and attaches its table to the anchor."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False
    parameters.minimum_amplitude = 1.0
    parameters.minimum_snr_db = 20.0
    progress: list[tuple[float, str | None]] = []
    context = RecipeExecutionContext(
        progress_callback=lambda value, message: progress.append((value, message))
    )

    outcome = PULSE_CAMPAIGN_RECIPE.run(
        {"signals": (_signal("Strong", 4.0, 10), _signal("Weak", 0.2, 20))},
        parameters,
        context,
    )

    assert len(outcome.objects) == 1
    anchor_output = outcome.objects[0]
    assert anchor_output.id == "amplitude_vs_shot"
    assert isinstance(anchor_output.value, SignalObj)
    np.testing.assert_array_equal(anchor_output.value.x, (10.0, 20.0))
    assert anchor_output.value.y[0] > anchor_output.value.y[1]
    assert anchor_output.value.xunit == "shot"
    assert anchor_output.value.yunit == "V"
    assert anchor_output.value.metadata[OUTPUT_ROLE_METADATA_KEY] == (
        "amplitude_vs_shot"
    )

    assert len(outcome.results) == 1
    table_output = outcome.results[0]
    assert table_output.id == "shot_metrics"
    assert table_output.anchor_id == "amplitude_vs_shot"
    assert isinstance(table_output.value, TableResult)
    assert [row[0] for row in table_output.value.data] == [10, 20]
    assert [row[2] for row in table_output.value.data] == [
        PulseStatus.VALID.value,
        PulseStatus.NO_PULSE.value,
    ]
    assert [row[4] for row in table_output.value.data] == ["square", "square"]
    assert table_output.value.attrs["normative"] is False
    assert (
        "polarity * (raw signal - raw baseline mean)"
        in (table_output.value.attrs["integral_convention"])
    )
    assert "20*log10" in table_output.value.attrs["snr_convention"]

    assert len(outcome.diagnostics) == 1
    diagnostic = outcome.diagnostics[0]
    assert diagnostic.code == "no_pulse"
    assert diagnostic.details["shot"] == 20
    assert diagnostic.details["minimum_amplitude"] == 1.0
    assert progress == [
        (0.0, "Preparing pulse campaign"),
        (0.375, "Analyzed pulse 1/2"),
        (0.75, "Analyzed pulse 2/2"),
        (0.8, "Building pulse campaign outputs"),
        (1.0, "Pulse campaign analysis complete"),
    ]


def test_campaign_recipe_descriptor_declares_many_signal_inputs() -> None:
    """The registry exposes the stable single-channel batch contract."""
    assert PULSE_CAMPAIGN_RECIPE.recipe_id.endswith(":single-channel-campaign")
    assert PULSE_CAMPAIGN_RECIPE.version == "1.0.0"
    assert len(PULSE_CAMPAIGN_RECIPE.inputs) == 1
    assert PULSE_CAMPAIGN_RECIPE.inputs[0].id == "signals"
    assert PULSE_CAMPAIGN_RECIPE.parameter_class is PulseCampaignRecipeParameters


def test_campaign_recipe_uses_automatic_ranges_by_default() -> None:
    """The default recipe delegates baseline range detection to Sigima."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.denoise = False

    outcome = PULSE_CAMPAIGN_RECIPE.run(
        {"signals": (_signal("Automatic", 4.0, 1),)},
        parameters,
        RecipeExecutionContext(),
    )

    row = outcome.results[0].value.data[0]
    assert row[2] == PulseStatus.VALID.value
    assert row[4] == SignalShape.SQUARE.value
    assert row[11] is not None
    assert row[13] is not None
    assert row[16] is not None
    json.dumps(outcome.results[0].value.to_dict(), allow_nan=False)


def test_campaign_recipe_rejects_duplicate_shot_metadata() -> None:
    """Stable shot identity cannot be silently collapsed in batch outputs."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False

    with pytest.raises(RecipeValidationError, match="shot indices must be unique"):
        PULSE_CAMPAIGN_RECIPE.run(
            {"signals": (_signal("First", 4.0, 10), _signal("Second", 4.0, 10))},
            parameters,
            RecipeExecutionContext(),
        )


def test_campaign_recipe_outputs_strict_json_for_infinite_core_snr() -> None:
    """Workflow serialization maps mathematical infinities to JSON null."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False
    parameters.detect_saturation = True
    parameters.saturation_min = -1.0
    parameters.saturation_max = 4.0

    outcome = PULSE_CAMPAIGN_RECIPE.run(
        {"signals": (_signal("Noiseless", 4.0, 1, noise=0.0),)},
        parameters,
        RecipeExecutionContext(),
    )

    table = outcome.results[0].value
    assert table.data[0][10] is None
    json.dumps(table.to_dict(), allow_nan=False)
    assert outcome.diagnostics[0].code == "saturated"
    json.dumps(dict(outcome.diagnostics[0].details), allow_nan=False)


def test_campaign_recipe_keeps_flat_missing_pulse_in_outputs() -> None:
    """One unextractable flat shot does not abort the remaining campaign."""
    missing = _signal("Missing", 0.0, 1, noise=0.0)
    strong = _signal("Strong", 4.0, 2)
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False
    parameters.minimum_amplitude = 1.0

    outcome = PULSE_CAMPAIGN_RECIPE.run(
        {"signals": (missing, strong)},
        parameters,
        RecipeExecutionContext(),
    )

    np.testing.assert_allclose(
        outcome.objects[0].value.y,
        (0.0, 4.0),
        atol=0.02,
    )
    assert [row[2] for row in outcome.results[0].value.data] == [
        PulseStatus.NO_PULSE.value,
        PulseStatus.VALID.value,
    ]
    assert outcome.results[0].value.data[0][4] is None
    json.dumps(outcome.results[0].value.to_dict(), allow_nan=False)


def test_campaign_recipe_honors_cancellation_between_shots() -> None:
    """The SDK context stops a batch after the current independent shot."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False
    cancelled = False
    progress: list[tuple[float, str | None]] = []

    def report(value: float, message: str | None) -> None:
        nonlocal cancelled
        progress.append((value, message))
        if message == "Analyzed pulse 1/3":
            cancelled = True

    context = RecipeExecutionContext(
        progress_callback=report,
        cancellation_callback=lambda: cancelled,
    )

    with pytest.raises(RecipeCancellationError):
        PULSE_CAMPAIGN_RECIPE.run(
            {
                "signals": tuple(
                    _signal(f"Shot {index}", 4.0, index) for index in range(1, 4)
                )
            },
            parameters,
            context,
        )

    assert progress == [
        (0.0, "Preparing pulse campaign"),
        (0.25, "Analyzed pulse 1/3"),
    ]
