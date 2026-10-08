# Single-Channel Pulse Campaign

[← Documentation index](README.md)

For a series of repeated acquisitions of one channel, this method measures each shot, flags the invalid shots with a reason, and computes the mean pulse before and after alignment.

Recipe: `org.datalab.pulse-characterization:single-channel-campaign`, version 1.1.0.

## Run

Select the signals, then choose **Plugins > Pulse & Transient Characterization > Run pulse campaign...**, or use the **Single-channel pulse campaign** method of the **Applications** catalog. **Open demo campaign** opens the demonstration.

## Inputs

- One signal per shot, at least two, recorded with the same time base, trigger and gain.
- An optional shot number in `plugin.org.datalab.pulse-characterization.shot`. Without it, the input order gives the shot number. See [Use your own signals](getting-started.md#use-your-own-signals).
- All signals come from **one channel** under **one acquisition configuration**. The method does not check this: mixed inputs give meaningless statistics. For two channels, use the [two-channel method](two-channel-delay.md). Comparing acquisition configurations is not supported.

**Parameters:** signal shape, baseline and end ranges, rise ratios, denoising, minimum amplitude and SNR, saturation detection, multiple-pulse threshold, outlier threshold.

## Results

| Output | Type | Content |
| --- | --- | --- |
| `amplitude_vs_shot` | Signal | Amplitude versus shot, with the per-shot metrics table |
| `raw_mean` | Signal | Mean of the valid shots, as acquired |
| `aligned_mean` | Signal | Mean of the same shots, aligned |

The `shot_metrics` table has one row per shot: status and reason, Sigima features (shape, polarity, offset, amplitude, rise and fall times, FWHM, `x0`, `x50`, `x100`), integral, SNR, and the alignment landmark and shift. Non-finite values, such as the infinite SNR of a noiseless shot, are stored as `null`.

## Method

Sigima measures the pulse shape, polarity, amplitude, offset, rise and fall times, FWHM and `x0`, `x50`, `x100`. The plugin adds:

- **Integral:** trapezoidal integral of `polarity * (signal - baseline_mean)`.
- **SNR:** `20 * log10(amplitude / baseline_noise_rms)`. Steps use the initial baseline; square pulses combine the initial and final baselines.
- **Quality:** `NO_PULSE`, `SATURATED`, `MULTIPLE_PULSES` and `LOW_SNR` are tested in that order. A valid shot may then be an `OUTLIER` from the modified Z-score of its amplitude. Each rejected shot records its reason, threshold and triggering values. A flat acquisition stays in the table as `NO_PULSE`, with `null` Sigima columns.

**Alignment:** valid shots are aligned on their rising 50 % crossing, polarity aware. The reference is the median crossing; for an even count, the lower of the two middle values. Each waveform is shifted by linear interpolation, with constant values beyond its edges. Invalid shots, and valid shots whose X range does not contain the reference, stay unchanged with a skip reason. Both means use the same subset of aligned shots. Signals with a different sampling are resampled onto the first aligned X grid.

Cross-correlation is not used: half-height alignment is deterministic and explainable, and already brings the timing error below one sample (see [Qualification](qualification.md#alignment-benchmark)).

## Demonstration

The **Synthetic pulse campaign** holds 500 shots of 501 samples. Shots alternate between Gaussian and asymmetric pulses, with a slow drift of the baseline and amplitude. The timing jitter grows after shot 300. Eleven shots carry deliberate anomalies:

| Anomaly | Shots | Expected status |
| --- | ---: | --- |
| Missing pulse | 2 | `NO_PULSE` |
| Low SNR | 2 | `LOW_SNR` |
| Saturation | 2 | `SATURATED` |
| Double pulse | 2 | `MULTIPLE_PULSES` |
| Amplitude outlier | 3 | `OUTLIER` |

The validation suite compares every shot with the simulator truth and requires exactly 489 `VALID` shots and the 11 expected flags. A fixed seed gives identical acquisitions.

## Limits

The demonstration model has no trigger electronics, ADC quantization, bandwidth limit, correlated noise or ringing. Synthetic truth validates the software, not the metrology of a real instrument.

## Python

```python
from datalab_pulse_characterization.core import (
    analyze_pulse_campaign,
    simulate_pulse_campaign,
)

simulation = simulate_pulse_campaign()
analysis = analyze_pulse_campaign(
    simulation.acquisitions,
    simulation.analysis_parameters,
)
```
