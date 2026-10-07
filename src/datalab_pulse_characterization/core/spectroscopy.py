"""Pulse-height (energy) spectroscopy of triggered detector events."""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Callable, Sequence

import numpy as np
import scipy.integrate
from scipy import ndimage, optimize, signal

from .campaign import PulseAcquisition

#: Ratio between the full width at half maximum and the Gaussian sigma.
FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))


class EventStatus(str, enum.Enum):
    """Acceptance status of one triggered event."""

    ACCEPTED = "ACCEPTED"
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    SATURATED = "SATURATED"
    PILE_UP = "PILE_UP"


class EnergyEstimator(str, enum.Enum):
    """Quantity proportional to the deposited energy."""

    CHARGE = "charge"
    PEAK = "peak"


@dataclasses.dataclass(frozen=True)
class PulseHeightParameters:
    """Explicit, non-normative settings for pulse-height spectroscopy.

    ``line_energies`` are the known photopeak energies (keV) of the
    calibration sources, matched in increasing order to the most prominent
    spectrum peaks. ``integration_gate`` (X units, 0 integrates to the end of
    the record) starts at the pulse onset: a gate of a few decay constants
    collects nearly all the charge while limiting the integrated baseline
    noise.
    """

    energy_estimator: EnergyEstimator | str = EnergyEstimator.CHARGE
    pretrigger_fraction: float = 0.1
    integration_gate: float = 0.0
    detection_threshold_sigma: float = 5.0
    pileup_prominence_ratio: float = 0.1
    saturation_min: float | None = None
    saturation_max: float | None = None
    minimum_saturated_samples: int = 2
    bin_count: int = 256
    smoothing_bins: float = 1.5
    line_energies: tuple[float, ...] = (661.657, 1173.228, 1332.492)

    def __post_init__(self) -> None:
        """Normalize and validate settings independently from events."""
        object.__setattr__(
            self, "energy_estimator", EnergyEstimator(self.energy_estimator)
        )
        if not 0.0 < self.pretrigger_fraction < 0.5:
            raise ValueError("Pretrigger fraction must be in (0, 0.5)")
        if not math.isfinite(self.integration_gate) or self.integration_gate < 0.0:
            raise ValueError("Integration gate must be finite and non-negative")
        for name, value in (
            ("Detection threshold", self.detection_threshold_sigma),
            ("Pile-up prominence ratio", self.pileup_prominence_ratio),
            ("Smoothing", self.smoothing_bins),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if (
            isinstance(self.bin_count, bool)
            or not isinstance(self.bin_count, int)
            or self.bin_count < 16
        ):
            raise ValueError("Bin count must be an integer of at least 16")
        energies = tuple(float(value) for value in self.line_energies)
        if not energies or any(not math.isfinite(e) or e <= 0.0 for e in energies):
            raise ValueError("Line energies must be finite and positive")
        if len(set(energies)) != len(energies):
            raise ValueError("Line energies must be distinct")
        object.__setattr__(self, "line_energies", tuple(sorted(energies)))


@dataclasses.dataclass(frozen=True)
class PulseHeightEvent:
    """Baseline, polarity, height, charge and status of one event."""

    shot_index: int
    status: EventStatus
    polarity: int
    noise_rms: float
    peak: float
    charge: float
    pulse_count: int

    def estimate(self, estimator: EnergyEstimator) -> float:
        """Return the quantity used to build the spectrum."""
        return self.charge if estimator is EnergyEstimator.CHARGE else self.peak


@dataclasses.dataclass(frozen=True)
class SpectrumPeak:
    """One calibration photopeak fitted by a Gaussian on a linear background."""

    energy: float
    centroid: float
    sigma: float
    net_counts: float
    resolution_percent: float

    @property
    def fwhm(self) -> float:
        """Return the full width at half maximum in estimator units."""
        return FWHM_PER_SIGMA * self.sigma


@dataclasses.dataclass(frozen=True)
class PulseHeightSpectrumResult:
    """Spectrum, linear energy calibration and energy resolution."""

    estimator: EnergyEstimator
    events: Sequence[PulseHeightEvent]
    bin_centers: np.ndarray
    counts: np.ndarray
    peaks: Sequence[SpectrumPeak]
    calibration_gain: float
    calibration_offset: float
    resolution_exponent: float

    @property
    def calibrated_centers(self) -> np.ndarray:
        """Return bin centers converted to energy (keV)."""
        return self.calibration_gain * self.bin_centers + self.calibration_offset

    def count(self, status: EventStatus) -> int:
        """Return the number of events with a given status."""
        return sum(event.status is status for event in self.events)


def analyze_event(
    acquisition: PulseAcquisition,
    shot_index: int,
    parameters: PulseHeightParameters,
) -> PulseHeightEvent:
    """Measure one triggered event against its pre-trigger baseline."""
    x, y = acquisition.x, acquisition.y
    pretrigger = max(int(parameters.pretrigger_fraction * x.size), 2)
    baseline = float(np.mean(y[:pretrigger]))
    noise_rms = float(np.std(y[:pretrigger], ddof=1))
    deviation = y - baseline
    polarity = 1 if np.max(deviation) >= -np.min(deviation) else -1
    oriented = polarity * deviation
    peak = float(np.max(oriented))
    onset = max(int(np.argmax(oriented >= 0.1 * peak)) - 2, 0)
    gate = slice(onset, None)
    if parameters.integration_gate > 0.0:
        gate = slice(
            onset,
            int(np.searchsorted(x, x[onset] + parameters.integration_gate)) + 1,
        )
    charge = float(scipy.integrate.trapezoid(oriented[gate], x[gate]))
    threshold = parameters.detection_threshold_sigma * noise_rms
    saturated = 0
    for bound in (parameters.saturation_min, parameters.saturation_max):
        if bound is not None:
            saturated += int(np.count_nonzero(y == bound))
    # Light smoothing keeps noise peak-to-trough excursions below the threshold.
    pulses, _properties = signal.find_peaks(
        ndimage.uniform_filter1d(oriented, 3),
        prominence=max(parameters.pileup_prominence_ratio * peak, threshold),
    )
    if saturated >= parameters.minimum_saturated_samples:
        status = EventStatus.SATURATED
    elif peak < threshold:
        status = EventStatus.BELOW_THRESHOLD
    elif pulses.size > 1:
        status = EventStatus.PILE_UP
    else:
        status = EventStatus.ACCEPTED
    return PulseHeightEvent(
        shot_index=shot_index,
        status=status,
        polarity=polarity,
        noise_rms=noise_rms,
        peak=peak,
        charge=charge,
        pulse_count=int(pulses.size),
    )


def _gaussian_with_background(x, height, center, sigma, slope, offset):
    """Return a Gaussian peak on a linear background."""
    return height * np.exp(-0.5 * ((x - center) / sigma) ** 2) + slope * x + offset


def _fit_peak(
    centers: np.ndarray,
    counts: np.ndarray,
    index: int,
    smoothed: np.ndarray,
) -> tuple[float, float, float]:
    """Return centroid, sigma and net counts of the peak around one bin."""
    width = float(centers[1] - centers[0])
    half = 0.5 * smoothed[index]
    left = index
    while left > 0 and smoothed[left] > half:
        left -= 1
    right = index
    while right < smoothed.size - 1 and smoothed[right] > half:
        right += 1
    sigma0 = max((right - left) * width / FWHM_PER_SIGMA, width)
    center0 = float(centers[index])
    height0 = float(smoothed[index])
    values = None
    # Refit once on a window centered on the first estimate.
    for _iteration in range(2):
        window = np.abs(centers - center0) <= 3.0 * sigma0
        x = centers[window]
        y = counts[window]
        try:
            values, _covariance = optimize.curve_fit(
                _gaussian_with_background,
                x,
                y,
                p0=(height0, center0, sigma0, 0.0, 0.0),
                sigma=np.sqrt(np.maximum(y, 1.0)),
                maxfev=5_000,
            )
        except (RuntimeError, ValueError):
            values = None
            break
        if not (x[0] <= values[1] <= x[-1]) or values[2] <= 0.0:
            values = None
            break
        height0, center0, sigma0 = float(values[0]), float(values[1]), float(values[2])
    if values is None:
        window = np.abs(centers - centers[index]) <= 3.0 * sigma0
        x = centers[window]
        weights = np.maximum(counts[window], 0.0)
        centroid = float(np.sum(weights * x) / np.sum(weights))
        sigma = float(np.sqrt(np.sum(weights * (x - centroid) ** 2) / np.sum(weights)))
        return centroid, sigma, float(np.sum(weights))
    height, centroid, sigma = float(values[0]), float(values[1]), abs(float(values[2]))
    return centroid, sigma, height * sigma * math.sqrt(2.0 * math.pi) / width


def analyze_pulse_height_spectrum(
    acquisitions: Sequence[PulseAcquisition],
    parameters: PulseHeightParameters | None = None,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> PulseHeightSpectrumResult:
    """Build the spectrum, fit calibration lines and derive the resolution.

    Accepted events are histogrammed. The ``len(line_energies)`` most
    prominent peaks of the smoothed spectrum, sorted by position, are matched
    to the sorted line energies; each is fitted by a Gaussian on a linear
    background. A linear least-squares fit of energy versus centroid gives the
    calibration, and the resolution is ``FWHM / E`` at each line.

    Raises:
        ValueError: If too few events are accepted or fewer peaks than
         calibration lines are found
    """
    parameters = parameters or PulseHeightParameters()
    acquisitions = tuple(acquisitions)
    events: list[PulseHeightEvent] = []
    for position, acquisition in enumerate(acquisitions, start=1):
        shot_index = (
            position if acquisition.shot_index is None else acquisition.shot_index
        )
        events.append(analyze_event(acquisition, shot_index, parameters))
        if progress_callback is not None:
            progress_callback(position, len(acquisitions))
    estimator = parameters.energy_estimator
    values = np.array(
        [
            event.estimate(estimator)
            for event in events
            if event.status is EventStatus.ACCEPTED
        ]
    )
    if values.size < 10 * len(parameters.line_energies):
        raise ValueError("Too few accepted events to build a spectrum")
    counts, edges = np.histogram(
        values,
        bins=parameters.bin_count,
        range=(0.0, 1.02 * float(np.max(values))),
    )
    centers = 0.5 * (edges[:-1] + edges[1:])
    counts = counts.astype(float)
    smoothed = ndimage.gaussian_filter1d(counts, parameters.smoothing_bins)
    candidates, properties = signal.find_peaks(
        smoothed,
        prominence=max(3.0, 0.05 * float(np.max(smoothed))),
    )
    line_count = len(parameters.line_energies)
    if candidates.size < line_count:
        raise ValueError(
            f"Found {candidates.size} spectrum peaks for {line_count} calibration lines"
        )
    strongest = np.sort(candidates[np.argsort(properties["prominences"])[-line_count:]])
    fits = [_fit_peak(centers, counts, int(index), smoothed) for index in strongest]
    centroids = np.array([fit[0] for fit in fits])
    energies = np.array(parameters.line_energies)
    if line_count >= 2:
        gain, offset = np.polyfit(centroids, energies, 1)
    else:
        gain, offset = energies[0] / centroids[0], 0.0
    peaks = tuple(
        SpectrumPeak(
            energy=float(energy),
            centroid=centroid,
            sigma=sigma,
            net_counts=net_counts,
            resolution_percent=100.0 * gain * FWHM_PER_SIGMA * sigma / energy,
        )
        for energy, (centroid, sigma, net_counts) in zip(energies, fits)
    )
    exponent = (
        float(
            np.polyfit(
                np.log(energies),
                np.log([peak.resolution_percent for peak in peaks]),
                1,
            )[0]
        )
        if line_count >= 2
        else math.nan
    )
    centers.setflags(write=False)
    counts.setflags(write=False)
    return PulseHeightSpectrumResult(
        estimator=estimator,
        events=tuple(events),
        bin_centers=centers,
        counts=counts,
        peaks=peaks,
        calibration_gain=float(gain),
        calibration_offset=float(offset),
        resolution_exponent=exponent,
    )


__all__ = [
    "EnergyEstimator",
    "EventStatus",
    "PulseHeightEvent",
    "PulseHeightParameters",
    "PulseHeightSpectrumResult",
    "SpectrumPeak",
    "analyze_event",
    "analyze_pulse_height_spectrum",
]
