"""Deterministic two-channel campaigns with common and independent jitter."""

from __future__ import annotations

import dataclasses
import math

import numpy as np
from sigima.enums import SignalShape

from .campaign import PulseAcquisition, PulseAnalysisParameters

#: Distance between a Gaussian center and its 50 % crossing, in sigma.
HALF_MAXIMUM_SIGMA = math.sqrt(2.0 * math.log(2.0))


@dataclasses.dataclass(frozen=True)
class TwoChannelSimulationParameters:
    """A reference pulse and a delayed detector response on two channels.

    Every shot draws one common timing offset (trigger jitter) applied to both
    channels and one independent offset (detector transit-time spread)
    applied to the measured channel only. The detector amplitude follows the
    reference amplitude through ``detector_gain`` with an independent relative
    fluctuation. X values are in nanoseconds.
    """

    shot_count: int = 300
    sample_count: int = 501
    x_min: float = 0.0
    x_max: float = 200.0
    reference_center: float = 50.0
    reference_width: float = 1.5
    reference_amplitude: float = 1.0
    source_fluctuation: float = 0.08
    delay: float = 37.5
    measured_rise_width: float = 2.0
    measured_fall_width: float = 6.0
    detector_gain: float = 0.5
    detector_fluctuation: float = 0.03
    common_jitter_std: float = 1.0
    independent_jitter_std: float = 0.2
    white_noise_std: float = 0.005
    missing_measured_shots: tuple[int, ...] = (57, 188, 240)
    no_pulse_measured_shots: tuple[int, ...] = (101, 266)
    seed: int = 20261007

    def __post_init__(self) -> None:
        """Validate the scenario before allocating waveforms."""
        if isinstance(self.shot_count, bool) or not isinstance(self.shot_count, int):
            raise TypeError("Shot count must be an integer")
        if self.shot_count < 3:
            raise ValueError("Shot count must be at least 3")
        for name, value in (
            ("Reference width", self.reference_width),
            ("Reference amplitude", self.reference_amplitude),
            ("Measured rise width", self.measured_rise_width),
            ("Measured fall width", self.measured_fall_width),
            ("Detector gain", self.detector_gain),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        for name, value in (
            ("Source fluctuation", self.source_fluctuation),
            ("Detector fluctuation", self.detector_fluctuation),
            ("Common jitter", self.common_jitter_std),
            ("Independent jitter", self.independent_jitter_std),
            ("White noise", self.white_noise_std),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        anomalies = self.missing_measured_shots + self.no_pulse_measured_shots
        if len(set(anomalies)) != len(anomalies) or any(
            not 1 <= shot <= self.shot_count for shot in anomalies
        ):
            raise ValueError("Measured-channel anomalies must be unique campaign shots")
        if not (
            self.x_min + 0.15 * (self.x_max - self.x_min)
            < self.reference_center - 6.0 * self.reference_width
            and self.reference_center + self.delay + 4.0 * self.measured_fall_width
            < self.x_max - 0.15 * (self.x_max - self.x_min)
        ):
            raise ValueError("Pulses must stay outside the baseline windows")

    @property
    def cfd_delay(self) -> float:
        """Return the expected difference between the two 50 % crossings."""
        return self.delay - HALF_MAXIMUM_SIGMA * (
            self.measured_rise_width - self.reference_width
        )


@dataclasses.dataclass(frozen=True)
class TwoChannelTruth:
    """Per-shot commanded offsets and amplitudes."""

    common_offsets: np.ndarray
    independent_offsets: np.ndarray
    reference_amplitudes: np.ndarray
    measured_amplitudes: np.ndarray
    cfd_delay: float


@dataclasses.dataclass(frozen=True)
class TwoChannelSimulationResult:
    """Two channels of acquisitions, truth and matching analysis settings."""

    parameters: TwoChannelSimulationParameters
    reference: tuple[PulseAcquisition, ...]
    measured: tuple[PulseAcquisition, ...]
    truth: TwoChannelTruth
    analysis_parameters: PulseAnalysisParameters


def _profile(x: np.ndarray, center: float, rise: float, fall: float) -> np.ndarray:
    """Return a unit-height two-sided Gaussian."""
    scale = np.where(x < center, rise, fall)
    return np.exp(-0.5 * ((x - center) / scale) ** 2)


def _readonly(values: list[float]) -> np.ndarray:
    """Return a read-only float array."""
    array = np.array(values, dtype=float)
    array.setflags(write=False)
    return array


def simulate_two_channel_campaign(
    parameters: TwoChannelSimulationParameters | None = None,
) -> TwoChannelSimulationResult:
    """Generate paired reference and measured acquisitions with exact truth."""
    parameters = parameters or TwoChannelSimulationParameters()
    x = np.linspace(parameters.x_min, parameters.x_max, parameters.sample_count)
    seeds = np.random.SeedSequence(parameters.seed).spawn(parameters.shot_count)
    reference: list[PulseAcquisition] = []
    measured: list[PulseAcquisition] = []
    common: list[float] = []
    independent: list[float] = []
    reference_amplitudes: list[float] = []
    measured_amplitudes: list[float] = []
    for shot_index, seed_sequence in enumerate(seeds, start=1):
        rng = np.random.default_rng(seed_sequence)
        common_offset = float(rng.normal(0.0, parameters.common_jitter_std))
        independent_offset = float(rng.normal(0.0, parameters.independent_jitter_std))
        reference_amplitude = parameters.reference_amplitude * (
            1.0 + float(rng.normal(0.0, parameters.source_fluctuation))
        )
        measured_amplitude = (
            parameters.detector_gain
            * reference_amplitude
            * (1.0 + float(rng.normal(0.0, parameters.detector_fluctuation)))
        )
        if shot_index in parameters.no_pulse_measured_shots:
            measured_amplitude = 0.0
        reference_center = parameters.reference_center + common_offset
        reference_y = reference_amplitude * _profile(
            x,
            reference_center,
            parameters.reference_width,
            parameters.reference_width,
        ) + rng.normal(0.0, parameters.white_noise_std, size=x.shape)
        measured_y = measured_amplitude * _profile(
            x,
            reference_center + parameters.delay + independent_offset,
            parameters.measured_rise_width,
            parameters.measured_fall_width,
        ) + rng.normal(0.0, parameters.white_noise_std, size=x.shape)
        reference.append(
            PulseAcquisition(x, reference_y, f"CH1 shot {shot_index:03d}", shot_index)
        )
        if shot_index not in parameters.missing_measured_shots:
            measured.append(
                PulseAcquisition(
                    x, measured_y, f"CH2 shot {shot_index:03d}", shot_index
                )
            )
        common.append(common_offset)
        independent.append(independent_offset)
        reference_amplitudes.append(reference_amplitude)
        measured_amplitudes.append(measured_amplitude)
    duration = parameters.x_max - parameters.x_min
    return TwoChannelSimulationResult(
        parameters=parameters,
        reference=tuple(reference),
        measured=tuple(measured),
        truth=TwoChannelTruth(
            common_offsets=_readonly(common),
            independent_offsets=_readonly(independent),
            reference_amplitudes=_readonly(reference_amplitudes),
            measured_amplitudes=_readonly(measured_amplitudes),
            cfd_delay=parameters.cfd_delay,
        ),
        analysis_parameters=PulseAnalysisParameters(
            start_range=(parameters.x_min, parameters.x_min + 0.15 * duration),
            end_range=(parameters.x_max - 0.15 * duration, parameters.x_max),
            signal_shape=SignalShape.SQUARE,
            denoise=False,
            minimum_amplitude=0.1 * parameters.detector_gain,
            minimum_snr_db=20.0,
        ),
    )


__all__ = [
    "TwoChannelSimulationParameters",
    "TwoChannelSimulationResult",
    "TwoChannelTruth",
    "simulate_two_channel_campaign",
]
