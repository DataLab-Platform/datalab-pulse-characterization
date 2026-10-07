"""IEEE 181-inspired step-response parameters of an averaged transition."""

from __future__ import annotations

import dataclasses
import math

import numpy as np


@dataclasses.dataclass(frozen=True)
class StepResponseParameters:
    """Explicit, non-normative settings for step-response analysis.

    ``instrument_rise_time`` (X units, 0 disables) removes the acquisition
    system contribution in quadrature, which holds for Gaussian-like responses.
    """

    lower_ratio: float = 0.1
    upper_ratio: float = 0.9
    settling_tolerance: float = 0.02
    histogram_bin_count: int = 200
    instrument_rise_time: float = 0.0
    ringing_noise_factor: float = 4.0

    def __post_init__(self) -> None:
        """Validate settings independently from a waveform."""
        if not 0.0 < self.lower_ratio < 0.5 < self.upper_ratio < 1.0:
            raise ValueError(
                "Reference levels must satisfy 0 < lower < 0.5 < upper < 1"
            )
        if not 0.0 < self.settling_tolerance < 0.5:
            raise ValueError("Settling tolerance must be in (0, 0.5)")
        if (
            isinstance(self.histogram_bin_count, bool)
            or not isinstance(self.histogram_bin_count, int)
            or self.histogram_bin_count < 10
        ):
            raise ValueError("Histogram bin count must be an integer of at least 10")
        if (
            not math.isfinite(self.instrument_rise_time)
            or self.instrument_rise_time < 0
        ):
            raise ValueError("Instrument rise time must be finite and non-negative")
        if (
            not math.isfinite(self.ringing_noise_factor)
            or self.ringing_noise_factor <= 0
        ):
            raise ValueError("Ringing noise factor must be finite and positive")


@dataclasses.dataclass(frozen=True)
class StepResponseResult:
    """Transition and second-order parameters of one step waveform.

    Times and frequencies use the waveform X unit and its inverse. ``NaN``
    marks a quantity that the record does not allow to measure (no settling
    within the record, no measurable ringing).
    """

    low_level: float
    high_level: float
    amplitude: float
    polarity: int
    noise_rms: float
    lower_crossing: float
    mid_crossing: float
    upper_crossing: float
    rise_time: float
    corrected_rise_time: float
    overshoot_percent: float
    undershoot_percent: float
    preshoot_percent: float
    settling_time: float
    ringing_extrema_times: np.ndarray
    ringing_extrema_values: np.ndarray
    damped_frequency: float
    damping_ratio_from_overshoot: float
    damping_ratio_from_decrement: float
    natural_frequency: float
    bandwidth_second_order: float
    bandwidth_single_pole: float

    @property
    def damping_ratio(self) -> float:
        """Return the decrement-based ratio, or the overshoot-based one."""
        if math.isfinite(self.damping_ratio_from_decrement):
            return self.damping_ratio_from_decrement
        return self.damping_ratio_from_overshoot


def _readonly(array: np.ndarray) -> np.ndarray:
    """Mark an owned result array as read-only and return it."""
    array.setflags(write=False)
    return array


def _state_level(samples: np.ndarray, bin_count: int) -> float:
    """Return the histogram mode refined by the mean of its neighborhood."""
    counts, edges = np.histogram(samples, bins=bin_count)
    mode = int(np.argmax(counts))
    lower = edges[max(mode - 1, 0)]
    upper = edges[min(mode + 2, edges.size - 1)]
    selected = samples[(samples >= lower) & (samples <= upper)]
    return float(np.mean(selected))


def _first_crossing(x: np.ndarray, y: np.ndarray, level: float, start: int) -> float:
    """Return the first upward crossing of ``level`` at or after ``start``."""
    above = y >= level
    candidates = np.flatnonzero(~above[start:-1] & above[start + 1 :]) + start
    if candidates.size == 0:
        return math.nan
    index = int(candidates[0])
    y0, y1 = y[index], y[index + 1]
    return float(x[index] + (level - y0) * (x[index + 1] - x[index]) / (y1 - y0))


def damping_ratio_from_overshoot(overshoot_fraction: float) -> float:
    """Return the second-order damping ratio producing a given overshoot."""
    if not 0.0 < overshoot_fraction < 1.0:
        return math.nan
    log_overshoot = math.log(overshoot_fraction)
    return -log_overshoot / math.sqrt(math.pi**2 + log_overshoot**2)


def second_order_bandwidth(natural_frequency: float, damping_ratio: float) -> float:
    """Return the -3 dB bandwidth of a second-order low-pass system."""
    zeta2 = damping_ratio**2
    return natural_frequency * math.sqrt(
        1.0 - 2.0 * zeta2 + math.sqrt(4.0 * zeta2**2 - 4.0 * zeta2 + 2.0)
    )


def second_order_step(
    tau: np.ndarray,
    natural_frequency: float,
    damping_ratio: float,
) -> np.ndarray:
    """Return the unit step response of an underdamped second-order system."""
    omega_n = 2.0 * math.pi * natural_frequency
    root = math.sqrt(1.0 - damping_ratio**2)
    omega_d = omega_n * root
    t = np.maximum(tau, 0.0)
    response = 1.0 - np.exp(-damping_ratio * omega_n * t) * (
        np.cos(omega_d * t) + damping_ratio / root * np.sin(omega_d * t)
    )
    return np.where(tau > 0.0, response, 0.0)


def _ringing_extrema(
    x: np.ndarray,
    error: np.ndarray,
    start: int,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return lobe extrema and bounding zero crossings of the settling error."""
    signs = np.sign(error[start:])
    changes = np.flatnonzero(signs[:-1] * signs[1:] < 0) + start
    crossings = [
        float(x[i] + (0.0 - error[i]) * (x[i + 1] - x[i]) / (error[i + 1] - error[i]))
        for i in changes
    ]
    times: list[float] = []
    values: list[float] = []
    kept_crossings: list[float] = []
    for lobe_start, lobe_stop, left, right in zip(
        changes[:-1], changes[1:], crossings[:-1], crossings[1:]
    ):
        lobe = error[lobe_start + 1 : lobe_stop + 1]
        index = int(np.argmax(np.abs(lobe)))
        value = float(lobe[index])
        if abs(value) < threshold:
            break
        times.append(float(x[lobe_start + 1 + index]))
        values.append(value)
        if not kept_crossings:
            kept_crossings.append(left)
        kept_crossings.append(right)
    return np.array(times), np.array(values), np.array(kept_crossings)


def analyze_step_response(
    x: np.ndarray,
    y: np.ndarray,
    parameters: StepResponseParameters | None = None,
    *,
    baseline_stop: float | None = None,
) -> StepResponseResult:
    """Measure transition duration, aberrations, settling and ringing.

    State levels use the histogram mode of each half of the waveform range
    (IEEE 181 histogram method). Ringing is measured on the settling error
    ``y - high`` between its zero crossings: the half-period gives the damped
    frequency and the logarithmic decrement of successive extrema gives the
    damping ratio of an equivalent second-order system.

    Args:
        x: Strictly increasing time axis
        y: Step waveform, typically an average of aligned acquisitions
        parameters: Reference levels and tolerances
        baseline_stop: End of the pre-transition window used for the noise
         estimate; defaults to the first 10 % of the record

    Returns:
        Step-response metrics in the X unit and its inverse

    Raises:
        ValueError: If no transition between two distinct states is found
    """
    parameters = parameters or StepResponseParameters()
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or x.size < 20:
        raise ValueError("Step analysis requires equal 1D arrays of length >= 20")
    polarity = 1 if np.mean(y[-x.size // 10 :]) >= np.mean(y[: x.size // 10]) else -1
    oriented = polarity * y
    middle = 0.5 * (float(np.min(oriented)) + float(np.max(oriented)))
    low_level = _state_level(
        oriented[oriented < middle], parameters.histogram_bin_count
    )
    high_level = _state_level(
        oriented[oriented >= middle], parameters.histogram_bin_count
    )
    amplitude = high_level - low_level
    if not amplitude > 0.0:
        raise ValueError("Step analysis found no transition between two states")
    if baseline_stop is None:
        baseline_stop = float(x[0] + 0.1 * (x[-1] - x[0]))
    baseline = oriented[x <= baseline_stop]
    noise_rms = float(np.std(baseline, ddof=1)) if baseline.size > 1 else 0.0

    mid_crossing = _first_crossing(x, oriented, low_level + 0.5 * amplitude, 0)
    if not math.isfinite(mid_crossing):
        raise ValueError("Step analysis found no 50 % crossing")
    mid_index = int(np.searchsorted(x, mid_crossing))
    # Search backward-safe crossings from the pre-transition region.
    search_start = int(np.flatnonzero(x <= baseline_stop)[-1]) if baseline.size else 0
    lower_crossing = _first_crossing(
        x, oriented, low_level + parameters.lower_ratio * amplitude, search_start
    )
    upper_crossing = _first_crossing(
        x, oriented, low_level + parameters.upper_ratio * amplitude, search_start
    )
    rise_time = upper_crossing - lower_crossing
    instrument = parameters.instrument_rise_time
    corrected_rise_time = (
        math.sqrt(rise_time**2 - instrument**2)
        if instrument > 0.0 and rise_time > instrument
        else (rise_time if instrument == 0.0 else math.nan)
    )

    after = oriented[mid_index:]
    before = oriented[:mid_index]
    overshoot_percent = 100.0 * max(float(np.max(after)) - high_level, 0.0) / amplitude
    peak_index = mid_index + int(np.argmax(after))
    undershoot_percent = (
        100.0 * max(high_level - float(np.min(oriented[peak_index:])), 0.0) / amplitude
    )
    preshoot_percent = (
        100.0 * max(low_level - float(np.min(before)), 0.0) / amplitude
        if before.size
        else 0.0
    )

    error = oriented - high_level
    outside = np.flatnonzero(
        np.abs(error[mid_index:]) > parameters.settling_tolerance * amplitude
    )
    if outside.size == 0:
        settling_time = 0.0
    elif mid_index + int(outside[-1]) >= x.size - 1:
        settling_time = math.nan
    else:
        settling_time = float(x[mid_index + int(outside[-1]) + 1]) - mid_crossing

    threshold = max(parameters.ringing_noise_factor * noise_rms, 1e-12 * amplitude)
    extrema_times, extrema_values, crossings = _ringing_extrema(
        x, error, mid_index, threshold
    )
    if crossings.size >= 2:
        half_period = float(np.mean(np.diff(crossings)))
        damped_frequency = 0.5 / half_period
    else:
        damped_frequency = math.nan
    zeta_overshoot = damping_ratio_from_overshoot(overshoot_percent / 100.0)
    if extrema_values.size >= 2:
        slope = np.polyfit(
            np.arange(extrema_values.size),
            np.log(np.abs(extrema_values)),
            1,
        )[0]
        decrement = -float(slope)
        zeta_decrement = (
            decrement / math.sqrt(math.pi**2 + decrement**2)
            if decrement > 0.0
            else math.nan
        )
    else:
        zeta_decrement = math.nan
    zeta = zeta_decrement if math.isfinite(zeta_decrement) else zeta_overshoot
    if math.isfinite(damped_frequency) and math.isfinite(zeta) and zeta < 1.0:
        natural_frequency = damped_frequency / math.sqrt(1.0 - zeta**2)
        bandwidth = second_order_bandwidth(natural_frequency, zeta)
    else:
        natural_frequency = math.nan
        bandwidth = math.nan
    single_pole = (
        0.35 / corrected_rise_time
        if math.isfinite(corrected_rise_time) and corrected_rise_time > 0.0
        else math.nan
    )
    return StepResponseResult(
        low_level=polarity * low_level,
        high_level=polarity * high_level,
        amplitude=amplitude,
        polarity=polarity,
        noise_rms=noise_rms,
        lower_crossing=lower_crossing,
        mid_crossing=mid_crossing,
        upper_crossing=upper_crossing,
        rise_time=rise_time,
        corrected_rise_time=corrected_rise_time,
        overshoot_percent=overshoot_percent,
        undershoot_percent=undershoot_percent,
        preshoot_percent=preshoot_percent,
        settling_time=settling_time,
        ringing_extrema_times=_readonly(extrema_times),
        ringing_extrema_values=_readonly(polarity * extrema_values),
        damped_frequency=damped_frequency,
        damping_ratio_from_overshoot=zeta_overshoot,
        damping_ratio_from_decrement=zeta_decrement,
        natural_frequency=natural_frequency,
        bandwidth_second_order=bandwidth,
        bandwidth_single_pole=single_pole,
    )


__all__ = [
    "StepResponseParameters",
    "StepResponseResult",
    "analyze_step_response",
    "damping_ratio_from_overshoot",
    "second_order_bandwidth",
    "second_order_step",
]
