"""Deterministic step acquisitions of a second-order system."""

from __future__ import annotations

import dataclasses
import math

import numpy as np
from sigima.enums import SignalShape

from .campaign import PulseAcquisition, PulseAnalysisParameters
from .step_response import second_order_bandwidth, second_order_step

#: Ratio between the 10-90 % rise time and the sigma of a Gaussian response.
GAUSSIAN_RISE_TIME_PER_SIGMA = 2.0 * 1.2815515655446004


@dataclasses.dataclass(frozen=True)
class StepSimulationParameters:
    """Repeated step acquisitions of an underdamped second-order system.

    The device under test is a second-order low-pass system with natural
    frequency ``natural_frequency`` (cycles per X unit) and damping ratio
    ``damping_ratio``. The acquisition system adds a Gaussian response whose
    10-90 % rise time is ``instrument_rise_time``, trigger jitter and white
    noise.
    """

    shot_count: int = 64
    sample_count: int = 2001
    x_min: float = 0.0
    x_max: float = 200.0
    step_time: float = 40.0
    baseline: float = 0.0
    amplitude: float = 1.0
    natural_frequency: float = 0.08
    damping_ratio: float = 0.35
    instrument_rise_time: float = 0.7
    white_noise_std: float = 0.01
    timing_jitter_std: float = 0.3
    seed: int = 20261006

    def __post_init__(self) -> None:
        """Validate the scenario before allocating waveforms."""
        for name, value in (
            ("Shot count", self.shot_count),
            ("Samples", self.sample_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 2:
                raise ValueError(f"{name} must be an integer of at least 2")
        if not self.x_min < self.step_time < self.x_max:
            raise ValueError("Step time must lie inside the X range")
        if not 0.0 < self.damping_ratio < 1.0:
            raise ValueError(
                "Damping ratio must be in (0, 1) for an underdamped system"
            )
        for name, value in (
            ("Amplitude", self.amplitude),
            ("Natural frequency", self.natural_frequency),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        for name, value in (
            ("Instrument rise time", self.instrument_rise_time),
            ("White-noise deviation", self.white_noise_std),
            ("Timing-jitter deviation", self.timing_jitter_std),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")


@dataclasses.dataclass(frozen=True)
class StepResponseTruth:
    """Exact parameters of the simulated system, from the noiseless response."""

    natural_frequency: float
    damping_ratio: float
    damped_frequency: float
    bandwidth: float
    device_rise_time: float
    measured_rise_time: float
    overshoot_percent: float
    settling_time: float
    timing_offsets: np.ndarray


@dataclasses.dataclass(frozen=True)
class StepSimulationResult:
    """Synthetic acquisitions, truth, and matching per-shot analysis settings."""

    parameters: StepSimulationParameters
    acquisitions: tuple[PulseAcquisition, ...]
    truth: StepResponseTruth
    analysis_parameters: PulseAnalysisParameters


def _gaussian_smoothed(values: np.ndarray, dx: float, rise_time: float) -> np.ndarray:
    """Convolve with a unit-area Gaussian of the given 10-90 % rise time."""
    if rise_time <= 0.0:
        return values
    sigma = rise_time / GAUSSIAN_RISE_TIME_PER_SIGMA
    half_width = int(math.ceil(5.0 * sigma / dx))
    kernel_x = dx * np.arange(-half_width, half_width + 1)
    kernel = np.exp(-0.5 * (kernel_x / sigma) ** 2)
    kernel /= np.sum(kernel)
    padded = np.pad(values, half_width, mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _noiseless_response(
    x: np.ndarray,
    step_time: float,
    parameters: StepSimulationParameters,
) -> np.ndarray:
    """Return the system and instrument response to a unit step."""
    dx = float(x[1] - x[0])
    response = second_order_step(
        x - step_time,
        parameters.natural_frequency,
        parameters.damping_ratio,
    )
    return _gaussian_smoothed(response, dx, parameters.instrument_rise_time)


def _crossing(x: np.ndarray, y: np.ndarray, level: float) -> float:
    """Return the first upward crossing of a level by linear interpolation."""
    index = int(np.flatnonzero((y[:-1] < level) & (y[1:] >= level))[0])
    return float(
        x[index]
        + (level - y[index]) * (x[index + 1] - x[index]) / (y[index + 1] - y[index])
    )


def _truth(parameters: StepSimulationParameters) -> tuple[float, float, float, float]:
    """Return device and measured rise times, overshoot and settling time."""
    duration = parameters.x_max - parameters.x_min
    fine_x = np.linspace(-0.2 * duration, 0.8 * duration, 40_001)
    device = second_order_step(
        fine_x, parameters.natural_frequency, parameters.damping_ratio
    )
    measured = _gaussian_smoothed(
        device, float(fine_x[1] - fine_x[0]), parameters.instrument_rise_time
    )
    device_rise = _crossing(fine_x, device, 0.9) - _crossing(fine_x, device, 0.1)
    measured_rise = _crossing(fine_x, measured, 0.9) - _crossing(fine_x, measured, 0.1)
    overshoot = 100.0 * (float(np.max(measured)) - 1.0)
    mid = _crossing(fine_x, measured, 0.5)
    outside = np.flatnonzero(np.abs(measured - 1.0) > 0.02)
    settling = float(fine_x[outside[-1] + 1]) - mid
    return device_rise, measured_rise, overshoot, settling


def simulate_step_campaign(
    parameters: StepSimulationParameters | None = None,
) -> StepSimulationResult:
    """Generate repeated step acquisitions and the exact system truth."""
    parameters = parameters or StepSimulationParameters()
    x = np.linspace(parameters.x_min, parameters.x_max, parameters.sample_count)
    shot_seeds = np.random.SeedSequence(parameters.seed).spawn(parameters.shot_count)
    acquisitions: list[PulseAcquisition] = []
    offsets: list[float] = []
    for shot_index, seed_sequence in enumerate(shot_seeds, start=1):
        rng = np.random.default_rng(seed_sequence)
        offset = float(rng.normal(0.0, parameters.timing_jitter_std))
        response = _noiseless_response(x, parameters.step_time + offset, parameters)
        y = (
            parameters.baseline
            + parameters.amplitude * response
            + rng.normal(0.0, parameters.white_noise_std, size=x.shape)
        )
        acquisitions.append(
            PulseAcquisition(
                x=x,
                y=y,
                title=f"Step shot {shot_index:03d}",
                shot_index=shot_index,
            )
        )
        offsets.append(offset)
    device_rise, measured_rise, overshoot, settling = _truth(parameters)
    damped_frequency = parameters.natural_frequency * math.sqrt(
        1.0 - parameters.damping_ratio**2
    )
    offset_array = np.array(offsets)
    offset_array.setflags(write=False)
    duration = parameters.x_max - parameters.x_min
    return StepSimulationResult(
        parameters=parameters,
        acquisitions=tuple(acquisitions),
        truth=StepResponseTruth(
            natural_frequency=parameters.natural_frequency,
            damping_ratio=parameters.damping_ratio,
            damped_frequency=damped_frequency,
            bandwidth=second_order_bandwidth(
                parameters.natural_frequency, parameters.damping_ratio
            ),
            device_rise_time=device_rise,
            measured_rise_time=measured_rise,
            overshoot_percent=overshoot,
            settling_time=settling,
            timing_offsets=offset_array,
        ),
        analysis_parameters=PulseAnalysisParameters(
            start_range=(parameters.x_min, parameters.x_min + 0.1 * duration),
            end_range=(parameters.x_max - 0.2 * duration, parameters.x_max),
            signal_shape=SignalShape.STEP,
            denoise=False,
            minimum_amplitude=0.25 * parameters.amplitude,
            minimum_snr_db=20.0,
        ),
    )


__all__ = [
    "StepResponseTruth",
    "StepSimulationParameters",
    "StepSimulationResult",
    "simulate_step_campaign",
]
