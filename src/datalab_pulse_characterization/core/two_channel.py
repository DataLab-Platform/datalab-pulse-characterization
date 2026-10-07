"""Delay and relative jitter between two synchronized pulse channels."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

import numpy as np

from .campaign import (
    PulseAcquisition,
    PulseCampaignResult,
    PulseShotResult,
    PulseStatus,
)


@dataclasses.dataclass(frozen=True)
class TwoChannelDelayParameters:
    """Settings for the delay estimators.

    ``maximum_lag`` bounds the cross-correlation search (X units, ``None``
    searches every lag).
    """

    maximum_lag: float | None = None

    def __post_init__(self) -> None:
        """Validate settings independently from a campaign."""
        if self.maximum_lag is not None and (
            not math.isfinite(self.maximum_lag) or self.maximum_lag <= 0.0
        ):
            raise ValueError("Maximum lag must be finite and positive or None")


@dataclasses.dataclass(frozen=True)
class ChannelPair:
    """One shot seen by both channels, or by only one of them."""

    shot_index: int
    reference: PulseShotResult | None
    measured: PulseShotResult | None
    cfd_delay: float | None
    xcorr_delay: float | None
    status: str


@dataclasses.dataclass(frozen=True)
class TwoChannelDelayResult:
    """Delay statistics over the valid pairs of a two-channel campaign.

    The CFD delay is the difference of the 50 % crossings (constant-fraction
    timing). The cross-correlation delay compares whole waveforms; it differs
    from the CFD delay by a constant when the two pulse shapes differ, but both
    share the same relative jitter.
    """

    pairs: Sequence[ChannelPair]
    mean_cfd_delay: float
    relative_jitter: float
    mean_xcorr_delay: float
    xcorr_relative_jitter: float
    reference_jitter: float
    measured_jitter: float
    common_jitter: float
    timing_correlation: float
    amplitude_correlation: float
    amplitude_gain: float
    integral_correlation: float

    @property
    def valid_pairs(self) -> tuple[ChannelPair, ...]:
        """Return pairs where both channels are valid."""
        return tuple(pair for pair in self.pairs if pair.status == "VALID")


def _crossing(shot: PulseShotResult | None) -> float | None:
    """Return the finite 50 % crossing of a valid shot."""
    if shot is None or shot.status is not PulseStatus.VALID or shot.features is None:
        return None
    x50 = shot.features.x50
    return float(x50) if x50 is not None and math.isfinite(x50) else None


def _oriented_waveform(
    acquisition: PulseAcquisition,
    shot: PulseShotResult,
) -> np.ndarray:
    """Return the baseline-subtracted, polarity-oriented waveform."""
    features = shot.features
    assert features is not None
    oriented = acquisition.y * features.polarity
    mask = (acquisition.x >= features.xstartmin) & (acquisition.x <= features.xstartmax)
    baseline = float(np.mean(oriented[mask])) if np.any(mask) else 0.0
    return oriented - baseline


def cross_correlation_delay(
    reference: PulseAcquisition,
    measured: PulseAcquisition,
    reference_waveform: np.ndarray,
    measured_waveform: np.ndarray,
    maximum_lag: float | None = None,
) -> float | None:
    """Return the measured-minus-reference delay maximizing the correlation.

    The integer-sample peak is refined by parabolic interpolation. Both
    acquisitions must share their sampling interval.
    """
    dx = float(reference.x[1] - reference.x[0])
    correlation = np.correlate(measured_waveform, reference_waveform, mode="full")
    lags = np.arange(-reference_waveform.size + 1, measured_waveform.size)
    if maximum_lag is not None:
        offset = float(measured.x[0] - reference.x[0])
        allowed = np.abs(lags * dx + offset) <= maximum_lag
        if not np.any(allowed):
            return None
        correlation = np.where(allowed, correlation, -np.inf)
    index = int(np.argmax(correlation))
    refinement = 0.0
    if 0 < index < correlation.size - 1 and np.all(
        np.isfinite(correlation[index - 1 : index + 2])
    ):
        left, center, right = correlation[index - 1 : index + 2]
        denominator = left - 2.0 * center + right
        if denominator < 0.0:
            refinement = 0.5 * (left - right) / denominator
    return float((lags[index] + refinement) * dx + measured.x[0] - reference.x[0])


def _correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Return the Pearson correlation, or NaN for constant samples."""
    if first.size < 2 or np.std(first) == 0.0 or np.std(second) == 0.0:
        return math.nan
    return float(np.corrcoef(first, second)[0, 1])


def _same_sampling(first: PulseAcquisition, second: PulseAcquisition) -> bool:
    """Return whether two evenly sampled acquisitions share their interval."""
    first_dx = np.diff(first.x)
    second_dx = np.diff(second.x)
    reference = float(first_dx[0])
    return bool(
        np.allclose(first_dx, reference, rtol=1e-6, atol=0.0)
        and np.allclose(second_dx, reference, rtol=1e-6, atol=0.0)
    )


def analyze_two_channel_delay(
    reference_acquisitions: Sequence[PulseAcquisition],
    reference_campaign: PulseCampaignResult,
    measured_acquisitions: Sequence[PulseAcquisition],
    measured_campaign: PulseCampaignResult,
    parameters: TwoChannelDelayParameters | None = None,
) -> TwoChannelDelayResult:
    """Pair shots by index and measure delay, relative jitter and correlations.

    Args:
        reference_acquisitions: Reference-channel acquisitions with shot indices
        reference_campaign: Their single-channel analysis, in the same order
        measured_acquisitions: Measured-channel acquisitions with shot indices
        measured_campaign: Their single-channel analysis, in the same order
        parameters: Cross-correlation settings

    Returns:
        One pair per shot index seen by either channel, and pair statistics

    Raises:
        ValueError: If shot indices are missing or fewer than three valid
         pairs remain
    """
    parameters = parameters or TwoChannelDelayParameters()
    channels = []
    for name, acquisitions, campaign in (
        ("reference", reference_acquisitions, reference_campaign),
        ("measured", measured_acquisitions, measured_campaign),
    ):
        acquisitions = tuple(acquisitions)
        if any(acquisition.shot_index is None for acquisition in acquisitions):
            raise ValueError(f"Every {name} acquisition requires a shot index")
        channels.append(
            {
                shot.shot_index: (acquisition, shot)
                for acquisition, shot in zip(acquisitions, campaign.shots)
            }
        )
    reference_by_shot, measured_by_shot = channels

    pairs: list[ChannelPair] = []
    for shot_index in sorted(set(reference_by_shot) | set(measured_by_shot)):
        reference = reference_by_shot.get(shot_index)
        measured = measured_by_shot.get(shot_index)
        reference_shot = None if reference is None else reference[1]
        measured_shot = None if measured is None else measured[1]
        if reference is None or measured is None:
            status = "MISSING_REFERENCE" if reference is None else "MISSING_MEASURED"
            pairs.append(
                ChannelPair(
                    shot_index, reference_shot, measured_shot, None, None, status
                )
            )
            continue
        reference_crossing = _crossing(reference_shot)
        measured_crossing = _crossing(measured_shot)
        if reference_crossing is None or measured_crossing is None:
            status = (
                f"REFERENCE_{reference_shot.status.value}"
                if reference_crossing is None
                else f"MEASURED_{measured_shot.status.value}"
            )
            pairs.append(
                ChannelPair(
                    shot_index, reference_shot, measured_shot, None, None, status
                )
            )
            continue
        xcorr_delay = None
        if _same_sampling(reference[0], measured[0]):
            xcorr_delay = cross_correlation_delay(
                reference[0],
                measured[0],
                _oriented_waveform(*reference),
                _oriented_waveform(*measured),
                parameters.maximum_lag,
            )
        pairs.append(
            ChannelPair(
                shot_index,
                reference_shot,
                measured_shot,
                measured_crossing - reference_crossing,
                xcorr_delay,
                "VALID",
            )
        )

    valid = [pair for pair in pairs if pair.status == "VALID"]
    if len(valid) < 3:
        raise ValueError("Two-channel delay requires at least three valid pairs")
    cfd = np.array([pair.cfd_delay for pair in valid])
    reference_times = np.array([_crossing(pair.reference) for pair in valid])
    measured_times = np.array([_crossing(pair.measured) for pair in valid])
    xcorr = np.array(
        [pair.xcorr_delay for pair in valid if pair.xcorr_delay is not None]
    )
    reference_amplitudes = np.array([pair.reference.amplitude for pair in valid])
    measured_amplitudes = np.array([pair.measured.amplitude for pair in valid])
    covariance = float(np.cov(reference_times, measured_times)[0, 1])
    gain = (
        float(np.polyfit(reference_amplitudes, measured_amplitudes, 1)[0])
        if np.std(reference_amplitudes) > 0.0
        else math.nan
    )
    return TwoChannelDelayResult(
        pairs=tuple(pairs),
        mean_cfd_delay=float(np.mean(cfd)),
        relative_jitter=float(np.std(cfd, ddof=1)),
        mean_xcorr_delay=float(np.mean(xcorr)) if xcorr.size else math.nan,
        xcorr_relative_jitter=float(np.std(xcorr, ddof=1))
        if xcorr.size > 1
        else math.nan,
        reference_jitter=float(np.std(reference_times, ddof=1)),
        measured_jitter=float(np.std(measured_times, ddof=1)),
        common_jitter=math.sqrt(max(covariance, 0.0)),
        timing_correlation=_correlation(reference_times, measured_times),
        amplitude_correlation=_correlation(reference_amplitudes, measured_amplitudes),
        amplitude_gain=gain,
        integral_correlation=_correlation(
            np.array([pair.reference.integral for pair in valid]),
            np.array([pair.measured.integral for pair in valid]),
        ),
    )


__all__ = [
    "ChannelPair",
    "TwoChannelDelayParameters",
    "TwoChannelDelayResult",
    "analyze_two_channel_delay",
    "cross_correlation_delay",
]
