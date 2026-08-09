"""Tests for headless pulse campaign alignment."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from sigima.tools.signal import pulse as sigima_pulse

from datalab_pulse_characterization.core import alignment as alignment_module
from datalab_pulse_characterization.core.alignment import (
    PulseAlignmentParameters,
    align_pulse_campaign,
)
from datalab_pulse_characterization.core.campaign import (
    PulseAcquisition,
    PulseAnalysisParameters,
    PulseCampaignResult,
    PulseStatus,
    analyze_pulse_campaign,
)
from datalab_pulse_characterization.core.simulation import (
    PulseSimulationParameters,
    simulate_pulse_campaign,
)


def _x50(shot) -> float:
    """Return one Sigima half-height landmark."""
    assert shot.features is not None
    return float(shot.features.x50)


def test_x50_alignment_reduces_valid_shot_jitter_and_preserves_invalids() -> None:
    """Valid waveforms converge while all explainable failures remain raw."""
    simulation = simulate_pulse_campaign()
    campaign = analyze_pulse_campaign(
        simulation.acquisitions,
        simulation.analysis_parameters,
    )

    alignment = align_pulse_campaign(simulation.acquisitions, campaign)

    valid_positions = [
        index
        for index, shot in enumerate(campaign.shots)
        if shot.status is PulseStatus.VALID
    ]
    aligned_campaign = analyze_pulse_campaign(
        alignment.aligned_acquisitions,
        simulation.analysis_parameters,
    )
    raw_landmarks = np.array([_x50(campaign.shots[index]) for index in valid_positions])
    aligned_landmarks = np.array(
        [_x50(aligned_campaign.shots[index]) for index in valid_positions]
    )
    assert alignment.aligned_count == 489
    assert np.std(aligned_landmarks) < 0.25 * np.std(raw_landmarks)
    assert np.max(np.abs(aligned_landmarks - alignment.reference_x)) <= 0.02
    raw_mean = alignment.mean_acquisition(aligned=False)
    aligned_mean = alignment.mean_acquisition(aligned=True)
    assert raw_mean.title == "Raw pulse campaign mean"
    assert aligned_mean.title == "Aligned pulse campaign mean"
    assert np.max(aligned_mean.y) > np.max(raw_mean.y)
    for index, (raw, aligned, record, shot) in enumerate(
        zip(
            simulation.acquisitions,
            alignment.aligned_acquisitions,
            alignment.records,
            campaign.shots,
        )
    ):
        if shot.status is PulseStatus.VALID:
            assert record.aligned
            assert record.landmark_x + record.shift_x == pytest.approx(
                alignment.reference_x
            )
            assert aligned is not raw
        else:
            assert not record.aligned
            assert aligned is raw
            assert shot.status.value in record.reason
        np.testing.assert_array_equal(alignment.raw_acquisitions[index].y, raw.y)


def test_explicit_reference_is_applied_without_mutating_inputs() -> None:
    """A caller may choose a finite reference shared by every X range."""
    simulation = simulate_pulse_campaign()
    campaign = analyze_pulse_campaign(
        simulation.acquisitions,
        simulation.analysis_parameters,
    )
    original = tuple(acquisition.y.copy() for acquisition in simulation.acquisitions)

    result = align_pulse_campaign(
        simulation.acquisitions,
        campaign,
        PulseAlignmentParameters(reference_x=5.0),
    )

    assert result.reference_x == 5.0
    for acquisition, expected in zip(simulation.acquisitions, original):
        np.testing.assert_array_equal(acquisition.y, expected)


def test_x50_alignment_uses_sigima_polarity_for_negative_pulses() -> None:
    """Negative pulses use the polarity-aware rising half-height crossing."""
    simulation = simulate_pulse_campaign(
        PulseSimulationParameters(
            shot_count=20,
            sample_count=101,
            jitter_transition_shot=10,
            polarity=-1,
            missing_shots=(),
            low_snr_shots=(),
            saturated_shots=(),
            multiple_pulse_shots=(),
            outlier_shots=(),
            seed=17,
        )
    )
    campaign = analyze_pulse_campaign(
        simulation.acquisitions,
        simulation.analysis_parameters,
    )

    alignment = align_pulse_campaign(simulation.acquisitions, campaign)
    aligned_campaign = analyze_pulse_campaign(
        alignment.aligned_acquisitions,
        simulation.analysis_parameters,
    )

    assert alignment.aligned_count == 20
    assert all(shot.features.polarity == -1 for shot in aligned_campaign.shots)
    assert (
        np.max(
            np.abs(
                np.array([_x50(shot) for shot in aligned_campaign.shots])
                - alignment.reference_x
            )
        )
        <= 0.1
    )


def test_default_reference_uses_lower_observation_for_adjacent_floats() -> None:
    """An even campaign selects the lower observed middle landmark exactly."""
    lower = np.nextafter(1.0, np.inf)
    higher = np.nextafter(lower, np.inf)

    reference = alignment_module._default_reference({2: higher, 1: lower})

    assert reference == lower


def test_alignment_rejects_mismatched_or_unusable_campaigns() -> None:
    """Alignment cannot silently pair the wrong analysis with acquisitions."""
    simulation = simulate_pulse_campaign()
    campaign = analyze_pulse_campaign(
        simulation.acquisitions,
        simulation.analysis_parameters,
    )
    with pytest.raises(ValueError, match="equal length"):
        align_pulse_campaign(simulation.acquisitions[:-1], campaign)

    wrong_first = dataclasses.replace(campaign.shots[0], shot_index=501)
    wrong_campaign = PulseCampaignResult((wrong_first, *campaign.shots[1:]))
    with pytest.raises(ValueError, match="shot indices differ"):
        align_pulse_campaign(simulation.acquisitions, wrong_campaign)

    invalid_campaign = PulseCampaignResult(
        tuple(
            dataclasses.replace(
                shot,
                status=PulseStatus.NO_PULSE,
                reason="No usable pulse",
            )
            for shot in campaign.shots
        )
    )
    unavailable = align_pulse_campaign(simulation.acquisitions, invalid_campaign)
    assert unavailable.reference_x is None
    assert unavailable.aligned_count == 0
    assert unavailable.aligned_acquisitions == simulation.acquisitions
    with pytest.raises(ValueError, match="alignable acquisition"):
        unavailable.mean_acquisition(aligned=True)

    outside = align_pulse_campaign(
        simulation.acquisitions,
        campaign,
        PulseAlignmentParameters(reference_x=20.0),
    )
    assert outside.reference_x == 20.0
    assert outside.aligned_count == 0
    assert all(
        "reference outside X range" in record.reason
        for record, shot in zip(outside.records, campaign.shots)
        if shot.status is PulseStatus.VALID
    )


def test_mean_aggregation_resamples_to_the_first_valid_x_grid() -> None:
    """Differently sampled valid acquisitions aggregate on one explicit grid."""
    simulation = simulate_pulse_campaign()
    acquisitions = list(simulation.acquisitions[:2])
    acquisitions[1] = dataclasses.replace(
        acquisitions[1],
        x=acquisitions[1].x + 0.001,
    )
    campaign = analyze_pulse_campaign(acquisitions, simulation.analysis_parameters)
    alignment = align_pulse_campaign(acquisitions, campaign)

    mean = alignment.mean_acquisition(aligned=True)
    np.testing.assert_array_equal(mean.x, acquisitions[0].x)
    assert np.all(np.isfinite(mean.y))


def test_skipped_acquisition_domain_does_not_block_valid_alignment() -> None:
    """A skipped shot remains reportable outside the valid reference domain."""
    simulation = simulate_pulse_campaign()
    acquisitions = list(simulation.acquisitions[:2])
    acquisitions[1] = dataclasses.replace(
        acquisitions[1],
        x=np.linspace(-2.0, -1.0, acquisitions[1].x.size),
    )
    campaign = analyze_pulse_campaign(
        simulation.acquisitions[:2],
        simulation.analysis_parameters,
    )
    skipped = dataclasses.replace(
        campaign.shots[1],
        status=PulseStatus.NO_PULSE,
        reason="No usable pulse",
    )

    alignment = align_pulse_campaign(
        acquisitions,
        PulseCampaignResult((campaign.shots[0], skipped)),
    )

    assert alignment.aligned_count == 1
    assert alignment.aligned_acquisitions[1] is acquisitions[1]
    assert not alignment.records[1].aligned


def test_disjoint_valid_domains_skip_only_incompatible_acquisition() -> None:
    """A measured reference aligns its own domain without aborting other shots."""
    simulation = simulate_pulse_campaign()
    acquisitions = list(simulation.acquisitions[:2])
    acquisitions[1] = dataclasses.replace(
        acquisitions[1],
        x=acquisitions[1].x + 20.0,
    )
    campaign = analyze_pulse_campaign(
        simulation.acquisitions[:2],
        simulation.analysis_parameters,
    )
    second_features = dataclasses.replace(
        campaign.shots[1].features,
        x50=campaign.shots[1].features.x50 + 20.0,
    )
    second_shot = dataclasses.replace(
        campaign.shots[1],
        features=second_features,
    )

    alignment = align_pulse_campaign(
        acquisitions,
        PulseCampaignResult((campaign.shots[0], second_shot)),
    )

    assert alignment.aligned_count == 1
    assert alignment.records[0].aligned
    assert not alignment.records[1].aligned
    assert alignment.records[1].landmark_x == pytest.approx(second_features.x50)
    assert alignment.records[1].shift_x is None
    assert "reference outside X range" in alignment.records[1].reason


def test_missing_x50_fallback_none_or_error_is_explainable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed Sigima fallback skips a valid shot without aborting the batch."""
    simulation = simulate_pulse_campaign()
    campaign = analyze_pulse_campaign(
        simulation.acquisitions[:1],
        simulation.analysis_parameters,
    )
    features_without_x50 = dataclasses.replace(
        campaign.shots[0].features,
        x50=None,
    )
    campaign = PulseCampaignResult(
        (dataclasses.replace(campaign.shots[0], features=features_without_x50),)
    )

    monkeypatch.setattr(
        alignment_module.sigima_pulse,
        "find_crossing_at_ratio",
        lambda *args, **kwargs: None,
    )
    unavailable = align_pulse_campaign(simulation.acquisitions[:1], campaign)
    assert unavailable.aligned_count == 0
    assert "50% crossing unavailable" in unavailable.records[0].reason

    def fail_crossing(*args, **kwargs):
        raise sigima_pulse.InvalidSignalError("cannot find crossing")

    monkeypatch.setattr(
        alignment_module.sigima_pulse,
        "find_crossing_at_ratio",
        fail_crossing,
    )
    unavailable = align_pulse_campaign(simulation.acquisitions[:1], campaign)
    assert unavailable.aligned_count == 0
    assert "50% crossing unavailable" in unavailable.records[0].reason


def test_x50_alignment_is_stable_on_noisy_square_plateaus() -> None:
    """Plateau noise maxima do not move the half-height timing landmark."""
    x = np.linspace(0.0, 10.0, 101)
    square = 4.0 * ((x >= 3.0) & (x <= 7.0))
    first_y = square.copy()
    second_y = square.copy()
    first_y[np.argmin(np.abs(x - 4.0))] += 0.2
    second_y[np.argmin(np.abs(x - 6.0))] += 0.2
    acquisitions = (
        PulseAcquisition(x, first_y, "First", 1),
        PulseAcquisition(x, second_y, "Second", 2),
    )
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape="square",
        denoise=False,
    )
    campaign = analyze_pulse_campaign(acquisitions, parameters)

    alignment = align_pulse_campaign(acquisitions, campaign)

    assert alignment.aligned_count == 2
    assert abs(alignment.records[0].shift_x) < 0.01
    assert abs(alignment.records[1].shift_x) < 0.01
