"""Headless shot-to-shot stability recipe."""

from __future__ import annotations

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
from sigima.tools.signal import pulse as sigima_pulse

from ..core import (
    PulseStabilityParameters,
    PulseStabilityResult,
    PulseStatus,
    analyze_pulse_campaign,
    analyze_pulse_stability,
)
from .campaign import PulseCampaignRecipeParameters, _acquisitions
from .outputs import histogram, metrics_table, signal_output


class PulseStabilityRecipeParameters(PulseCampaignRecipeParameters):
    """Parameters for shot-to-shot timing and amplitude stability."""

    rolling_window = gds.IntItem("Rolling jitter window (shots)", default=25, min=3)
    detect_regime_change = gds.BoolItem("Detect a jitter regime change", default=True)
    minimum_segment_shots = gds.IntItem("Minimum shots per regime", default=30, min=5)
    regime_change_threshold = gds.FloatItem(
        "Regime-change log-likelihood threshold",
        default=25.0,
        min=1e-3,
    )
    histogram_bin_count = gds.IntItem(
        "Arrival-time histogram bins",
        default=40,
        min=4,
    )

    def to_stability_parameters(self) -> PulseStabilityParameters:
        """Return host-independent stability parameters."""
        return PulseStabilityParameters(
            rolling_window=int(self.rolling_window),
            detect_regime_change=bool(self.detect_regime_change),
            minimum_segment_shots=int(self.minimum_segment_shots),
            regime_change_threshold=float(self.regime_change_threshold),
        )


def _adev_minimum(adev) -> tuple[float, float]:
    """Return the minimum Allan deviation and its averaging length."""
    index = int(np.nanargmin(adev.deviation))
    return float(adev.deviation[index]), float(adev.tau_shots[index])


def _metrics(result: PulseStabilityResult, x_unit: str, y_unit: str):
    """Build the stability summary table."""
    adev_min, adev_tau = _adev_minimum(result.arrival_time_adev)
    rows: list[tuple[str, object, str]] = [
        ("Valid shots", int(result.shot_indices.size), "shot"),
        ("Excluded shots", result.excluded_shot_count, "shot"),
        ("RMS timing jitter", result.rms_jitter, x_unit),
        ("Peak-to-peak timing jitter", result.peak_to_peak_jitter, x_unit),
        ("Timing drift", 100.0 * result.timing_drift_per_shot, f"{x_unit}/100 shots"),
        ("Detrended RMS timing jitter", result.detrended_rms_jitter, x_unit),
        ("Mean amplitude", result.amplitude_mean, y_unit),
        ("Relative amplitude RMS", 100.0 * result.amplitude_relative_std, "%"),
        (
            "Relative amplitude peak-to-peak",
            100.0 * result.amplitude_relative_peak_to_peak,
            "%",
        ),
        (
            "Relative amplitude drift",
            1e4 * result.amplitude_drift_per_shot / result.amplitude_mean,
            "%/100 shots",
        ),
        ("Relative integral (energy) RMS", 100.0 * result.integral_relative_std, "%"),
        (
            "Timing Allan deviation (1 shot)",
            float(result.arrival_time_adev.deviation[0]),
            x_unit,
        ),
        ("Minimum timing Allan deviation", adev_min, x_unit),
        ("Optimal averaging length", adev_tau, "shot"),
    ]
    change = result.regime_change
    if change is None:
        rows.append(("Jitter regime change", "Not detected", ""))
    else:
        rows.extend(
            [
                ("Jitter regime change at shot", change.shot_index, "shot"),
                ("Jitter before change", change.jitter_before, x_unit),
                ("Jitter after change", change.jitter_after, x_unit),
                ("Change log-likelihood ratio", change.log_likelihood_ratio, ""),
            ]
        )
    return metrics_table(
        "Pulse stability metrics",
        "pulse_stability",
        rows,
        {
            "measurement_domain": "shot_to_shot_stability",
            "arrival_time_convention": "50 % crossing relative to the trigger",
            "allan_deviation": "overlapping, octave averaging lengths in shots",
        },
    )


def run_pulse_stability(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Analyze timing jitter, drifts and amplitude stability of a campaign."""
    if not isinstance(parameters, PulseStabilityRecipeParameters):
        raise RecipeValidationError(
            "Pulse stability requires PulseStabilityRecipeParameters"
        )
    context.raise_if_cancelled()
    context.report_progress(0.0, "Preparing pulse campaign")
    acquisitions = _acquisitions(inputs.get("signals"))

    def report_shot_progress(completed: int, total: int) -> None:
        """Bridge core shot progress to the recipe execution context."""
        context.report_progress(0.8 * completed / total, f"Analyzed pulse {completed}")
        context.raise_if_cancelled()

    try:
        campaign = analyze_pulse_campaign(
            acquisitions,
            parameters.to_core_parameters(),
            progress_callback=report_shot_progress,
        )
        result = analyze_pulse_stability(campaign, parameters.to_stability_parameters())
    except (TypeError, ValueError, sigima_pulse.PulseAnalysisError) as error:
        raise RecipeValidationError(str(error)) from error
    context.report_progress(0.9, "Building stability outputs")
    context.raise_if_cancelled()

    first = inputs["signals"][0]
    x_unit, y_unit = first.xunit or "", first.yunit or ""
    shots = result.shot_indices
    rolling = np.isfinite(result.rolling_jitter)
    centers, counts = histogram(
        result.detrended_arrival_times, int(parameters.histogram_bin_count)
    )
    objects = (
        RecipeObjectOutput(
            "arrival_time_vs_shot",
            signal_output(
                "Arrival time vs shot",
                shots,
                result.arrival_times,
                "arrival_time_vs_shot",
                units=("shot", x_unit),
                labels=("Shot", "50% arrival time"),
            ),
        ),
        RecipeObjectOutput(
            "amplitude_vs_shot",
            signal_output(
                "Amplitude vs shot",
                shots,
                result.amplitudes,
                "amplitude_vs_shot",
                units=("shot", y_unit),
                labels=("Shot", "Amplitude"),
            ),
        ),
        RecipeObjectOutput(
            "integral_vs_shot",
            signal_output(
                "Pulse integral vs shot",
                shots,
                result.integrals,
                "integral_vs_shot",
                units=("shot", f"{y_unit}.{x_unit}"),
                labels=("Shot", "Integral"),
            ),
        ),
        RecipeObjectOutput(
            "rolling_jitter",
            signal_output(
                "Rolling timing jitter",
                shots[rolling],
                result.rolling_jitter[rolling],
                "rolling_jitter",
                units=("shot", x_unit),
                labels=("Shot", "Detrended RMS jitter"),
            ),
        ),
        RecipeObjectOutput(
            "arrival_time_adev",
            signal_output(
                "Timing Allan deviation",
                result.arrival_time_adev.tau_shots,
                result.arrival_time_adev.deviation,
                "arrival_time_adev",
                units=("shot", x_unit),
                labels=("Averaging length", "Allan deviation"),
            ),
        ),
        RecipeObjectOutput(
            "amplitude_adev",
            signal_output(
                "Relative amplitude Allan deviation",
                result.amplitude_adev.tau_shots,
                result.amplitude_adev.deviation,
                "amplitude_adev",
                units=("shot", ""),
                labels=("Averaging length", "Relative Allan deviation"),
            ),
        ),
        RecipeObjectOutput(
            "arrival_time_distribution",
            signal_output(
                "Detrended arrival-time distribution",
                centers,
                counts,
                "arrival_time_distribution",
                units=(x_unit, ""),
                labels=("Arrival-time deviation", "Shot count"),
            ),
        ),
    )
    excluded = [shot for shot in campaign.shots if shot.status is not PulseStatus.VALID]
    diagnostics = (
        (
            RecipeDiagnostic(
                level=RecipeDiagnosticLevel.WARNING,
                code="excluded_shots",
                message=f"{len(excluded)} non-valid shots were excluded",
                details={
                    "shots": [shot.shot_index for shot in excluded],
                    "statuses": [shot.status.value for shot in excluded],
                },
            ),
        )
        if excluded
        else ()
    )
    context.report_progress(1.0, "Pulse stability analysis complete")
    return RecipeOutcome(
        objects=objects,
        results=(
            RecipeResultOutput(
                "stability_metrics",
                _metrics(result, x_unit, y_unit),
                anchor_id="arrival_time_vs_shot",
            ),
        ),
        diagnostics=diagnostics,
    )


__all__ = ["PulseStabilityRecipeParameters", "run_pulse_stability"]
