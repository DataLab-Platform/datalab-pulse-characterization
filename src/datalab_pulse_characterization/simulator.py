"""Host-neutral oscilloscope simulator, shared by the Desktop and Web adapters.

The simulator behaves like an oscilloscope on a test bench: a source is
connected first, then the time base, channels and ADC are set. The live view
shows one trigger, and each acquisition adds one signal per trigger and
channel, tagged with the metadata the Pulse methods expect.
"""

from __future__ import annotations

import itertools

import guidata.dataset as gds
import numpy as np
from datalab.plugin_instruments import (
    InstrumentAcquisition,
    InstrumentFrame,
    PluginInstrument,
)
from datalab.plugin_tools import PluginTool
from datalab.recipes import RecipeObjectType
from sigima.objects import SignalObj, create_signal

from .core import metadata_key
from .core.oscilloscope import (
    OscilloscopeSettings,
    PulseSource,
    ScopeChannel,
    SourceKind,
    acquire_traces,
)
from .workflow import CHANNEL_METADATA_KEY, SHOT_METADATA_KEY

#: Largest number of samples created by one acquisition (all signals together)
MAX_ACQUISITION_SAMPLES = 5_000_000

OSCILLOSCOPE_SIMULATOR_TOOL = PluginTool(
    id="oscilloscope-simulator",
    title="Oscilloscope simulator...",
    description="Acquire pulses, steps or delayed pulse pairs with live view",
    instrument="oscilloscope_simulator",
    object_type=RecipeObjectType.SIGNAL,
)

SOURCE_LABELS = {
    SourceKind.LASER_PULSE.value: "Laser pulse (photodiode)",
    SourceKind.STEP.value: "Amplifier step response",
    SourceKind.PULSE_PAIR.value: "Pulse pair: reference and delayed detector",
}

_SOURCE = gds.ValueProp(SourceKind.LASER_PULSE.value)


def _source_is(*kinds: SourceKind) -> gds.FuncProp:
    """Return a property active when one of the given sources is connected."""
    values = {kind.value for kind in kinds}
    return gds.FuncProp(_SOURCE, lambda source: source in values)


_LASER = _source_is(SourceKind.LASER_PULSE)
_STEP = _source_is(SourceKind.STEP)
_PAIR = _source_is(SourceKind.PULSE_PAIR)
_PULSES = _source_is(SourceKind.LASER_PULSE, SourceKind.PULSE_PAIR)


class OscilloscopeSimulatorSettings(gds.DataSet):
    """Oscilloscope simulator"""

    _tabs = gds.BeginTabGroup("Settings")

    _source_tab = gds.BeginGroup("Source")
    source = gds.ChoiceItem(
        "Source", tuple(SOURCE_LABELS.items()), default=SourceKind.LASER_PULSE.value
    ).set_prop("display", store=_SOURCE)
    amplitude = gds.FloatItem("Amplitude", default=0.5, min=0.0, nonzero=True, unit="V")
    amplitude_jitter = gds.FloatItem(
        "Amplitude jitter", default=1.0, min=0.0, max=50.0, unit="% RMS"
    )
    timing_jitter = gds.FloatItem(
        "Trigger jitter", default=0.05, min=0.0, unit="ns RMS"
    )
    pulse_width = gds.FloatItem(
        "Pulse width (FWHM)", default=2.0, min=0.0, nonzero=True, unit="ns"
    ).set_prop("display", active=_PULSES)
    _laser = gds.BeginGroup("Laser pulse")
    asymmetric = gds.BoolItem("Asymmetric profile", default=False).set_prop(
        "display", active=_LASER
    )
    timing_drift = gds.FloatItem(
        "Timing drift",
        default=0.0,
        unit="ns",
        help="Linear drift of the pulse time over one acquisition",
    ).set_prop("display", active=_LASER)
    amplitude_drift = gds.FloatItem(
        "Amplitude drift",
        default=0.0,
        min=-90.0,
        max=90.0,
        unit="%",
        help="Linear drift of the pulse amplitude over one acquisition",
    ).set_prop("display", active=_LASER)
    _laser_end = gds.EndGroup("Laser pulse")
    _step = gds.BeginGroup("Amplifier step response")
    natural_frequency = gds.FloatItem(
        "Natural frequency", default=80.0, min=0.0, nonzero=True, unit="MHz"
    ).set_prop("display", active=_STEP)
    damping_ratio = gds.FloatItem(
        "Damping ratio", default=0.35, min=0.01, max=0.99
    ).set_prop("display", active=_STEP)
    _step_end = gds.EndGroup("Amplifier step response")
    _pair = gds.BeginGroup("Pulse pair")
    delay = gds.FloatItem("Detector delay", default=37.5, unit="ns").set_prop(
        "display", active=_PAIR
    )
    detector_gain = gds.FloatItem(
        "Detector gain", default=0.5, min=0.0, nonzero=True
    ).set_prop("display", active=_PAIR)
    detector_width = gds.FloatItem(
        "Detector pulse width (FWHM)", default=6.0, min=0.0, nonzero=True, unit="ns"
    ).set_prop("display", active=_PAIR)
    detector_jitter = gds.FloatItem(
        "Detector jitter", default=0.2, min=0.0, unit="ns RMS"
    ).set_prop("display", active=_PAIR)
    _pair_end = gds.EndGroup("Pulse pair")
    _source_tab_end = gds.EndGroup("Source")

    _scope_tab = gds.BeginGroup("Oscilloscope")
    _horizontal = gds.BeginGroup("Horizontal")
    time_per_div = gds.FloatItem(
        "Time base", default=10.0, min=0.0, nonzero=True, unit="ns/div"
    )
    sample_rate = gds.FloatItem(
        "Sample rate", default=5.0, min=0.0, nonzero=True, max=1_000.0, unit="GS/s"
    )
    trigger_position = gds.FloatItem(
        "Trigger position",
        default=20.0,
        min=0.0,
        max=99.0,
        unit="%",
        help="Part of the record before the trigger",
    )
    _horizontal_end = gds.EndGroup("Horizontal")
    _vertical = gds.BeginGroup("Vertical")
    ch1_volts_per_div = gds.FloatItem(
        "CH1 scale", default=0.1, min=0.0, nonzero=True, unit="V/div"
    )
    ch1_offset = gds.FloatItem("CH1 offset", default=0.3, unit="V")
    ch2_volts_per_div = gds.FloatItem(
        "CH2 scale", default=0.1, min=0.0, nonzero=True, unit="V/div"
    ).set_prop("display", active=_PAIR)
    ch2_offset = gds.FloatItem("CH2 offset", default=0.3, unit="V").set_prop(
        "display", active=_PAIR
    )
    adc_bits = gds.IntItem("ADC resolution", default=8, min=4, max=16, unit="bits")
    noise = gds.FloatItem("Noise", default=0.005, min=0.0, unit="V RMS")
    _vertical_end = gds.EndGroup("Vertical")
    _acquisition = gds.BeginGroup("Acquisition")
    trigger_count = gds.IntItem(
        "Triggers per acquisition", default=200, min=1, max=10_000
    )
    seed = gds.IntItem(
        "Random seed",
        default=20261007,
        min=0,
        help="Makes the acquisitions of a session reproducible",
    )
    _acquisition_end = gds.EndGroup("Acquisition")
    _scope_tab_end = gds.EndGroup("Oscilloscope")

    _tabs_end = gds.EndTabGroup("Settings")


class OscilloscopeSimulator(PluginInstrument):
    """Oscilloscope simulator.

    The seed and the acquisition number fix the noise and jitter of each
    acquisition; live traces use their own random streams.
    """

    live_interval_ms = 200

    def __init__(self) -> None:
        super().__init__(OscilloscopeSimulatorSettings())
        self._acquisition_count = 0
        self._previews = itertools.count(1)

    def source(self) -> PulseSource:
        """Return the source set in the settings."""
        s = self.settings
        return PulseSource(
            kind=SourceKind(s.source),
            amplitude_v=float(s.amplitude),
            amplitude_jitter_percent=float(s.amplitude_jitter),
            timing_jitter_ns=float(s.timing_jitter),
            pulse_width_ns=float(s.pulse_width),
            asymmetric=bool(s.asymmetric),
            timing_drift_ns=float(s.timing_drift),
            amplitude_drift_percent=float(s.amplitude_drift),
            natural_frequency_mhz=float(s.natural_frequency),
            damping_ratio=float(s.damping_ratio),
            delay_ns=float(s.delay),
            detector_gain=float(s.detector_gain),
            detector_width_ns=float(s.detector_width),
            detector_jitter_ns=float(s.detector_jitter),
        )

    def scope(self) -> OscilloscopeSettings:
        """Return the oscilloscope set in the settings."""
        s = self.settings
        return OscilloscopeSettings(
            time_per_div_ns=float(s.time_per_div),
            sample_rate_gsps=float(s.sample_rate),
            trigger_position=float(s.trigger_position) / 100.0,
            ch1=ScopeChannel(float(s.ch1_volts_per_div), float(s.ch1_offset)),
            ch2=ScopeChannel(float(s.ch2_volts_per_div), float(s.ch2_offset)),
            adc_bits=int(s.adc_bits),
            noise_v=float(s.noise),
        )

    def preview(self) -> InstrumentFrame:
        """Return the traces of one trigger, on the oscilloscope screen."""
        source, scope = self.source(), self.scope()
        seed = np.random.SeedSequence(
            (int(self.settings.seed), 2, next(self._previews))
        )
        t, (traces,) = acquire_traces(source, scope, 1, seed)
        channels = (scope.ch1, scope.ch2)[: source.channel_count]
        signals: list[SignalObj] = []
        parts: list[str] = []
        for index, (trace, channel) in enumerate(zip(traces, channels), start=1):
            signals.append(create_signal(f"CH{index}", t, trace, units=("ns", "V")))
            low, high = channel.screen_range
            clipped = np.count_nonzero((trace <= low) | (trace >= high))
            parts.append(
                f"CH{index}: peak {np.max(trace):.3g} V, {clipped} clipped samples"
            )
        lows, highs = zip(*(channel.screen_range for channel in channels))
        return InstrumentFrame(signals, " - ".join(parts), (min(lows), max(highs)))

    def acquire(self) -> InstrumentAcquisition:
        """Acquire one signal per trigger and channel."""
        source, scope = self.source(), self.scope()
        trigger_count = int(self.settings.trigger_count)
        samples = trigger_count * scope.record_length * source.channel_count
        if samples > MAX_ACQUISITION_SAMPLES:
            raise ValueError(
                f"This acquisition would create {samples / 1e6:.1f} million samples "
                f"(limit: {MAX_ACQUISITION_SAMPLES / 1e6:g}): reduce the number of "
                "triggers, the time base or the sample rate"
            )
        seed_value = int(self.settings.seed)
        acquisition_number = self._acquisition_count + 1
        seed = np.random.SeedSequence((seed_value, 1, acquisition_number))
        t, traces = acquire_traces(source, scope, trigger_count, seed)
        signals: list[SignalObj] = []
        for channel_index in range(source.channel_count):
            channel = f"CH{channel_index + 1}"
            for shot, shot_traces in enumerate(traces, start=1):
                signal = create_signal(
                    f"{channel} shot {shot:03d}",
                    t,
                    shot_traces[channel_index],
                    units=("ns", "V"),
                )
                signal.metadata[SHOT_METADATA_KEY] = shot
                signal.metadata[CHANNEL_METADATA_KEY] = channel
                signal.metadata[metadata_key("synthetic")] = True
                signal.metadata[metadata_key("simulation_seed")] = seed_value
                signals.append(signal)
        self._acquisition_count = acquisition_number
        label = SOURCE_LABELS[source.kind.value].split(" (")[0].split(":")[0]
        return InstrumentAcquisition(
            f"Oscilloscope - {label} - acquisition {acquisition_number:03d}", signals
        )


__all__ = [
    "MAX_ACQUISITION_SAMPLES",
    "OSCILLOSCOPE_SIMULATOR_TOOL",
    "OscilloscopeSimulator",
    "OscilloscopeSimulatorSettings",
]
