"""Pulse campaign analysis tests."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.integrate
from sigima.enums import SignalShape
from sigima.tools.signal.pulse import PulseFeatures

from datalab_pulse_characterization.core.campaign import (
    PulseAcquisition,
    PulseAnalysisParameters,
    PulseStatus,
    analyze_pulse,
    analyze_pulse_campaign,
)


def _square_pulse(
    title: str,
    amplitude: float,
    *,
    noise: float = 0.1,
    windows: tuple[tuple[float, float], ...] = ((3.0, 7.0),),
) -> PulseAcquisition:
    """Build one explicit pulse array without using a campaign simulator."""
    x = np.linspace(0.0, 10.0, 101)
    y = np.where(np.arange(x.size) % 2 == 0, noise, -noise)
    for lower, upper in windows:
        y = y + amplitude * ((x >= lower) & (x <= upper))
    return PulseAcquisition(x=x, y=y, title=title)


def test_analyze_pulse_uses_raw_baseline_for_integral_and_snr() -> None:
    """Single-shot metrics follow the documented baseline convention."""
    x = np.linspace(0.0, 10.0, 101)
    noise = np.where(np.arange(x.size) % 2 == 0, 0.1, -0.1)
    y = noise + 4.0 * ((x >= 3.0) & (x <= 7.0))
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 2.0),
        end_range=(8.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
        minimum_amplitude=1.0,
        minimum_snr_db=20.0,
    )

    result = analyze_pulse(
        x,
        y,
        shot_index=7,
        title="Shot 7",
        parameters=parameters,
    )

    assert isinstance(result.features, PulseFeatures)
    baseline_mask = ((x >= 0.0) & (x <= 2.0)) | ((x >= 8.0) & (x <= 10.0))
    baseline = y[baseline_mask]
    baseline_mean = float(np.mean(baseline))
    baseline_noise_rms = float(np.sqrt(np.mean((baseline - baseline_mean) ** 2)))
    oriented = y * result.features.polarity - baseline_mean
    expected_integral = float(scipy.integrate.trapezoid(oriented, x))
    expected_snr_db = 20.0 * np.log10(result.features.amplitude / baseline_noise_rms)

    assert result.baseline_noise_rms == pytest.approx(baseline_noise_rms)
    assert result.integral == pytest.approx(expected_integral)
    assert result.snr_db == pytest.approx(expected_snr_db)
    assert result.status is PulseStatus.VALID


@pytest.mark.parametrize(
    ("acquisition", "parameter_overrides", "expected_status", "detail_key"),
    [
        (
            _square_pulse("No pulse", 0.2),
            {"minimum_amplitude": 1.0},
            PulseStatus.NO_PULSE,
            "minimum_amplitude",
        ),
        (
            _square_pulse("Low SNR", 4.0, noise=1.0),
            {"minimum_snr_db": 20.0},
            PulseStatus.LOW_SNR,
            "minimum_snr_db",
        ),
        (
            _square_pulse("Saturated", 4.0, noise=0.0),
            {"saturation_max": 4.0, "minimum_saturated_samples": 2},
            PulseStatus.SATURATED,
            "saturated_samples",
        ),
        (
            _square_pulse(
                "Double pulse",
                4.0,
                windows=((2.0, 3.0), (6.0, 7.0)),
            ),
            {"minimum_pulse_samples": 3},
            PulseStatus.MULTIPLE_PULSES,
            "pulse_regions",
        ),
    ],
)
def test_analyze_pulse_assigns_explainable_quality_status(
    acquisition: PulseAcquisition,
    parameter_overrides: dict[str, object],
    expected_status: PulseStatus,
    detail_key: str,
) -> None:
    """Every configured single-shot rejection records its triggering value."""
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
        **parameter_overrides,
    )

    result = analyze_pulse(
        acquisition.x,
        acquisition.y,
        shot_index=1,
        title=acquisition.title,
        parameters=parameters,
    )

    assert result.status is expected_status
    assert expected_status.value.replace("_", " ").lower() in result.reason.lower()
    assert detail_key in result.diagnostic_values


@pytest.mark.parametrize(
    ("minimum_amplitude", "saturation_max", "expected_status"),
    [
        (5.0, 5.0, PulseStatus.NO_PULSE),
        (0.0, 5.0, PulseStatus.SATURATED),
        (0.0, None, PulseStatus.MULTIPLE_PULSES),
    ],
)
def test_quality_status_priority_with_overlapping_failures(
    minimum_amplitude: float,
    saturation_max: float | None,
    expected_status: PulseStatus,
) -> None:
    """Higher-priority failures win when one shot triggers several checks."""
    acquisition = _square_pulse(
        "Overlapping failures",
        4.0,
        noise=1.0,
        windows=((2.0, 3.0), (6.0, 7.0)),
    )
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
        minimum_amplitude=minimum_amplitude,
        saturation_max=saturation_max,
        minimum_saturated_samples=2,
        minimum_pulse_samples=3,
        minimum_snr_db=20.0,
    )

    result = analyze_pulse(
        acquisition.x,
        acquisition.y,
        shot_index=1,
        title=acquisition.title,
        parameters=parameters,
    )

    assert result.status is expected_status
    assert result.diagnostic_values["pulse_regions"] == 2
    assert result.snr_db < parameters.minimum_snr_db


def test_flat_acquisition_becomes_no_pulse_without_sigima_features() -> None:
    """A truly missing pulse remains a reportable row in the campaign."""
    x = np.linspace(0.0, 10.0, 101)
    y = np.full(x.shape, 2.5)
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
        minimum_amplitude=1.0,
    )

    result = analyze_pulse(
        x,
        y,
        shot_index=1,
        title="Missing",
        parameters=parameters,
    )

    assert result.features is None
    assert result.amplitude == 0.0
    assert result.baseline_noise_rms == 0.0
    assert result.integral is None
    assert result.snr_db == -np.inf
    assert result.status is PulseStatus.NO_PULSE
    assert result.diagnostic_values["extraction_error"]


def test_analyze_pulse_campaign_marks_only_robust_amplitude_outlier() -> None:
    """Batch classification applies an explicit modified-Z-score threshold."""
    acquisitions = tuple(
        _square_pulse(f"Shot {index}", amplitude)
        for index, amplitude in enumerate((3.8, 3.9, 4.0, 4.1, 9.0), start=1)
    )
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
        outlier_modified_zscore=3.5,
        minimum_outlier_shots=5,
    )

    result = analyze_pulse_campaign(acquisitions, parameters)

    assert [shot.shot_index for shot in result.shots] == [1, 2, 3, 4, 5]
    assert [shot.status for shot in result.shots] == [
        PulseStatus.VALID,
        PulseStatus.VALID,
        PulseStatus.VALID,
        PulseStatus.VALID,
        PulseStatus.OUTLIER,
    ]
    outlier = result.shots[-1]
    assert "modified Z-score" in outlier.reason
    assert outlier.diagnostic_values["outlier_modified_zscore"] > 3.5


def test_negative_pulse_has_negative_polarity_and_positive_oriented_integral() -> None:
    """Campaign integral orientation follows Sigima's detected polarity."""
    acquisition = _square_pulse("Negative", -4.0)
    acquisition = PulseAcquisition(
        acquisition.x,
        acquisition.y + 5.0,
        acquisition.title,
    )
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
    )

    result = analyze_pulse(
        acquisition.x,
        acquisition.y,
        shot_index=1,
        title=acquisition.title,
        parameters=parameters,
    )

    assert result.features is not None
    assert result.features.polarity == -1
    baseline_mask = ((acquisition.x >= 0.0) & (acquisition.x <= 1.0)) | (
        (acquisition.x >= 9.0) & (acquisition.x <= 10.0)
    )
    raw_baseline = acquisition.y[baseline_mask]
    raw_baseline_mean = float(np.mean(raw_baseline))
    expected_noise_rms = float(
        np.sqrt(np.mean(np.square(raw_baseline - raw_baseline_mean)))
    )
    expected_integral = float(
        scipy.integrate.trapezoid(
            result.features.polarity * (acquisition.y - raw_baseline_mean),
            acquisition.x,
        )
    )
    expected_snr_db = 20.0 * np.log10(result.features.amplitude / expected_noise_rms)

    assert result.baseline_noise_rms == pytest.approx(expected_noise_rms)
    assert result.integral == pytest.approx(expected_integral)
    assert result.snr_db == pytest.approx(expected_snr_db)
    assert result.integral > 0.0
    assert result.status is PulseStatus.VALID


def test_step_snr_uses_only_initial_baseline() -> None:
    """A step's final range is its plateau and cannot estimate baseline noise."""
    x = np.linspace(0.0, 10.0, 101)
    initial_noise = np.where(np.arange(x.size) % 2 == 0, 0.1, -0.1)
    plateau_noise = np.where(np.arange(x.size) % 2 == 0, 0.8, -0.8)
    y = np.where(x < 5.0, initial_noise, 4.0 + plateau_noise)
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.STEP,
        denoise=False,
    )

    result = analyze_pulse(
        x,
        y,
        shot_index=1,
        title="Step",
        parameters=parameters,
    )

    initial_baseline = y[(x >= 0.0) & (x <= 1.0)]
    expected_noise_rms = float(np.std(initial_baseline, ddof=0))
    assert result.features is not None
    assert result.features.signal_shape is SignalShape.STEP
    assert result.baseline_noise_rms == pytest.approx(expected_noise_rms)
    assert result.snr_db == pytest.approx(
        20.0 * np.log10(result.features.amplitude / expected_noise_rms)
    )


def test_batch_matches_single_shots_and_is_deterministic() -> None:
    """Batch orchestration does not alter independent shot measurements."""
    acquisitions = (
        _square_pulse("Shot 1", 3.8),
        _square_pulse("Shot 2", 4.2),
    )
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
    )
    expected = tuple(
        analyze_pulse(
            acquisition.x,
            acquisition.y,
            shot_index=index,
            title=acquisition.title,
            parameters=parameters,
        )
        for index, acquisition in enumerate(acquisitions, start=1)
    )

    first = analyze_pulse_campaign(acquisitions, parameters)
    second = analyze_pulse_campaign(acquisitions, parameters)

    assert first.shots == expected
    assert second == first


def test_batch_reports_each_completed_shot_before_continuing() -> None:
    """A host callback may stop a campaign between independent shots."""
    acquisitions = tuple(_square_pulse(f"Shot {index}", 4.0) for index in range(1, 4))
    parameters = PulseAnalysisParameters(
        start_range=(0.0, 1.0),
        end_range=(9.0, 10.0),
        signal_shape=SignalShape.SQUARE,
        denoise=False,
    )
    progress: list[tuple[int, int]] = []

    def stop_after_first(completed: int, total: int) -> None:
        progress.append((completed, total))
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        analyze_pulse_campaign(
            acquisitions,
            parameters,
            progress_callback=stop_after_first,
        )

    assert progress == [(1, 3)]
