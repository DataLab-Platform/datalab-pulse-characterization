"""Shot-to-shot timing and amplitude stability of a single-channel campaign."""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from .campaign import PulseCampaignResult, PulseStatus


@dataclasses.dataclass(frozen=True)
class PulseStabilityParameters:
    """Explicit, non-normative settings for the stability method."""

    rolling_window: int = 25
    detect_regime_change: bool = True
    minimum_segment_shots: int = 30
    regime_change_threshold: float = 25.0

    def __post_init__(self) -> None:
        """Validate settings independently from a campaign."""
        for name, value, minimum in (
            ("Rolling window", self.rolling_window, 3),
            ("Minimum segment shots", self.minimum_segment_shots, 5),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer of at least {minimum}")
        threshold = float(self.regime_change_threshold)
        if not math.isfinite(threshold) or threshold <= 0.0:
            raise ValueError("Regime-change threshold must be finite and positive")


@dataclasses.dataclass(frozen=True)
class AllanDeviation:
    """Overlapping Allan (two-sample) deviation versus averaging length."""

    tau_shots: np.ndarray
    deviation: np.ndarray


@dataclasses.dataclass(frozen=True)
class RegimeChange:
    """Most likely single change of timing jitter along the campaign."""

    shot_index: int
    log_likelihood_ratio: float
    jitter_before: float
    jitter_after: float


@dataclasses.dataclass(frozen=True)
class PulseStabilityResult:
    """Stability metrics of the valid shots of one campaign.

    Arrival times are the 50 % crossings relative to the acquisition origin,
    that is to the trigger. Allan deviations treat consecutive valid shots as
    evenly spaced samples; invalid shots are removed beforehand.
    """

    shot_indices: np.ndarray
    arrival_times: np.ndarray
    amplitudes: np.ndarray
    integrals: np.ndarray
    detrended_arrival_times: np.ndarray
    rolling_jitter: np.ndarray
    rms_jitter: float
    peak_to_peak_jitter: float
    timing_drift_per_shot: float
    detrended_rms_jitter: float
    amplitude_mean: float
    amplitude_relative_std: float
    amplitude_relative_peak_to_peak: float
    amplitude_drift_per_shot: float
    integral_mean: float
    integral_relative_std: float
    arrival_time_adev: AllanDeviation
    amplitude_adev: AllanDeviation
    regime_change: RegimeChange | None
    excluded_shot_count: int


def _readonly(array: np.ndarray) -> np.ndarray:
    """Mark an owned result array as read-only and return it."""
    array.setflags(write=False)
    return array


def overlapping_allan_deviation(values: np.ndarray) -> AllanDeviation:
    """Return the overlapping Allan deviation at octave averaging lengths.

    For averages ``ybar_j`` of ``m`` consecutive samples,
    ``sigma(m)**2 = mean((ybar_(j+m) - ybar_j)**2) / 2``. White noise decreases
    as ``m**-0.5`` while a linear drift grows as ``m``.
    """
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    cumulative = np.concatenate(([0.0], np.cumsum(centered)))
    taus: list[int] = []
    deviations: list[float] = []
    m = 1
    # Lengths beyond a quarter of the series leave too few independent pairs.
    while m == 1 or m <= centered.size // 4:
        averages = (cumulative[m:] - cumulative[:-m]) / m
        differences = averages[m:] - averages[:-m]
        taus.append(m)
        deviations.append(math.sqrt(0.5 * float(np.mean(differences**2))))
        m *= 2
    return AllanDeviation(
        tau_shots=_readonly(np.array(taus, dtype=float)),
        deviation=_readonly(np.array(deviations, dtype=float)),
    )


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """Return a centered rolling sample standard deviation (NaN at the edges)."""
    result = np.full(values.size, np.nan)
    if values.size < window:
        return result
    cumulative = np.concatenate(([0.0], np.cumsum(values)))
    cumulative_sq = np.concatenate(([0.0], np.cumsum(values**2)))
    sums = cumulative[window:] - cumulative[:-window]
    sums_sq = cumulative_sq[window:] - cumulative_sq[:-window]
    variances = (sums_sq - sums**2 / window) / (window - 1)
    start = (window - 1) // 2
    result[start : start + variances.size] = np.sqrt(np.maximum(variances, 0.0))
    return result


def _regime_change(
    shot_indices: np.ndarray,
    residuals: np.ndarray,
    parameters: PulseStabilityParameters,
) -> RegimeChange | None:
    """Return the variance change point maximizing a Gaussian likelihood ratio."""
    count = residuals.size
    minimum = parameters.minimum_segment_shots
    if count < 2 * minimum:
        return None
    squares = residuals**2
    cumulative = np.cumsum(squares)
    total_variance = cumulative[-1] / count
    if total_variance <= 0.0:
        return None
    best_index = -1
    best_ratio = -math.inf
    for split in range(minimum, count - minimum + 1):
        variance_before = cumulative[split - 1] / split
        variance_after = (cumulative[-1] - cumulative[split - 1]) / (count - split)
        if variance_before <= 0.0 or variance_after <= 0.0:
            continue
        ratio = (
            count * math.log(total_variance)
            - split * math.log(variance_before)
            - (count - split) * math.log(variance_after)
        )
        if ratio > best_ratio:
            best_ratio = ratio
            best_index = split
    if best_index < 0 or best_ratio < parameters.regime_change_threshold:
        return None
    return RegimeChange(
        shot_index=int(shot_indices[best_index]),
        log_likelihood_ratio=float(best_ratio),
        jitter_before=float(np.std(residuals[:best_index], ddof=1)),
        jitter_after=float(np.std(residuals[best_index:], ddof=1)),
    )


def analyze_pulse_stability(
    campaign: PulseCampaignResult,
    parameters: PulseStabilityParameters | None = None,
) -> PulseStabilityResult:
    """Characterize timing jitter, drifts and amplitude stability.

    Args:
        campaign: Analyzed campaign; only ``VALID`` shots with a finite 50 %
         crossing are used
        parameters: Rolling window and regime-change settings

    Returns:
        Arrival-time, amplitude and integral statistics, Allan deviations and
        the optional jitter regime change

    Raises:
        ValueError: If fewer than four valid shots remain
    """
    parameters = parameters or PulseStabilityParameters()
    valid = [
        shot
        for shot in campaign.shots
        if shot.status is PulseStatus.VALID
        and shot.features is not None
        and shot.features.x50 is not None
        and math.isfinite(shot.features.x50)
    ]
    if len(valid) < 4:
        raise ValueError("Stability analysis requires at least four valid shots")
    shot_indices = np.array([shot.shot_index for shot in valid], dtype=float)
    arrival_times = np.array([float(shot.features.x50) for shot in valid])
    amplitudes = np.array([shot.amplitude for shot in valid])
    integrals = np.array([float(shot.integral) for shot in valid])

    timing_drift, timing_intercept = np.polyfit(shot_indices, arrival_times, 1)
    residuals = arrival_times - (timing_drift * shot_indices + timing_intercept)
    amplitude_mean = float(np.mean(amplitudes))
    amplitude_drift = float(np.polyfit(shot_indices, amplitudes, 1)[0])
    integral_mean = float(np.mean(integrals))

    regime_change = (
        _regime_change(shot_indices, residuals, parameters)
        if parameters.detect_regime_change
        else None
    )
    return PulseStabilityResult(
        shot_indices=_readonly(shot_indices),
        arrival_times=_readonly(arrival_times),
        amplitudes=_readonly(amplitudes),
        integrals=_readonly(integrals),
        detrended_arrival_times=_readonly(residuals),
        rolling_jitter=_readonly(_rolling_std(residuals, parameters.rolling_window)),
        rms_jitter=float(np.std(arrival_times, ddof=1)),
        peak_to_peak_jitter=float(np.ptp(arrival_times)),
        timing_drift_per_shot=float(timing_drift),
        detrended_rms_jitter=float(np.std(residuals, ddof=1)),
        amplitude_mean=amplitude_mean,
        amplitude_relative_std=float(np.std(amplitudes, ddof=1)) / amplitude_mean,
        amplitude_relative_peak_to_peak=float(np.ptp(amplitudes)) / amplitude_mean,
        amplitude_drift_per_shot=amplitude_drift,
        integral_mean=integral_mean,
        integral_relative_std=float(np.std(integrals, ddof=1)) / integral_mean,
        arrival_time_adev=overlapping_allan_deviation(arrival_times),
        amplitude_adev=overlapping_allan_deviation(amplitudes / amplitude_mean),
        regime_change=regime_change,
        excluded_shot_count=len(campaign.shots) - len(valid),
    )


__all__ = [
    "AllanDeviation",
    "PulseStabilityParameters",
    "PulseStabilityResult",
    "RegimeChange",
    "analyze_pulse_stability",
    "overlapping_allan_deviation",
]
