"""Scientific validation of the generated Pulse demonstrations against truth."""

from __future__ import annotations

import math

import numpy as np
import pytest
from datalab.plugins.recipe_binding import (
    RecipeReadinessStatus,
    assess_recipe_inputs,
    create_recipe_parameters,
)
from datalab.plugins.recipes import RecipeExecutionContext

from datalab_pulse_characterization import demo
from datalab_pulse_characterization.core import (
    simulate_pulse_campaign,
    simulate_spectrum_events,
    simulate_step_campaign,
    simulate_two_channel_campaign,
)
from datalab_pulse_characterization.core.spectrum_simulation import CS137_LINE_KEV
from datalab_pulse_characterization.workflow import (
    PULSE_CAMPAIGN_RECIPE,
    PULSE_HEIGHT_RECIPE,
    PULSE_STABILITY_RECIPE,
    RECIPES,
    STEP_RESPONSE_RECIPE,
    TWO_CHANNEL_DELAY_RECIPE,
    suggest_channel_roles,
)


def _run(recipe, data, inputs):
    """Run one recipe with the example's parameter values for that recipe."""
    parameters = recipe.parameter_class()
    demo.apply_parameter_values(parameters, data.values_for(recipe.recipe_id))
    return recipe.run(inputs, parameters, RecipeExecutionContext())


def _rows(outcome, result_id: str) -> dict[str, list[object]]:
    """Return one metrics table by metric name."""
    table = next(item.value for item in outcome.results if item.id == result_id)
    return {row[0]: row for row in table.data}


@pytest.mark.parametrize("example", demo.EXAMPLES, ids=lambda example: example.id)
def test_generated_examples_suit_every_declared_recipe(example) -> None:
    """Each generated example is ready for the recipes it is designed for."""
    data = demo.GENERATED_EXAMPLES[example.id]()
    recipes = {recipe.recipe_id: recipe for recipe in RECIPES}
    for recipe_id in example.recipe_ids:
        recipe = recipes[recipe_id]
        parameters = create_recipe_parameters(recipe, data.values_for(recipe_id))
        readiness = assess_recipe_inputs(recipe, data.objects, parameters)
        assert readiness.status is RecipeReadinessStatus.READY, readiness


def test_stability_demo_also_runs_as_a_pulse_campaign() -> None:
    """The warm-up campaign gives per-shot pulse features and aligned means."""
    data = demo.build_stability_campaign()

    outcome = _run(PULSE_CAMPAIGN_RECIPE, data, {"signals": data.objects})

    assert [output.id for output in outcome.objects] == [
        "amplitude_vs_shot",
        "raw_mean",
        "aligned_mean",
    ]
    (shot_table,) = (item.value for item in outcome.results)
    assert len(shot_table.data) == 600


def test_stability_demo_recovers_jitter_regime_and_drift() -> None:
    """The jitter increase, its two levels and the timing drift are found."""
    data = demo.build_stability_campaign()
    truth = simulate_pulse_campaign(
        demo.PulseSimulationParameters(
            shot_count=600,
            sample_count=301,
            amplitude_drift_fraction=0.05,
            profiles=(demo.PulseProfile.GAUSSIAN,),
            white_noise_std=0.02,
            timing_jitter_std=0.015,
            late_timing_jitter_std=0.05,
            jitter_transition_shot=400,
            timing_drift=0.06,
            missing_shots=(150, 480),
            low_snr_shots=(),
            saturated_shots=(),
            multiple_pulse_shots=(),
            outlier_shots=(),
            seed=20261009,
        )
    ).truth

    outcome = _run(PULSE_STABILITY_RECIPE, data, {"signals": data.objects})
    rows = _rows(outcome, "stability_metrics")
    early = np.std([s.timing_offset for s in truth.shots[:400]], ddof=1)
    late = np.std([s.timing_offset for s in truth.shots[400:]], ddof=1)

    assert rows["Excluded shots"][1] == 2
    assert abs(rows["Jitter regime change at shot"][1] - 401) <= 5
    assert rows["Jitter before change"][1] == pytest.approx(early, rel=0.15)
    assert rows["Jitter after change"][1] == pytest.approx(late, rel=0.15)
    assert rows["Timing drift"][1] == pytest.approx(100 * 0.06 / 599, rel=0.2)
    assert rows["Relative amplitude drift"][1] == pytest.approx(
        1e4 * 0.05 / 599, rel=0.2
    )


def test_step_response_demo_recovers_system_truth() -> None:
    """Rise time, overshoot, settling and second-order parameters match."""
    data = demo.build_step_response_campaign()
    truth = simulate_step_campaign().truth

    outcome = _run(STEP_RESPONSE_RECIPE, data, {"signals": data.objects})
    rows = _rows(outcome, "step_metrics")

    assert rows["Averaged shots"][1] == 64
    assert rows["Rise time"][1] == pytest.approx(truth.measured_rise_time, rel=0.03)
    assert rows["Rise time corrected for instrument"][1] == pytest.approx(
        truth.device_rise_time, rel=0.03
    )
    assert rows["Overshoot"][1] == pytest.approx(truth.overshoot_percent, abs=1.0)
    assert rows["Settling time"][1] == pytest.approx(truth.settling_time, rel=0.05)
    assert rows["Damped ringing frequency"][1] == pytest.approx(
        1e3 * truth.damped_frequency, rel=0.03
    )
    assert rows["Damped ringing frequency"][2] == "MHz"
    assert rows["Damping ratio (logarithmic decrement)"][1] == pytest.approx(
        truth.damping_ratio, rel=0.06
    )
    assert rows["Bandwidth (second-order model)"][1] == pytest.approx(
        1e3 * truth.bandwidth, rel=0.05
    )


def test_two_channel_demo_rejects_common_mode_jitter() -> None:
    """Relative jitter matches the detector part only; missing shots are listed."""
    data = demo.build_two_channel_campaign()
    truth = simulate_two_channel_campaign().truth
    inputs = suggest_channel_roles(data.objects)

    outcome = _run(TWO_CHANNEL_DELAY_RECIPE, data, inputs)
    rows = _rows(outcome, "delay_summary")

    assert rows["Missing measured"][1] == 3
    assert rows["Mean 50% (CFD) delay"][1] == pytest.approx(truth.cfd_delay, abs=0.1)
    assert rows["Relative jitter (CFD)"][1] == pytest.approx(
        np.std(truth.independent_offsets, ddof=1), rel=0.15
    )
    assert rows["Common-mode timing jitter"][1] == pytest.approx(
        np.std(truth.common_offsets, ddof=1), rel=0.1
    )
    assert rows["Reference timing jitter"][1] > 4 * rows["Relative jitter (CFD)"][1]
    assert rows["Amplitude correlation"][1] > 0.8
    assert {item.code for item in outcome.diagnostics} >= {
        "missing_channel",
        "invalid_pair",
    }


def test_spectrum_demo_recovers_calibration_and_resolution() -> None:
    """Calibration gain, line positions and 662 keV resolution match truth."""
    data = demo.build_spectrum_campaign()
    parameters = simulate_spectrum_events().parameters

    outcome = _run(PULSE_HEIGHT_RECIPE, data, {"signals": data.objects})
    summary = _rows(outcome, "spectrum_summary")
    peaks = _rows(outcome, "calibration_peaks")

    assert summary["Calibration gain"][1] == pytest.approx(
        1.0 / parameters.charge_per_kev, rel=0.02
    )
    assert summary["Saturated events"][1] == 13
    assert summary["Pile up events"][1] >= 15
    for energy, row in peaks.items():
        assert row[2] == pytest.approx(energy, abs=5.0)
        expected = (
            100 * parameters.resolution_at_662 * math.sqrt(CS137_LINE_KEV / energy)
        )
        assert row[5] == pytest.approx(expected, rel=0.2)
    assert -1.0 < summary["Resolution scaling exponent"][1] < -0.2
