"""Host-neutral demonstration campaign shared by the Desktop and Web adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from datalab.plugin_examples import PluginExample, PluginExampleData
from datalab.recipes import RecipeValidationError
from sigima.objects import SignalObj, create_signal

from .core import (
    PulseAcquisition,
    PulseAnalysisParameters,
    PulseProfile,
    PulseSimulationParameters,
    simulate_pulse_campaign,
    simulate_spectrum_events,
    simulate_step_campaign,
    simulate_two_channel_campaign,
)
from .workflow import (
    CHANNEL_METADATA_KEY,
    PULSE_CAMPAIGN_RECIPE,
    PULSE_HEIGHT_RECIPE,
    PULSE_STABILITY_RECIPE,
    SHOT_METADATA_KEY,
    STEP_RESPONSE_RECIPE,
    TWO_CHANNEL_DELAY_RECIPE,
    PulseCampaignRecipeParameters,
)

PULSE_DEMO = PluginExample(
    id="demo",
    title="Synthetic pulse campaign",
    description="Deterministic 500-shot campaign with explainable quality cases.",
    recipe_ids=(PULSE_CAMPAIGN_RECIPE.recipe_id,),
)
STABILITY_DEMO = PluginExample(
    id="stability-demo",
    title="Synthetic laser warm-up campaign",
    description=(
        "600 pulses with a slow timing drift, an amplitude drift and timing "
        "jitter rising from 15 ns to 50 ns after shot 400."
    ),
    # One Gaussian profile: pulse features also compare from shot to shot
    recipe_ids=(PULSE_STABILITY_RECIPE.recipe_id, PULSE_CAMPAIGN_RECIPE.recipe_id),
)
STEP_RESPONSE_DEMO = PluginExample(
    id="step-response-demo",
    title="Synthetic amplifier step response",
    description=(
        "64 steps of an 80 MHz, 0.35-damped second-order amplifier seen "
        "through a 0.7 ns oscilloscope."
    ),
    recipe_ids=(STEP_RESPONSE_RECIPE.recipe_id,),
)
TWO_CHANNEL_DEMO = PluginExample(
    id="two-channel-demo",
    title="Synthetic two-channel delay campaign",
    description=(
        "300 reference and detector pulses 37.5 ns apart, with 1 ns common "
        "trigger jitter, 0.2 ns detector jitter and missing detector shots."
    ),
    recipe_ids=(TWO_CHANNEL_DELAY_RECIPE.recipe_id,),
)
SPECTRUM_DEMO = PluginExample(
    id="spectrum-demo",
    title="Synthetic NaI(Tl) gamma spectrum",
    description=(
        "2,500 triggered scintillation events from Cs-137 and Co-60 sources, "
        "with Compton scattering, pile-up and saturating cosmic rays."
    ),
    recipe_ids=(PULSE_HEIGHT_RECIPE.recipe_id,),
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


def _signals(
    acquisitions: Sequence[PulseAcquisition],
    units: tuple[str, str],
    channel: str | None = None,
) -> list[SignalObj]:
    """Convert acquisitions to signals carrying shot and channel metadata."""
    signals: list[SignalObj] = []
    for acquisition in acquisitions:
        signal = create_signal(
            acquisition.title, acquisition.x, acquisition.y, units=units
        )
        signal.metadata[SHOT_METADATA_KEY] = acquisition.shot_index
        if channel is not None:
            signal.metadata[CHANNEL_METADATA_KEY] = channel
        signals.append(signal)
    return signals


def build_stability_campaign() -> PluginExampleData:
    """Build a laser warm-up campaign with drifts and a jitter increase."""
    simulation = simulate_pulse_campaign(
        PulseSimulationParameters(
            shot_count=600,
            sample_count=301,
            amplitude_drift_fraction=0.05,
            profiles=(PulseProfile.GAUSSIAN,),
            white_noise_std=0.02,
            timing_jitter_std=0.015,
            late_timing_jitter_std=0.05,
            jitter_transition_shot=400,
            timing_drift=0.06,
            missing_shots=(150, 480),
            low_snr_shots=(),
            saturated_shots=(),
            multiple_pulse_shots=(),
            outlier_shots=(),
            seed=20261009,
        )
    )
    values = _analysis_parameter_values(simulation.analysis_parameters)
    return PluginExampleData(
        tuple(_signals(simulation.acquisitions, ("us", "V"))),
        {
            PULSE_STABILITY_RECIPE.recipe_id: values,
            PULSE_CAMPAIGN_RECIPE.recipe_id: values,
        },
    )


def build_step_response_campaign() -> PluginExampleData:
    """Build repeated steps of an underdamped amplifier."""
    simulation = simulate_step_campaign()
    start = simulation.analysis_parameters.start_range
    end = simulation.analysis_parameters.end_range
    return PluginExampleData(
        tuple(_signals(simulation.acquisitions, ("ns", "V"))),
        {
            STEP_RESPONSE_RECIPE.recipe_id: {
                "use_explicit_ranges": True,
                "xstartmin": start[0],
                "xstartmax": start[1],
                "xendmin": end[0],
                "xendmax": end[1],
                "instrument_rise_time": simulation.parameters.instrument_rise_time,
            }
        },
    )


def build_two_channel_campaign() -> PluginExampleData:
    """Build a reference channel and a delayed detector channel."""
    simulation = simulate_two_channel_campaign()
    signals = _signals(simulation.reference, ("ns", "V"), "CH1") + _signals(
        simulation.measured, ("ns", "V"), "CH2"
    )
    parameter_values = _analysis_parameter_values(simulation.analysis_parameters)
    return PluginExampleData(
        tuple(signals),
        {
            TWO_CHANNEL_DELAY_RECIPE.recipe_id: {
                name: value
                for name, value in parameter_values.items()
                if value is not None
            }
        },
    )


def build_spectrum_campaign() -> PluginExampleData:
    """Build triggered scintillation events from calibration sources."""
    simulation = simulate_spectrum_events()
    level = simulation.parameters.saturation_level
    return PluginExampleData(
        tuple(_signals(simulation.acquisitions, ("us", "V"))),
        {
            PULSE_HEIGHT_RECIPE.recipe_id: {
                "pretrigger_fraction": 0.14,
                "integration_gate": 1.2,
                "detect_saturation": True,
                "saturation_min": -level,
                "saturation_max": level,
            }
        },
    )


def _build_campaign_demo() -> PluginExampleData:
    """Wrap the original campaign demonstration as example data."""
    signals, parameter_values = build_simulated_campaign()
    return PluginExampleData(
        signals, {PULSE_CAMPAIGN_RECIPE.recipe_id: parameter_values}
    )


GENERATED_EXAMPLES: Mapping[str, Callable[[], PluginExampleData]] = {
    PULSE_DEMO.id: _build_campaign_demo,
    STABILITY_DEMO.id: build_stability_campaign,
    STEP_RESPONSE_DEMO.id: build_step_response_campaign,
    TWO_CHANNEL_DEMO.id: build_two_channel_campaign,
    SPECTRUM_DEMO.id: build_spectrum_campaign,
}
EXAMPLES: tuple[PluginExample, ...] = (
    PULSE_DEMO,
    STABILITY_DEMO,
    STEP_RESPONSE_DEMO,
    TWO_CHANNEL_DEMO,
    SPECTRUM_DEMO,
)


def materialize_generated_example(example_id: str) -> PluginExampleData | None:
    """Return generated example data, or ``None`` for an unknown example."""
    builder = GENERATED_EXAMPLES.get(example_id)
    return None if builder is None else builder()


__all__ = [
    "EXAMPLES",
    "GENERATED_EXAMPLES",
    "PULSE_DEMO",
    "SPECTRUM_DEMO",
    "STABILITY_DEMO",
    "STEP_RESPONSE_DEMO",
    "TWO_CHANNEL_DEMO",
    "apply_parameter_values",
    "build_simulated_campaign",
    "materialize_generated_example",
]
