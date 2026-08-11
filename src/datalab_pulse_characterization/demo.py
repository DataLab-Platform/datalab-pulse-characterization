"""Host-neutral demonstration campaign shared by the Desktop and Web adapters."""

from __future__ import annotations

from collections.abc import Mapping

from datalab.plugin_examples import PluginExample
from datalab.recipes import RecipeValidationError
from sigima.objects import SignalObj, create_signal

from .core import PulseAnalysisParameters, simulate_pulse_campaign
from .workflow import (
    PULSE_CAMPAIGN_RECIPE,
    SHOT_METADATA_KEY,
    PulseCampaignRecipeParameters,
)

PULSE_DEMO = PluginExample(
    id="demo",
    title="Synthetic pulse campaign",
    description="Deterministic 500-shot campaign with explainable quality cases.",
    recipe_id=PULSE_CAMPAIGN_RECIPE.recipe_id,
)


def apply_parameter_values(
    parameters: PulseCampaignRecipeParameters,
    parameter_values: Mapping[str, object],
) -> None:
    """Apply recipe parameter values after validating every public name."""
    for name, value in parameter_values.items():
        if not isinstance(name, str) or not hasattr(parameters, name):
            raise RecipeValidationError(f"Unknown Pulse recipe parameter: {name!r}")
        setattr(parameters, name, value)


def _analysis_parameter_values(
    parameters: PulseAnalysisParameters,
) -> dict[str, object]:
    """Map simulator analysis settings to the public recipe DataSet."""
    start_range = parameters.start_range
    end_range = parameters.end_range
    if start_range is None or end_range is None:
        raise ValueError("The demo campaign requires explicit simulator ranges")
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
    """Build the deterministic 500-shot qualification campaign."""
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
    "PULSE_DEMO",
    "apply_parameter_values",
    "build_simulated_campaign",
]
