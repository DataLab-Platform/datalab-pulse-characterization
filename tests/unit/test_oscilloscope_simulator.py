"""Tests of the oscilloscope simulator instrument."""

from __future__ import annotations

import numpy as np
import pytest
from datalab.plugin_instruments import InstrumentAcquisition, InstrumentFrame
from datalab.recipe_binding import (
    RecipeReadinessStatus,
    assess_recipe_inputs,
    create_recipe_parameters,
)
from datalab.recipes import RecipeExecutionContext

from datalab_pulse_characterization.core.oscilloscope import (
    OscilloscopeSettings,
    PulseSource,
    ScopeChannel,
    SourceKind,
    acquire_traces,
)
from datalab_pulse_characterization.simulator import OscilloscopeSimulator
from datalab_pulse_characterization.workflow import (
    CHANNEL_METADATA_KEY,
    PULSE_CAMPAIGN_RECIPE,
    PULSE_STABILITY_RECIPE,
    SHOT_METADATA_KEY,
    STEP_RESPONSE_RECIPE,
    TWO_CHANNEL_DELAY_RECIPE,
    suggest_channel_roles,
)


def _ready(recipe, objects) -> bool:
    """Return True if a recipe can run on objects with its default parameters."""
    parameters = create_recipe_parameters(recipe, {})
    readiness = assess_recipe_inputs(recipe, objects, parameters)
    return readiness.status is RecipeReadinessStatus.READY


def _rows(outcome, result_id: str) -> dict[str, list[object]]:
    """Return one metrics table by metric name."""
    table = next(item.value for item in outcome.results if item.id == result_id)
    return {row[0]: row for row in table.data}


def test_time_base_places_the_trigger_and_the_adc_codes_the_screen() -> None:
    """The record spans ten divisions; the ADC clips and quantizes the screen."""
    scope = OscilloscopeSettings(adc_bits=4, ch1=ScopeChannel(0.1, 0.0))
    t = scope.time_axis()

    assert scope.record_length == 500
    assert t[0] == pytest.approx(-20.0)
    assert t[1] - t[0] == pytest.approx(0.2)
    digitized = scope.digitize(np.linspace(-1.0, 1.0, 1001), scope.ch1)
    assert digitized.min() == pytest.approx(-0.4)
    assert digitized.max() == pytest.approx(0.4)
    assert np.unique(digitized).size == 16
    for kwargs, message in (
        ({"trigger_position": 1.0}, "Trigger position"),
        ({"adc_bits": 20}, "ADC resolution"),
        ({"time_per_div_ns": 1e6}, "record must hold"),
    ):
        with pytest.raises(ValueError, match=message):
            OscilloscopeSettings(**kwargs)


def test_sources_give_pulses_steps_and_delayed_pulse_pairs() -> None:
    """Each source shapes its channels as connected to the oscilloscope."""
    scope = OscilloscopeSettings(noise_v=0.0, adc_bits=16)
    seed = np.random.SeedSequence(1)
    quiet = {"timing_jitter_ns": 0.0, "amplitude_jitter_percent": 0.0}

    t, ((laser,),) = acquire_traces(PulseSource(**quiet), scope, 1, seed)
    assert t[np.argmax(laser)] == pytest.approx(0.0, abs=0.2)
    assert laser.max() == pytest.approx(0.5, abs=0.005)

    step = PulseSource(kind=SourceKind.STEP, **quiet)
    _t, ((response,),) = acquire_traces(step, scope, 1, seed)
    assert response[t < 0].max() == pytest.approx(0.0, abs=0.005)
    assert response.max() == pytest.approx(0.5 * 1.309, rel=0.01)
    assert response[-1] == pytest.approx(0.5, abs=0.01)

    pair = PulseSource(kind=SourceKind.PULSE_PAIR, **quiet, detector_jitter_ns=0.0)
    assert pair.channel_count == 2
    _t, ((reference, measured),) = acquire_traces(pair, scope, 1, seed)
    assert t[np.argmax(reference)] == pytest.approx(0.0, abs=0.2)
    assert t[np.argmax(measured)] == pytest.approx(37.5, abs=0.2)
    assert measured.max() == pytest.approx(0.25, abs=0.005)


def test_live_view_shows_the_oscilloscope_screen() -> None:
    """Live traces use the screen range of the channels and report clipping."""
    scope = OscilloscopeSimulator()
    frame = scope.preview()

    assert isinstance(frame, InstrumentFrame)
    (trace,) = frame.objects
    assert trace.title == "CH1"
    assert trace.xunit == "ns"
    assert frame.value_range == pytest.approx((-0.1, 0.7))
    assert frame.summary.startswith("CH1: peak ")
    assert not np.array_equal(trace.y, scope.preview().objects[0].y)

    scope.settings.source = SourceKind.PULSE_PAIR.value
    scope.settings.ch2_offset = 0.0
    frame = scope.preview()
    assert [signal.title for signal in frame.objects] == ["CH1", "CH2"]
    assert frame.value_range == pytest.approx((-0.4, 0.7))
    assert "CH2: peak " in frame.summary


def test_acquisitions_are_tagged_and_reproducible() -> None:
    """Shots carry their number and channel; the seed fixes each acquisition."""
    scope = OscilloscopeSimulator()
    scope.settings.trigger_count = 5
    acquisition = scope.acquire()

    assert isinstance(acquisition, InstrumentAcquisition)
    assert acquisition.group_title == "Oscilloscope - Laser pulse - acquisition 001"
    assert [signal.title for signal in acquisition.objects] == [
        f"CH1 shot {shot:03d}" for shot in range(1, 6)
    ]
    assert [signal.metadata[SHOT_METADATA_KEY] for signal in acquisition.objects] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert {
        signal.metadata[CHANNEL_METADATA_KEY] for signal in acquisition.objects
    } == {"CH1"}
    second = scope.acquire()
    assert second.group_title.endswith("acquisition 002")
    assert not np.array_equal(acquisition.objects[0].y, second.objects[0].y)

    other = OscilloscopeSimulator()
    other.settings.trigger_count = 5
    assert np.array_equal(other.acquire().objects[0].y, acquisition.objects[0].y)

    scope.settings.trigger_count = 10_000
    scope.settings.sample_rate = 100.0
    with pytest.raises(ValueError, match="million samples"):
        scope.acquire()


def test_laser_and_step_acquisitions_suit_the_pulse_methods() -> None:
    """Laser pulses suit the campaign and stability methods; steps are analyzed."""
    scope = OscilloscopeSimulator()
    scope.settings.trigger_count = 50
    pulses = scope.acquire().objects
    assert _ready(PULSE_CAMPAIGN_RECIPE, pulses)
    assert _ready(PULSE_STABILITY_RECIPE, pulses)

    scope.settings.source = SourceKind.STEP.value
    steps = scope.acquire().objects
    assert _ready(STEP_RESPONSE_RECIPE, steps)
    outcome = STEP_RESPONSE_RECIPE.run(
        {"signals": steps},
        STEP_RESPONSE_RECIPE.parameter_class(),
        RecipeExecutionContext(),
    )
    rows = _rows(outcome, "step_metrics")
    assert rows["Overshoot"][1] == pytest.approx(30.9, abs=1.5)


def test_pulse_pair_acquisitions_measure_the_detector_delay() -> None:
    """The two-channel method measures the 50 % crossing delay of the pair."""
    scope = OscilloscopeSimulator()
    scope.settings.source = SourceKind.PULSE_PAIR.value
    scope.settings.trigger_count = 50
    signals = scope.acquire().objects
    assert len(signals) == 100
    assert _ready(TWO_CHANNEL_DELAY_RECIPE, signals)

    outcome = TWO_CHANNEL_DELAY_RECIPE.run(
        suggest_channel_roles(signals),
        TWO_CHANNEL_DELAY_RECIPE.parameter_class(),
        RecipeExecutionContext(),
    )
    rows = _rows(outcome, "delay_summary")
    # 50 % crossings: rise side of each pulse (detector rise factor 0.65)
    expected = 37.5 - 0.65 * 6.0 / 2 + 2.0 / 2
    assert rows["Mean 50% (CFD) delay"][1] == pytest.approx(expected, abs=0.2)
