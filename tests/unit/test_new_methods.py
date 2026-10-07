"""Core methods added in 0.2.0: stability, step response, delay, spectroscopy."""

from __future__ import annotations

import math

import numpy as np
import pytest

from datalab_pulse_characterization.core import (
    EventStatus,
    PulseAcquisition,
    PulseHeightParameters,
    StepResponseParameters,
    analyze_step_response,
    overlapping_allan_deviation,
    second_order_step,
)
from datalab_pulse_characterization.core.spectroscopy import analyze_event
from datalab_pulse_characterization.core.spectrum_simulation import (
    ELECTRON_REST_ENERGY_KEV,
    compton_energy,
)
from datalab_pulse_characterization.core.stability import (
    PulseStabilityParameters,
    _regime_change,
)
from datalab_pulse_characterization.core.step_response import (
    damping_ratio_from_overshoot,
    second_order_bandwidth,
)
from datalab_pulse_characterization.core.two_channel import cross_correlation_delay


def test_allan_deviation_separates_white_noise_from_drift() -> None:
    """White noise falls as m**-0.5 while a linear drift grows as m."""
    rng = np.random.default_rng(0)
    white = overlapping_allan_deviation(rng.normal(0.0, 1.0, 4_096))
    drift = overlapping_allan_deviation(0.01 * np.arange(4_096.0))

    assert white.tau_shots[:4].tolist() == [1.0, 2.0, 4.0, 8.0]
    assert white.deviation[0] == pytest.approx(1.0, rel=0.05)
    assert white.deviation[4] == pytest.approx(0.25, rel=0.15)
    assert drift.deviation[3] / drift.deviation[0] == pytest.approx(8.0, rel=1e-9)


def test_regime_change_locates_a_jitter_increase() -> None:
    """The likelihood-ratio split finds a fourfold jitter change."""
    rng = np.random.default_rng(1)
    residuals = np.concatenate((rng.normal(0, 1, 300), rng.normal(0, 4, 200)))
    shots = np.arange(1.0, 501.0)

    change = _regime_change(shots, residuals, PulseStabilityParameters())
    quiet = _regime_change(shots, rng.normal(0, 1, 500), PulseStabilityParameters())

    assert change is not None and abs(change.shot_index - 301) <= 5
    assert change.jitter_after / change.jitter_before == pytest.approx(4.0, rel=0.15)
    assert quiet is None


def test_step_response_matches_second_order_theory() -> None:
    """A noiseless second-order step yields its analytic parameters."""
    x = np.linspace(0.0, 200.0, 20_001)
    y = 2.0 + 3.0 * second_order_step(x - 40.0, 0.08, 0.35)

    result = analyze_step_response(x, y)

    assert result.low_level == pytest.approx(2.0, abs=0.01)
    assert result.amplitude == pytest.approx(3.0, rel=0.005)
    expected_overshoot = 100.0 * math.exp(-0.35 * math.pi / math.sqrt(1 - 0.35**2))
    assert result.overshoot_percent == pytest.approx(expected_overshoot, rel=0.01)
    assert result.damping_ratio_from_overshoot == pytest.approx(0.35, rel=0.01)
    assert result.damped_frequency == pytest.approx(
        0.08 * math.sqrt(1 - 0.35**2), rel=0.01
    )
    assert result.natural_frequency == pytest.approx(0.08, rel=0.02)
    assert result.bandwidth_second_order == pytest.approx(
        second_order_bandwidth(0.08, 0.35), rel=0.03
    )


def test_step_response_handles_falling_steps_and_instrument_correction() -> None:
    """Polarity is detected and the rise time is corrected in quadrature."""
    x = np.linspace(0.0, 200.0, 20_001)
    y = -second_order_step(x - 40.0, 0.08, 0.6)

    plain = analyze_step_response(x, y)
    corrected = analyze_step_response(
        x, y, StepResponseParameters(instrument_rise_time=1.0)
    )

    assert plain.polarity == -1
    assert corrected.corrected_rise_time == pytest.approx(
        math.sqrt(plain.rise_time**2 - 1.0), rel=1e-9
    )
    assert damping_ratio_from_overshoot(0.0) != damping_ratio_from_overshoot(0.0)


def test_cross_correlation_recovers_subsample_delay() -> None:
    """Parabolic refinement recovers a delay between two sample positions."""
    x = np.linspace(0.0, 100.0, 1_001)
    reference = np.exp(-0.5 * ((x - 30.0) / 2.0) ** 2)
    measured = np.exp(-0.5 * ((x - 42.37) / 2.0) ** 2)

    delay = cross_correlation_delay(
        PulseAcquisition(x, reference, "ref", 1),
        PulseAcquisition(x, measured, "meas", 1),
        reference,
        measured,
    )
    bounded = cross_correlation_delay(
        PulseAcquisition(x, reference, "ref", 1),
        PulseAcquisition(x, measured, "meas", 1),
        reference,
        measured,
        maximum_lag=5.0,
    )

    assert delay == pytest.approx(12.37, abs=0.01)
    assert abs(bounded) <= 5.0


def test_compton_energies_stay_below_the_compton_edge() -> None:
    """Klein-Nishina sampling never exceeds the kinematic maximum."""
    rng = np.random.default_rng(2)
    energy = 661.657
    epsilon = energy / ELECTRON_REST_ENERGY_KEV
    edge = energy * 2.0 * epsilon / (1.0 + 2.0 * epsilon)

    samples = np.array([compton_energy(energy, rng) for _ in range(2_000)])

    assert edge == pytest.approx(477.3, abs=0.5)
    assert samples.min() >= 0.0 and samples.max() <= edge
    # The continuum rises toward the edge: the upper third is the most populated.
    assert np.mean(samples > 2 * edge / 3) > 1 / 3


def _event(*pulses: tuple[float, float], noise: float = 0.0) -> PulseAcquisition:
    """Return one negative scintillation-like event."""
    x = np.linspace(0.0, 2.0, 256)
    y = np.zeros_like(x)
    for start, height in pulses:
        t = np.maximum(x - start, 0.0)
        y -= height * np.where(x > start, np.exp(-t / 0.23) - np.exp(-t / 0.02), 0.0)
    y += np.random.default_rng(3).normal(0.0, noise, x.size) if noise else 0.0
    return PulseAcquisition(x, y, "event", 1)


@pytest.mark.parametrize(
    ("pulses", "status"),
    [
        (((0.3, 1.0),), EventStatus.ACCEPTED),
        (((0.3, 1.0), (1.0, 0.5)), EventStatus.PILE_UP),
        (((0.3, 0.01),), EventStatus.BELOW_THRESHOLD),
        (((0.3, 5.0),), EventStatus.SATURATED),
    ],
)
def test_event_classification(pulses, status: EventStatus) -> None:
    """Events are accepted, rejected as pile-up, below threshold or saturated."""
    acquisition = _event(*pulses, noise=0.005)
    y = np.clip(acquisition.y, -2.0, 2.0)
    acquisition = PulseAcquisition(acquisition.x, y, "event", 1)

    event = analyze_event(
        acquisition,
        1,
        PulseHeightParameters(saturation_min=-2.0, saturation_max=2.0),
    )

    assert event.status is status
    assert event.polarity == -1
