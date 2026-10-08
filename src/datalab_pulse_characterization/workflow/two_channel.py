"""Headless two-channel delay and relative-jitter recipe."""

from __future__ import annotations

from collections.abc import Sequence
from numbers import Integral

import guidata.dataset as gds
import numpy as np
from datalab.plugins.recipes import (
    RecipeDiagnostic,
    RecipeDiagnosticLevel,
    RecipeExecutionContext,
    RecipeInputs,
    RecipeObjectOutput,
    RecipeOutcome,
    RecipeResultOutput,
    RecipeValidationError,
)
from sigima.objects import NO_ROI, SignalObj, TableResult
from sigima.tools.signal import pulse as sigima_pulse

from ..core import (
    PulseAcquisition,
    TwoChannelDelayParameters,
    TwoChannelDelayResult,
    analyze_pulse_campaign,
    analyze_two_channel_delay,
    metadata_key,
)
from .campaign import SHOT_METADATA_KEY, PulseCampaignRecipeParameters, _metric
from .outputs import histogram, metrics_table, signal_output

CHANNEL_METADATA_KEY = metadata_key("channel")


def suggest_channel_roles(
    signals: Sequence[SignalObj],
) -> dict[str, tuple[SignalObj, ...]]:
    """Assign the first of exactly two sorted channel labels to the reference.

    Channel labels are only a binding convenience: pairing relies on shot
    metadata, and hosts let users change the proposed roles.
    """
    labels = sorted(
        {
            str(signal.metadata[CHANNEL_METADATA_KEY])
            for signal in signals
            if CHANNEL_METADATA_KEY in signal.metadata
        }
    )
    if len(labels) != 2:
        return {}
    return {
        slot: tuple(
            signal
            for signal in signals
            if str(signal.metadata.get(CHANNEL_METADATA_KEY)) == label
        )
        for slot, label in zip(("reference", "measured"), labels)
    }


class TwoChannelDelayRecipeParameters(PulseCampaignRecipeParameters):
    """Parameters for delay and relative jitter between two channels."""

    maximum_lag = gds.FloatItem(
        "Maximum cross-correlation lag (X units, 0 = unlimited)",
        default=0.0,
        min=0.0,
    )
    histogram_bin_count = gds.IntItem("Delay histogram bins", default=40, min=4)

    def to_delay_parameters(self) -> TwoChannelDelayParameters:
        """Return host-independent delay parameters."""
        maximum_lag = float(self.maximum_lag)
        return TwoChannelDelayParameters(
            maximum_lag=maximum_lag if maximum_lag > 0.0 else None
        )


def _channel(signals: object, slot: str) -> tuple[PulseAcquisition, ...]:
    """Convert one slot into acquisitions identified by their shot metadata."""
    if not isinstance(signals, (list, tuple)) or len(signals) < 3:
        raise RecipeValidationError(f"Slot {slot!r} requires at least three signals")
    acquisitions: list[PulseAcquisition] = []
    seen: set[int] = set()
    for signal in signals:
        if not isinstance(signal, SignalObj):
            raise RecipeValidationError("Two-channel inputs must be SignalObj values")
        shot = signal.metadata.get(SHOT_METADATA_KEY)
        if isinstance(shot, bool) or not isinstance(shot, Integral) or shot < 1:
            raise RecipeValidationError(
                f"Signal {signal.title!r} in {slot!r} requires a positive "
                f"{SHOT_METADATA_KEY!r} metadata value to be paired"
            )
        if int(shot) in seen:
            raise RecipeValidationError(f"Shot {int(shot)} appears twice in {slot!r}")
        seen.add(int(shot))
        try:
            acquisitions.append(
                PulseAcquisition(signal.x, signal.y, signal.title, int(shot))
            )
        except ValueError as error:
            raise RecipeValidationError(
                f"Invalid pulse signal {signal.title!r}: {error}"
            ) from error
    return tuple(acquisitions)


def _summary(result: TwoChannelDelayResult, x_unit: str, y_unit: str) -> TableResult:
    """Build the two-channel summary table."""
    statuses = [pair.status for pair in result.pairs]
    rows: list[tuple[str, object, str]] = [
        ("Valid pairs", statuses.count("VALID"), "shot"),
        ("Missing reference", statuses.count("MISSING_REFERENCE"), "shot"),
        ("Missing measured", statuses.count("MISSING_MEASURED"), "shot"),
        (
            "Pairs with an invalid channel",
            sum(status.startswith(("REFERENCE_", "MEASURED_")) for status in statuses),
            "shot",
        ),
        ("Mean 50% (CFD) delay", result.mean_cfd_delay, x_unit),
        ("Relative jitter (CFD)", result.relative_jitter, x_unit),
        ("Mean cross-correlation delay", result.mean_xcorr_delay, x_unit),
        ("Relative jitter (cross-correlation)", result.xcorr_relative_jitter, x_unit),
        ("Reference timing jitter", result.reference_jitter, x_unit),
        ("Measured timing jitter", result.measured_jitter, x_unit),
        ("Common-mode timing jitter", result.common_jitter, x_unit),
        ("Timing correlation", result.timing_correlation, ""),
        ("Amplitude correlation", result.amplitude_correlation, ""),
        ("Amplitude gain (measured / reference)", result.amplitude_gain, ""),
        ("Integral correlation", result.integral_correlation, ""),
    ]
    return metrics_table(
        "Two-channel delay summary",
        "pulse_two_channel_delay",
        rows,
        {
            "measurement_domain": "two_channel_delay",
            "pairing": f"shot metadata {SHOT_METADATA_KEY}",
            "cfd_convention": "measured 50 % crossing - reference 50 % crossing",
            "amplitude_unit": y_unit,
        },
    )


def _pair_table(result: TwoChannelDelayResult) -> TableResult:
    """Build the per-shot pair table."""

    def crossing(shot) -> float | None:
        if shot is None or shot.features is None:
            return None
        return _metric(shot.features.x50)

    rows = [
        [
            pair.shot_index,
            pair.status,
            None if pair.reference is None else pair.reference.status.value,
            None if pair.measured is None else pair.measured.status.value,
            crossing(pair.reference),
            crossing(pair.measured),
            _metric(pair.cfd_delay),
            _metric(pair.xcorr_delay),
            None if pair.reference is None else _metric(pair.reference.amplitude),
            None if pair.measured is None else _metric(pair.measured.amplitude),
        ]
        for pair in result.pairs
    ]
    return TableResult(
        title="Two-channel pair metrics",
        kind="pulse_two_channel_pairs",
        headers=[
            "Shot",
            "Pair status",
            "Reference status",
            "Measured status",
            "Reference X50",
            "Measured X50",
            "CFD delay",
            "Cross-correlation delay",
            "Reference amplitude",
            "Measured amplitude",
        ],
        data=rows,
        roi_indices=[NO_ROI] * len(rows),
        attrs={"normative": False},
    )


def run_two_channel_delay(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Pair two channels by shot and measure their delay and relative jitter."""
    if not isinstance(parameters, TwoChannelDelayRecipeParameters):
        raise RecipeValidationError(
            "Two-channel delay requires TwoChannelDelayRecipeParameters"
        )
    context.raise_if_cancelled()
    context.report_progress(0.0, "Pairing channels by shot")
    reference_signals = inputs.get("reference")
    measured_signals = inputs.get("measured")
    reference = _channel(reference_signals, "reference")
    measured = _channel(measured_signals, "measured")
    reference_unit = reference_signals[0].xunit or ""
    if (measured_signals[0].xunit or "") != reference_unit:
        raise RecipeValidationError("Both channels must share the same X unit")

    def progress(offset: float, label: str):
        def report(completed: int, total: int) -> None:
            context.report_progress(offset + 0.4 * completed / total, label)
            context.raise_if_cancelled()

        return report

    try:
        core_parameters = parameters.to_core_parameters()
        reference_campaign = analyze_pulse_campaign(
            reference,
            core_parameters,
            progress_callback=progress(0.0, "Analyzed reference pulse"),
        )
        measured_campaign = analyze_pulse_campaign(
            measured,
            core_parameters,
            progress_callback=progress(0.4, "Analyzed measured pulse"),
        )
        result = analyze_two_channel_delay(
            reference,
            reference_campaign,
            measured,
            measured_campaign,
            parameters.to_delay_parameters(),
        )
    except (TypeError, ValueError, sigima_pulse.PulseAnalysisError) as error:
        raise RecipeValidationError(str(error)) from error
    context.report_progress(0.9, "Building two-channel outputs")
    context.raise_if_cancelled()

    y_unit = reference_signals[0].yunit or ""
    valid = result.valid_pairs
    shots = np.array([pair.shot_index for pair in valid], dtype=float)
    delays = np.array([pair.cfd_delay for pair in valid])
    xcorr = [pair for pair in valid if pair.xcorr_delay is not None]
    amplitudes = np.array(
        sorted((pair.reference.amplitude, pair.measured.amplitude) for pair in valid)
    )
    centers, counts = histogram(delays, int(parameters.histogram_bin_count))
    objects = [
        RecipeObjectOutput(
            "delay_vs_shot",
            signal_output(
                "CFD delay vs shot",
                shots,
                delays,
                "delay_vs_shot",
                units=("shot", reference_unit),
                labels=("Shot", "Measured - reference delay"),
            ),
        ),
        RecipeObjectOutput(
            "delay_distribution",
            signal_output(
                "CFD delay distribution",
                centers,
                counts,
                "delay_distribution",
                units=(reference_unit, ""),
                labels=("Delay", "Shot count"),
            ),
        ),
        RecipeObjectOutput(
            "amplitude_correlation",
            signal_output(
                "Measured vs reference amplitude",
                amplitudes[:, 0],
                amplitudes[:, 1],
                "amplitude_correlation",
                units=(y_unit, measured_signals[0].yunit or ""),
                labels=("Reference amplitude", "Measured amplitude"),
            ),
        ),
    ]
    if len(xcorr) >= 2:
        objects.insert(
            1,
            RecipeObjectOutput(
                "xcorr_delay_vs_shot",
                signal_output(
                    "Cross-correlation delay vs shot",
                    np.array([pair.shot_index for pair in xcorr], dtype=float),
                    np.array([pair.xcorr_delay for pair in xcorr]),
                    "xcorr_delay_vs_shot",
                    units=("shot", reference_unit),
                    labels=("Shot", "Measured - reference delay"),
                ),
            ),
        )
    diagnostics = tuple(
        RecipeDiagnostic(
            level=RecipeDiagnosticLevel.WARNING,
            code=(
                "missing_channel"
                if pair.status.startswith("MISSING")
                else "invalid_pair"
            ),
            message=f"Shot {pair.shot_index}: {pair.status}",
            details={"shot": pair.shot_index, "status": pair.status},
        )
        for pair in result.pairs
        if pair.status != "VALID"
    )
    context.report_progress(1.0, "Two-channel analysis complete")
    return RecipeOutcome(
        objects=tuple(objects),
        results=(
            RecipeResultOutput(
                "delay_summary",
                _summary(result, reference_unit, y_unit),
                anchor_id="delay_vs_shot",
            ),
            RecipeResultOutput(
                "pair_metrics",
                _pair_table(result),
                anchor_id="delay_vs_shot",
            ),
        ),
        diagnostics=diagnostics,
    )


__all__ = [
    "CHANNEL_METADATA_KEY",
    "TwoChannelDelayRecipeParameters",
    "run_two_channel_delay",
    "suggest_channel_roles",
]
