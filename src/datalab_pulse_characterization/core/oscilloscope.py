"""Simulated oscilloscope: pulse sources, time base and digitizing front end."""

from __future__ import annotations

import dataclasses
import enum
import math

import numpy as np

from .step_response import second_order_step

#: Horizontal and vertical divisions of the oscilloscope screen
HORIZONTAL_DIVISIONS = 10
VERTICAL_DIVISIONS = 8
#: Longest record, in samples
MAX_RECORD_LENGTH = 1_000_000
#: Ratio between a Gaussian's FWHM and its standard deviation
FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
#: Rise and fall width factors of asymmetric pulses
ASYMMETRIC_RISE_FACTOR = 0.65
ASYMMETRIC_FALL_FACTOR = 1.6


def _check_positive(value: float, name: str) -> None:
    """Validate a positive finite number."""
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _check_nonnegative(value: float, name: str) -> None:
    """Validate a non-negative finite number."""
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be non-negative")


@dataclasses.dataclass(frozen=True)
class ScopeChannel:
    """Vertical settings of one oscilloscope channel.

    The screen shows ``VERTICAL_DIVISIONS`` divisions centered on
    ``offset_v``; the ADC codes this range.
    """

    volts_per_div: float = 0.1
    offset_v: float = 0.0

    def __post_init__(self) -> None:
        """Validate the channel settings."""
        _check_positive(self.volts_per_div, "Volts per division")
        if not math.isfinite(self.offset_v):
            raise ValueError("Offset must be finite")

    @property
    def screen_range(self) -> tuple[float, float]:
        """Return the lowest and highest voltages coded by the ADC."""
        half_range = 0.5 * VERTICAL_DIVISIONS * self.volts_per_div
        return self.offset_v - half_range, self.offset_v + half_range


@dataclasses.dataclass(frozen=True)
class OscilloscopeSettings:
    """Time base, channels and ADC of the oscilloscope (times in ns)."""

    time_per_div_ns: float = 10.0
    sample_rate_gsps: float = 5.0
    trigger_position: float = 0.2
    ch1: ScopeChannel = ScopeChannel(0.1, 0.3)
    ch2: ScopeChannel = ScopeChannel(0.1, 0.3)
    adc_bits: int = 8
    noise_v: float = 0.005

    def __post_init__(self) -> None:
        """Validate the time base and the ADC."""
        _check_positive(self.time_per_div_ns, "Time per division")
        _check_positive(self.sample_rate_gsps, "Sample rate")
        if not 0.0 <= self.trigger_position < 1.0:
            raise ValueError("Trigger position must be between 0 and 100 %")
        if not 4 <= self.adc_bits <= 16:
            raise ValueError("ADC resolution must be between 4 and 16 bits")
        _check_nonnegative(self.noise_v, "Noise")
        if not 21 <= self.record_length <= MAX_RECORD_LENGTH:
            raise ValueError(
                f"The record must hold between 21 and {MAX_RECORD_LENGTH} samples "
                f"(now {self.record_length}): change the time base or the sample "
                "rate"
            )

    @property
    def record_length(self) -> int:
        """Return the number of samples of one record."""
        duration = HORIZONTAL_DIVISIONS * self.time_per_div_ns
        return int(round(duration * self.sample_rate_gsps))

    def time_axis(self) -> np.ndarray:
        """Return sample times, in ns, the trigger being at t = 0."""
        count = self.record_length
        start = -self.trigger_position * count / self.sample_rate_gsps
        return start + np.arange(count) / self.sample_rate_gsps

    def digitize(self, y: np.ndarray, channel: ScopeChannel) -> np.ndarray:
        """Clip a waveform to the screen of a channel and quantize it."""
        low, high = channel.screen_range
        step = (high - low) / (2**self.adc_bits - 1)
        codes = np.clip(np.round((y - low) / step), 0, 2**self.adc_bits - 1)
        return low + codes * step


class SourceKind(str, enum.Enum):
    """Signal source connected to the oscilloscope."""

    LASER_PULSE = "laser-pulse"
    STEP = "step"
    PULSE_PAIR = "pulse-pair"


@dataclasses.dataclass(frozen=True)
class PulseSource:
    """Source connected to the oscilloscope, triggered at t = 0 (times in ns).

    Common settings apply to every source. A laser pulse has a Gaussian or
    asymmetric profile and may drift over an acquisition. An amplifier step
    is the response of a second-order system. A pulse pair feeds a reference
    pulse to CH1 and the delayed pulse of a detector to CH2.
    """

    kind: SourceKind = SourceKind.LASER_PULSE
    amplitude_v: float = 0.5
    amplitude_jitter_percent: float = 1.0
    timing_jitter_ns: float = 0.05
    pulse_width_ns: float = 2.0
    asymmetric: bool = False
    timing_drift_ns: float = 0.0
    amplitude_drift_percent: float = 0.0
    natural_frequency_mhz: float = 80.0
    damping_ratio: float = 0.35
    delay_ns: float = 37.5
    detector_gain: float = 0.5
    detector_width_ns: float = 6.0
    detector_jitter_ns: float = 0.2

    def __post_init__(self) -> None:
        """Validate the source settings."""
        object.__setattr__(self, "kind", SourceKind(self.kind))
        for name, value in (
            ("Amplitude", self.amplitude_v),
            ("Pulse width", self.pulse_width_ns),
            ("Natural frequency", self.natural_frequency_mhz),
            ("Detector gain", self.detector_gain),
            ("Detector pulse width", self.detector_width_ns),
        ):
            _check_positive(value, name)
        for name, value in (
            ("Amplitude jitter", self.amplitude_jitter_percent),
            ("Timing jitter", self.timing_jitter_ns),
            ("Detector jitter", self.detector_jitter_ns),
        ):
            _check_nonnegative(value, name)
        for name, value in (
            ("Timing drift", self.timing_drift_ns),
            ("Amplitude drift", self.amplitude_drift_percent),
            ("Delay", self.delay_ns),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0.0 < self.damping_ratio < 1.0:
            raise ValueError("Damping ratio must be between 0 and 1")

    @property
    def channel_count(self) -> int:
        """Return the number of channels fed by the source."""
        return 2 if self.kind is SourceKind.PULSE_PAIR else 1

    def waveforms(
        self,
        t: np.ndarray,
        rng: np.random.Generator,
        campaign_fraction: float = 0.0,
    ) -> tuple[np.ndarray, ...]:
        """Return the noise-free waveform of each channel for one trigger.

        Args:
            t: sample times, in ns
            rng: random generator of this trigger
            campaign_fraction: position of the trigger in the acquisition,
             from -0.5 (first) to 0.5 (last), scaling the drifts
        """
        trigger_jitter = rng.normal(0.0, self.timing_jitter_ns)
        amplitude = self.amplitude_v * (
            1.0
            + 0.01 * self.amplitude_drift_percent * campaign_fraction
            + rng.normal(0.0, 0.01 * self.amplitude_jitter_percent)
        )
        if self.kind is SourceKind.STEP:
            natural_frequency = 1e-3 * self.natural_frequency_mhz
            return (
                amplitude
                * second_order_step(
                    t - trigger_jitter, natural_frequency, self.damping_ratio
                ),
            )
        sigma = self.pulse_width_ns / FWHM_PER_SIGMA
        if self.kind is SourceKind.LASER_PULSE:
            center = trigger_jitter + self.timing_drift_ns * campaign_fraction
            rise, fall = (
                (ASYMMETRIC_RISE_FACTOR, ASYMMETRIC_FALL_FACTOR)
                if self.asymmetric
                else (1.0, 1.0)
            )
            return (amplitude * _pulse(t, center, sigma * rise, sigma * fall),)
        detector_center = (
            trigger_jitter + self.delay_ns + rng.normal(0.0, self.detector_jitter_ns)
        )
        detector_sigma = self.detector_width_ns / FWHM_PER_SIGMA
        return (
            amplitude * _pulse(t, trigger_jitter, sigma, sigma),
            amplitude
            * self.detector_gain
            * _pulse(
                t,
                detector_center,
                detector_sigma * ASYMMETRIC_RISE_FACTOR,
                detector_sigma * ASYMMETRIC_FALL_FACTOR,
            ),
        )


def _pulse(t: np.ndarray, center: float, rise: float, fall: float) -> np.ndarray:
    """Return a unit-height pulse with Gaussian rising and falling edges."""
    scale = np.where(t < center, rise, fall)
    return np.exp(-0.5 * np.square((t - center) / scale))


def acquire_traces(
    source: PulseSource,
    scope: OscilloscopeSettings,
    trigger_count: int,
    seed: np.random.SeedSequence,
) -> tuple[np.ndarray, list[tuple[np.ndarray, ...]]]:
    """Acquire digitized traces for successive triggers.

    Args:
        source: source connected to the oscilloscope
        scope: oscilloscope settings
        trigger_count: number of triggers
        seed: seed of the acquisition, spawning one stream per trigger

    Returns:
        Sample times (ns), then the traces of each trigger, one per channel
    """
    if trigger_count < 1:
        raise ValueError("Trigger count must be positive")
    t = scope.time_axis()
    channels = (scope.ch1, scope.ch2)[: source.channel_count]
    traces: list[tuple[np.ndarray, ...]] = []
    for index, child in enumerate(seed.spawn(trigger_count)):
        rng = np.random.default_rng(child)
        fraction = 0.0 if trigger_count == 1 else index / (trigger_count - 1) - 0.5
        waveforms = source.waveforms(t, rng, fraction)
        traces.append(
            tuple(
                scope.digitize(
                    waveform + rng.normal(0.0, scope.noise_v, t.size), channel
                )
                for waveform, channel in zip(waveforms, channels)
            )
        )
    return t, traces


__all__ = [
    "HORIZONTAL_DIVISIONS",
    "MAX_RECORD_LENGTH",
    "VERTICAL_DIVISIONS",
    "OscilloscopeSettings",
    "PulseSource",
    "ScopeChannel",
    "SourceKind",
    "acquire_traces",
]
