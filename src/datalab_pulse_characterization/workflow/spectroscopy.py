"""Headless pulse-height spectroscopy recipe."""

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
from sigima.objects import NO_ROI, TableResult

from ..core import (
    EnergyEstimator,
    EventStatus,
    PulseHeightParameters,
    PulseHeightSpectrumResult,
    analyze_pulse_height_spectrum,
)
from .campaign import _acquisitions, _metric
from .outputs import metrics_table, signal_output


class PulseHeightRecipeParameters(gds.DataSet):
    """Parameters for pulse-height (energy) spectroscopy."""

    energy_estimator = gds.ChoiceItem(
        "Energy estimator",
        [("charge", "Charge (pulse integral)"), ("peak", "Peak height")],
        default="charge",
    )
    pretrigger_fraction = gds.FloatItem(
        "Pre-trigger baseline fraction",
        default=0.1,
        min=1e-3,
        max=0.49,
    )
    integration_gate = gds.FloatItem(
        "Charge integration gate (X units, 0 = to record end)",
        default=0.0,
        min=0.0,
    )
    detection_threshold_sigma = gds.FloatItem(
        "Detection threshold (baseline noise RMS)",
        default=5.0,
        min=1e-3,
    )
    pileup_prominence_ratio = gds.FloatItem(
        "Pile-up prominence ratio",
        default=0.1,
        min=1e-3,
        max=1.0,
    )
    detect_saturation = gds.BoolItem("Detect digitizer saturation", default=False)
    saturation_min = gds.FloatItem("Digitizer minimum", default=-1.0)
    saturation_max = gds.FloatItem("Digitizer maximum", default=1.0)
    minimum_saturated_samples = gds.IntItem(
        "Minimum saturated samples",
        default=2,
        min=1,
    )
    bin_count = gds.IntItem("Spectrum bins", default=256, min=16)
    smoothing_bins = gds.FloatItem(
        "Peak-search smoothing (bins)",
        default=1.5,
        min=1e-3,
    )
    line_energies = gds.StringItem(
        "Calibration line energies (keV, comma-separated)",
        default="661.657, 1173.228, 1332.492",
    )

    def to_core_parameters(self) -> PulseHeightParameters:
        """Return host-independent spectroscopy parameters."""
        try:
            energies = tuple(
                float(value) for value in str(self.line_energies).split(",") if value
            )
        except ValueError as error:
            raise RecipeValidationError(
                "Calibration line energies must be comma-separated numbers"
            ) from error
        detect = bool(self.detect_saturation)
        return PulseHeightParameters(
            energy_estimator=self.energy_estimator,
            pretrigger_fraction=float(self.pretrigger_fraction),
            integration_gate=float(self.integration_gate),
            detection_threshold_sigma=float(self.detection_threshold_sigma),
            pileup_prominence_ratio=float(self.pileup_prominence_ratio),
            saturation_min=float(self.saturation_min) if detect else None,
            saturation_max=float(self.saturation_max) if detect else None,
            minimum_saturated_samples=int(self.minimum_saturated_samples),
            bin_count=int(self.bin_count),
            smoothing_bins=float(self.smoothing_bins),
            line_energies=energies,
        )


def _summary(result: PulseHeightSpectrumResult, estimator_unit: str) -> TableResult:
    """Build the spectrum summary table."""
    rows: list[tuple[str, object, str]] = [
        ("Events", len(result.events), ""),
        *(
            (
                f"{status.value.replace('_', ' ').capitalize()} events",
                result.count(status),
                "",
            )
            for status in EventStatus
        ),
        ("Calibration gain", result.calibration_gain, f"keV/({estimator_unit})"),
        ("Calibration offset", result.calibration_offset, "keV"),
        ("Resolution scaling exponent", result.resolution_exponent, ""),
    ]
    return metrics_table(
        "Pulse-height spectrum summary",
        "pulse_height_spectrum",
        rows,
        {
            "measurement_domain": "pulse_height_spectroscopy",
            "energy_estimator": result.estimator.value,
            "resolution_convention": "FWHM / E of a Gaussian on a linear background",
            "statistical_exponent": -0.5,
        },
    )


def _peak_table(result: PulseHeightSpectrumResult) -> TableResult:
    """Build the calibration-line table."""
    rows = []
    for peak in result.peaks:
        calibrated = result.calibration_gain * peak.centroid + result.calibration_offset
        rows.append(
            [
                peak.energy,
                _metric(peak.centroid),
                _metric(calibrated),
                _metric(calibrated - peak.energy),
                _metric(result.calibration_gain * peak.fwhm),
                _metric(peak.resolution_percent),
                _metric(peak.net_counts),
            ]
        )
    return TableResult(
        title="Calibration photopeaks",
        kind="pulse_height_peaks",
        headers=[
            "Line energy (keV)",
            "Centroid",
            "Calibrated centroid (keV)",
            "Calibration residual (keV)",
            "FWHM (keV)",
            "Resolution (%)",
            "Net counts",
        ],
        data=rows,
        roi_indices=[NO_ROI] * len(rows),
        attrs={"normative": False},
    )


def run_pulse_height_spectrum(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Build an energy spectrum from triggered events and calibrate it."""
    if not isinstance(parameters, PulseHeightRecipeParameters):
        raise RecipeValidationError(
            "Pulse-height spectroscopy requires PulseHeightRecipeParameters"
        )
    context.raise_if_cancelled()
    context.report_progress(0.0, "Preparing triggered events")
    acquisitions = _acquisitions(inputs.get("signals"))

    def report_event_progress(completed: int, total: int) -> None:
        """Bridge core event progress to the recipe execution context."""
        context.report_progress(0.8 * completed / total, f"Analyzed event {completed}")
        context.raise_if_cancelled()

    try:
        result = analyze_pulse_height_spectrum(
            acquisitions,
            parameters.to_core_parameters(),
            progress_callback=report_event_progress,
        )
    except ValueError as error:
        raise RecipeValidationError(str(error)) from error
    context.report_progress(0.9, "Building spectrum outputs")
    context.raise_if_cancelled()

    first = inputs["signals"][0]
    x_unit, y_unit = first.xunit or "", first.yunit or ""
    estimator_unit = (
        f"{y_unit}.{x_unit}" if result.estimator is EnergyEstimator.CHARGE else y_unit
    )
    energies = np.array([peak.energy for peak in result.peaks])
    objects = (
        RecipeObjectOutput(
            "raw_spectrum",
            signal_output(
                "Pulse-height spectrum",
                result.bin_centers,
                result.counts,
                "raw_spectrum",
                units=(estimator_unit, "counts"),
                labels=(result.estimator.value.capitalize(), "Counts"),
            ),
        ),
        RecipeObjectOutput(
            "energy_spectrum",
            signal_output(
                "Calibrated energy spectrum",
                result.calibrated_centers,
                result.counts,
                "energy_spectrum",
                units=("keV", "counts"),
                labels=("Energy", "Counts"),
            ),
        ),
        RecipeObjectOutput(
            "calibration_curve",
            signal_output(
                "Energy calibration points",
                np.array([peak.centroid for peak in result.peaks]),
                energies,
                "calibration_curve",
                units=(estimator_unit, "keV"),
                labels=(result.estimator.value.capitalize(), "Line energy"),
            ),
        ),
        RecipeObjectOutput(
            "resolution_vs_energy",
            signal_output(
                "Energy resolution vs energy",
                energies,
                np.array([peak.resolution_percent for peak in result.peaks]),
                "resolution_vs_energy",
                units=("keV", "%"),
                labels=("Energy", "FWHM / E"),
            ),
        ),
    )
    rejected = len(result.events) - result.count(EventStatus.ACCEPTED)
    diagnostics = (
        (
            RecipeDiagnostic(
                level=RecipeDiagnosticLevel.INFO,
                code="rejected_events",
                message=f"{rejected} events were not included in the spectrum",
                details={
                    status.value: result.count(status)
                    for status in EventStatus
                    if status is not EventStatus.ACCEPTED
                },
            ),
        )
        if rejected
        else ()
    )
    context.report_progress(1.0, "Pulse-height spectroscopy complete")
    return RecipeOutcome(
        objects=objects,
        results=(
            RecipeResultOutput(
                "spectrum_summary",
                _summary(result, estimator_unit),
                anchor_id="raw_spectrum",
            ),
            RecipeResultOutput(
                "calibration_peaks",
                _peak_table(result),
                anchor_id="raw_spectrum",
            ),
        ),
        diagnostics=diagnostics,
    )


__all__ = ["PulseHeightRecipeParameters", "run_pulse_height_spectrum"]
