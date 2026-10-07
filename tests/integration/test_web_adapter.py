"""DataLab-Web adapter contract tests."""

from __future__ import annotations

import numpy as np
import pytest
from datalab.plugins import PluginCapability
from datalab.recipes import RecipeValidationError
from sigima.objects import create_signal

from datalab_pulse_characterization import PLUGIN_ID, __version__
from datalab_pulse_characterization.adapters.web import (
    PULSE_DEMO,
    WEB_STATUS,
    PulseTransientCharacterizationWebPlugin,
    build_recipe_inputs,
    get_web_manifest,
    run_pulse_campaign_recipe,
)
from datalab_pulse_characterization.core import metadata_key
from datalab_pulse_characterization.demo import EXAMPLES, TWO_CHANNEL_DEMO
from datalab_pulse_characterization.workflow import (
    CHANNEL_METADATA_KEY,
    PULSE_CAMPAIGN_RECIPE,
    RECIPES,
    TWO_CHANNEL_DELAY_RECIPE,
)


def _pulse(title: str, center: float):
    """Create one browser-imported square pulse."""
    x = np.linspace(0.0, 10.0, 101)
    y = 4.0 * ((x >= center) & (x <= center + 2.0))
    return create_signal(title, x, y)


def _parameters() -> dict[str, object]:
    """Return explicit recipe ranges for the square test pulses."""
    return {
        "signal_shape": "square",
        "use_explicit_ranges": True,
        "xstartmin": 0.0,
        "xstartmax": 1.0,
        "xendmin": 9.0,
        "xendmax": 10.0,
        "denoise": False,
    }


def test_web_adapter_declares_verified_version_matrix() -> None:
    """The qualified bundle declares its exact verified browser target."""
    assert WEB_STATUS == "verified"
    assert get_web_manifest() == {
        "plugin_id": PLUGIN_ID,
        "plugin_version": __version__,
        "web_status": "verified",
        "datalab_web_version": "0.9.0",
        "pyodide_version": "0.26.4",
        "recipes": [
            {"recipe_id": recipe.recipe_id, "recipe_version": recipe.version}
            for recipe in RECIPES
        ],
        "examples": [
            "demo",
            "stability-demo",
            "step-response-demo",
            "two-channel-demo",
            "spectrum-demo",
        ],
    }
    assert PulseTransientCharacterizationWebPlugin.get_plugin_id() == PLUGIN_ID
    assert PulseTransientCharacterizationWebPlugin.get_recipes() == RECIPES
    assert PulseTransientCharacterizationWebPlugin.get_examples() == EXAMPLES
    assert EXAMPLES[0] is PULSE_DEMO
    assert PluginCapability.APPLICATION in (
        PulseTransientCharacterizationWebPlugin.PLUGIN_INFO.capabilities
    )


def test_web_adapter_suggests_two_channel_roles_from_channel_labels() -> None:
    """Channel labels propose reference and measured slots; pairing uses shots."""
    data = PulseTransientCharacterizationWebPlugin.materialize_example(
        TWO_CHANNEL_DEMO.id
    )
    shot_key = metadata_key("shot")

    bindings = TWO_CHANNEL_DELAY_RECIPE.suggest_bindings(data.objects)

    assert {
        signal.metadata[CHANNEL_METADATA_KEY] for signal in bindings["reference"]
    } == {"CH1"}
    assert len(bindings["reference"]) == 300
    assert len(bindings["measured"]) == 297
    assert all(shot_key in signal.metadata for signal in data.objects)
    assert PULSE_CAMPAIGN_RECIPE.suggest_bindings is None


def test_web_adapter_maps_signals_and_runs_headless_recipe() -> None:
    """Browser-imported signals execute the same typed campaign recipe."""
    signals = (_pulse("Shot 1", 3.9), _pulse("Shot 2", 4.1))

    inputs = build_recipe_inputs(signals)
    outcome = run_pulse_campaign_recipe(signals, _parameters())

    assert inputs == {"signals": signals}
    assert [output.id for output in outcome.objects] == [
        "amplitude_vs_shot",
        "raw_mean",
        "aligned_mean",
    ]
    assert outcome.results[0].anchor_id == "amplitude_vs_shot"


def test_web_adapter_rejects_incomplete_or_unknown_inputs() -> None:
    """Browser validation fails before running an incomplete campaign."""
    with pytest.raises(RecipeValidationError, match="two signals"):
        build_recipe_inputs((_pulse("Shot 1", 4.0),))
    with pytest.raises(RecipeValidationError, match="Unknown Pulse"):
        run_pulse_campaign_recipe(
            (_pulse("Shot 1", 3.9), _pulse("Shot 2", 4.1)),
            {"not_a_parameter": 1},
        )


def test_web_adapter_builds_reproducible_qualification_campaign() -> None:
    """The browser gate uses the documented deterministic 500-shot scenario."""
    materialized = PulseTransientCharacterizationWebPlugin.materialize_example("demo")
    assert materialized is not None
    signals = materialized.objects
    parameters = materialized.values_for(PULSE_CAMPAIGN_RECIPE.recipe_id)

    assert len(signals) == 500
    assert signals[0].title == "Synthetic shot 001"
    assert signals[-1].title == "Synthetic shot 500"
    assert parameters["minimum_snr_db"] == 20.0
    assert parameters["minimum_outlier_shots"] == 20
