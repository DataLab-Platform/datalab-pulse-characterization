"""Thin DataLab-Web adapter for the bundled Pulse workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from datalab.plugin_examples import PluginExample, PluginExampleData
from datalab.plugins import PluginBase, PluginCapability, PluginInfo
from datalab.recipes import (
    RecipeExecutionContext,
    RecipeInputs,
    RecipeOutcome,
    RecipeValidationError,
)
from sigima.objects import SignalObj, create_signal

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..core import PulseAnalysisParameters, simulate_pulse_campaign
from ..workflow import (
    PULSE_CAMPAIGN_RECIPE,
    SHOT_METADATA_KEY,
    PulseCampaignRecipeParameters,
)

WEB_STATUS = "verified"
DATALAB_WEB_VERSION = "0.8.0"
PYODIDE_VERSION = "0.26.4"

PULSE_DEMO = PluginExample(
    id="demo",
    title="Synthetic pulse campaign",
    description="Deterministic 500-shot campaign with explainable quality cases.",
    recipe_id=PULSE_CAMPAIGN_RECIPE.recipe_id,
)


class PulseTransientCharacterizationWebPlugin(PluginBase):
    """Declare the Pulse application contract supported by DataLab-Web."""

    PLUGIN_INFO = PluginInfo(
        id=PLUGIN_ID,
        name=PLUGIN_NAME,
        version=__version__,
        description=PLUGIN_DESCRIPTION,
        capabilities=(
            PluginCapability.APPLICATION,
            PluginCapability.PROCESSING,
        ),
        documentation_url=(
            "https://github.com/DataLab-Platform/datalab-pulse-characterization"
        ),
    )
    RECIPES = (PULSE_CAMPAIGN_RECIPE,)
    EXAMPLES = (PULSE_DEMO,)

    def create_actions(self) -> None:
        """Application actions are provided by DataLab-Web's generic host."""

    @classmethod
    def materialize_example(cls, example_id: str) -> PluginExampleData | None:
        """Build the deterministic browser qualification campaign."""
        cls.get_example(example_id)
        if example_id != PULSE_DEMO.id:
            return None
        signals, parameter_values = build_simulated_campaign()
        return PluginExampleData(signals, parameter_values)


def get_web_manifest() -> dict[str, str]:
    """Return the explicit browser bundle and compatibility contract."""
    return {
        "plugin_id": PLUGIN_ID,
        "plugin_version": __version__,
        "web_status": WEB_STATUS,
        "datalab_web_version": DATALAB_WEB_VERSION,
        "pyodide_version": PYODIDE_VERSION,
        "recipe_id": PULSE_CAMPAIGN_RECIPE.recipe_id,
        "recipe_version": PULSE_CAMPAIGN_RECIPE.version,
    }


def build_recipe_inputs(signals: Sequence[SignalObj]) -> RecipeInputs:
    """Map browser-selected signals to the shared campaign recipe slot."""
    signal_values = tuple(signals)
    if any(not isinstance(signal, SignalObj) for signal in signal_values):
        raise RecipeValidationError("Pulse Web inputs must be signal objects")
    if len(signal_values) < 2:
        raise RecipeValidationError("Pulse Web inputs require at least two signals")
    return {"signals": signal_values}


def _set_parameter_values(
    parameters: PulseCampaignRecipeParameters,
    parameter_values: Mapping[str, object],
) -> None:
    """Apply browser parameter values after validating every public name."""
    for name, value in parameter_values.items():
        if not isinstance(name, str) or not hasattr(parameters, name):
            raise RecipeValidationError(f"Unknown Pulse recipe parameter: {name!r}")
        setattr(parameters, name, value)


def run_pulse_campaign_recipe(
    signals: Sequence[SignalObj],
    parameter_values: Mapping[str, object] | None = None,
    context: RecipeExecutionContext | None = None,
) -> RecipeOutcome:
    """Run the shared recipe for browser-imported signals without GUI calls."""
    parameters = PulseCampaignRecipeParameters()
    _set_parameter_values(parameters, dict(parameter_values or {}))
    return PULSE_CAMPAIGN_RECIPE.run(
        build_recipe_inputs(signals),
        parameters,
        context or RecipeExecutionContext(),
    )


def _analysis_parameter_values(
    parameters: PulseAnalysisParameters,
) -> dict[str, object]:
    """Map simulator analysis settings to the public recipe DataSet."""
    start_range = parameters.start_range
    end_range = parameters.end_range
    if start_range is None or end_range is None:
        raise ValueError("Browser qualification requires explicit simulator ranges")
    return {
        "signal_shape": (
            None
            if parameters.signal_shape is None
            else str(parameters.signal_shape.value)
        ),
        "use_explicit_ranges": True,
        "xstartmin": start_range[0],
        "xstartmax": start_range[1],
        "xendmin": end_range[0],
        "xendmax": end_range[1],
        "start_ratio": parameters.start_ratio,
        "stop_ratio": parameters.stop_ratio,
        "baseline_fraction": parameters.baseline_fraction,
        "denoise": parameters.denoise,
        "minimum_amplitude": parameters.minimum_amplitude,
        "minimum_snr_db": parameters.minimum_snr_db,
        "detect_saturation": (
            parameters.saturation_min is not None
            and parameters.saturation_max is not None
        ),
        "saturation_min": parameters.saturation_min,
        "saturation_max": parameters.saturation_max,
        "saturation_tolerance": parameters.saturation_tolerance,
        "minimum_saturated_samples": parameters.minimum_saturated_samples,
        "multiple_pulse_threshold_ratio": (parameters.multiple_pulse_threshold_ratio),
        "minimum_pulse_samples": parameters.minimum_pulse_samples,
        "outlier_modified_zscore": parameters.outlier_modified_zscore,
        "minimum_outlier_shots": parameters.minimum_outlier_shots,
    }


def build_simulated_campaign() -> tuple[tuple[SignalObj, ...], dict[str, object]]:
    """Build the deterministic 500-shot browser qualification campaign."""
    simulation = simulate_pulse_campaign()
    signals: list[SignalObj] = []
    for acquisition in simulation.acquisitions:
        signal = create_signal(
            acquisition.title,
            acquisition.x,
            acquisition.y,
            units=("us", "V"),
        )
        signal.metadata[SHOT_METADATA_KEY] = acquisition.shot_index
        signals.append(signal)
    return tuple(signals), _analysis_parameter_values(simulation.analysis_parameters)


__all__ = [
    "DATALAB_WEB_VERSION",
    "PULSE_DEMO",
    "PYODIDE_VERSION",
    "PulseTransientCharacterizationWebPlugin",
    "WEB_STATUS",
    "build_recipe_inputs",
    "build_simulated_campaign",
    "get_web_manifest",
    "run_pulse_campaign_recipe",
]
