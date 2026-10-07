"""Headless IEEE 181-inspired step-response recipe."""

from __future__ import annotations

import math

import guidata.dataset as gds
import numpy as np
from datalab.recipes import (
    RecipeDiagnostic,
    RecipeDiagnosticLevel,
    RecipeExecutionContext,
    RecipeInputs,
    RecipeObjectOutput,
    RecipeOutcome,
    RecipeResultOutput,
    RecipeValidationError,
)
from sigima.enums import SignalShape
from sigima.tools.signal import pulse as sigima_pulse

from ..core import (
    PulseAnalysisParameters,
    PulseStatus,
    StepResponseParameters,
    StepResponseResult,
    align_pulse_campaign,
    analyze_pulse_campaign,
    analyze_step_response,
    second_order_step,
)
from .campaign import _acquisitions
from .outputs import frequency, metrics_table, signal_output


class StepResponseRecipeParameters(gds.DataSet):
    """Parameters for step-response (transition and ringing) analysis."""

    use_explicit_ranges = gds.BoolItem(
        "Use explicit baseline and plateau ranges",
        default=False,
    )
    xstartmin = gds.FloatItem("Baseline minimum", default=0.0)
    xstartmax = gds.FloatItem("Baseline maximum", default=0.0)
    xendmin = gds.FloatItem("Final plateau minimum", default=1.0)
    xendmax = gds.FloatItem("Final plateau maximum", default=1.0)
    baseline_fraction = gds.FloatItem(
        "Automatic baseline fraction",
        default=0.1,
        min=1e-3,
        max=0.5,
    )
    minimum_snr_db = gds.FloatItem("Minimum SNR per shot (dB)", default=20.0)
    lower_ratio = gds.FloatItem("Lower reference level", default=0.1, min=0.01)
    upper_ratio = gds.FloatItem("Upper reference level", default=0.9, max=0.99)
    settling_tolerance_percent = gds.FloatItem(
        "Settling tolerance (% of amplitude)",
        default=2.0,
        min=0.01,
        max=49.0,
    )
    histogram_bin_count = gds.IntItem("State-level histogram bins", default=200, min=10)
    instrument_rise_time = gds.FloatItem(
        "Instrument rise time (X units, 0 disables correction)",
        default=0.0,
        min=0.0,
    )
    ringing_noise_factor = gds.FloatItem(
        "Ringing detection threshold (noise RMS)",
        default=4.0,
        min=1e-3,
    )

    def to_analysis_parameters(self) -> PulseAnalysisParameters:
        """Return per-shot analysis parameters used to align the steps."""
        explicit = bool(self.use_explicit_ranges)
        return PulseAnalysisParameters(
            start_range=(
                (float(self.xstartmin), float(self.xstartmax)) if explicit else None
            ),
            end_range=(float(self.xendmin), float(self.xendmax)) if explicit else None,
            signal_shape=SignalShape.STEP,
            start_ratio=float(self.lower_ratio),
            stop_ratio=float(self.upper_ratio),
            baseline_fraction=float(self.baseline_fraction),
            denoise=False,
            minimum_snr_db=float(self.minimum_snr_db),
        )

    def to_step_parameters(self) -> StepResponseParameters:
        """Return host-independent step-response parameters."""
        return StepResponseParameters(
            lower_ratio=float(self.lower_ratio),
            upper_ratio=float(self.upper_ratio),
            settling_tolerance=float(self.settling_tolerance_percent) / 100.0,
            histogram_bin_count=int(self.histogram_bin_count),
            instrument_rise_time=float(self.instrument_rise_time),
            ringing_noise_factor=float(self.ringing_noise_factor),
        )


def _model(x: np.ndarray, result: StepResponseResult) -> np.ndarray | None:
    """Return the equivalent second-order step aligned on the 50 % crossing."""
    if not (
        math.isfinite(result.natural_frequency) and math.isfinite(result.damping_ratio)
    ):
        return None
    period = 1.0 / result.natural_frequency
    tau = np.linspace(0.0, 2.0 * period, 4_001)
    unit = second_order_step(tau, result.natural_frequency, result.damping_ratio)
    tau50 = float(
        np.interp(0.5, unit[: int(np.argmax(unit))], tau[: int(np.argmax(unit))])
    )
    response = second_order_step(
        x - result.mid_crossing + tau50,
        result.natural_frequency,
        result.damping_ratio,
    )
    return result.low_level + result.polarity * result.amplitude * response


def _metrics(result: StepResponseResult, shots: int, x_unit: str, y_unit: str):
    """Build the step-response summary table."""
    fd, f_unit = frequency(result.damped_frequency, x_unit)
    fn, _unit = frequency(result.natural_frequency, x_unit)
    bw2, _unit = frequency(result.bandwidth_second_order, x_unit)
    bw1, _unit = frequency(result.bandwidth_single_pole, x_unit)
    rows: list[tuple[str, object, str]] = [
        ("Averaged shots", shots, "shot"),
        ("Low state level", result.low_level, y_unit),
        ("High state level", result.high_level, y_unit),
        ("Amplitude", result.amplitude, y_unit),
        ("Mean waveform noise RMS", result.noise_rms, y_unit),
        ("Rise time", result.rise_time, x_unit),
        ("Rise time corrected for instrument", result.corrected_rise_time, x_unit),
        ("Overshoot", result.overshoot_percent, "%"),
        ("Undershoot", result.undershoot_percent, "%"),
        ("Preshoot", result.preshoot_percent, "%"),
        ("Settling time", result.settling_time, x_unit),
        ("Damped ringing frequency", fd, f_unit),
        (
            "Damping ratio (logarithmic decrement)",
            result.damping_ratio_from_decrement,
            "",
        ),
        ("Damping ratio (overshoot)", result.damping_ratio_from_overshoot, ""),
        ("Natural frequency", fn, f_unit),
        ("Bandwidth (second-order model)", bw2, f_unit),
        ("Bandwidth (0.35 / rise time)", bw1, f_unit),
    ]
    return metrics_table(
        "Step-response metrics",
        "pulse_step_response",
        rows,
        {
            "measurement_domain": "step_response",
            "state_levels": "histogram mode (IEEE 181-inspired)",
            "settling_reference": "50 % crossing",
        },
    )


def run_step_response(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Average aligned step acquisitions and measure their response."""
    if not isinstance(parameters, StepResponseRecipeParameters):
        raise RecipeValidationError(
            "Step response requires StepResponseRecipeParameters"
        )
    context.raise_if_cancelled()
    context.report_progress(0.0, "Preparing step acquisitions")
    acquisitions = _acquisitions(inputs.get("signals"))

    def report_shot_progress(completed: int, total: int) -> None:
        """Bridge core shot progress to the recipe execution context."""
        context.report_progress(0.7 * completed / total, f"Analyzed step {completed}")
        context.raise_if_cancelled()

    try:
        analysis_parameters = parameters.to_analysis_parameters()
        campaign = analyze_pulse_campaign(
            acquisitions,
            analysis_parameters,
            progress_callback=report_shot_progress,
        )
        alignment = align_pulse_campaign(acquisitions, campaign)
        if not alignment.aligned_count:
            raise ValueError("No valid step could be aligned")
        mean = alignment.mean_acquisition(aligned=True)
        result = analyze_step_response(
            mean.x,
            mean.y,
            parameters.to_step_parameters(),
            baseline_stop=(
                None
                if analysis_parameters.start_range is None
                else analysis_parameters.start_range[1]
            ),
        )
    except (TypeError, ValueError, sigima_pulse.PulseAnalysisError) as error:
        raise RecipeValidationError(str(error)) from error
    context.report_progress(0.9, "Building step-response outputs")
    context.raise_if_cancelled()

    first = inputs["signals"][0]
    x_unit, y_unit = first.xunit or "", first.yunit or ""
    after = mean.x >= result.mid_crossing
    objects = [
        RecipeObjectOutput(
            "mean_step",
            signal_output(
                f"Aligned mean step ({alignment.aligned_count} shots)",
                mean.x,
                mean.y,
                "mean_step",
                units=(x_unit, y_unit),
                labels=(first.xlabel or "Time", first.ylabel or "Signal"),
            ),
        ),
        RecipeObjectOutput(
            "settling_error",
            signal_output(
                "Settling error",
                mean.x[after] - result.mid_crossing,
                100.0
                * np.abs(
                    result.polarity * mean.y[after]
                    - result.polarity * result.high_level
                )
                / result.amplitude,
                "settling_error",
                units=(x_unit, "%"),
                labels=("Time after 50% crossing", "Error to high level"),
            ),
        ),
    ]
    model = _model(mean.x, result)
    if model is not None:
        objects.append(
            RecipeObjectOutput(
                "second_order_model",
                signal_output(
                    "Equivalent second-order model",
                    mean.x,
                    model,
                    "second_order_model",
                    units=(x_unit, y_unit),
                    labels=(first.xlabel or "Time", "Model"),
                ),
            )
        )
    diagnostics: list[RecipeDiagnostic] = []
    excluded = [shot for shot in campaign.shots if shot.status is not PulseStatus.VALID]
    if excluded:
        diagnostics.append(
            RecipeDiagnostic(
                level=RecipeDiagnosticLevel.WARNING,
                code="excluded_shots",
                message=f"{len(excluded)} non-valid steps were not averaged",
                details={"shots": [shot.shot_index for shot in excluded]},
            )
        )
    if not math.isfinite(result.settling_time):
        diagnostics.append(
            RecipeDiagnostic(
                level=RecipeDiagnosticLevel.WARNING,
                code="not_settled",
                message="The step does not settle within the record",
            )
        )
    if not math.isfinite(result.damped_frequency):
        diagnostics.append(
            RecipeDiagnostic(
                level=RecipeDiagnosticLevel.INFO,
                code="no_ringing",
                message="No ringing above the noise threshold was found",
            )
        )
    context.report_progress(1.0, "Step-response analysis complete")
    return RecipeOutcome(
        objects=tuple(objects),
        results=(
            RecipeResultOutput(
                "step_metrics",
                _metrics(result, alignment.aligned_count, x_unit, y_unit),
                anchor_id="mean_step",
            ),
        ),
        diagnostics=tuple(diagnostics),
    )


__all__ = ["StepResponseRecipeParameters", "run_step_response"]
