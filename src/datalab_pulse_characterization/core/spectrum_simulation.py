"""Deterministic scintillation-detector events from gamma-ray sources."""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from .campaign import PulseAcquisition

#: Electron rest energy (keV).
ELECTRON_REST_ENERGY_KEV = 510.999
CS137_LINE_KEV = 661.657
CO60_LINES_KEV = (1173.228, 1332.492)


@dataclasses.dataclass(frozen=True)
class SpectrumSimulationParameters:
    """Triggered NaI(Tl)-like events from a Cs-137 and Co-60 source mix.

    Each gamma ray is either fully absorbed (photopeak) or deposits the
    energy of one Compton scattering, drawn from the Klein-Nishina
    distribution. The detected energy is smeared with a statistical
    resolution ``resolution_at_662 * sqrt(661.657 / E)`` (FWHM fraction).
    Pulses have a double-exponential shape scaled by ``volts_per_kev``; a few
    events pile up with a second gamma ray and cosmic-ray muons saturate the
    digitizer. X values are in microseconds.
    """

    event_count: int = 2_500
    sample_count: int = 256
    x_min: float = 0.0
    x_max: float = 2.0
    trigger_time: float = 0.3
    rise_time_constant: float = 0.02
    decay_time_constant: float = 0.23
    volts_per_kev: float = 0.001
    polarity: int = -1
    resolution_at_662: float = 0.07
    white_noise_std: float = 0.005
    cs137_fraction: float = 0.3
    cs137_photofraction: float = 0.45
    co60_photofraction: float = 0.45
    pileup_fraction: float = 0.01
    cosmic_fraction: float = 0.005
    saturation_level: float = 2.0
    seed: int = 20261008

    def __post_init__(self) -> None:
        """Validate the scenario before allocating waveforms."""
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int):
            raise TypeError("Event count must be an integer")
        if self.event_count < 10:
            raise ValueError("Event count must be at least 10")
        if self.polarity not in (-1, 1):
            raise ValueError("Polarity must be -1 or 1")
        if not 0.0 < self.rise_time_constant < self.decay_time_constant:
            raise ValueError("Rise time constant must be below the decay constant")
        for name, value in (
            ("Cs-137 fraction", self.cs137_fraction),
            ("Cs-137 photofraction", self.cs137_photofraction),
            ("Co-60 photofraction", self.co60_photofraction),
            ("Pile-up fraction", self.pileup_fraction),
            ("Cosmic fraction", self.cosmic_fraction),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if not self.x_min < self.trigger_time < self.x_max:
            raise ValueError("Trigger time must lie inside the X range")
        for name, value in (
            ("Volts per keV", self.volts_per_kev),
            ("Resolution at 662 keV", self.resolution_at_662),
            ("Saturation level", self.saturation_level),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")

    @property
    def unit_pulse_integral(self) -> float:
        """Return the integral of the unit-peak pulse shape (X units)."""
        rise, decay = self.rise_time_constant, self.decay_time_constant
        peak_time = rise * decay / (decay - rise) * math.log(decay / rise)
        peak = math.exp(-peak_time / decay) - math.exp(-peak_time / rise)
        return (decay - rise) / peak

    @property
    def charge_per_kev(self) -> float:
        """Return the pulse integral per deposited keV (V x X unit)."""
        return self.volts_per_kev * self.unit_pulse_integral


@dataclasses.dataclass(frozen=True)
class SpectrumTruth:
    """Per-event source energy, deposited and detected energies and flags."""

    source_energies: np.ndarray
    deposited_energies: np.ndarray
    detected_energies: np.ndarray
    pileup: np.ndarray
    cosmic: np.ndarray


@dataclasses.dataclass(frozen=True)
class SpectrumSimulationResult:
    """Triggered acquisitions and exact truth."""

    parameters: SpectrumSimulationParameters
    acquisitions: tuple[PulseAcquisition, ...]
    truth: SpectrumTruth


def _klein_nishina_density(fraction: np.ndarray, epsilon: float) -> np.ndarray:
    """Return the Compton electron kinetic-energy density (unnormalized).

    ``fraction`` is the electron kinetic energy over the photon energy and
    ``epsilon`` the photon energy over the electron rest energy.
    """
    remaining = 1.0 - fraction
    return (
        2.0
        + fraction**2 / (epsilon**2 * remaining**2)
        + fraction / remaining * (fraction - 2.0 / epsilon)
    )


def compton_energy(photon_kev: float, rng: np.random.Generator) -> float:
    """Draw one Compton electron energy by rejection from Klein-Nishina."""
    epsilon = photon_kev / ELECTRON_REST_ENERGY_KEV
    maximum_fraction = 2.0 * epsilon / (1.0 + 2.0 * epsilon)
    grid = np.linspace(0.0, maximum_fraction, 256)
    ceiling = 1.05 * float(np.max(_klein_nishina_density(grid, epsilon)))
    while True:
        fraction = rng.uniform(0.0, maximum_fraction)
        if rng.uniform(0.0, ceiling) <= _klein_nishina_density(
            np.array(fraction), epsilon
        ):
            return float(fraction * photon_kev)


def _gamma_ray(
    parameters: SpectrumSimulationParameters,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Draw one source photon and the energy it deposits in the crystal."""
    if rng.uniform() < parameters.cs137_fraction:
        energy, photofraction = CS137_LINE_KEV, parameters.cs137_photofraction
    else:
        energy = CO60_LINES_KEV[int(rng.integers(2))]
        photofraction = parameters.co60_photofraction
    if rng.uniform() < photofraction:
        return energy, energy
    return energy, compton_energy(energy, rng)


def _smeared(
    energy: float,
    parameters: SpectrumSimulationParameters,
    rng: np.random.Generator,
) -> float:
    """Apply the statistical energy resolution of the detector."""
    if energy <= 0.0:
        return 0.0
    fwhm_fraction = parameters.resolution_at_662 * math.sqrt(CS137_LINE_KEV / energy)
    sigma = energy * fwhm_fraction / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    return max(float(rng.normal(energy, sigma)), 0.0)


def _pulse(
    x: np.ndarray,
    start: float,
    parameters: SpectrumSimulationParameters,
) -> np.ndarray:
    """Return the unit-peak double-exponential scintillation pulse."""
    rise, decay = parameters.rise_time_constant, parameters.decay_time_constant
    t = np.maximum(x - start, 0.0)
    shape = np.exp(-t / decay) - np.exp(-t / rise)
    peak_time = rise * decay / (decay - rise) * math.log(decay / rise)
    peak = math.exp(-peak_time / decay) - math.exp(-peak_time / rise)
    return np.where(x > start, shape / peak, 0.0)


def simulate_spectrum_events(
    parameters: SpectrumSimulationParameters | None = None,
) -> SpectrumSimulationResult:
    """Generate triggered events and the exact energies that produced them."""
    parameters = parameters or SpectrumSimulationParameters()
    x = np.linspace(parameters.x_min, parameters.x_max, parameters.sample_count)
    dx = float(x[1] - x[0])
    seeds = np.random.SeedSequence(parameters.seed).spawn(parameters.event_count)
    acquisitions: list[PulseAcquisition] = []
    sources: list[float] = []
    deposited: list[float] = []
    detected: list[float] = []
    pileup: list[bool] = []
    cosmic: list[bool] = []
    for shot_index, seed_sequence in enumerate(seeds, start=1):
        rng = np.random.default_rng(seed_sequence)
        is_cosmic = bool(rng.uniform() < parameters.cosmic_fraction)
        if is_cosmic:
            source = deposit = float(rng.uniform(3_000.0, 10_000.0))
        else:
            source, deposit = _gamma_ray(parameters, rng)
        energy = _smeared(deposit, parameters, rng)
        start = parameters.trigger_time + float(rng.uniform(0.0, dx))
        y = energy * _pulse(x, start, parameters)
        is_pileup = bool(rng.uniform() < parameters.pileup_fraction)
        if is_pileup:
            _second_source, second_deposit = _gamma_ray(parameters, rng)
            y += _smeared(second_deposit, parameters, rng) * _pulse(
                x, start + float(rng.uniform(0.15, 1.2)), parameters
            )
        y = parameters.polarity * parameters.volts_per_kev * y + rng.normal(
            0.0, parameters.white_noise_std, size=x.shape
        )
        np.clip(y, -parameters.saturation_level, parameters.saturation_level, out=y)
        acquisitions.append(
            PulseAcquisition(x, y, f"Event {shot_index:04d}", shot_index)
        )
        sources.append(source)
        deposited.append(deposit)
        detected.append(energy)
        pileup.append(is_pileup)
        cosmic.append(is_cosmic)
    arrays = [
        np.array(values) for values in (sources, deposited, detected, pileup, cosmic)
    ]
    for array in arrays:
        array.setflags(write=False)
    return SpectrumSimulationResult(
        parameters=parameters,
        acquisitions=tuple(acquisitions),
        truth=SpectrumTruth(*arrays),
    )


__all__ = [
    "CO60_LINES_KEV",
    "CS137_LINE_KEV",
    "SpectrumSimulationParameters",
    "SpectrumSimulationResult",
    "SpectrumTruth",
    "compton_energy",
    "simulate_spectrum_events",
]
