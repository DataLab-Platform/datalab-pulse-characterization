# Deterministic Pulse Simulation

The headless simulator produces an ordered single-channel campaign and the
exact settings used for every waveform. It is designed to exercise the normal
Sigima-backed analysis path with reproducible drift, jitter, noise, and quality
failures. It is not a calibrated oscilloscope model.

## Waveform Model

Every acquisition uses the same evenly sampled X axis. Regular shots alternate
between two unit-height profiles:

- a Gaussian profile with one configured standard deviation;
- an asymmetric two-sided Gaussian with independent rise and fall scale
  factors.

The profile is shifted by a seeded timing offset and multiplied by a slowly
drifting amplitude. A linear baseline offset drift applies across the campaign,
and a small slope applies within each waveform. Independent Gaussian white
noise is generated from a child `numpy.random.SeedSequence` for every shot.

The first 300 shots use the configured regular timing-jitter deviation. Later
shots use the larger late-jitter deviation. `PulseShotTruth` retains the actual
offset and requested deviation, so the transition can be inspected without
inferring it from extracted features.

## Demonstration Scenario

`PulseSimulationParameters()` defines the versioned demonstration shape used by
the tests:

| Property | Default |
| --- | ---: |
| Shots | 500 |
| Samples per shot | 501 |
| Profiles | Gaussian, asymmetric |
| Jitter transition | After shot 300 |
| Missing pulses | 2 |
| Low-SNR pulses | 2 |
| Saturated pulses | 2 |
| Double pulses | 2 |
| Amplitude outliers | 3 |
| Total expected invalid shots | 11 |

Anomaly indices are explicit, positive, unique, and disjoint. Parameter
validation rejects ambiguous truth before any waveform is generated.

Saturated shots increase the pulse amplitude before clipping at the configured
acquisition bounds. Missing shots remove the pulse while retaining baseline and
noise. Double shots add a separated second profile. Low-SNR shots use a larger
white-noise deviation in the initial and final baseline windows where noise is
measured; this lowers SNR without manufacturing extra pulse regions. Outliers
retain an otherwise valid waveform with a known amplitude multiplier.

The configurable surface is validated as a classification envelope, not merely
for numerical finiteness. Regular and low-SNR shots must remain on opposite
sides of the SNR threshold with margin, profiles may not overlap the baseline
windows, injected outliers must exceed the robust Z-score threshold, saturated
shots must cross an acquisition bound, and all other shots must retain an
eight-standard-deviation margin from those bounds.

## Ground Truth and Analysis

`simulate_pulse_campaign()` returns:

- immutable `PulseAcquisition` objects accepted directly by
  `analyze_pulse_campaign()`;
- a `PulseSimulationTruth` containing profile, anomaly, expected status,
  baseline, amplitude, center, timing offset, jitter deviation, and noise
  deviation in the measured baseline for every shot;
- `PulseAnalysisParameters` matched to the scenario's baseline ranges,
  acquisition bounds, and explainable quality thresholds.

The simulator never assigns measured features. The production campaign analyzer
still calls Sigima for polarity, amplitude, timing, and width, then applies the
plugin's existing integral, SNR, and quality rules. Tests compare those results
with truth for all 500 shots and require the exact distribution:

```text
489 VALID
  2 NO_PULSE
  2 LOW_SNR
  2 SATURATED
  2 MULTIPLE_PULSES
  3 OUTLIER
```

## Reproducibility and Limits

A fixed seed produces bitwise-identical acquisitions with the supported NumPy
random implementation. Each shot owns read-only X and Y arrays. Cross-version
serialized fixtures should record the NumPy version if bitwise replay matters.

The model omits trigger electronics, ADC quantization, bandwidth limits,
correlated noise, ringing, pile-up beyond one deliberate second pulse, and
instrument-specific transfer functions. Synthetic truth validates software
behavior; it does not establish metrological accuracy or replace the real-data
and scientific-review gates required for a stable release.