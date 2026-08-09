"""Deterministic synthetic pulse campaign generation."""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType

import numpy as np
from sigima.enums import SignalShape

from .campaign import PulseAcquisition, PulseAnalysisParameters, PulseStatus


class PulseProfile(str, enum.Enum):
    """Supported synthetic transient profiles."""

    GAUSSIAN = "gaussian"
    ASYMMETRIC = "asymmetric"


class PulseAnomaly(str, enum.Enum):
    """Known anomaly injected into one synthetic acquisition."""

    NONE = "none"
    MISSING = "missing"
    LOW_SNR = "low_snr"
    SATURATED = "saturated"
    MULTIPLE_PULSES = "multiple_pulses"
    OUTLIER = "outlier"


@dataclasses.dataclass(frozen=True)
class PulseSimulationParameters:
    """Configuration for a deterministic single-channel pulse campaign.

    ``baseline_drift`` is the total baseline-offset change from the first to
    the last shot. ``amplitude_drift_fraction`` is the corresponding relative
    peak-to-peak amplitude change. Timing jitter switches from
    ``timing_jitter_std`` to ``late_timing_jitter_std`` after
    ``jitter_transition_shot``.
    """

    shot_count: int = 500
    sample_count: int = 501
    x_min: float = 0.0
    x_max: float = 10.0
    baseline_offset: float = 0.25
    baseline_drift: float = 0.4
    baseline_slope: float = 0.02
    amplitude: float = 4.0
    amplitude_drift_fraction: float = 0.1
    pulse_center: float = 4.5
    pulse_width: float = 0.3
    asymmetric_rise_factor: float = 0.65
    asymmetric_fall_factor: float = 1.6
    white_noise_std: float = 0.05
    low_snr_noise_std: float = 0.6
    timing_jitter_std: float = 0.015
    late_timing_jitter_std: float = 0.08
    jitter_transition_shot: int = 300
    saturation_min: float = -10.0
    saturation_max: float = 10.0
    saturation_amplitude_multiplier: float = 3.0
    outlier_amplitude_multiplier: float = 1.8
    double_pulse_separation: float = 1.5
    double_pulse_amplitude_ratio: float = 0.9
    polarity: int = 1
    profiles: tuple[PulseProfile | str, ...] = (
        PulseProfile.GAUSSIAN,
        PulseProfile.ASYMMETRIC,
    )
    missing_shots: tuple[int, ...] = (37, 233)
    low_snr_shots: tuple[int, ...] = (278, 451)
    saturated_shots: tuple[int, ...] = (89, 377)
    multiple_pulse_shots: tuple[int, ...] = (145, 412)
    outlier_shots: tuple[int, ...] = (120, 320, 487)
    seed: int = 20260809

    def __post_init__(self) -> None:
        """Validate the scenario before allocating acquisition arrays."""
        _validate_positive_integer(self.shot_count, "Shot count")
        _validate_positive_integer(self.sample_count, "Sample count")
        if self.sample_count < 21:
            raise ValueError("Sample count must be at least 21")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("Random seed must be an integer")
        if self.seed < 0:
            raise ValueError("Random seed must be non-negative")
        if self.polarity not in (-1, 1):
            raise ValueError("Pulse polarity must be -1 or 1")

        for name, value in (
            ("X minimum", self.x_min),
            ("X maximum", self.x_max),
            ("Baseline offset", self.baseline_offset),
            ("Baseline drift", self.baseline_drift),
            ("Baseline slope", self.baseline_slope),
            ("Amplitude", self.amplitude),
            ("Amplitude drift fraction", self.amplitude_drift_fraction),
            ("Pulse center", self.pulse_center),
            ("Pulse width", self.pulse_width),
            ("Asymmetric rise factor", self.asymmetric_rise_factor),
            ("Asymmetric fall factor", self.asymmetric_fall_factor),
            ("White-noise deviation", self.white_noise_std),
            ("Low-SNR noise deviation", self.low_snr_noise_std),
            ("Timing-jitter deviation", self.timing_jitter_std),
            ("Late timing-jitter deviation", self.late_timing_jitter_std),
            ("Saturation minimum", self.saturation_min),
            ("Saturation maximum", self.saturation_max),
            ("Saturation amplitude multiplier", self.saturation_amplitude_multiplier),
            ("Outlier amplitude multiplier", self.outlier_amplitude_multiplier),
            ("Double-pulse separation", self.double_pulse_separation),
            ("Double-pulse amplitude ratio", self.double_pulse_amplitude_ratio),
        ):
            _validate_finite(value, name)
        if self.x_min >= self.x_max:
            raise ValueError("X minimum must be below X maximum")
        if not self.x_min < self.pulse_center < self.x_max:
            raise ValueError("Pulse center must lie inside the X range")
        for name, value in (
            ("Amplitude", self.amplitude),
            ("Pulse width", self.pulse_width),
            ("Asymmetric rise factor", self.asymmetric_rise_factor),
            ("Asymmetric fall factor", self.asymmetric_fall_factor),
            ("Saturation amplitude multiplier", self.saturation_amplitude_multiplier),
            ("Outlier amplitude multiplier", self.outlier_amplitude_multiplier),
            ("Double-pulse separation", self.double_pulse_separation),
            ("Double-pulse amplitude ratio", self.double_pulse_amplitude_ratio),
        ):
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
        for name, value in (
            ("Amplitude drift fraction", self.amplitude_drift_fraction),
            ("White-noise deviation", self.white_noise_std),
            ("Low-SNR noise deviation", self.low_snr_noise_std),
            ("Timing-jitter deviation", self.timing_jitter_std),
            ("Late timing-jitter deviation", self.late_timing_jitter_std),
        ):
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative")
        if self.amplitude_drift_fraction >= 2.0:
            raise ValueError("Amplitude drift fraction must be below 2")
        if self.saturation_min >= self.saturation_max:
            raise ValueError("Saturation minimum must be below saturation maximum")
        if self.low_snr_shots and self.low_snr_noise_std <= self.white_noise_std:
            raise ValueError("Low-SNR noise must exceed regular white noise")
        if self.late_timing_jitter_std < self.timing_jitter_std:
            raise ValueError("Late timing jitter must not decrease")
        if (
            isinstance(self.jitter_transition_shot, bool)
            or not isinstance(self.jitter_transition_shot, int)
            or not 1 <= self.jitter_transition_shot <= self.shot_count
        ):
            raise ValueError("Jitter transition shot must belong to the campaign")

        profiles = tuple(PulseProfile(profile) for profile in self.profiles)
        if not profiles:
            raise ValueError("At least one pulse profile is required")
        object.__setattr__(self, "profiles", profiles)

        anomaly_shots: set[int] = set()
        for name, shot_indices in self.anomaly_schedule.items():
            if not isinstance(shot_indices, tuple):
                raise TypeError(f"{name.replace('_', ' ').title()} must be a tuple")
            for shot_index in shot_indices:
                if (
                    isinstance(shot_index, bool)
                    or not isinstance(shot_index, int)
                    or not 1 <= shot_index <= self.shot_count
                ):
                    raise ValueError(
                        f"{name.replace('_', ' ').title()} contains an invalid shot"
                    )
                if shot_index in anomaly_shots:
                    raise ValueError("Synthetic anomaly shot indices must be disjoint")
                anomaly_shots.add(shot_index)
        _validate_classification_envelope(self)

    @property
    def anomaly_schedule(self) -> Mapping[str, tuple[int, ...]]:
        """Return the configured anomaly groups by parameter name."""
        return MappingProxyType(
            {
                "missing_shots": self.missing_shots,
                "low_snr_shots": self.low_snr_shots,
                "saturated_shots": self.saturated_shots,
                "multiple_pulse_shots": self.multiple_pulse_shots,
                "outlier_shots": self.outlier_shots,
            }
        )


@dataclasses.dataclass(frozen=True)
class PulseShotTruth:
    """Exact commanded settings and expected quality state for one shot.

    ``amplitude`` is the commanded profile height after drift and anomaly
    scaling, before white noise and saturation clipping.
    """

    shot_index: int
    profile: PulseProfile
    anomaly: PulseAnomaly
    expected_status: PulseStatus
    baseline_offset: float
    amplitude: float
    center: float
    timing_offset: float
    timing_jitter_std: float
    baseline_noise_std: float


@dataclasses.dataclass(frozen=True)
class PulseSimulationTruth:
    """Ordered truth records for a synthetic pulse campaign."""

    seed: int
    shots: Sequence[PulseShotTruth]

    def __post_init__(self) -> None:
        """Freeze and validate the ordered truth sequence."""
        shots = tuple(self.shots)
        if not shots:
            raise ValueError("Pulse simulation truth requires at least one shot")
        if tuple(shot.shot_index for shot in shots) != tuple(range(1, len(shots) + 1)):
            raise ValueError("Pulse simulation truth must use ordered shot indices")
        object.__setattr__(self, "shots", shots)

    @property
    def invalid_shots(self) -> tuple[PulseShotTruth, ...]:
        """Return shots whose expected status is not valid."""
        return tuple(
            shot for shot in self.shots if shot.expected_status is not PulseStatus.VALID
        )


@dataclasses.dataclass(frozen=True)
class PulseSimulationResult:
    """Synthetic acquisitions, exact truth, and matching analysis settings."""

    parameters: PulseSimulationParameters
    acquisitions: Sequence[PulseAcquisition]
    truth: PulseSimulationTruth
    analysis_parameters: PulseAnalysisParameters

    def __post_init__(self) -> None:
        """Freeze and validate the acquisition sequence."""
        acquisitions = tuple(self.acquisitions)
        if len(acquisitions) != len(self.truth.shots):
            raise ValueError("Simulation acquisitions and truth must have equal length")
        object.__setattr__(self, "acquisitions", acquisitions)


def _validate_positive_integer(value: int, name: str) -> None:
    """Validate a positive built-in integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_finite(value: float, name: str) -> None:
    """Validate one finite real simulator parameter."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


def _validate_classification_envelope(
    parameters: PulseSimulationParameters,
) -> None:
    """Reject custom scenarios whose declared status truth is ambiguous."""
    minimum_amplitude = parameters.amplitude * (
        1.0 - 0.5 * parameters.amplitude_drift_fraction
    )
    maximum_amplitude = parameters.amplitude * (
        1.0 + 0.5 * parameters.amplitude_drift_fraction
    )
    if minimum_amplitude <= 0.25 * parameters.amplitude:
        raise ValueError("Amplitude drift leaves regular pulses below the minimum")

    regular_baseline_noise = math.hypot(
        parameters.white_noise_std,
        0.5 * abs(parameters.baseline_slope),
    )
    if regular_baseline_noise:
        regular_snr_floor = 20.0 * math.log10(
            minimum_amplitude / regular_baseline_noise
        )
        if regular_snr_floor <= 22.0:
            raise ValueError("Regular pulse SNR must retain at least a 2 dB margin")
    if parameters.low_snr_shots:
        low_baseline_noise = math.hypot(
            parameters.low_snr_noise_std,
            0.5 * abs(parameters.baseline_slope),
        )
        low_snr_ceiling = 20.0 * math.log10(maximum_amplitude / low_baseline_noise)
        if low_snr_ceiling >= 18.0:
            raise ValueError("Low-SNR pulses must retain at least a 2 dB margin")

    duration = parameters.x_max - parameters.x_min
    baseline_start_stop = parameters.x_min + 0.15 * duration
    baseline_end_start = parameters.x_max - 0.15 * duration
    profile_extent = (
        3.0
        * parameters.pulse_width
        * max(parameters.asymmetric_rise_factor, parameters.asymmetric_fall_factor)
    )
    jitter_extent = 6.0 * parameters.late_timing_jitter_std
    if parameters.pulse_center - profile_extent - jitter_extent <= baseline_start_stop:
        raise ValueError("Pulse profile may overlap the initial baseline")
    if parameters.multiple_pulse_shots and (
        parameters.pulse_center
        + parameters.double_pulse_separation
        + profile_extent
        + jitter_extent
        >= baseline_end_start
    ):
        raise ValueError("Second pulse may overlap the final baseline")

    if parameters.outlier_shots:
        if parameters.amplitude_drift_fraction == 0.0:
            raise ValueError("Amplitude outliers require non-zero regular drift")
        amplitude_mad = (
            0.25 * (parameters.amplitude * parameters.amplitude_drift_fraction)
            + 3.0 * parameters.white_noise_std
        )
        closest_outlier_amplitude = (
            minimum_amplitude * parameters.outlier_amplitude_multiplier
        )
        conservative_score = (
            0.6744897501960817
            * (closest_outlier_amplitude - parameters.amplitude)
            / amplitude_mad
        )
        if conservative_score <= 5.0:
            raise ValueError("Amplitude outliers need a robust Z-score margin")

    baseline_low = (
        parameters.baseline_offset
        - 0.5 * abs(parameters.baseline_drift)
        - 0.5 * abs(parameters.baseline_slope)
    )
    baseline_high = (
        parameters.baseline_offset
        + 0.5 * abs(parameters.baseline_drift)
        + 0.5 * abs(parameters.baseline_slope)
    )
    non_saturated_multiplier = 1.0
    if parameters.multiple_pulse_shots:
        non_saturated_multiplier = max(
            non_saturated_multiplier,
            1.0 + parameters.double_pulse_amplitude_ratio,
        )
    if parameters.outlier_shots:
        non_saturated_multiplier = max(
            non_saturated_multiplier,
            parameters.outlier_amplitude_multiplier,
        )
    noise_margin = 8.0 * parameters.white_noise_std
    maximum_signal = maximum_amplitude * non_saturated_multiplier
    if parameters.polarity > 0:
        nonsaturated_margin = parameters.saturation_max - (
            baseline_high + maximum_signal
        )
        saturated_excess = (
            baseline_low
            + minimum_amplitude * parameters.saturation_amplitude_multiplier
            - parameters.saturation_max
        )
    else:
        nonsaturated_margin = baseline_low - maximum_signal - parameters.saturation_min
        saturated_excess = parameters.saturation_min - (
            baseline_high
            - minimum_amplitude * parameters.saturation_amplitude_multiplier
        )
    if nonsaturated_margin <= noise_margin:
        raise ValueError("Non-saturated pulses need an eight-sigma ADC margin")
    if parameters.low_snr_shots:
        low_snr_baseline_margin = 8.0 * parameters.low_snr_noise_std
        if (
            parameters.saturation_max - baseline_high <= low_snr_baseline_margin
            or baseline_low - parameters.saturation_min <= low_snr_baseline_margin
        ):
            raise ValueError("Low-SNR baselines need an eight-sigma ADC margin")
    if parameters.saturated_shots and saturated_excess <= noise_margin:
        raise ValueError("Saturated pulses must exceed the ADC bound with margin")


def _anomaly_by_shot(parameters: PulseSimulationParameters) -> dict[int, PulseAnomaly]:
    """Return the configured anomaly assigned to each affected shot."""
    anomaly_by_shot: dict[int, PulseAnomaly] = {}
    groups = (
        (parameters.missing_shots, PulseAnomaly.MISSING),
        (parameters.low_snr_shots, PulseAnomaly.LOW_SNR),
        (parameters.saturated_shots, PulseAnomaly.SATURATED),
        (parameters.multiple_pulse_shots, PulseAnomaly.MULTIPLE_PULSES),
        (parameters.outlier_shots, PulseAnomaly.OUTLIER),
    )
    for shot_indices, anomaly in groups:
        anomaly_by_shot.update({shot_index: anomaly for shot_index in shot_indices})
    return anomaly_by_shot


def _expected_status(anomaly: PulseAnomaly) -> PulseStatus:
    """Map one injected anomaly to its expected explainable status."""
    return {
        PulseAnomaly.NONE: PulseStatus.VALID,
        PulseAnomaly.MISSING: PulseStatus.NO_PULSE,
        PulseAnomaly.LOW_SNR: PulseStatus.LOW_SNR,
        PulseAnomaly.SATURATED: PulseStatus.SATURATED,
        PulseAnomaly.MULTIPLE_PULSES: PulseStatus.MULTIPLE_PULSES,
        PulseAnomaly.OUTLIER: PulseStatus.OUTLIER,
    }[anomaly]


def _profile_values(
    x: np.ndarray,
    center: float,
    width: float,
    profile: PulseProfile,
    parameters: PulseSimulationParameters,
) -> np.ndarray:
    """Return a unit-height Gaussian or two-sided Gaussian profile."""
    if profile is PulseProfile.GAUSSIAN:
        scale = np.full(x.shape, width)
    else:
        scale = np.where(
            x < center,
            width * parameters.asymmetric_rise_factor,
            width * parameters.asymmetric_fall_factor,
        )
    return np.exp(-0.5 * np.square((x - center) / scale))


def _analysis_parameters(
    parameters: PulseSimulationParameters,
) -> PulseAnalysisParameters:
    """Return thresholds matched to the documented synthetic scenario."""
    duration = parameters.x_max - parameters.x_min
    return PulseAnalysisParameters(
        start_range=(parameters.x_min, parameters.x_min + 0.15 * duration),
        end_range=(parameters.x_max - 0.15 * duration, parameters.x_max),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
        minimum_amplitude=0.25 * parameters.amplitude,
        minimum_snr_db=20.0,
        saturation_min=parameters.saturation_min,
        saturation_max=parameters.saturation_max,
        saturation_tolerance=0.0,
        minimum_saturated_samples=3,
        multiple_pulse_threshold_ratio=0.6,
        minimum_pulse_samples=7,
        outlier_modified_zscore=4.0,
        minimum_outlier_shots=20,
    )


def simulate_pulse_campaign(
    parameters: PulseSimulationParameters | None = None,
) -> PulseSimulationResult:
    """Generate deterministic acquisitions and exact per-shot ground truth."""
    if parameters is None:
        parameters = PulseSimulationParameters()
    if not isinstance(parameters, PulseSimulationParameters):
        raise TypeError("Pulse simulation requires PulseSimulationParameters")

    x = np.linspace(
        parameters.x_min,
        parameters.x_max,
        parameters.sample_count,
    )
    midpoint = 0.5 * (parameters.x_min + parameters.x_max)
    duration = parameters.x_max - parameters.x_min
    anomaly_by_shot = _anomaly_by_shot(parameters)
    shot_seeds = np.random.SeedSequence(parameters.seed).spawn(parameters.shot_count)
    acquisitions: list[PulseAcquisition] = []
    truth_shots: list[PulseShotTruth] = []

    for shot_index, seed_sequence in enumerate(shot_seeds, start=1):
        rng = np.random.default_rng(seed_sequence)
        campaign_fraction = (
            0.0
            if parameters.shot_count == 1
            else (shot_index - 1) / (parameters.shot_count - 1)
        )
        centered_fraction = campaign_fraction - 0.5
        baseline_offset = (
            parameters.baseline_offset + parameters.baseline_drift * centered_fraction
        )
        amplitude = parameters.amplitude * (
            1.0 + parameters.amplitude_drift_fraction * centered_fraction
        )
        jitter_std = (
            parameters.timing_jitter_std
            if shot_index <= parameters.jitter_transition_shot
            else parameters.late_timing_jitter_std
        )
        timing_offset = float(rng.normal(0.0, jitter_std))
        center = parameters.pulse_center + timing_offset
        profile = parameters.profiles[(shot_index - 1) % len(parameters.profiles)]
        anomaly = anomaly_by_shot.get(shot_index, PulseAnomaly.NONE)
        noise_std = (
            parameters.low_snr_noise_std
            if anomaly is PulseAnomaly.LOW_SNR
            else parameters.white_noise_std
        )
        baseline = (
            baseline_offset + parameters.baseline_slope * (x - midpoint) / duration
        )
        pulse = _profile_values(
            x,
            center,
            parameters.pulse_width,
            profile,
            parameters,
        )

        if anomaly is PulseAnomaly.MISSING:
            amplitude = 0.0
        elif anomaly is PulseAnomaly.SATURATED:
            amplitude *= parameters.saturation_amplitude_multiplier
        elif anomaly is PulseAnomaly.OUTLIER:
            amplitude *= parameters.outlier_amplitude_multiplier

        signal = parameters.polarity * amplitude * pulse
        if anomaly is PulseAnomaly.MULTIPLE_PULSES:
            second_pulse = _profile_values(
                x,
                center + parameters.double_pulse_separation,
                parameters.pulse_width,
                profile,
                parameters,
            )
            signal += (
                parameters.polarity
                * amplitude
                * parameters.double_pulse_amplitude_ratio
                * second_pulse
            )
        noise = rng.normal(0.0, parameters.white_noise_std, size=x.shape)
        if anomaly is PulseAnomaly.LOW_SNR:
            baseline_mask = (x <= parameters.x_min + 0.15 * duration) | (
                x >= parameters.x_max - 0.15 * duration
            )
            noise[baseline_mask] = rng.normal(
                0.0,
                parameters.low_snr_noise_std,
                size=np.count_nonzero(baseline_mask),
            )
        y = baseline + signal + noise
        np.clip(
            y,
            parameters.saturation_min,
            parameters.saturation_max,
            out=y,
        )

        acquisitions.append(
            PulseAcquisition(
                x=x,
                y=y,
                title=f"Synthetic shot {shot_index:03d}",
                shot_index=shot_index,
            )
        )
        truth_shots.append(
            PulseShotTruth(
                shot_index=shot_index,
                profile=profile,
                anomaly=anomaly,
                expected_status=_expected_status(anomaly),
                baseline_offset=baseline_offset,
                amplitude=amplitude,
                center=center,
                timing_offset=timing_offset,
                timing_jitter_std=jitter_std,
                baseline_noise_std=noise_std,
            )
        )

    truth = PulseSimulationTruth(seed=parameters.seed, shots=truth_shots)
    return PulseSimulationResult(
        parameters=parameters,
        acquisitions=acquisitions,
        truth=truth,
        analysis_parameters=_analysis_parameters(parameters),
    )


__all__ = [
    "PulseAnomaly",
    "PulseProfile",
    "PulseShotTruth",
    "PulseSimulationParameters",
    "PulseSimulationResult",
    "PulseSimulationTruth",
    "simulate_pulse_campaign",
]
