"""Tests for deterministic synthetic pulse campaigns."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from datalab_pulse_characterization.core import (
    PulseAnomaly,
    PulseProfile,
    PulseSimulationParameters,
    PulseStatus,
    analyze_pulse_campaign,
    simulate_pulse_campaign,
)


def test_default_simulation_is_deterministic_and_read_only() -> None:
    """The demonstration seed reproduces all 500 waveforms and truth rows."""
    first = simulate_pulse_campaign()
    second = simulate_pulse_campaign()

    assert len(first.acquisitions) == 500
    assert first.truth == second.truth
    assert {shot.profile for shot in first.truth.shots} == {
        PulseProfile.GAUSSIAN,
        PulseProfile.ASYMMETRIC,
    }
    for first_acquisition, second_acquisition in zip(
        first.acquisitions,
        second.acquisitions,
    ):
        assert not first_acquisition.x.flags.writeable
        assert not first_acquisition.y.flags.writeable
        np.testing.assert_array_equal(first_acquisition.x, second_acquisition.x)
        np.testing.assert_array_equal(first_acquisition.y, second_acquisition.y)


def test_default_truth_contains_eleven_explainable_anomalies() -> None:
    """The demonstration truth covers every non-valid campaign status."""
    truth = simulate_pulse_campaign().truth

    assert len(truth.invalid_shots) == 11
    assert Counter(shot.anomaly for shot in truth.invalid_shots) == {
        PulseAnomaly.MISSING: 2,
        PulseAnomaly.LOW_SNR: 2,
        PulseAnomaly.SATURATED: 2,
        PulseAnomaly.MULTIPLE_PULSES: 2,
        PulseAnomaly.OUTLIER: 3,
    }
    assert Counter(shot.expected_status for shot in truth.shots) == {
        PulseStatus.VALID: 489,
        PulseStatus.NO_PULSE: 2,
        PulseStatus.LOW_SNR: 2,
        PulseStatus.SATURATED: 2,
        PulseStatus.MULTIPLE_PULSES: 2,
        PulseStatus.OUTLIER: 3,
    }


def test_default_truth_records_drift_and_increasing_timing_jitter() -> None:
    """Slow drifts and the post-shot-300 jitter increase remain inspectable."""
    result = simulate_pulse_campaign()
    shots = result.truth.shots

    assert shots[-1].baseline_offset - shots[0].baseline_offset == pytest.approx(
        result.parameters.baseline_drift
    )
    assert shots[-1].amplitude / shots[0].amplitude == pytest.approx(
        (1.0 + 0.5 * result.parameters.amplitude_drift_fraction)
        / (1.0 - 0.5 * result.parameters.amplitude_drift_fraction)
    )
    early = np.array(
        [
            shot.timing_offset
            for shot in shots
            if shot.shot_index <= result.parameters.jitter_transition_shot
        ]
    )
    late = np.array(
        [
            shot.timing_offset
            for shot in shots
            if shot.shot_index > result.parameters.jitter_transition_shot
        ]
    )
    assert all(
        shot.timing_jitter_std == result.parameters.timing_jitter_std
        for shot in shots[: result.parameters.jitter_transition_shot]
    )
    assert all(
        shot.timing_jitter_std == result.parameters.late_timing_jitter_std
        for shot in shots[result.parameters.jitter_transition_shot :]
    )
    assert np.std(late, ddof=1) > 3.0 * np.std(early, ddof=1)


def test_campaign_analysis_recovers_every_ground_truth_status() -> None:
    """The real batch analyzer recovers all 500 declared quality states."""
    simulated = simulate_pulse_campaign()

    analyzed = analyze_pulse_campaign(
        simulated.acquisitions,
        simulated.analysis_parameters,
    )

    assert [shot.status for shot in analyzed.shots] == [
        shot.expected_status for shot in simulated.truth.shots
    ]
    required_diagnostic_key = {
        PulseStatus.NO_PULSE: "minimum_amplitude",
        PulseStatus.LOW_SNR: "minimum_snr_db",
        PulseStatus.SATURATED: "minimum_saturated_samples",
        PulseStatus.MULTIPLE_PULSES: "multiple_pulse_threshold_ratio",
        PulseStatus.OUTLIER: "outlier_threshold",
    }
    for shot in analyzed.shots:
        if shot.status is PulseStatus.VALID:
            continue
        assert shot.reason
        assert required_diagnostic_key[shot.status] in shot.diagnostic_values


def test_alternate_seed_and_negative_polarity_preserve_status_truth() -> None:
    """Truth recovery does not depend on the demonstration seed or polarity."""
    simulated = simulate_pulse_campaign(PulseSimulationParameters(seed=17, polarity=-1))

    analyzed = analyze_pulse_campaign(
        simulated.acquisitions,
        simulated.analysis_parameters,
    )

    assert [shot.status for shot in analyzed.shots] == [
        shot.expected_status for shot in simulated.truth.shots
    ]


@pytest.mark.parametrize(
    ("overrides", "error_type"),
    [
        ({"shot_count": 0}, ValueError),
        ({"sample_count": 20}, ValueError),
        ({"x_max": 0.0}, ValueError),
        ({"polarity": 0}, ValueError),
        ({"white_noise_std": -1.0}, ValueError),
        ({"low_snr_noise_std": 0.01}, ValueError),
        ({"white_noise_std": 0.5, "low_snr_noise_std": 0.6}, ValueError),
        ({"amplitude_drift_fraction": 1.9}, ValueError),
        ({"outlier_amplitude_multiplier": 1.01}, ValueError),
        ({"double_pulse_separation": 6.0}, ValueError),
        ({"saturation_max": 8.0}, ValueError),
        ({"late_timing_jitter_std": 0.001}, ValueError),
        ({"jitter_transition_shot": 501}, ValueError),
        ({"profiles": ()}, ValueError),
        ({"missing_shots": [1]}, TypeError),
        ({"missing_shots": (0,)}, ValueError),
        ({"missing_shots": (37,), "outlier_shots": (37,)}, ValueError),
        ({"seed": True}, TypeError),
    ],
)
def test_invalid_simulation_parameters_are_rejected(
    overrides: dict[str, object],
    error_type: type[Exception],
) -> None:
    """Invalid or ambiguous synthetic truth fails before generation."""
    with pytest.raises(error_type):
        PulseSimulationParameters(**overrides)
