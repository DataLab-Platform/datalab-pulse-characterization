"""Headless single-channel pulse campaign recipe."""

from __future__ import annotations

import math
from numbers import Integral, Real

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
from sigima.objects import NO_ROI, SignalObj, TableResult, create_signal
from sigima.tools.signal import pulse as sigima_pulse

from ..core import (
    PulseAcquisition,
    PulseAlignmentRecord,
    PulseAnalysisParameters,
    PulseShotResult,
    PulseStatus,
    align_pulse_campaign,
    analyze_pulse_campaign,
    metadata_key,
)

SHOT_METADATA_KEY = metadata_key("shot")
OUTPUT_ROLE_METADATA_KEY = metadata_key("output_role")


class PulseCampaignRecipeParameters(gds.DataSet):
    """Parameters for a single-channel pulse campaign."""

    signal_shape = gds.ChoiceItem(
        "Signal shape",
        [(None, "Auto"), ("step", "Step"), ("square", "Square")],
        default=None,
    )
    use_explicit_ranges = gds.BoolItem("Use explicit X ranges", default=False)
    xstartmin = gds.FloatItem("Start baseline minimum", default=0.0)
    xstartmax = gds.FloatItem("Start baseline maximum", default=0.0)
    xendmin = gds.FloatItem("End range minimum", default=1.0)
    xendmax = gds.FloatItem("End range maximum", default=1.0)
    start_ratio = gds.FloatItem("Rise start ratio", default=0.1, min=0.0, max=1.0)
    stop_ratio = gds.FloatItem("Rise stop ratio", default=0.9, min=0.0, max=1.0)
    baseline_fraction = gds.FloatItem(
        "Automatic baseline fraction",
        default=0.05,
        min=1e-12,
        max=0.5,
    )
    denoise = gds.BoolItem("Denoise feature extraction", default=True)
    minimum_amplitude = gds.FloatItem(
        "Minimum pulse amplitude",
        default=0.0,
        min=0.0,
    )
    minimum_snr_db = gds.FloatItem("Minimum SNR (dB)", default=0.0)
    detect_saturation = gds.BoolItem("Detect configured saturation", default=False)
    saturation_min = gds.FloatItem("Acquisition minimum", default=-1.0)
    saturation_max = gds.FloatItem("Acquisition maximum", default=1.0)
    saturation_tolerance = gds.FloatItem(
        "Saturation tolerance",
        default=0.0,
        min=0.0,
    )
    minimum_saturated_samples = gds.IntItem(
        "Minimum saturated samples",
        default=1,
        min=1,
    )
    multiple_pulse_threshold_ratio = gds.FloatItem(
        "Multiple-pulse threshold ratio",
        default=0.5,
        min=1e-12,
        max=1.0 - 1e-12,
    )
    minimum_pulse_samples = gds.IntItem(
        "Minimum pulse region samples",
        default=3,
        min=1,
    )
    outlier_modified_zscore = gds.FloatItem(
        "Amplitude outlier modified Z-score",
        default=3.5,
        min=1e-12,
    )
    minimum_outlier_shots = gds.IntItem(
        "Minimum shots for outlier detection",
        default=5,
        min=1,
    )

    def to_core_parameters(self) -> PulseAnalysisParameters:
        """Return validated host-independent analysis parameters."""
        use_ranges = bool(self.use_explicit_ranges)
        detect_saturation = bool(self.detect_saturation)
        return PulseAnalysisParameters(
            start_range=(
                (float(self.xstartmin), float(self.xstartmax)) if use_ranges else None
            ),
            end_range=(
                (float(self.xendmin), float(self.xendmax)) if use_ranges else None
            ),
            signal_shape=self.signal_shape,
            start_ratio=float(self.start_ratio),
            stop_ratio=float(self.stop_ratio),
            baseline_fraction=float(self.baseline_fraction),
            denoise=bool(self.denoise),
            minimum_amplitude=float(self.minimum_amplitude),
            minimum_snr_db=float(self.minimum_snr_db),
            saturation_min=(float(self.saturation_min) if detect_saturation else None),
            saturation_max=(float(self.saturation_max) if detect_saturation else None),
            saturation_tolerance=float(self.saturation_tolerance),
            minimum_saturated_samples=int(self.minimum_saturated_samples),
            multiple_pulse_threshold_ratio=float(self.multiple_pulse_threshold_ratio),
            minimum_pulse_samples=int(self.minimum_pulse_samples),
            outlier_modified_zscore=float(self.outlier_modified_zscore),
            minimum_outlier_shots=int(self.minimum_outlier_shots),
        )


def _shot_index(signal: SignalObj, fallback: int) -> int:
    """Return one positive shot number from metadata or input order."""
    value = signal.metadata.get(SHOT_METADATA_KEY, fallback)
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise RecipeValidationError(
            f"Signal {signal.title!r} has invalid metadata {SHOT_METADATA_KEY!r}"
        )
    return int(value)


def _acquisitions(signals: object) -> tuple[PulseAcquisition, ...]:
    """Convert recipe signals into validated host-independent acquisitions."""
    if not isinstance(signals, (list, tuple)) or not signals:
        raise RecipeValidationError("Pulse campaign requires at least one signal")
    acquisitions: list[PulseAcquisition] = []
    for position, signal in enumerate(signals, start=1):
        if not isinstance(signal, SignalObj):
            raise RecipeValidationError(
                "Pulse campaign inputs must be SignalObj values"
            )
        try:
            acquisitions.append(
                PulseAcquisition(
                    x=signal.x,
                    y=signal.y,
                    title=signal.title,
                    shot_index=_shot_index(signal, position),
                )
            )
        except ValueError as error:
            raise RecipeValidationError(
                f"Invalid pulse signal {signal.title!r}: {error}"
            ) from error
    return tuple(acquisitions)


def _metric(value: float | None) -> float | None:
    """Return a finite numeric table value or JSON null."""
    if value is None:
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _json_value(value: object) -> object:
    """Return one diagnostic value composed of strict JSON primitives."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return _metric(float(value))
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _shot_row(
    shot: PulseShotResult,
    alignment: PulseAlignmentRecord,
) -> list[object]:
    """Return one JSON-friendly consolidated metrics row."""
    features = shot.features
    return [
        shot.shot_index,
        shot.title,
        shot.status.value,
        shot.reason,
        None if features is None else SignalShape(features.signal_shape).value,
        None if features is None else features.polarity,
        None if features is None else _metric(features.offset),
        _metric(shot.amplitude),
        _metric(shot.integral),
        _metric(shot.baseline_noise_rms),
        _metric(shot.snr_db),
        None if features is None else _metric(features.x0),
        None if features is None else _metric(features.x50),
        None if features is None else _metric(features.x100),
        None if features is None else _metric(features.rise_time),
        None if features is None else _metric(features.fall_time),
        None if features is None else _metric(features.fwhm),
        shot.diagnostic_values["saturated_samples"],
        shot.diagnostic_values["pulse_regions"],
        alignment.aligned,
        _metric(alignment.landmark_x),
        _metric(alignment.shift_x),
        alignment.reason,
    ]


def _metrics_table(
    shots: tuple[PulseShotResult, ...],
    alignments: tuple[PulseAlignmentRecord, ...],
    parameters: PulseAnalysisParameters,
    alignment_reference_x: float | None,
) -> TableResult:
    """Build the per-shot table with explicit scientific conventions."""
    return TableResult(
        title="Pulse campaign shot metrics",
        kind="pulse_campaign",
        headers=[
            "Shot",
            "Title",
            "Status",
            "Reason",
            "Shape",
            "Polarity",
            "Offset",
            "Amplitude",
            "Integral",
            "Baseline noise RMS",
            "SNR (dB)",
            "X0",
            "X50",
            "X100",
            "Rise time",
            "Fall time",
            "FWHM",
            "Saturated samples",
            "Pulse regions",
            "Aligned",
            "Alignment landmark",
            "Alignment shift",
            "Alignment reason",
        ],
        data=[_shot_row(shot, alignment) for shot, alignment in zip(shots, alignments)],
        roi_indices=[NO_ROI] * len(shots),
        attrs={
            "measurement_domain": "single_channel_pulse_campaign",
            "normative": False,
            "integral_convention": (
                "Trapezoidal integral of polarity * (raw signal - raw baseline mean)"
            ),
            "snr_convention": "20*log10(amplitude/raw baseline noise RMS)",
            "minimum_amplitude": parameters.minimum_amplitude,
            "minimum_snr_db": parameters.minimum_snr_db,
            "multiple_pulse_threshold_ratio": (
                parameters.multiple_pulse_threshold_ratio
            ),
            "outlier_modified_zscore": parameters.outlier_modified_zscore,
            "alignment_method": "50_percent_crossing",
            "alignment_reference_x": alignment_reference_x,
            "alignment_subset": "alignable VALID shots",
            "alignment_fill": "constant edge values",
        },
    )


def _mean_signal(
    acquisition: PulseAcquisition,
    template: SignalObj,
    output_role: str,
) -> SignalObj:
    """Convert one core campaign mean to a typed recipe output."""
    signal = create_signal(
        acquisition.title,
        acquisition.x,
        acquisition.y,
        units=(template.xunit, template.yunit),
        labels=(template.xlabel, template.ylabel),
    )
    signal.metadata[OUTPUT_ROLE_METADATA_KEY] = output_role
    return signal


def run_pulse_campaign(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Analyze one ordered single-channel campaign and build SDK outputs."""
    if not isinstance(parameters, PulseCampaignRecipeParameters):
        raise RecipeValidationError(
            "Pulse campaign requires PulseCampaignRecipeParameters"
        )
    context.raise_if_cancelled()
    context.report_progress(0.0, "Preparing pulse campaign")
    acquisitions = _acquisitions(inputs.get("signals"))

    def report_shot_progress(completed: int, total: int) -> None:
        """Bridge core shot progress to the recipe execution context."""
        context.report_progress(
            0.75 * completed / total,
            f"Analyzed pulse {completed}/{total}",
        )
        context.raise_if_cancelled()

    try:
        core_parameters = parameters.to_core_parameters()
        result = analyze_pulse_campaign(
            acquisitions,
            core_parameters,
            progress_callback=report_shot_progress,
        )
        alignment = align_pulse_campaign(acquisitions, result)
        if alignment.aligned_count:
            raw_mean = alignment.mean_acquisition(aligned=False)
            aligned_mean = alignment.mean_acquisition(aligned=True)
        else:
            raw_mean = None
            aligned_mean = None
    except (TypeError, ValueError, sigima_pulse.PulseAnalysisError) as error:
        raise RecipeValidationError(str(error)) from error
    context.raise_if_cancelled()
    context.report_progress(0.8, "Aligned valid pulses at 50% crossing")

    first_signal = inputs["signals"][0]
    shots = tuple(result.shots)
    anchor = create_signal(
        "Pulse amplitude vs shot",
        np.array([shot.shot_index for shot in shots], dtype=float),
        np.array([shot.amplitude for shot in shots], dtype=float),
        units=("shot", first_signal.yunit),
        labels=("Shot", first_signal.ylabel or "Amplitude"),
    )
    anchor.metadata[OUTPUT_ROLE_METADATA_KEY] = "amplitude_vs_shot"
    mean_outputs: tuple[RecipeObjectOutput, ...] = ()
    if raw_mean is not None and aligned_mean is not None:
        mean_outputs = (
            RecipeObjectOutput(
                "raw_mean",
                _mean_signal(raw_mean, first_signal, "raw_mean"),
            ),
            RecipeObjectOutput(
                "aligned_mean",
                _mean_signal(aligned_mean, first_signal, "aligned_mean"),
            ),
        )
    table = _metrics_table(
        shots,
        tuple(alignment.records),
        core_parameters,
        alignment.reference_x,
    )
    status_diagnostics = tuple(
        RecipeDiagnostic(
            level=RecipeDiagnosticLevel.WARNING,
            code=shot.status.value.lower(),
            message=f"Shot {shot.shot_index}: {shot.reason}",
            details={
                "shot": shot.shot_index,
                "title": shot.title,
                **{
                    key: _json_value(value)
                    for key, value in shot.diagnostic_values.items()
                },
            },
        )
        for shot in shots
        if shot.status is not PulseStatus.VALID
    )
    alignment_diagnostics = tuple(
        RecipeDiagnostic(
            level=RecipeDiagnosticLevel.WARNING,
            code="alignment_unavailable",
            message=f"Shot {shot.shot_index}: {alignment_record.reason}",
            details={
                "shot": shot.shot_index,
                "title": shot.title,
                "alignment_method": "50_percent_crossing",
                "alignment_reference_x": _metric(alignment.reference_x),
            },
        )
        for shot, alignment_record in zip(shots, alignment.records)
        if shot.status is PulseStatus.VALID and not alignment_record.aligned
    )
    context.report_progress(1.0, "Pulse campaign analysis complete")
    return RecipeOutcome(
        objects=(
            RecipeObjectOutput("amplitude_vs_shot", anchor),
            *mean_outputs,
        ),
        results=(
            RecipeResultOutput(
                "shot_metrics",
                table,
                anchor_id="amplitude_vs_shot",
            ),
        ),
        diagnostics=(*status_diagnostics, *alignment_diagnostics),
    )


__all__ = [
    "OUTPUT_ROLE_METADATA_KEY",
    "PulseCampaignRecipeParameters",
    "SHOT_METADATA_KEY",
    "run_pulse_campaign",
]
