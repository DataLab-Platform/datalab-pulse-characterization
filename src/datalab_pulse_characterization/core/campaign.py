"""Headless pulse campaign analysis."""

from __future__ import annotations

import dataclasses
import enum
import math
import warnings
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType

import numpy as np
import scipy.integrate
from sigima.enums import SignalShape
from sigima.tools.signal import pulse as sigima_pulse


class PulseStatus(str, enum.Enum):
    """Explainable quality status assigned to one pulse acquisition."""

    VALID = "VALID"
    NO_PULSE = "NO_PULSE"
    LOW_SNR = "LOW_SNR"
    SATURATED = "SATURATED"
    MULTIPLE_PULSES = "MULTIPLE_PULSES"
    OUTLIER = "OUTLIER"


@dataclasses.dataclass(frozen=True)
class PulseAnalysisParameters:
    """Host-independent parameters for single-channel pulse analysis."""

    start_range: tuple[float, float] | None = None
    end_range: tuple[float, float] | None = None
    signal_shape: SignalShape | str | None = None
    start_ratio: float = 0.1
    stop_ratio: float = 0.9
    baseline_fraction: float = 0.05
    denoise: bool = True
    minimum_amplitude: float = 0.0
    minimum_snr_db: float = 0.0
    saturation_min: float | None = None
    saturation_max: float | None = None
    saturation_tolerance: float = 0.0
    minimum_saturated_samples: int = 1
    multiple_pulse_threshold_ratio: float = 0.5
    minimum_pulse_samples: int = 3
    outlier_modified_zscore: float = 3.5
    minimum_outlier_shots: int = 5

    def __post_init__(self) -> None:
        """Validate numerical conventions before processing any shot."""
        if not 0.0 <= self.start_ratio < self.stop_ratio <= 1.0:
            raise ValueError(
                "Pulse reference ratios must satisfy 0 <= start < stop <= 1"
            )
        if not 0.0 < self.baseline_fraction <= 0.5:
            raise ValueError("Baseline fraction must be in the interval (0, 0.5]")
        if not math.isfinite(self.minimum_amplitude) or self.minimum_amplitude < 0.0:
            raise ValueError("Minimum amplitude must be finite and non-negative")
        if not math.isfinite(self.minimum_snr_db):
            raise ValueError("Minimum SNR must be finite")
        for name, value in (
            ("Saturation minimum", self.saturation_min),
            ("Saturation maximum", self.saturation_max),
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite or None")
        if (
            self.saturation_min is not None
            and self.saturation_max is not None
            and self.saturation_min >= self.saturation_max
        ):
            raise ValueError("Saturation minimum must be below saturation maximum")
        if (
            not math.isfinite(self.saturation_tolerance)
            or self.saturation_tolerance < 0.0
        ):
            raise ValueError("Saturation tolerance must be finite and non-negative")
        for name, value in (
            ("Minimum saturated samples", self.minimum_saturated_samples),
            ("Minimum pulse samples", self.minimum_pulse_samples),
            ("Minimum outlier shots", self.minimum_outlier_shots),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not 0.0 < self.multiple_pulse_threshold_ratio < 1.0:
            raise ValueError("Multiple-pulse threshold ratio must be between 0 and 1")
        if (
            not math.isfinite(self.outlier_modified_zscore)
            or self.outlier_modified_zscore <= 0.0
        ):
            raise ValueError("Outlier modified Z-score must be finite and positive")
        for name, value_range in (
            ("start", self.start_range),
            ("end", self.end_range),
        ):
            if value_range is None:
                continue
            if (
                len(value_range) != 2
                or not all(math.isfinite(value) for value in value_range)
                or value_range[0] > value_range[1]
            ):
                raise ValueError(f"Invalid {name} range")
        if self.signal_shape is not None:
            try:
                SignalShape(self.signal_shape)
            except ValueError as error:
                raise ValueError(
                    "Signal shape must be step, square, or None"
                ) from error


@dataclasses.dataclass(frozen=True)
class PulseAcquisition:
    """One host-independent pulse acquisition in a campaign."""

    x: np.ndarray
    y: np.ndarray
    title: str
    shot_index: int | None = None

    def __post_init__(self) -> None:
        """Copy and validate arrays so campaign analysis is deterministic."""
        x = np.array(self.x, copy=True)
        y = np.array(self.y, copy=True)
        if x.ndim != 1 or y.ndim != 1 or x.size != y.size or x.size < 3:
            raise ValueError(
                "Pulse acquisition requires equal 1D arrays of length >= 3"
            )
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError("Pulse acquisition arrays must contain finite values")
        if np.any(np.diff(x) <= 0.0):
            raise ValueError("Pulse acquisition X values must be strictly increasing")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Pulse acquisition title must be non-empty")
        if self.shot_index is not None and (
            isinstance(self.shot_index, bool)
            or not isinstance(self.shot_index, int)
            or self.shot_index < 1
        ):
            raise ValueError("Pulse acquisition shot index must be positive or None")
        x.setflags(write=False)
        y.setflags(write=False)
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)


@dataclasses.dataclass(frozen=True)
class PulseShotResult:
    """Features, added metrics, and explainable status for one shot."""

    shot_index: int
    title: str
    features: sigima_pulse.PulseFeatures | None
    amplitude: float
    # None when Sigima extraction failed: without polarity the sign is unknown
    integral: float | None
    baseline_noise_rms: float
    snr_db: float
    status: PulseStatus
    reason: str
    diagnostic_values: Mapping[str, object] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze diagnostic values for deterministic downstream reporting."""
        if self.shot_index < 1:
            raise ValueError("Shot index must be positive")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Shot title must be non-empty")
        object.__setattr__(self, "status", PulseStatus(self.status))
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Pulse status reason must be non-empty")
        object.__setattr__(
            self,
            "diagnostic_values",
            MappingProxyType(dict(self.diagnostic_values)),
        )


@dataclasses.dataclass(frozen=True)
class PulseCampaignResult:
    """Immutable ordered results for a single-channel pulse campaign."""

    shots: Sequence[PulseShotResult]

    def __post_init__(self) -> None:
        """Freeze and validate the ordered shot sequence."""
        shots = tuple(self.shots)
        if not shots:
            raise ValueError("Pulse campaign requires at least one shot")
        if not all(isinstance(shot, PulseShotResult) for shot in shots):
            raise TypeError("Pulse campaign shots must be PulseShotResult values")
        shot_indices = tuple(shot.shot_index for shot in shots)
        if len(set(shot_indices)) != len(shot_indices):
            raise ValueError("Pulse campaign shot indices must be unique")
        object.__setattr__(self, "shots", shots)


def _baseline_values(
    x: np.ndarray,
    y_oriented: np.ndarray,
    features: sigima_pulse.PulseFeatures,
) -> np.ndarray:
    """Return raw baseline samples using Sigima's resolved X ranges."""
    start_mask = (x >= features.xstartmin) & (x <= features.xstartmax)
    baseline_parts = [y_oriented[start_mask]]
    if SignalShape(features.signal_shape) == SignalShape.SQUARE:
        end_mask = (x >= features.xendmin) & (x <= features.xendmax)
        baseline_parts.append(y_oriented[end_mask])
    baseline = np.concatenate(baseline_parts)
    if baseline.size == 0:
        raise ValueError("Pulse baseline ranges contain no samples")
    return baseline


def _initial_baseline_values(
    x: np.ndarray,
    y: np.ndarray,
    parameters: PulseAnalysisParameters,
) -> np.ndarray:
    """Return the configured or automatic initial baseline samples."""
    start_range = parameters.start_range
    if start_range is None:
        start_range = sigima_pulse.get_start_range(x, parameters.baseline_fraction)
    baseline = y[(x >= start_range[0]) & (x <= start_range[1])]
    if baseline.size == 0:
        raise ValueError("Pulse start baseline range contains no samples")
    return baseline


def _snr_db(amplitude: float, noise_rms: float) -> float:
    """Return amplitude SNR in dB with explicit zero-noise behavior."""
    if noise_rms == 0.0:
        return math.inf if amplitude > 0.0 else -math.inf
    if amplitude == 0.0:
        return -math.inf
    return 20.0 * math.log10(amplitude / noise_rms)


def _count_saturated_samples(
    y: np.ndarray,
    parameters: PulseAnalysisParameters,
) -> int:
    """Count samples at configured acquisition bounds."""
    saturated = np.zeros(y.shape, dtype=bool)
    for bound in (parameters.saturation_min, parameters.saturation_max):
        if bound is not None:
            saturated |= np.isclose(
                y,
                bound,
                rtol=0.0,
                atol=parameters.saturation_tolerance,
            )
    return int(np.count_nonzero(saturated))


def _count_pulse_regions(
    y_oriented: np.ndarray,
    baseline_mean: float,
    amplitude: float,
    parameters: PulseAnalysisParameters,
) -> int:
    """Count separated above-threshold regions with a minimum sample width."""
    threshold = amplitude * parameters.multiple_pulse_threshold_ratio
    above_threshold = y_oriented - baseline_mean >= threshold
    boundaries = np.diff(np.pad(above_threshold.astype(np.int8), (1, 1)))
    starts = np.flatnonzero(boundaries == 1)
    stops = np.flatnonzero(boundaries == -1)
    widths = stops - starts
    return int(np.count_nonzero(widths >= parameters.minimum_pulse_samples))


def analyze_pulse(
    x: np.ndarray,
    y: np.ndarray,
    *,
    shot_index: int,
    title: str,
    parameters: PulseAnalysisParameters,
) -> PulseShotResult:
    """Analyze one pulse while preserving Sigima as the feature authority."""
    try:
        with warnings.catch_warnings(record=True) as feature_warnings:
            warnings.simplefilter("always")
            features = sigima_pulse.extract_pulse_features(
                x,
                y,
                start_range=parameters.start_range,
                end_range=parameters.end_range,
                start_ratio=parameters.start_ratio,
                stop_ratio=parameters.stop_ratio,
                signal_shape=parameters.signal_shape,
                fraction=parameters.baseline_fraction,
                denoise=parameters.denoise,
            )
    except sigima_pulse.PulseAnalysisError as error:
        baseline = _initial_baseline_values(x, y, parameters)
        baseline_mean = float(np.mean(baseline))
        baseline_noise_rms = float(
            np.sqrt(np.mean(np.square(baseline - baseline_mean)))
        )
        amplitude = float(np.ptp(y))
        return PulseShotResult(
            shot_index=shot_index,
            title=title,
            features=None,
            amplitude=amplitude,
            integral=None,
            baseline_noise_rms=baseline_noise_rms,
            snr_db=_snr_db(amplitude, baseline_noise_rms),
            status=PulseStatus.NO_PULSE,
            reason=f"No pulse: Sigima feature extraction failed ({error})",
            diagnostic_values={
                "amplitude": amplitude,
                "minimum_amplitude": parameters.minimum_amplitude,
                "baseline_noise_rms": baseline_noise_rms,
                "snr_db": _snr_db(amplitude, baseline_noise_rms),
                "minimum_snr_db": parameters.minimum_snr_db,
                "saturated_samples": _count_saturated_samples(y, parameters),
                "pulse_regions": 0,
                "extraction_error": str(error),
                "feature_warnings": (),
            },
        )
    y_oriented = y * features.polarity
    baseline = _baseline_values(x, y_oriented, features)
    baseline_mean = float(np.mean(baseline))
    baseline_noise_rms = float(np.sqrt(np.mean(np.square(baseline - baseline_mean))))
    integral = float(scipy.integrate.trapezoid(y_oriented - baseline_mean, x))
    snr_db = _snr_db(features.amplitude, baseline_noise_rms)
    saturated_samples = _count_saturated_samples(y, parameters)
    pulse_regions = _count_pulse_regions(
        y_oriented,
        baseline_mean,
        features.amplitude,
        parameters,
    )

    if features.amplitude < parameters.minimum_amplitude:
        status = PulseStatus.NO_PULSE
        reason = (
            f"No pulse: amplitude {features.amplitude:g} is below the minimum "
            f"{parameters.minimum_amplitude:g}"
        )
    elif saturated_samples >= parameters.minimum_saturated_samples:
        status = PulseStatus.SATURATED
        reason = (
            f"Saturated: {saturated_samples} samples reached configured "
            "acquisition bounds"
        )
    elif pulse_regions > 1:
        status = PulseStatus.MULTIPLE_PULSES
        reason = f"Multiple pulses: {pulse_regions} separated regions were detected"
    elif snr_db < parameters.minimum_snr_db:
        status = PulseStatus.LOW_SNR
        reason = (
            f"Low SNR: {snr_db:g} dB is below the minimum "
            f"{parameters.minimum_snr_db:g} dB"
        )
    else:
        status = PulseStatus.VALID
        reason = "Pulse passed configured single-shot checks"

    return PulseShotResult(
        shot_index=shot_index,
        title=title,
        features=features,
        amplitude=features.amplitude,
        integral=integral,
        baseline_noise_rms=baseline_noise_rms,
        snr_db=snr_db,
        status=status,
        reason=reason,
        diagnostic_values={
            "amplitude": features.amplitude,
            "minimum_amplitude": parameters.minimum_amplitude,
            "baseline_noise_rms": baseline_noise_rms,
            "snr_db": snr_db,
            "minimum_snr_db": parameters.minimum_snr_db,
            "saturated_samples": saturated_samples,
            "minimum_saturated_samples": parameters.minimum_saturated_samples,
            "pulse_regions": pulse_regions,
            "multiple_pulse_threshold_ratio": (
                parameters.multiple_pulse_threshold_ratio
            ),
            "feature_warnings": tuple(
                str(warning.message) for warning in feature_warnings
            ),
        },
    )


def _mark_amplitude_outliers(
    shots: Sequence[PulseShotResult],
    parameters: PulseAnalysisParameters,
) -> tuple[PulseShotResult, ...]:
    """Mark valid amplitude outliers with a robust modified Z-score."""
    valid = tuple(shot for shot in shots if shot.status is PulseStatus.VALID)
    if len(valid) < parameters.minimum_outlier_shots:
        return tuple(shots)
    amplitudes = np.array([shot.amplitude for shot in valid])
    median = float(np.median(amplitudes))
    median_absolute_deviation = float(np.median(np.abs(amplitudes - median)))
    if median_absolute_deviation == 0.0:
        return tuple(shots)
    scores = 0.6744897501960817 * (amplitudes - median) / median_absolute_deviation
    score_by_index = {
        shot.shot_index: float(score) for shot, score in zip(valid, scores)
    }
    marked: list[PulseShotResult] = []
    for shot in shots:
        score = score_by_index.get(shot.shot_index)
        if score is None or abs(score) <= parameters.outlier_modified_zscore:
            marked.append(shot)
            continue
        details = dict(shot.diagnostic_values)
        details.update(
            {
                "outlier_modified_zscore": abs(score),
                "outlier_threshold": parameters.outlier_modified_zscore,
                "amplitude_median": median,
                "amplitude_mad": median_absolute_deviation,
            }
        )
        marked.append(
            dataclasses.replace(
                shot,
                status=PulseStatus.OUTLIER,
                reason=(
                    f"Amplitude outlier: modified Z-score {abs(score):g} exceeds "
                    f"{parameters.outlier_modified_zscore:g}"
                ),
                diagnostic_values=details,
            )
        )
    return tuple(marked)


def analyze_pulse_campaign(
    acquisitions: Sequence[PulseAcquisition],
    parameters: PulseAnalysisParameters,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> PulseCampaignResult:
    """Analyze an ordered single-channel campaign without materializing a stack."""
    acquisitions = tuple(acquisitions)
    if not acquisitions:
        raise ValueError("Pulse campaign requires at least one acquisition")
    if not all(isinstance(item, PulseAcquisition) for item in acquisitions):
        raise TypeError("Pulse campaign requires PulseAcquisition values")
    shots: list[PulseShotResult] = []
    total = len(acquisitions)
    for index, acquisition in enumerate(acquisitions, start=1):
        shots.append(
            analyze_pulse(
                acquisition.x,
                acquisition.y,
                shot_index=(
                    index if acquisition.shot_index is None else acquisition.shot_index
                ),
                title=acquisition.title,
                parameters=parameters,
            )
        )
        if progress_callback is not None:
            progress_callback(index, total)
    return PulseCampaignResult(_mark_amplitude_outliers(shots, parameters))


__all__ = [
    "PulseAcquisition",
    "PulseAnalysisParameters",
    "PulseCampaignResult",
    "PulseShotResult",
    "PulseStatus",
    "analyze_pulse",
    "analyze_pulse_campaign",
]
